<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { Picture, Search, UploadFilled, UserFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

import PhotoCard from '../components/PhotoCard.vue'
import PhotoDetailDrawer from '../components/PhotoDetailDrawer.vue'
import {
  findSimilarPhotos,
  getPhoto,
  listFaceClusters,
  listPeople,
  listPhotos,
  reanalyzePhoto,
  renameFaceCluster,
  searchByImage,
  searchByPersonImage,
  searchPhotos,
} from '../services/api'
import type {
  FaceCluster,
  PersonProfile,
  Photo,
  SearchHit,
  SearchMode,
  SourceKind,
} from '../types'
import {
  parseTagInput,
  resolveErrorMessage,
  searchModeOptions,
  sourceKindOptions,
} from '../utils/format'

const loading = ref(false)
const mode = ref<'recent' | 'search' | 'similar' | 'image' | 'personImage'>('recent')
const hits = ref<SearchHit[]>([])
const detailOpen = ref(false)
const selectedPhoto = ref<Photo | null>(null)
const reanalyzing = ref(false)
const findingSimilar = ref(false)
const faceClusters = ref<FaceCluster[]>([])
const renamingLabels = ref<string[]>([])
const peopleProfiles = ref<PersonProfile[]>([])

const imageSearching = ref(false)
const queryImagePreview = ref<string | null>(null)
const queryImageName = ref('')
const fileInputRef = ref<HTMLInputElement | null>(null)

const personImageSearching = ref(false)
const personQueryImagePreview = ref<string | null>(null)
const personQueryImageName = ref('')
const personFileInputRef = ref<HTMLInputElement | null>(null)

const form = reactive<{
  text: string
  peopleText: string
  sceneText: string
  objectText: string
  sourceKinds: SourceKind[]
  selectedPeople: string[]
  mode: SearchMode
  limit: number
}>({
  text: '',
  peopleText: '',
  sceneText: '',
  objectText: '',
  sourceKinds: [],
  selectedPeople: [],
  mode: 'hybrid',
  limit: 24,
})

const quickQueries = [
  '去年夏天和家人在海边拍的日落',
  '带有发票文字的截图',
  '微信里导入的聚会合影',
  '包含乐高和孩子的照片',
  '和小明在教室里合影的照片',
]

const resultTitle = computed(() => {
  if (mode.value === 'similar') return '相似图片'
  if (mode.value === 'image') return '参考图检索结果'
  if (mode.value === 'personImage') return '人物图检索结果'
  if (mode.value === 'search') return '搜索结果'
  return '最近导入'
})

function buildPeopleFilters(): string[] {
  return Array.from(new Set([...parseTagInput(form.peopleText), ...form.selectedPeople]))
}

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

async function loadPeopleList() {
  try {
    peopleProfiles.value = await listPeople(120)
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, '读取人物库失败。'))
  }
}

async function runSearch(showBusy = true) {
  if (showBusy) loading.value = true

  try {
    const response = await searchPhotos({
      text: form.text.trim(),
      people: buildPeopleFilters(),
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
      form.selectedPeople.length ||
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
  form.selectedPeople = []
  form.sourceKinds = []
  form.mode = 'hybrid'
  clearQueryImage()
  clearPersonQueryImage()
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
    await Promise.all([loadFaceClusterList(), loadPeopleList()])
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
    await Promise.all([loadFaceClusterList(), refreshSelectedPhoto(), loadPeopleList()])
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

function openPersonImagePicker() {
  personFileInputRef.value?.click()
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

async function handlePersonImageFileChange(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return

  if (personQueryImagePreview.value) {
    URL.revokeObjectURL(personQueryImagePreview.value)
  }
  personQueryImagePreview.value = URL.createObjectURL(file)
  personQueryImageName.value = file.name
  personImageSearching.value = true

  try {
    const response = await searchByPersonImage(file, form.limit)
    hits.value = response.hits
    mode.value = 'personImage'
    ElMessage.success('人物图检索已完成。')
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, '按人物图检索失败。'))
  } finally {
    personImageSearching.value = false
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

function clearPersonQueryImage() {
  if (personQueryImagePreview.value) {
    URL.revokeObjectURL(personQueryImagePreview.value)
  }
  personQueryImagePreview.value = null
  personQueryImageName.value = ''
}

function handleWorkspaceRefresh() {
  void Promise.all([loadFaceClusterList(), loadPeopleList()])
  if (mode.value === 'search' && hasSearchFilters()) {
    void runSearch(false)
    return
  }
  if (mode.value === 'similar' && selectedPhoto.value) {
    void handleFindSimilar()
    return
  }
  if (mode.value === 'image' || mode.value === 'personImage') {
    return
  }
  void loadRecent(false)
}

onMounted(() => {
  void Promise.all([loadRecent(), loadFaceClusterList(), loadPeopleList()])
  window.addEventListener('workspace:refresh', handleWorkspaceRefresh)
})

onBeforeUnmount(() => {
  window.removeEventListener('workspace:refresh', handleWorkspaceRefresh)
  clearQueryImage()
  clearPersonQueryImage()
})
</script>

<template>
  <div class="page-stack">
    <section class="page-section search-board fade-in">
      <div class="page-heading">
        <p class="eyebrow">Natural Retrieval</p>
        <h3>用一句话、一张图，或者一张人物参考图搜索跨来源图片</h3>
        <p>
          输入自然语言时可以直接写人物名，例如“和小明在海边拍的日落”。
          如果你已经在“人物库”里上传过参考图，系统会把这些人名一起带入识别与搜索。
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
          <label>人物名</label>
          <el-input
            v-model="form.peopleText"
            placeholder="多个名称用逗号分隔，例如：爸爸，小明"
          />
        </div>
        <div class="soft-panel mini-panel">
          <label>已知人物</label>
          <el-select
            v-model="form.selectedPeople"
            multiple
            collapse-tags
            placeholder="从人物库选择已标注人物"
          >
            <el-option
              v-for="person in peopleProfiles"
              :key="person.id"
              :label="person.name"
              :value="person.name"
            />
          </el-select>
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

      <div class="query-panel-grid">
        <div class="image-query-panel soft-panel">
          <div class="section-head compact-head">
            <h4>以图搜图</h4>
            <span class="section-tip">适合按整体画面、构图、颜色和 OCR 内容找相似图。</span>
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

        <div class="image-query-panel soft-panel">
          <div class="section-head compact-head">
            <h4>按人物图检索</h4>
            <span class="section-tip">只看人脸特征，适合用一张人物头像去找同一个人。</span>
          </div>

          <div class="image-query-row">
            <div v-if="personQueryImagePreview" class="image-query-preview person-preview">
              <img :src="personQueryImagePreview" :alt="personQueryImageName || 'person-query-image'" />
            </div>
            <div class="image-query-actions">
              <input
                ref="personFileInputRef"
                class="hidden-input"
                type="file"
                accept="image/*"
                @change="handlePersonImageFileChange"
              />
              <el-button
                type="primary"
                plain
                :icon="UserFilled"
                :loading="personImageSearching"
                @click="openPersonImagePicker"
              >
                上传人物图
              </el-button>
              <span v-if="personQueryImageName" class="image-query-name">{{ personQueryImageName }}</span>
              <el-button
                v-if="personQueryImagePreview"
                text
                :icon="Picture"
                @click="clearPersonQueryImage"
              >
                清除人物图
              </el-button>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section class="page-section fade-in">
      <div class="section-head">
        <h4>{{ resultTitle }}</h4>
        <span class="section-tip">点击图片可查看详情、重分析、命名人脸簇或查找相似图。</span>
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
.query-panel-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
  margin-top: 18px;
}

.image-query-panel {
  margin-top: 0;
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

.person-preview {
  border-color: rgba(255, 190, 120, 0.28);
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

@media (max-width: 960px) {
  .query-panel-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .image-query-row {
    grid-template-columns: 1fr;
  }
}
</style>
