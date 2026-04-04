<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { Plus, UploadFilled, UserFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

import PhotoCard from '../components/PhotoCard.vue'
import PhotoDetailDrawer from '../components/PhotoDetailDrawer.vue'
import {
  addPersonSample,
  createPerson,
  findSimilarPhotos,
  getPersonSampleAssetUrl,
  getPhoto,
  listFaceClusters,
  listPeople,
  listPersonSamples,
  listPhotosByPerson,
  reanalyzePhoto,
  renameFaceCluster,
  renamePerson,
} from '../services/api'
import type { FaceCluster, PersonProfile, PersonSample, Photo, SearchHit } from '../types'
import { formatCount, formatDateTime, resolveErrorMessage } from '../utils/format'

const people = ref<PersonProfile[]>([])
const samples = ref<PersonSample[]>([])
const personHits = ref<SearchHit[]>([])
const selectedPersonId = ref<number | null>(null)
const peopleLoading = ref(false)
const detailLoading = ref(false)
const creating = ref(false)
const renaming = ref(false)
const uploadingSample = ref(false)
const createName = ref('')
const renameDrafts = reactive<Record<number, string>>({})
const sampleInputRef = ref<HTMLInputElement | null>(null)

const detailOpen = ref(false)
const selectedPhoto = ref<Photo | null>(null)
const reanalyzing = ref(false)
const findingSimilar = ref(false)
const faceClusters = ref<FaceCluster[]>([])
const renamingLabels = ref<string[]>([])

const selectedPerson = computed(() =>
  people.value.find((person) => person.id === selectedPersonId.value) || null,
)

function exampleSampleUrl(person: PersonProfile): string {
  return person.example_sample_id ? getPersonSampleAssetUrl(person.example_sample_id) : ''
}

async function loadPeople(showBusy = true) {
  if (showBusy) peopleLoading.value = true

  try {
    const response = await listPeople(200)
    people.value = response.sort((a, b) => b.linked_photo_count - a.linked_photo_count)
    for (const person of people.value) {
      renameDrafts[person.id] = person.name
    }

    const selectedStillExists = people.value.some((person) => person.id === selectedPersonId.value)
    if (!selectedStillExists) {
      selectedPersonId.value = people.value[0]?.id || null
    }

    if (selectedPersonId.value) {
      await loadPersonDetail(selectedPersonId.value, false)
    } else {
      samples.value = []
      personHits.value = []
    }
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, '读取人物库失败。'))
  } finally {
    if (showBusy) peopleLoading.value = false
  }
}

async function loadFaceClusterList() {
  try {
    faceClusters.value = await listFaceClusters(120)
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, '读取人脸簇列表失败。'))
  }
}

async function loadPersonDetail(personId: number, showBusy = true) {
  if (showBusy) detailLoading.value = true

  try {
    const [sampleList, photoResponse] = await Promise.all([
      listPersonSamples(personId),
      listPhotosByPerson(personId, 48),
    ])
    samples.value = sampleList
    personHits.value = photoResponse.hits
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, '读取人物详情失败。'))
  } finally {
    if (showBusy) detailLoading.value = false
  }
}

async function handleCreatePerson() {
  const name = createName.value.trim()
  if (!name) {
    ElMessage.warning('请先输入人物名称。')
    return
  }

  creating.value = true
  try {
    const person = await createPerson(name)
    createName.value = ''
    selectedPersonId.value = person.id
    await loadPeople(false)
    ElMessage.success('人物档案已创建。')
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, '创建人物档案失败。'))
  } finally {
    creating.value = false
  }
}

async function handleRenamePerson() {
  if (!selectedPerson.value) return

  renaming.value = true
  try {
    const updated = await renamePerson(selectedPerson.value.id, renameDrafts[selectedPerson.value.id] || '')
    people.value = people.value.map((item) => (item.id === updated.id ? updated : item))
    renameDrafts[updated.id] = updated.name
    await Promise.all([loadPersonDetail(updated.id, false), loadFaceClusterList()])
    ElMessage.success('人物名称已保存。')
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, '重命名人物失败。'))
  } finally {
    renaming.value = false
  }
}

function selectPerson(person: PersonProfile) {
  selectedPersonId.value = person.id
  void loadPersonDetail(person.id)
}

function openSamplePicker() {
  if (!selectedPerson.value) {
    ElMessage.info('请先选择一个人物档案。')
    return
  }
  sampleInputRef.value?.click()
}

async function handleSampleFileChange(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file || !selectedPerson.value) return

  uploadingSample.value = true
  try {
    const updated = await addPersonSample(selectedPerson.value.id, file)
    people.value = people.value.map((item) => (item.id === updated.id ? updated : item))
    renameDrafts[updated.id] = updated.name
    await Promise.all([loadPersonDetail(updated.id, false), loadFaceClusterList()])
    ElMessage.success('人物参考图已上传，系统会自动用于识别该人物。')
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, '上传人物参考图失败。'))
  } finally {
    uploadingSample.value = false
    target.value = ''
  }
}

function openDetails(photo: Photo) {
  selectedPhoto.value = photo
  detailOpen.value = true
}

function replacePhoto(updatedPhoto: Photo) {
  personHits.value = personHits.value.map((hit) =>
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
    await Promise.all([loadPeople(false), loadFaceClusterList()])
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
    personHits.value = response.hits
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
    await Promise.all([loadFaceClusterList(), refreshSelectedPhoto(), loadPeople(false)])
    ElMessage.success(displayName.trim() ? '人脸簇名称已保存。' : '人脸簇名称已清空。')
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, '保存人脸簇名称失败。'))
  } finally {
    renamingLabels.value = renamingLabels.value.filter((item) => item !== label)
  }
}

function handleWorkspaceRefresh() {
  void Promise.all([loadPeople(false), loadFaceClusterList()])
}

onMounted(() => {
  void Promise.all([loadPeople(), loadFaceClusterList()])
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
        <h4>人物库</h4>
        <span class="section-tip">上传带名字的人像参考图，系统会自动把该人物绑定到相似人脸簇。</span>
      </div>

      <div class="people-create-row">
        <el-input v-model="createName" placeholder="例如：爸爸 / 小明 / 同学 A" />
        <el-button type="primary" :icon="Plus" :loading="creating" @click="handleCreatePerson">
          新建人物
        </el-button>
      </div>
    </section>

    <section class="page-section fade-in">
      <div class="people-layout">
        <aside class="soft-panel people-sidebar">
          <div class="section-head compact-head">
            <h4>人物列表</h4>
            <span class="section-tip">{{ formatCount(people.length) }} 个档案</span>
          </div>

          <div v-if="people.length" class="people-list">
            <button
              v-for="person in people"
              :key="person.id"
              type="button"
              class="people-item"
              :class="{ active: selectedPersonId === person.id }"
              @click="selectPerson(person)"
            >
              <div class="people-thumb">
                <img v-if="person.example_sample_id" :src="exampleSampleUrl(person)" :alt="person.name" />
                <div v-else class="people-empty">
                  <el-icon><UserFilled /></el-icon>
                </div>
              </div>
              <div class="people-copy">
                <strong>{{ person.name }}</strong>
                <small>{{ person.sample_count }} 张参考图</small>
                <span>{{ person.linked_photo_count }} 张识别图片</span>
              </div>
            </button>
          </div>

          <el-empty v-else :description="peopleLoading ? '正在读取人物库...' : '还没有人物档案'" />
        </aside>

        <div class="people-main">
          <section v-if="selectedPerson" class="glass-panel">
            <div class="people-main-head">
              <div class="people-cover">
                <img
                  v-if="selectedPerson.example_sample_id"
                  :src="exampleSampleUrl(selectedPerson)"
                  :alt="selectedPerson.name"
                />
                <div v-else class="people-empty">
                  <el-icon><UserFilled /></el-icon>
                </div>
              </div>

              <div class="people-summary">
                <p class="eyebrow">Person Profile</p>
                <h3>{{ selectedPerson.name }}</h3>
                <div class="tag-cloud">
                  <span class="photo-tag">{{ selectedPerson.sample_count }} 张参考图</span>
                  <span class="photo-tag">{{ selectedPerson.linked_cluster_count }} 个人脸簇</span>
                  <span class="photo-tag">{{ selectedPerson.linked_photo_count }} 张识别图片</span>
                  <span class="photo-tag">
                    最近更新 {{ formatDateTime(selectedPerson.updated_at) }}
                  </span>
                </div>
              </div>
            </div>

            <div class="people-rename-row">
              <el-input v-model="renameDrafts[selectedPerson.id]" placeholder="更新人物名称" />
              <el-button type="primary" :loading="renaming" @click="handleRenamePerson">
                保存名称
              </el-button>
              <input
                ref="sampleInputRef"
                class="hidden-input"
                type="file"
                accept="image/*"
                @change="handleSampleFileChange"
              />
              <el-button
                plain
                :icon="UploadFilled"
                :loading="uploadingSample"
                @click="openSamplePicker"
              >
                上传参考图
              </el-button>
            </div>

            <div class="section-head compact-head">
              <h4>参考图样本</h4>
              <span class="section-tip">至少上传 1 张清晰正脸图，建议 3-5 张不同角度图片。</span>
            </div>

            <div v-if="samples.length" class="sample-grid">
              <article v-for="sample in samples" :key="sample.id" class="sample-card">
                <img :src="getPersonSampleAssetUrl(sample.id)" :alt="sample.original_filename" />
                <div class="sample-card__copy">
                  <strong>{{ sample.original_filename }}</strong>
                  <span>{{ formatDateTime(sample.created_at) }}</span>
                </div>
              </article>
            </div>
            <el-empty v-else :description="detailLoading ? '正在读取样本...' : '先上传一张人物参考图'" />
          </section>

          <section class="page-section inner-section">
            <div class="section-head">
              <h4>该人物相关图片</h4>
              <span class="section-tip">识别结果来自已绑定人脸簇，人物名也可直接用于搜索页的自然语言描述。</span>
            </div>

            <div v-if="personHits.length" class="photo-grid">
              <PhotoCard
                v-for="hit in personHits"
                :key="hit.photo.id"
                :photo="hit.photo"
                :score="hit.score"
                @select="openDetails(hit.photo)"
              />
            </div>

            <el-empty
              v-else
              :description="
                detailLoading
                  ? '正在读取人物图片...'
                  : selectedPerson
                    ? '该人物当前还没有识别到关联图片'
                    : '请先从左侧选择一个人物档案'
              "
            />
          </section>
        </div>
      </div>
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
.people-create-row,
.people-rename-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  gap: 12px;
}

.people-layout {
  display: grid;
  grid-template-columns: 340px minmax(0, 1fr);
  gap: 18px;
}

.people-sidebar {
  min-height: 560px;
}

.compact-head {
  margin-bottom: 12px;
}

.people-list {
  display: grid;
  gap: 12px;
}

.people-item {
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

.people-item:hover,
.people-item.active {
  transform: translateY(-1px);
  border-color: rgba(255, 184, 121, 0.28);
  background: rgba(255, 165, 90, 0.08);
}

.people-thumb,
.people-cover {
  aspect-ratio: 1 / 1;
  overflow: hidden;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.04);
}

.people-thumb {
  width: 80px;
}

.people-cover {
  width: 140px;
}

.people-thumb img,
.people-cover img,
.sample-card img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.people-empty {
  width: 100%;
  height: 100%;
  display: grid;
  place-items: center;
  color: var(--muted);
}

.people-copy,
.sample-card__copy {
  display: grid;
  gap: 6px;
}

.people-copy small,
.people-copy span,
.sample-card__copy span {
  color: var(--muted);
}

.people-main {
  display: grid;
  gap: 18px;
}

.people-main-head {
  display: grid;
  grid-template-columns: 140px minmax(0, 1fr);
  gap: 18px;
  align-items: center;
}

.people-summary h3 {
  margin: 8px 0 12px;
  font-size: 28px;
}

.sample-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 14px;
  margin-top: 18px;
}

.sample-card {
  overflow: hidden;
  border-radius: 18px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.03);
}

.sample-card img {
  aspect-ratio: 1 / 1;
}

.sample-card__copy {
  padding: 12px;
}

.hidden-input {
  display: none;
}

.inner-section {
  padding: 0;
  background: transparent;
  border: none;
  box-shadow: none;
}

@media (max-width: 1100px) {
  .people-layout {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .people-create-row,
  .people-rename-row,
  .people-main-head {
    grid-template-columns: 1fr;
  }
}
</style>
