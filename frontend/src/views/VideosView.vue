<script setup lang="ts">
import { Film, Search, UploadFilled } from '@element-plus/icons-vue'
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import VideoCard from '../components/VideoCard.vue'
import VideoDetailDrawer from '../components/VideoDetailDrawer.vue'
import {
  findSimilarVideos,
  getVideo,
  listPeople,
  listVideos,
  searchByVideo,
  searchVideos,
} from '../services/api'
import type { PersonProfile, SearchMode, SourceKind, Video, VideoSearchHit } from '../types'
import {
  parseTagInput,
  resolveErrorMessage,
  searchModeOptions,
  sourceKindOptions,
} from '../utils/format'

const loading = ref(false)
const mode = ref<'recent' | 'search' | 'video' | 'similar'>('recent')
const hits = ref<VideoSearchHit[]>([])
const peopleProfiles = ref<PersonProfile[]>([])

const detailOpen = ref(false)
const selectedVideo = ref<Video | null>(null)
const findingSimilar = ref(false)

const videoSearching = ref(false)
const videoQueryName = ref('')
const videoInputRef = ref<HTMLInputElement | null>(null)

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

const resultTitle = computed(() => {
  if (mode.value === 'video') return '视频样例检索结果'
  if (mode.value === 'similar') return '相似视频'
  if (mode.value === 'search') return '视频搜索结果'
  return '最近导入的视频'
})

const quickQueries = [
  '和小明一起出游的视频',
  '有海边和日落场景的视频',
  '包含课堂或白板的视频',
  '有孩子和乐高的视频片段',
]

function buildPeopleFilters(): string[] {
  return Array.from(new Set([...parseTagInput(form.peopleText), ...form.selectedPeople]))
}

async function loadPeopleList() {
  try {
    peopleProfiles.value = await listPeople(120)
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, '读取人物列表失败'))
  }
}

async function loadRecentVideos(showBusy = true) {
  if (showBusy) loading.value = true
  try {
    const videos = await listVideos(form.limit)
    hits.value = videos.map((video) => ({
      score: 1,
      video,
    }))
    mode.value = 'recent'
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, '读取最近视频失败'))
  } finally {
    if (showBusy) loading.value = false
  }
}

async function runSearch(showBusy = true) {
  if (showBusy) loading.value = true
  try {
    const response = await searchVideos({
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
    ElMessage.error(resolveErrorMessage(error, '执行视频搜索失败'))
  } finally {
    if (showBusy) loading.value = false
  }
}

function resetFilters() {
  form.text = ''
  form.peopleText = ''
  form.sceneText = ''
  form.objectText = ''
  form.selectedPeople = []
  form.sourceKinds = []
  form.mode = 'hybrid'
  videoQueryName.value = ''
  void loadRecentVideos()
}

function applyQuickQuery(query: string) {
  form.text = query
  void runSearch()
}

function openVideoPicker() {
  videoInputRef.value?.click()
}

async function handleVideoFileChange(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return

  videoSearching.value = true
  try {
    videoQueryName.value = file.name
    const response = await searchByVideo(file, form.limit)
    hits.value = response.hits
    mode.value = 'video'
    ElMessage.success('已切换到视频样例检索结果')
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, '按视频检索失败'))
  } finally {
    videoSearching.value = false
    target.value = ''
  }
}

function openDetails(video: Video) {
  selectedVideo.value = video
  detailOpen.value = true
}

function replaceVideo(updatedVideo: Video) {
  hits.value = hits.value.map((hit) =>
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

async function refreshSelectedVideo() {
  if (!selectedVideo.value) return
  const latest = await getVideo(selectedVideo.value.id)
  replaceVideo(latest)
}

async function handleFindSimilar() {
  if (!selectedVideo.value) return

  findingSimilar.value = true
  try {
    const response = await findSimilarVideos(selectedVideo.value.id, form.limit)
    hits.value = response.hits
    mode.value = 'similar'
    await refreshSelectedVideo()
    ElMessage.success('已切换到相似视频结果')
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, '查找相似视频失败'))
  } finally {
    findingSimilar.value = false
  }
}

onMounted(() => {
  void Promise.all([loadRecentVideos(), loadPeopleList()])
})
</script>

<template>
  <div class="page-stack">
    <section class="page-section fade-in">
      <div class="section-head">
        <h4>视频检索</h4>
        <span class="section-tip">
          支持文本搜视频、按视频样例搜视频，并聚合展示视频中的人物、场景和对象标签。
        </span>
      </div>

      <div class="search-panel">
        <div class="search-panel__main">
          <el-input
            v-model="form.text"
            type="textarea"
            :rows="3"
            placeholder="例如：去年夏天和小明在海边出游的视频"
          />

          <div class="quick-query-row">
            <button
              v-for="query in quickQueries"
              :key="query"
              type="button"
              class="quick-query-chip"
              @click="applyQuickQuery(query)"
            >
              {{ query }}
            </button>
          </div>
        </div>

        <div class="search-panel__side">
          <el-input v-model="form.peopleText" placeholder="人物标签，逗号分隔" clearable />
          <el-select v-model="form.selectedPeople" multiple collapse-tags placeholder="已知人物">
            <el-option
              v-for="person in peopleProfiles"
              :key="person.id"
              :label="person.name"
              :value="person.name"
            />
          </el-select>
          <el-input v-model="form.sceneText" placeholder="场景标签，如 海边、室内" clearable />
          <el-input v-model="form.objectText" placeholder="物体标签，如 猫、乐高" clearable />
          <el-select v-model="form.sourceKinds" multiple collapse-tags placeholder="来源类型">
            <el-option
              v-for="option in sourceKindOptions"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
          <el-select v-model="form.mode" placeholder="搜索模式">
            <el-option
              v-for="option in searchModeOptions"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
        </div>
      </div>

      <div class="search-actions">
        <el-button type="primary" :icon="Search" :loading="loading" @click="runSearch">
          搜索视频
        </el-button>
        <input
          ref="videoInputRef"
          class="hidden-input"
          type="file"
          accept="video/*"
          @change="handleVideoFileChange"
        />
        <el-button plain :icon="UploadFilled" :loading="videoSearching" @click="openVideoPicker">
          以视频搜视频
        </el-button>
        <el-button plain :icon="Film" @click="loadRecentVideos">最近视频</el-button>
        <el-button plain @click="resetFilters">重置</el-button>
        <span v-if="videoQueryName" class="query-hint">当前样例：{{ videoQueryName }}</span>
      </div>
    </section>

    <section class="page-section fade-in">
      <div class="section-head">
        <h4>{{ resultTitle }}</h4>
        <span class="section-tip">{{ hits.length }} 个结果</span>
      </div>

      <div v-if="hits.length" class="photo-grid">
        <VideoCard
          v-for="hit in hits"
          :key="hit.video.id"
          :video="hit.video"
          :score="mode === 'recent' ? undefined : hit.score"
          @select="openDetails(hit.video)"
        />
      </div>

      <el-empty
        v-else
        :description="
          loading
            ? '正在加载视频结果...'
            : mode === 'recent'
              ? '还没有导入视频'
              : '没有找到匹配的视频'
        "
      />
    </section>

    <VideoDetailDrawer
      v-model="detailOpen"
      :video="selectedVideo"
      :finding-similar="findingSimilar"
      @find-similar="handleFindSimilar"
    />
  </div>
</template>

<style scoped>
.search-panel {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(320px, 420px);
  gap: 18px;
}

.search-panel__main,
.search-panel__side {
  display: grid;
  gap: 12px;
}

.quick-query-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.quick-query-chip {
  padding: 8px 14px;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.03);
  color: inherit;
}

.search-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  margin-top: 16px;
}

.query-hint {
  color: var(--muted);
}

.hidden-input {
  display: none;
}

@media (max-width: 1100px) {
  .search-panel {
    grid-template-columns: 1fr;
  }
}
</style>
