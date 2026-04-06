<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Delete, Refresh, Warning } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import {
  deletePhoto,
  deleteVideo,
  getPhotoAssetUrl,
  getVideoThumbnailUrl,
  listCleanupCandidates,
} from '../services/api'
import type {
  CleanupCategory,
  CleanupPhotoHit,
  CleanupResponse,
  CleanupVideoHit,
} from '../types'
import { formatDateTime, resolveErrorMessage, sourceKindLabel } from '../utils/format'

const loading = ref(false)
const deleting = ref(false)
const candidateLimit = ref(80)
const activeCategory = ref<CleanupCategory>('thumbnail_images')
const cleanupResponse = ref<CleanupResponse>({
  category: 'thumbnail_images',
  total: 0,
  photo_hits: [],
  video_hits: [],
})
const selectedPhotoIds = ref<number[]>([])
const selectedVideoIds = ref<number[]>([])

const categoryOptions: Array<{
  value: CleanupCategory
  label: string
  summary: string
}> = [
  {
    value: 'thumbnail_images',
    label: 'Thumb 缩略图',
    summary: '清理聊天目录和素材目录里明显偏小、带 thumb 特征的缩略图图片。',
  },
  {
    value: 'low_resolution_images',
    label: '低分辨率图片',
    summary: '找出分辨率明显偏低、可优先清理或二次筛选的图片。',
  },
  {
    value: 'junk_transfer_images',
    label: '微信/QQ 无价值图',
    summary: '综合来源、文件名、分辨率、OCR 和人物信号，筛出疑似无保留价值的传输图。',
  },
  {
    value: 'duplicate_images',
    label: '重复 / 高度重复图片',
    summary: '结合文件名、语义向量和感知哈希，找出建议删除的低质量重复图片。',
  },
  {
    value: 'low_resolution_videos',
    label: '低分辨率视频',
    summary: '找出清晰度明显偏低的视频，便于批量清理。',
  },
  {
    value: 'duplicate_videos',
    label: '重复 / 高度重复视频',
    summary: '结合规范化文件名、视频向量和时长，找出建议删除的低质量重复视频。',
  },
]

const currentCategory = computed(
  () => categoryOptions.find((item) => item.value === activeCategory.value) || categoryOptions[0],
)

function emitWorkspaceRefresh() {
  window.dispatchEvent(new Event('workspace:refresh'))
}

function clearSelections() {
  selectedPhotoIds.value = []
  selectedVideoIds.value = []
}

function updatePhotoSelection(rows: CleanupPhotoHit[]) {
  selectedPhotoIds.value = rows.map((row) => row.photo.id)
}

function updateVideoSelection(rows: CleanupVideoHit[]) {
  selectedVideoIds.value = rows.map((row) => row.video.id)
}

async function loadCandidates(showBusy = true) {
  if (showBusy) loading.value = true
  clearSelections()
  try {
    cleanupResponse.value = await listCleanupCandidates(activeCategory.value, candidateLimit.value)
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, '读取整理候选失败'))
  } finally {
    if (showBusy) loading.value = false
  }
}

function handleSelectCategory(category: CleanupCategory) {
  activeCategory.value = category
  void loadCandidates()
}

async function removePhotos(photoIds: number[], successMessage: string) {
  for (const photoId of photoIds) {
    await deletePhoto(photoId)
  }
  emitWorkspaceRefresh()
  await loadCandidates(false)
  ElMessage.success(successMessage)
}

async function removeVideos(videoIds: number[], successMessage: string) {
  for (const videoId of videoIds) {
    await deleteVideo(videoId)
  }
  emitWorkspaceRefresh()
  await loadCandidates(false)
  ElMessage.success(successMessage)
}

async function confirmDelete(message: string, title: string) {
  await ElMessageBox.confirm(message, title, {
    type: 'warning',
    confirmButtonText: '删除',
    cancelButtonText: '取消',
  })
}

async function handleDeletePhoto(hit: CleanupPhotoHit) {
  try {
    await confirmDelete(
      '删除后会同时清理应用归档副本，并默认尝试同步删除本地同步源中的原文件。',
      '删除图片',
    )
  } catch (error) {
    if (error === 'cancel' || error === 'close') return
    ElMessage.error(resolveErrorMessage(error, '删除图片前确认失败'))
    return
  }

  deleting.value = true
  try {
    await removePhotos([hit.photo.id], '图片已删除')
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, '删除图片失败'))
  } finally {
    deleting.value = false
  }
}

async function handleDeleteVideo(hit: CleanupVideoHit) {
  try {
    await confirmDelete(
      '删除后会同时清理应用归档副本、缩略图与抽帧缓存，并默认尝试同步删除本地同步源中的原文件。',
      '删除视频',
    )
  } catch (error) {
    if (error === 'cancel' || error === 'close') return
    ElMessage.error(resolveErrorMessage(error, '删除视频前确认失败'))
    return
  }

  deleting.value = true
  try {
    await removeVideos([hit.video.id], '视频已删除')
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, '删除视频失败'))
  } finally {
    deleting.value = false
  }
}

async function handleBatchDeletePhotos() {
  if (!selectedPhotoIds.value.length) return

  try {
    await confirmDelete(
      `将批量删除 ${selectedPhotoIds.value.length} 张图片，并默认尝试同步删除本地同步源中的原文件。是否继续？`,
      '批量删除图片',
    )
  } catch (error) {
    if (error === 'cancel' || error === 'close') return
    ElMessage.error(resolveErrorMessage(error, '批量删除图片前确认失败'))
    return
  }

  deleting.value = true
  try {
    await removePhotos(
      [...selectedPhotoIds.value],
      `已批量删除 ${selectedPhotoIds.value.length} 张图片`,
    )
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, '批量删除图片失败'))
  } finally {
    deleting.value = false
  }
}

async function handleBatchDeleteVideos() {
  if (!selectedVideoIds.value.length) return

  try {
    await confirmDelete(
      `将批量删除 ${selectedVideoIds.value.length} 个视频，并默认尝试同步删除本地同步源中的原文件。是否继续？`,
      '批量删除视频',
    )
  } catch (error) {
    if (error === 'cancel' || error === 'close') return
    ElMessage.error(resolveErrorMessage(error, '批量删除视频前确认失败'))
    return
  }

  deleting.value = true
  try {
    await removeVideos(
      [...selectedVideoIds.value],
      `已批量删除 ${selectedVideoIds.value.length} 个视频`,
    )
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, '批量删除视频失败'))
  } finally {
    deleting.value = false
  }
}

function photoPreviewUrl(hit: CleanupPhotoHit): string {
  return getPhotoAssetUrl(hit.photo.id)
}

function videoPreviewUrl(hit: CleanupVideoHit): string | null {
  return hit.video.thumbnail_asset_url ? getVideoThumbnailUrl(hit.video.id) : null
}

onMounted(() => {
  void loadCandidates()
})
</script>

<template>
  <div class="page-stack">
    <section class="page-section fade-in">
      <div class="section-head">
        <h4>整理工作台</h4>
        <span class="section-tip">
          快速清理 thumb、低清晰度图片 / 视频，以及微信 QQ 中疑似无保留价值的传输图。
        </span>
      </div>

      <div class="cleanup-category-grid">
        <button
          v-for="item in categoryOptions"
          :key="item.value"
          type="button"
          class="cleanup-category-card"
          :class="{ active: activeCategory === item.value }"
          @click="handleSelectCategory(item.value)"
        >
          <strong>{{ item.label }}</strong>
          <span>{{ item.summary }}</span>
        </button>
      </div>
    </section>

    <section class="page-section fade-in">
      <div class="cleanup-toolbar">
        <div>
          <p class="eyebrow">Cleanup Category</p>
          <h3>{{ currentCategory.label }}</h3>
          <p class="cleanup-summary">{{ currentCategory.summary }}</p>
        </div>

        <div class="cleanup-toolbar__actions">
          <el-input-number v-model="candidateLimit" :min="20" :max="200" :step="20" />
          <el-button class="ghost-button" :icon="Refresh" :loading="loading" @click="loadCandidates()">
            刷新候选
          </el-button>
        </div>
      </div>

      <div class="cleanup-callout">
        <el-icon><Warning /></el-icon>
        <span>
          当前候选会综合来源目录、规范化文件名、分辨率、OCR、语义向量、感知哈希与视频时长来推荐可清理项。删除操作会默认同步清理同步源里的原文件。
        </span>
      </div>
    </section>

    <section v-if="cleanupResponse.photo_hits.length" class="page-section fade-in">
      <div class="section-head">
        <h4>图片候选</h4>
        <span class="section-tip">共 {{ cleanupResponse.photo_hits.length }} 张候选图片</span>
      </div>

      <div class="cleanup-action-row">
        <span>已选 {{ selectedPhotoIds.length }} 张</span>
        <el-button
          type="danger"
          plain
          :icon="Delete"
          :disabled="!selectedPhotoIds.length"
          :loading="deleting"
          @click="handleBatchDeletePhotos"
        >
          批量删除图片
        </el-button>
      </div>

      <el-table
        :data="cleanupResponse.photo_hits"
        row-key="photo.id"
        @selection-change="updatePhotoSelection"
      >
        <el-table-column type="selection" width="52" />
        <el-table-column label="预览" width="108">
          <template #default="{ row }">
            <img class="cleanup-thumb" :src="photoPreviewUrl(row)" :alt="row.photo.caption || row.photo.original_path" />
          </template>
        </el-table-column>
        <el-table-column label="原因 / 信息" min-width="360">
          <template #default="{ row }">
            <div class="cleanup-cell">
              <strong>{{ row.photo.caption || row.photo.source_name || '图片候选' }}</strong>
              <span>{{ row.reason }}</span>
              <small>{{ row.photo.original_path }}</small>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="分辨率" width="140">
          <template #default="{ row }">{{ row.width || 0 }} x {{ row.height || 0 }}</template>
        </el-table-column>
        <el-table-column label="来源" width="150">
          <template #default="{ row }">{{ sourceKindLabel(row.photo.source_kind) }}</template>
        </el-table-column>
        <el-table-column label="时间" width="180">
          <template #default="{ row }">{{ formatDateTime(row.photo.taken_at || row.photo.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button
              type="danger"
              text
              :loading="deleting"
              @click="handleDeletePhoto(row)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <section v-if="cleanupResponse.video_hits.length" class="page-section fade-in">
      <div class="section-head">
        <h4>视频候选</h4>
        <span class="section-tip">共 {{ cleanupResponse.video_hits.length }} 个候选视频</span>
      </div>

      <div class="cleanup-action-row">
        <span>已选 {{ selectedVideoIds.length }} 个</span>
        <el-button
          type="danger"
          plain
          :icon="Delete"
          :disabled="!selectedVideoIds.length"
          :loading="deleting"
          @click="handleBatchDeleteVideos"
        >
          批量删除视频
        </el-button>
      </div>

      <el-table
        :data="cleanupResponse.video_hits"
        row-key="video.id"
        @selection-change="updateVideoSelection"
      >
        <el-table-column type="selection" width="52" />
        <el-table-column label="预览" width="108">
          <template #default="{ row }">
            <img
              v-if="videoPreviewUrl(row)"
              class="cleanup-thumb"
              :src="videoPreviewUrl(row) || ''"
              :alt="row.video.caption || row.video.original_path"
            />
            <div v-else class="cleanup-thumb cleanup-thumb--empty">No Thumb</div>
          </template>
        </el-table-column>
        <el-table-column label="原因 / 信息" min-width="360">
          <template #default="{ row }">
            <div class="cleanup-cell">
              <strong>{{ row.video.caption || row.video.source_name || '视频候选' }}</strong>
              <span>{{ row.reason }}</span>
              <small>{{ row.video.original_path }}</small>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="分辨率" width="140">
          <template #default="{ row }">{{ row.width || 0 }} x {{ row.height || 0 }}</template>
        </el-table-column>
        <el-table-column label="来源" width="150">
          <template #default="{ row }">{{ sourceKindLabel(row.video.source_kind) }}</template>
        </el-table-column>
        <el-table-column label="时间" width="180">
          <template #default="{ row }">{{ formatDateTime(row.video.taken_at || row.video.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button
              type="danger"
              text
              :loading="deleting"
              @click="handleDeleteVideo(row)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <section
      v-if="!loading && !cleanupResponse.photo_hits.length && !cleanupResponse.video_hits.length"
      class="page-section fade-in"
    >
      <el-empty description="当前分类下没有可清理候选" />
    </section>
  </div>
</template>

<style scoped>
.cleanup-category-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 14px;
}

.cleanup-category-card {
  display: grid;
  gap: 10px;
  padding: 18px;
  border-radius: 22px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.03);
  color: inherit;
  text-align: left;
  transition:
    transform 0.18s ease,
    border-color 0.18s ease,
    background 0.18s ease;
}

.cleanup-category-card:hover,
.cleanup-category-card.active {
  transform: translateY(-2px);
  border-color: rgba(255, 120, 84, 0.34);
  background: rgba(255, 120, 84, 0.08);
}

.cleanup-category-card span,
.cleanup-summary {
  color: var(--muted);
  line-height: 1.6;
}

.cleanup-toolbar {
  display: flex;
  justify-content: space-between;
  gap: 18px;
  align-items: flex-start;
}

.cleanup-toolbar h3 {
  margin: 8px 0;
}

.cleanup-toolbar__actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  align-items: center;
}

.cleanup-callout {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  padding: 14px 16px;
  border-radius: 18px;
  background: rgba(255, 184, 77, 0.1);
  color: var(--muted);
}

.cleanup-action-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  margin-bottom: 12px;
}

.cleanup-thumb {
  width: 72px;
  height: 72px;
  border-radius: 16px;
  object-fit: cover;
  display: block;
  background: rgba(255, 255, 255, 0.04);
}

.cleanup-thumb--empty {
  display: grid;
  place-items: center;
  color: var(--muted);
  font-size: 12px;
}

.cleanup-cell {
  display: grid;
  gap: 6px;
}

.cleanup-cell span,
.cleanup-cell small {
  color: var(--muted);
  line-height: 1.5;
  word-break: break-all;
}

@media (max-width: 900px) {
  .cleanup-toolbar,
  .cleanup-action-row {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
