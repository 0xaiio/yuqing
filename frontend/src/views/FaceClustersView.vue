<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { UserFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

import PhotoCard from '../components/PhotoCard.vue'
import PhotoDetailDrawer from '../components/PhotoDetailDrawer.vue'
import {
  findSimilarPhotos,
  getPhoto,
  getPhotoAssetUrl,
  listFaceClusters,
  listPhotosByFaceCluster,
  reanalyzePhoto,
  renameFaceCluster,
} from '../services/api'
import type { FaceCluster, Photo, SearchHit } from '../types'
import { formatCount, formatDateTime, resolveErrorMessage } from '../utils/format'

const clusters = ref<FaceCluster[]>([])
const clusterLoading = ref(false)
const photoLoading = ref(false)
const selectedClusterLabel = ref<string | null>(null)
const clusterHits = ref<SearchHit[]>([])
const resultTitle = ref('该人脸簇的图片')
const renamingLabels = ref<string[]>([])
const renameDrafts = reactive<Record<string, string>>({})
const filterText = ref('')
const filterMode = ref<'all' | 'named' | 'unnamed'>('all')

const detailOpen = ref(false)
const selectedPhoto = ref<Photo | null>(null)
const reanalyzing = ref(false)
const findingSimilar = ref(false)

const selectedCluster = computed(() =>
  clusters.value.find((cluster) => cluster.label === selectedClusterLabel.value) || null,
)
const filteredClusters = computed(() => {
  const keyword = filterText.value.trim().toLowerCase()
  return clusters.value.filter((cluster) => {
    if (filterMode.value === 'named' && !cluster.named) return false
    if (filterMode.value === 'unnamed' && cluster.named) return false
    if (!keyword) return true
    return (
      cluster.label.toLowerCase().includes(keyword) ||
      (cluster.display_name || '').toLowerCase().includes(keyword)
    )
  })
})
const namedCount = computed(() => clusters.value.filter((cluster) => cluster.named).length)

function examplePhotoUrl(cluster: FaceCluster): string {
  return cluster.example_photo_id ? getPhotoAssetUrl(cluster.example_photo_id) : ''
}

async function loadClusters(showBusy = true) {
  if (showBusy) clusterLoading.value = true

  try {
    const response = await listFaceClusters(200)
    clusters.value = response.sort((a, b) => {
      if (b.photo_count !== a.photo_count) return b.photo_count - a.photo_count
      return (b.latest_photo_at || '').localeCompare(a.latest_photo_at || '')
    })
    for (const cluster of clusters.value) {
      renameDrafts[cluster.label] = cluster.display_name || ''
    }

    const selectedStillExists = clusters.value.some((cluster) => cluster.label === selectedClusterLabel.value)
    if (!selectedStillExists) {
      selectedClusterLabel.value = clusters.value[0]?.label || null
    }
    if (selectedClusterLabel.value) {
      await loadClusterPhotos(selectedClusterLabel.value, false)
    } else {
      clusterHits.value = []
    }
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, '读取人脸簇列表失败。'))
  } finally {
    if (showBusy) clusterLoading.value = false
  }
}

async function loadClusterPhotos(clusterLabel: string, showBusy = true) {
  if (showBusy) photoLoading.value = true

  try {
    const response = await listPhotosByFaceCluster(clusterLabel, 48)
    clusterHits.value = response.hits
    resultTitle.value = '该人脸簇的图片'
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, '读取人脸簇图片失败。'))
  } finally {
    if (showBusy) photoLoading.value = false
  }
}

function selectCluster(cluster: FaceCluster) {
  selectedClusterLabel.value = cluster.label
  void loadClusterPhotos(cluster.label)
}

async function handleRenameCluster(cluster: FaceCluster) {
  renamingLabels.value = [...renamingLabels.value, cluster.label]

  try {
    const updated = await renameFaceCluster(cluster.label, renameDrafts[cluster.label] || '')
    clusters.value = clusters.value.map((item) => (item.label === cluster.label ? updated : item))
    renameDrafts[cluster.label] = updated.display_name || ''
    ElMessage.success(updated.display_name ? '人脸簇名称已保存。' : '人脸簇名称已清空。')
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, '保存人脸簇名称失败。'))
  } finally {
    renamingLabels.value = renamingLabels.value.filter((item) => item !== cluster.label)
  }
}

function openDetails(photo: Photo) {
  selectedPhoto.value = photo
  detailOpen.value = true
}

function replacePhoto(updatedPhoto: Photo) {
  clusterHits.value = clusterHits.value.map((hit) =>
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
    await loadClusters(false)
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
    const response = await findSimilarPhotos(selectedPhoto.value.id, 24)
    clusterHits.value = response.hits
    resultTitle.value = '相似图片'
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
    const updated = await renameFaceCluster(label, displayName.trim())
    clusters.value = clusters.value.map((item) => (item.label === label ? updated : item))
    renameDrafts[label] = updated.display_name || ''
    await refreshSelectedPhoto()
    ElMessage.success(displayName.trim() ? '人脸簇名称已保存。' : '人脸簇名称已清空。')
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, '保存人脸簇名称失败。'))
  } finally {
    renamingLabels.value = renamingLabels.value.filter((item) => item !== label)
  }
}

function handleWorkspaceRefresh() {
  void loadClusters(false)
}

onMounted(() => {
  void loadClusters()
  window.addEventListener('workspace:refresh', handleWorkspaceRefresh)
})

onBeforeUnmount(() => {
  window.removeEventListener('workspace:refresh', handleWorkspaceRefresh)
})
</script>

<template>
  <div class="page-stack">
    <section class="page-section fade-in">
      <div class="section-head">
        <h4>人脸簇概览</h4>
        <span class="section-tip">
          共 {{ formatCount(clusters.length) }} 个聚类，其中已命名 {{ formatCount(namedCount) }} 个
        </span>
      </div>

      <div class="face-toolbar">
        <el-input v-model="filterText" placeholder="搜索名称或聚类标签" clearable />
        <el-segmented
          v-model="filterMode"
          :options="[
            { label: '全部', value: 'all' },
            { label: '已命名', value: 'named' },
            { label: '未命名', value: 'unnamed' },
          ]"
        />
      </div>
    </section>

    <section class="page-section fade-in">
      <div class="face-layout">
        <aside class="soft-panel face-sidebar">
          <div class="section-head compact-head">
            <h4>聚类列表</h4>
            <span class="section-tip">{{ filteredClusters.length }} 个结果</span>
          </div>

          <div v-if="filteredClusters.length" class="face-sidebar-list">
            <button
              v-for="cluster in filteredClusters"
              :key="cluster.label"
              type="button"
              class="face-sidebar-item"
              :class="{ active: selectedClusterLabel === cluster.label }"
              @click="selectCluster(cluster)"
            >
              <div class="face-sidebar-thumb">
                <img
                  v-if="cluster.example_photo_id"
                  :src="examplePhotoUrl(cluster)"
                  :alt="cluster.display_name || cluster.label"
                />
                <div v-else class="face-sidebar-empty">
                  <el-icon><UserFilled /></el-icon>
                </div>
              </div>
              <div class="face-sidebar-copy">
                <strong>{{ cluster.display_name || '未命名人脸簇' }}</strong>
                <small>{{ cluster.label }}</small>
                <span>{{ cluster.photo_count }} 张图片</span>
              </div>
            </button>
          </div>

          <el-empty
            v-else
            :description="clusterLoading ? '正在读取人脸簇...' : '当前没有匹配的人脸簇'"
          />
        </aside>

        <div class="face-main">
          <section v-if="selectedCluster" class="glass-panel">
            <div class="face-main-head">
              <div class="face-main-cover">
                <img
                  v-if="selectedCluster.example_photo_id"
                  :src="examplePhotoUrl(selectedCluster)"
                  :alt="selectedCluster.display_name || selectedCluster.label"
                />
                <div v-else class="face-sidebar-empty">
                  <el-icon><UserFilled /></el-icon>
                </div>
              </div>
              <div class="face-main-copy">
                <p class="eyebrow">Face Cluster</p>
                <h3>{{ selectedCluster.display_name || '未命名人脸簇' }}</h3>
                <p>{{ selectedCluster.label }}</p>
                <div class="tag-cloud">
                  <span class="photo-tag">{{ selectedCluster.photo_count }} 张图片</span>
                  <span class="photo-tag">
                    最近更新 {{ formatDateTime(selectedCluster.latest_photo_at || selectedCluster.updated_at) }}
                  </span>
                </div>
              </div>
            </div>

            <div class="face-rename-row">
              <el-input
                v-model="renameDrafts[selectedCluster.label]"
                placeholder="例如：爸爸 / 小明 / 同学 A"
              />
              <el-button
                type="primary"
                :loading="renamingLabels.includes(selectedCluster.label)"
                @click="handleRenameCluster(selectedCluster)"
              >
                保存命名
              </el-button>
            </div>
          </section>

          <section class="page-section inner-section">
            <div class="section-head">
              <h4>{{ resultTitle }}</h4>
              <span class="section-tip">选中某个人脸簇后，会展示该聚类关联的所有图片</span>
            </div>

            <div v-if="clusterHits.length" class="photo-grid">
              <PhotoCard
                v-for="hit in clusterHits"
                :key="hit.photo.id"
                :photo="hit.photo"
                :score="resultTitle === '相似图片' ? hit.score : null"
                @select="openDetails(hit.photo)"
              />
            </div>

            <el-empty
              v-else
              :description="
                photoLoading
                  ? '正在读取该人脸簇的图片...'
                  : selectedCluster
                    ? '该人脸簇下暂时没有图片'
                    : '请先从左侧选择一个人脸簇'
              "
            />
          </section>
        </div>
      </div>
    </section>

    <PhotoDetailDrawer
      v-model="detailOpen"
      :photo="selectedPhoto"
      :face-clusters="clusters"
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
.face-toolbar {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 12px;
}

.face-layout {
  display: grid;
  grid-template-columns: 340px minmax(0, 1fr);
  gap: 18px;
}

.face-sidebar {
  min-height: 560px;
}

.compact-head {
  margin-bottom: 12px;
}

.face-sidebar-list {
  display: grid;
  gap: 12px;
}

.face-sidebar-item {
  display: grid;
  grid-template-columns: 80px minmax(0, 1fr);
  gap: 12px;
  padding: 12px;
  border-radius: 18px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.03);
  color: inherit;
  text-align: left;
  transition:
    transform 180ms ease,
    border-color 180ms ease,
    background 180ms ease;
}

.face-sidebar-item:hover,
.face-sidebar-item.active {
  transform: translateY(-1px);
  border-color: rgba(255, 184, 121, 0.28);
  background: rgba(255, 165, 90, 0.08);
}

.face-sidebar-thumb {
  width: 80px;
  aspect-ratio: 1 / 1;
  overflow: hidden;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.04);
}

.face-sidebar-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.face-sidebar-empty {
  width: 100%;
  height: 100%;
  display: grid;
  place-items: center;
  color: var(--muted);
}

.face-sidebar-empty .el-icon {
  font-size: 24px;
}

.face-sidebar-copy {
  display: grid;
  gap: 6px;
}

.face-sidebar-copy strong {
  font-size: 15px;
}

.face-sidebar-copy small,
.face-sidebar-copy span {
  color: var(--muted);
  word-break: break-all;
}

.face-main {
  display: grid;
  gap: 18px;
}

.face-main-head {
  display: grid;
  grid-template-columns: 140px minmax(0, 1fr);
  gap: 18px;
  align-items: center;
}

.face-main-cover {
  overflow: hidden;
  border-radius: 22px;
  aspect-ratio: 1 / 1;
  background: rgba(255, 255, 255, 0.04);
}

.face-main-cover img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.face-main-copy h3 {
  margin: 8px 0;
  font-size: 28px;
}

.face-main-copy p {
  margin: 0 0 12px;
  color: var(--muted);
  word-break: break-all;
}

.face-rename-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 12px;
  margin-top: 18px;
}

.inner-section {
  padding: 0;
  background: transparent;
  border: none;
  box-shadow: none;
}

@media (max-width: 1100px) {
  .face-layout {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .face-toolbar,
  .face-main-head,
  .face-rename-row {
    grid-template-columns: 1fr;
  }
}
</style>
