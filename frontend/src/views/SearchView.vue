<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { Picture, Search, UploadFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

import PhotoCard from '../components/PhotoCard.vue'
import PhotoDetailDrawer from '../components/PhotoDetailDrawer.vue'
import {
  findSimilarPhotos,
  getPhoto,
  listFaceClusters,
  listPhotos,
  reanalyzePhoto,
  renameFaceCluster,
  searchByImage,
  searchPhotos,
} from '../services/api'
import type { FaceCluster, Photo, SearchHit, SearchMode, SourceKind } from '../types'
import {
  parseTagInput,
  resolveErrorMessage,
  searchModeOptions,
  sourceKindOptions,
} from '../utils/format'

const loading = ref(false)
const mode = ref<'recent' | 'search' | 'similar' | 'image'>('recent')
const hits = ref<SearchHit[]>([])
const detailOpen = ref(false)
const selectedPhoto = ref<Photo | null>(null)
const reanalyzing = ref(false)
const findingSimilar = ref(false)
const faceClusters = ref<FaceCluster[]>([])
const renamingLabels = ref<string[]>([])
const imageSearching = ref(false)
const queryImagePreview = ref<string | null>(null)
const queryImageName = ref('')
const fileInputRef = ref<HTMLInputElement | null>(null)

const form = reactive<{
  text: string
  peopleText: string
  sceneText: string
  objectText: string
  sourceKinds: SourceKind[]
  mode: SearchMode
  limit: number
}>({
  text: '',
  peopleText: '',
  sceneText: '',
  objectText: '',
  sourceKinds: [],
  mode: 'hybrid',
  limit: 24,
})

const quickQueries = [
  '去年夏天和家人在海边拍的日落',
  '带有发票文字的截图',
  '微信里导入的聚会合影',
  '包含乐高和孩子的照片',
]

const resultTitle = computed(() => {
  if (mode.value === 'similar') return '相似图片'
  if (mode.value === 'image') return '参考图检索结果'
  if (mode.value === 'search') return '搜索结果'
  return '最近导入'
})

async function loadRecent(showBusy = true) {
  if (showBusy) loading.value = true

  try {
    const photos = await listPhotos(form.limit)
    hits.value = photos.map((photo) => ({
      score: 1,
      photo,
    }))
    mode.value = 'recent'
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, '加载最近图片失败。'))
  } finally {
    if (showBusy) loading.value = false
  }
}

async function loadFaceClusterList() {
  try {
    faceClusters.value = await listFaceClusters(80)
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, '读取人脸簇列表失败。'))
  }
}

async function runSearch(showBusy = true) {
  if (showBusy) loading.value = true

  try {
    const response = await searchPhotos({
      text: form.text.trim(),
      people: parseTagInput(form.peopleText),
      scene_tags: parseTagInput(form.sceneText),
      object_tags: parseTagInput(form.objectText),
      source_kinds: form.sourceKinds,
      face_cluster_labels: [],
      mode: form.mode,
      limit: form.limit,
    })
    hits.value = response.hits
    mode.value = 'search'
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, '执行搜索失败。'))
  } finally {
    if (showBusy) loading.value = false
  }
}

function hasSearchFilters(): boolean {
  return Boolean(
    form.text.trim() ||
      form.peopleText.trim() ||
      form.sceneText.trim() ||
      form.objectText.trim() ||
      form.sourceKinds.length,
  )
}

function applyQuickQuery(query: string) {
  form.text = query
  void runSearch()
}

function resetFilters() {
  form.text = ''
  form.peopleText = ''
  form.sceneText = ''
  form.objectText = ''
  form.sourceKinds = []
  form.mode = 'hybrid'
  clearQueryImage()
  void loadRecent()
}

function openDetails(photo: Photo) {
  selectedPhoto.value = photo
  detailOpen.value = true
}

function replacePhoto(updatedPhoto: Photo) {
  hits.value = hits.value.map((hit) =>
    hit.photo.id === updatedPhoto.id
      ? {
          ...hit,
          photo: updatedPhoto,
        }
      : hit,
  )

  if (selectedPhoto.value?.id === updatedPhoto.id) {
    selectedPhoto.value = updatedPhoto
  }
}

async function refreshSelectedPhoto() {
  if (!selectedPhoto.value) return
  const latest = await getPhoto(selectedPhoto.value.id)
  replacePhoto(latest)
}

async function handleReanalyze() {
  if (!selectedPhoto.value) return

  reanalyzing.value = true
  try {
    const updatedPhoto = await reanalyzePhoto(selectedPhoto.value.id)
    replacePhoto(updatedPhoto)
    await loadFaceClusterList()
    ElMessage.success('图片已重新分析。')
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, '重新分析失败。'))
  } finally {
    reanalyzing.value = false
  }
}

async function handleFindSimilar() {
  if (!selectedPhoto.value) return

  findingSimilar.value = true
  try {
    const response = await findSimilarPhotos(selectedPhoto.value.id, form.limit)
    hits.value = response.hits
    mode.value = 'similar'
    ElMessage.success('已切换到相似图片结果。')
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, '查找相似图片失败。'))
  } finally {
    findingSimilar.value = false
  }
}

async function handleRenameFaceCluster(label: string, displayName: string) {
  renamingLabels.value = [...renamingLabels.value, label]

  try {
    await renameFaceCluster(label, displayName.trim())
    await Promise.all([loadFaceClusterList(), refreshSelectedPhoto()])
    ElMessage.success(displayName.trim() ? '人脸簇名称已保存。' : '人脸簇名称已清空。')
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, '保存人脸簇名称失败。'))
  } finally {
    renamingLabels.value = renamingLabels.value.filter((item) => item !== label)
  }
}

function openImagePicker() {
  fileInputRef.value?.click()
}

async function handleImageFileChange(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return

  if (queryImagePreview.value) {
    URL.revokeObjectURL(queryImagePreview.value)
  }
  queryImagePreview.value = URL.createObjectURL(file)
  queryImageName.value = file.name
  imageSearching.value = true

  try {
    const response = await searchByImage(file, form.limit)
    hits.value = response.hits
    mode.value = 'image'
    ElMessage.success('参考图检索已完成。')
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, '以图搜图失败。'))
  } finally {
    imageSearching.value = false
    target.value = ''
  }
}

function clearQueryImage() {
  if (queryImagePreview.value) {
    URL.revokeObjectURL(queryImagePreview.value)
  }
  queryImagePreview.value = null
  queryImageName.value = ''
}

function handleWorkspaceRefresh() {
  void loadFaceClusterList()
  if (mode.value === 'search' && hasSearchFilters()) {
    void runSearch(false)
    return
  }
  if (mode.value === 'similar' && selectedPhoto.value) {
    void handleFindSimilar()
    return
  }
  if (mode.value === 'image') {
    return
  }
  void loadRecent(false)
}

onMounted(() => {
  void loadRecent()
  void loadFaceClusterList()
  window.addEventListener('workspace:refresh', handleWorkspaceRefresh)
})

onBeforeUnmount(() => {
  window.removeEventListener('workspace:refresh', handleWorkspaceRefresh)
  clearQueryImage()
})
</script>

<template>
  <div class="page-stack">
    <section class="page-section search-board fade-in">
      <div class="page-heading">
        <p class="eyebrow">Natural Retrieval</p>
        <h3>用一句话或一张参考图搜索跨来源图片</h3>
        <p>
          支持关键词检索、向量相似度召回、以图搜图，也支持叠加人物、场景、物体和来源维度的结构化过滤。
        </p>
      </div>

      <div class="search-input-row">
        <el-input
          v-model="form.text"
          type="textarea"
          :rows="2"
          placeholder="例如：去年夏天和小明在海边拍的日落"
        />
        <div class="search-actions">
          <el-button type="primary" :icon="Search" :loading="loading" @click="runSearch()">
            开始检索
          </el-button>
          <el-button @click="resetFilters">恢复最近导入</el-button>
        </div>
      </div>

      <div class="quick-query-row">
        <button
          v-for="query in quickQueries"
          :key="query"
          type="button"
          class="quick-chip"
          @click="applyQuickQuery(query)"
        >
          {{ query }}
        </button>
      </div>

      <div class="filter-grid">
        <div class="soft-panel mini-panel">
          <label>检索模式</label>
          <el-segmented v-model="form.mode" :options="searchModeOptions" />
        </div>
        <div class="soft-panel mini-panel">
          <label>人物标签</label>
          <el-input v-model="form.peopleText" placeholder="多个标签用逗号分隔，例如：爸爸，小明" />
        </div>
        <div class="soft-panel mini-panel">
          <label>场景标签</label>
          <el-input v-model="form.sceneText" placeholder="例如：海边，办公室，旅行" />
        </div>
        <div class="soft-panel mini-panel">
          <label>物体标签</label>
          <el-input v-model="form.objectText" placeholder="例如：猫，车，乐高" />
        </div>
        <div class="soft-panel mini-panel">
          <label>来源过滤</label>
          <el-select v-model="form.sourceKinds" multiple collapse-tags placeholder="选择来源类型">
            <el-option
              v-for="option in sourceKindOptions"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
        </div>
      </div>

      <div class="image-query-panel soft-panel">
        <div class="section-head compact-head">
          <h4>以图搜图</h4>
          <span class="section-tip">上传参考图后，会用本地向量与 OCR 特征召回相似图片</span>
        </div>

        <div class="image-query-row">
          <div v-if="queryImagePreview" class="image-query-preview">
            <img :src="queryImagePreview" :alt="queryImageName || 'query-image'" />
          </div>
          <div class="image-query-actions">
            <input
              ref="fileInputRef"
              class="hidden-input"
              type="file"
              accept="image/*"
              @change="handleImageFileChange"
            />
            <el-button
              type="primary"
              plain
              :icon="UploadFilled"
              :loading="imageSearching"
              @click="openImagePicker"
            >
              上传参考图
            </el-button>
            <span v-if="queryImageName" class="image-query-name">{{ queryImageName }}</span>
            <el-button v-if="queryImagePreview" text :icon="Picture" @click="clearQueryImage">
              清除参考图
            </el-button>
          </div>
        </div>
      </div>
    </section>

    <section class="page-section fade-in">
      <div class="section-head">
        <h4>{{ resultTitle }}</h4>
        <span class="section-tip">点击图片可查看详情、重分析、命名人脸簇或查找相似图</span>
      </div>

      <div v-if="hits.length" class="photo-grid">
        <PhotoCard
          v-for="hit in hits"
          :key="`${mode}-${hit.photo.id}`"
          :photo="hit.photo"
          :score="mode === 'recent' ? null : hit.score"
          @select="openDetails(hit.photo)"
        />
      </div>

      <el-empty v-else description="没有找到符合条件的图片" />
    </section>

    <PhotoDetailDrawer
      v-model="detailOpen"
      :photo="selectedPhoto"
      :face-clusters="faceClusters"
      :reanalyzing="reanalyzing"
      :renaming-labels="renamingLabels"
      :finding-similar="findingSimilar"
      @reanalyze="handleReanalyze"
      @find-similar="handleFindSimilar"
      @rename-face-cluster="handleRenameFaceCluster"
    />
  </div>
</template>

<style scoped>
.image-query-panel {
  margin-top: 18px;
}

.compact-head {
  margin-bottom: 12px;
}

.image-query-row {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 14px;
  align-items: center;
}

.image-query-preview {
  width: 120px;
  aspect-ratio: 1 / 1;
  overflow: hidden;
  border-radius: 18px;
  border: 1px solid rgba(255, 255, 255, 0.12);
}

.image-query-preview img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.image-query-actions {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}

.image-query-name {
  color: var(--muted);
  word-break: break-all;
}

.hidden-input {
  display: none;
}

@media (max-width: 720px) {
  .image-query-row {
    grid-template-columns: 1fr;
  }
}
</style>
