<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { UserFilled } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import MediaBatchToolbar from '../components/MediaBatchToolbar.vue'
import PhotoCard from '../components/PhotoCard.vue'
import PhotoDetailDrawer from '../components/PhotoDetailDrawer.vue'
import VideoCard from '../components/VideoCard.vue'
import VideoDetailDrawer from '../components/VideoDetailDrawer.vue'
import {
  deletePhoto,
  deleteVideo,
  findSimilarPhotos,
  findSimilarVideos,
  getPhoto,
  getPhotoAssetUrl,
  getVideo,
  listFaceClusters,
  listPhotosByFaceCluster,
  listVideosByFaceCluster,
  reanalyzePhoto,
  renameFaceCluster,
} from '../services/api'
import type { FaceCluster, Photo, SearchHit, Video, VideoSearchHit } from '../types'
import { formatCount, formatDateTime, resolveErrorMessage } from '../utils/format'

const clusters = ref<FaceCluster[]>([])
const clusterLoading = ref(false)
const mediaLoading = ref(false)
const selectedClusterLabel = ref<string | null>(null)
const clusterHits = ref<SearchHit[]>([])
const clusterVideoHits = ref<VideoSearchHit[]>([])
const photoTitle = ref('该人脸簇的图片')
const videoTitle = ref('该人脸簇的视频')
const renamingLabels = ref<string[]>([])
const renameDrafts = reactive<Record<string, string>>({})
const filterText = ref('')
const filterMode = ref<'all' | 'named' | 'unnamed'>('all')

const detailOpen = ref(false)
const selectedPhoto = ref<Photo | null>(null)
const reanalyzing = ref(false)
const findingSimilar = ref(false)
const deletingPhoto = ref(false)
const batchDeletingPhotos = ref(false)
const photoSelectionMode = ref(false)
const selectedPhotoIds = ref<number[]>([])

const videoDetailOpen = ref(false)
const selectedVideo = ref<Video | null>(null)
const findingSimilarVideo = ref(false)
const deletingVideo = ref(false)
const batchDeletingVideos = ref(false)
const videoSelectionMode = ref(false)
const selectedVideoIds = ref<number[]>([])

const selectedCluster = computed(
  () => clusters.value.find((cluster) => cluster.label === selectedClusterLabel.value) || null,
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
const currentPhotoIds = computed(() => clusterHits.value.map((hit) => hit.photo.id))
const currentVideoIds = computed(() => clusterVideoHits.value.map((hit) => hit.video.id))

function emitWorkspaceRefresh() {
  window.dispatchEvent(new Event('workspace:refresh'))
}

function isMessageBoxCancel(error: unknown): boolean {
  return error === 'cancel' || error === 'close'
}

function examplePhotoUrl(cluster: FaceCluster): string {
  return cluster.example_photo_id ? getPhotoAssetUrl(cluster.example_photo_id) : ''
}

function clearPhotoSelection() {
  selectedPhotoIds.value = []
}

function startPhotoSelectionMode() {
  photoSelectionMode.value = true
}

function exitPhotoSelectionMode() {
  photoSelectionMode.value = false
  clearPhotoSelection()
}

function togglePhotoSelection(photoId: number) {
  if (selectedPhotoIds.value.includes(photoId)) {
    selectedPhotoIds.value = selectedPhotoIds.value.filter((id) => id !== photoId)
    return
  }
  selectedPhotoIds.value = [...selectedPhotoIds.value, photoId]
}

function selectAllCurrentPhotos() {
  selectedPhotoIds.value = [...currentPhotoIds.value]
}

function clearVideoSelection() {
  selectedVideoIds.value = []
}

function startVideoSelectionMode() {
  videoSelectionMode.value = true
}

function exitVideoSelectionMode() {
  videoSelectionMode.value = false
  clearVideoSelection()
}

function toggleVideoSelection(videoId: number) {
  if (selectedVideoIds.value.includes(videoId)) {
    selectedVideoIds.value = selectedVideoIds.value.filter((id) => id !== videoId)
    return
  }
  selectedVideoIds.value = [...selectedVideoIds.value, videoId]
}

function selectAllCurrentVideos() {
  selectedVideoIds.value = [...currentVideoIds.value]
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
      await loadClusterMedia(selectedClusterLabel.value, false)
    } else {
      clusterHits.value = []
      clusterVideoHits.value = []
    }
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, '读取人脸簇列表失败'))
  } finally {
    if (showBusy) clusterLoading.value = false
  }
}

async function loadClusterMedia(clusterLabel: string, showBusy = true) {
  if (showBusy) mediaLoading.value = true

  try {
    const [photoResponse, videoResponse] = await Promise.all([
      listPhotosByFaceCluster(clusterLabel, 48),
      listVideosByFaceCluster(clusterLabel, 24),
    ])
    clusterHits.value = photoResponse.hits
    clusterVideoHits.value = videoResponse.hits
    photoTitle.value = '该人脸簇的图片'
    videoTitle.value = '该人脸簇的视频'
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, '读取人脸簇媒体失败'))
  } finally {
    if (showBusy) mediaLoading.value = false
  }
}

function selectCluster(cluster: FaceCluster) {
  selectedClusterLabel.value = cluster.label
  void loadClusterMedia(cluster.label)
}

async function handleRenameCluster(cluster: FaceCluster) {
  renamingLabels.value = [...renamingLabels.value, cluster.label]

  try {
    const updated = await renameFaceCluster(cluster.label, renameDrafts[cluster.label] || '')
    clusters.value = clusters.value.map((item) => (item.label === cluster.label ? updated : item))
    renameDrafts[cluster.label] = updated.display_name || ''
    emitWorkspaceRefresh()
    ElMessage.success(updated.display_name ? '人脸簇名称已保存' : '人脸簇名称已清空')
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, '保存人脸簇名称失败'))
  } finally {
    renamingLabels.value = renamingLabels.value.filter((item) => item !== cluster.label)
  }
}

function openDetails(photo: Photo) {
  selectedPhoto.value = photo
  detailOpen.value = true
}

function openVideoDetails(video: Video) {
  selectedVideo.value = video
  videoDetailOpen.value = true
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

function replaceVideo(updatedVideo: Video) {
  clusterVideoHits.value = clusterVideoHits.value.map((hit) =>
    hit.video.id === updatedVideo.id
      ? {
          ...hit,
          video: updatedVideo,
        }
      : hit,
  )

  if (selectedVideo.value?.id === updatedVideo.id) {
    selectedVideo.value = updatedVideo
  }
}

async function refreshSelectedPhoto() {
  if (!selectedPhoto.value) return
  const latest = await getPhoto(selectedPhoto.value.id)
  replacePhoto(latest)
}

async function refreshSelectedVideo() {
  if (!selectedVideo.value) return
  const latest = await getVideo(selectedVideo.value.id)
  replaceVideo(latest)
}

async function handleReanalyze() {
  if (!selectedPhoto.value) return

  reanalyzing.value = true
  try {
    const updatedPhoto = await reanalyzePhoto(selectedPhoto.value.id)
    replacePhoto(updatedPhoto)
    await loadClusters(false)
    emitWorkspaceRefresh()
    ElMessage.success('图片已重新分析')
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, '重新分析失败'))
  } finally {
    reanalyzing.value = false
  }
}

async function handleFindSimilarPhoto() {
  if (!selectedPhoto.value) return

  findingSimilar.value = true
  try {
    const response = await findSimilarPhotos(selectedPhoto.value.id, 24)
    clusterHits.value = response.hits
    photoTitle.value = '相似图片'
    exitPhotoSelectionMode()
    ElMessage.success('已切换到相似图片结果')
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, '查找相似图片失败'))
  } finally {
    findingSimilar.value = false
  }
}

async function handleFindSimilarVideo() {
  if (!selectedVideo.value) return

  findingSimilarVideo.value = true
  try {
    const response = await findSimilarVideos(selectedVideo.value.id, 24)
    clusterVideoHits.value = response.hits
    videoTitle.value = '相似视频'
    await refreshSelectedVideo()
    exitVideoSelectionMode()
    ElMessage.success('已切换到相似视频结果')
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, '查找相似视频失败'))
  } finally {
    findingSimilarVideo.value = false
  }
}

async function removePhotosByIds(photoIds: number[], successMessage: string) {
  const uniqueIds = Array.from(new Set(photoIds))
  const idSet = new Set(uniqueIds)

  for (const photoId of uniqueIds) {
    await deletePhoto(photoId)
  }

  clusterHits.value = clusterHits.value.filter((hit) => !idSet.has(hit.photo.id))
  selectedPhotoIds.value = selectedPhotoIds.value.filter((id) => !idSet.has(id))

  if (selectedPhoto.value && idSet.has(selectedPhoto.value.id)) {
    selectedPhoto.value = null
    detailOpen.value = false
  }

  await loadClusters(false)
  emitWorkspaceRefresh()
  ElMessage.success(successMessage)
}

async function removeVideosByIds(videoIds: number[], successMessage: string) {
  const uniqueIds = Array.from(new Set(videoIds))
  const idSet = new Set(uniqueIds)

  for (const videoId of uniqueIds) {
    await deleteVideo(videoId)
  }

  clusterVideoHits.value = clusterVideoHits.value.filter((hit) => !idSet.has(hit.video.id))
  selectedVideoIds.value = selectedVideoIds.value.filter((id) => !idSet.has(id))

  if (selectedVideo.value && idSet.has(selectedVideo.value.id)) {
    selectedVideo.value = null
    videoDetailOpen.value = false
  }

  await loadClusters(false)
  emitWorkspaceRefresh()
  ElMessage.success(successMessage)
}

async function handleDeletePhoto() {
  if (!selectedPhoto.value) return

  try {
    await ElMessageBox.confirm(
      '删除后会移除图片归档文件，并更新该人脸簇下的相关结果。是否继续？',
      '删除图片',
      {
        type: 'warning',
        confirmButtonText: '删除',
        cancelButtonText: '取消',
      },
    )
  } catch (error) {
    if (isMessageBoxCancel(error)) return
    ElMessage.error(resolveErrorMessage(error, '删除图片前确认失败'))
    return
  }

  deletingPhoto.value = true
  try {
    await removePhotosByIds([selectedPhoto.value.id], '图片已删除')
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, '删除图片失败'))
  } finally {
    deletingPhoto.value = false
  }
}

async function handleDeleteVideo() {
  if (!selectedVideo.value) return

  try {
    await ElMessageBox.confirm(
      '删除后会移除视频归档文件、缩略图和抽帧缓存，并更新该人脸簇下的结果。是否继续？',
      '删除视频',
      {
        type: 'warning',
        confirmButtonText: '删除',
        cancelButtonText: '取消',
      },
    )
  } catch (error) {
    if (isMessageBoxCancel(error)) return
    ElMessage.error(resolveErrorMessage(error, '删除视频前确认失败'))
    return
  }

  deletingVideo.value = true
  try {
    await removeVideosByIds([selectedVideo.value.id], '视频已删除')
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, '删除视频失败'))
  } finally {
    deletingVideo.value = false
  }
}

async function handleBatchDeletePhotos() {
  if (!selectedPhotoIds.value.length) return

  try {
    await ElMessageBox.confirm(
      `将删除 ${selectedPhotoIds.value.length} 张图片，并更新该人脸簇下的相关结果。是否继续？`,
      '批量删除图片',
      {
        type: 'warning',
        confirmButtonText: '删除',
        cancelButtonText: '取消',
      },
    )
  } catch (error) {
    if (isMessageBoxCancel(error)) return
    ElMessage.error(resolveErrorMessage(error, '批量删除图片前确认失败'))
    return
  }

  batchDeletingPhotos.value = true
  try {
    const deleteCount = selectedPhotoIds.value.length
    await removePhotosByIds([...selectedPhotoIds.value], `已批量删除 ${deleteCount} 张图片`)
    exitPhotoSelectionMode()
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, '批量删除图片失败'))
  } finally {
    batchDeletingPhotos.value = false
  }
}

async function handleBatchDeleteVideos() {
  if (!selectedVideoIds.value.length) return

  try {
    await ElMessageBox.confirm(
      `将删除 ${selectedVideoIds.value.length} 个视频，并更新该人脸簇下的结果。是否继续？`,
      '批量删除视频',
      {
        type: 'warning',
        confirmButtonText: '删除',
        cancelButtonText: '取消',
      },
    )
  } catch (error) {
    if (isMessageBoxCancel(error)) return
    ElMessage.error(resolveErrorMessage(error, '批量删除视频前确认失败'))
    return
  }

  batchDeletingVideos.value = true
  try {
    const deleteCount = selectedVideoIds.value.length
    await removeVideosByIds([...selectedVideoIds.value], `已批量删除 ${deleteCount} 个视频`)
    exitVideoSelectionMode()
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, '批量删除视频失败'))
  } finally {
    batchDeletingVideos.value = false
  }
}

async function handleRenameFaceCluster(label: string, displayName: string) {
  renamingLabels.value = [...renamingLabels.value, label]

  try {
    const updated = await renameFaceCluster(label, displayName.trim())
    clusters.value = clusters.value.map((item) => (item.label === label ? updated : item))
    renameDrafts[label] = updated.display_name || ''
    await refreshSelectedPhoto()
    emitWorkspaceRefresh()
    ElMessage.success(displayName.trim() ? '人脸簇名称已保存' : '人脸簇名称已清空')
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, '保存人脸簇名称失败'))
  } finally {
    renamingLabels.value = renamingLabels.value.filter((item) => item !== label)
  }
}

function handleWorkspaceRefresh() {
  void loadClusters(false)
}

watch(currentPhotoIds, () => {
  if (!currentPhotoIds.value.length) {
    exitPhotoSelectionMode()
    return
  }
  selectedPhotoIds.value = selectedPhotoIds.value.filter((id) => currentPhotoIds.value.includes(id))
})

watch(currentVideoIds, () => {
  if (!currentVideoIds.value.length) {
    exitVideoSelectionMode()
    return
  }
  selectedVideoIds.value = selectedVideoIds.value.filter((id) => currentVideoIds.value.includes(id))
})

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
          共 {{ formatCount(clusters.length) }} 个聚类，其中已命名 {{ formatCount(namedCount) }} 个。
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
              <h4>{{ photoTitle }}</h4>
              <span class="section-tip">可查看详情，或开启多选后批量删除不需要的图片。</span>
            </div>

            <MediaBatchToolbar
              v-if="clusterHits.length"
              :active="photoSelectionMode"
              :selected-count="selectedPhotoIds.length"
              :total-count="clusterHits.length"
              media-label="图片"
              :deleting="batchDeletingPhotos"
              @start="startPhotoSelectionMode"
              @cancel="exitPhotoSelectionMode"
              @select-all="selectAllCurrentPhotos"
              @clear="clearPhotoSelection"
              @remove="handleBatchDeletePhotos"
            />

            <div v-if="clusterHits.length" class="photo-grid">
              <PhotoCard
                v-for="hit in clusterHits"
                :key="hit.photo.id"
                :photo="hit.photo"
                :score="photoTitle === '相似图片' ? hit.score : null"
                :selection-mode="photoSelectionMode"
                :selected="selectedPhotoIds.includes(hit.photo.id)"
                @select="openDetails(hit.photo)"
                @toggle-selection="togglePhotoSelection(hit.photo.id)"
              />
            </div>

            <el-empty
              v-else
              :description="
                mediaLoading
                  ? '正在读取该人脸簇的图片...'
                  : selectedCluster
                    ? '该人脸簇下暂无图片'
                    : '请先从左侧选择一个人脸簇'
              "
            />
          </section>

          <section class="page-section inner-section">
            <div class="section-head">
              <h4>{{ videoTitle }}</h4>
              <span class="section-tip">同一人物在视频中的结果也会聚合展示，可多选批量清理误匹配视频。</span>
            </div>

            <MediaBatchToolbar
              v-if="clusterVideoHits.length"
              :active="videoSelectionMode"
              :selected-count="selectedVideoIds.length"
              :total-count="clusterVideoHits.length"
              media-label="视频"
              :deleting="batchDeletingVideos"
              @start="startVideoSelectionMode"
              @cancel="exitVideoSelectionMode"
              @select-all="selectAllCurrentVideos"
              @clear="clearVideoSelection"
              @remove="handleBatchDeleteVideos"
            />

            <div v-if="clusterVideoHits.length" class="photo-grid">
              <VideoCard
                v-for="hit in clusterVideoHits"
                :key="hit.video.id"
                :video="hit.video"
                :score="videoTitle === '相似视频' ? hit.score : undefined"
                :selection-mode="videoSelectionMode"
                :selected="selectedVideoIds.includes(hit.video.id)"
                @select="openVideoDetails(hit.video)"
                @toggle-selection="toggleVideoSelection(hit.video.id)"
              />
            </div>

            <el-empty
              v-else
              :description="
                mediaLoading
                  ? '正在读取该人脸簇的视频...'
                  : selectedCluster
                    ? '该人脸簇下暂无视频'
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
      :deleting="deletingPhoto"
      @reanalyze="handleReanalyze"
      @find-similar="handleFindSimilarPhoto"
      @delete="handleDeletePhoto"
      @rename-face-cluster="handleRenameFaceCluster"
    />

    <VideoDetailDrawer
      v-model="videoDetailOpen"
      :video="selectedVideo"
      :finding-similar="findingSimilarVideo"
      :deleting="deletingVideo"
      @find-similar="handleFindSimilarVideo"
      @delete="handleDeleteVideo"
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
