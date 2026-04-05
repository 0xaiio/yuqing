<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Check, Refresh, UserFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

import {
  applyPersonClusterCorrection,
  getPhotoAssetUrl,
  listPeople,
  listPersonCorrectionCandidates,
} from '../services/api'
import type { PersonClusterCorrectionCandidate, PersonProfile } from '../types'
import { formatCount, resolveErrorMessage } from '../utils/format'

const people = ref<PersonProfile[]>([])
const selectedPersonId = ref<number | null>(null)
const candidates = ref<PersonClusterCorrectionCandidate[]>([])
const peopleLoading = ref(false)
const candidateLoading = ref(false)
const actionLoading = ref(false)
const keyword = ref('')
const minScore = ref(0)
const filterMode = ref<'all' | 'recommended' | 'linked' | 'unlinked' | 'reassign'>('recommended')
const selectedLabels = ref<string[]>([])

const selectedPerson = computed(
  () => people.value.find((person) => person.id === selectedPersonId.value) || null,
)

const filteredCandidates = computed(() => {
  const searchKeyword = keyword.value.trim().toLowerCase()
  return candidates.value.filter((candidate) => {
    if (candidate.score < minScore.value) return false
    if (filterMode.value === 'recommended' && !candidate.recommended) return false
    if (filterMode.value === 'linked' && !candidate.linked_to_selected_person) return false
    if (filterMode.value === 'unlinked' && candidate.linked_to_selected_person) return false
    if (
      filterMode.value === 'reassign' &&
      (!candidate.current_person_id || candidate.current_person_id === selectedPersonId.value)
    ) {
      return false
    }
    if (!searchKeyword) return true
    return (
      candidate.label.toLowerCase().includes(searchKeyword) ||
      (candidate.display_name || '').toLowerCase().includes(searchKeyword) ||
      (candidate.current_person_name || '').toLowerCase().includes(searchKeyword)
    )
  })
})

const selectedCount = computed(
  () => selectedLabels.value.filter((label) => filteredCandidates.value.some((item) => item.label === label)).length,
)

function emitWorkspaceRefresh() {
  window.dispatchEvent(new Event('workspace:refresh'))
}

function isSelected(label: string): boolean {
  return selectedLabels.value.includes(label)
}

function toggleSelection(label: string, checked: boolean) {
  if (checked) {
    selectedLabels.value = Array.from(new Set([...selectedLabels.value, label]))
    return
  }
  selectedLabels.value = selectedLabels.value.filter((item) => item !== label)
}

function selectRecommended() {
  selectedLabels.value = filteredCandidates.value
    .filter((candidate) => candidate.recommended)
    .map((candidate) => candidate.label)
}

function clearSelection() {
  selectedLabels.value = []
}

function examplePhotoUrl(candidate: PersonClusterCorrectionCandidate): string {
  return candidate.example_photo_id ? getPhotoAssetUrl(candidate.example_photo_id) : ''
}

async function loadPeople(showBusy = true) {
  if (showBusy) peopleLoading.value = true
  try {
    const response = await listPeople(200)
    people.value = response.sort((a, b) => b.linked_photo_count - a.linked_photo_count)
    const selectedStillExists = people.value.some((person) => person.id === selectedPersonId.value)
    if (!selectedStillExists) {
      selectedPersonId.value = people.value[0]?.id || null
    }
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, '读取人物库失败'))
  } finally {
    if (showBusy) peopleLoading.value = false
  }
}

async function loadCandidates(showBusy = true) {
  if (!selectedPersonId.value) {
    candidates.value = []
    selectedLabels.value = []
    return
  }

  if (showBusy) candidateLoading.value = true
  try {
    candidates.value = await listPersonCorrectionCandidates(selectedPersonId.value, 120)
    selectedLabels.value = selectedLabels.value.filter((label) =>
      candidates.value.some((candidate) => candidate.label === label),
    )
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, '读取校正候选失败'))
  } finally {
    if (showBusy) candidateLoading.value = false
  }
}

async function selectPerson(person: PersonProfile) {
  selectedPersonId.value = person.id
  clearSelection()
  await loadCandidates()
}

async function handleApply(action: 'bind' | 'unbind') {
  if (!selectedPerson.value) {
    ElMessage.warning('请先选择人物档案')
    return
  }
  if (!selectedLabels.value.length) {
    ElMessage.warning('请先选择至少一个人脸簇')
    return
  }

  actionLoading.value = true
  try {
    const result = await applyPersonClusterCorrection(
      selectedPerson.value.id,
      action,
      selectedLabels.value,
    )
    await Promise.all([loadPeople(false), loadCandidates(false)])
    clearSelection()
    emitWorkspaceRefresh()
    ElMessage.success(
      action === 'bind'
        ? `已批量绑定 ${formatCount(result.updated_cluster_count)} 个人脸簇`
        : `已批量解绑 ${formatCount(result.updated_cluster_count)} 个人脸簇`,
    )
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, '批量校正失败'))
  } finally {
    actionLoading.value = false
  }
}

async function handleRefresh() {
  await Promise.all([loadPeople(), loadCandidates(false)])
  ElMessage.success('校正候选已刷新')
}

onMounted(async () => {
  await loadPeople()
  await loadCandidates()
})
</script>

<template>
  <div class="page-stack">
    <section class="page-section fade-in">
      <div class="section-head">
        <h4>批量人物标注校正</h4>
        <span class="section-tip">
          以人脸簇为粒度，批量把误识别样本重新绑定到指定人物，或把错误绑定的一组人脸簇一次性解绑。
        </span>
      </div>
    </section>

    <section class="page-section fade-in">
      <div class="correction-layout">
        <aside class="soft-panel correction-sidebar">
          <div class="section-head compact-head">
            <h4>人物档案</h4>
            <span class="section-tip">{{ formatCount(people.length) }} 个档案</span>
          </div>

          <div v-if="people.length" class="correction-person-list">
            <button
              v-for="person in people"
              :key="person.id"
              type="button"
              class="correction-person-item"
              :class="{ active: selectedPersonId === person.id }"
              @click="selectPerson(person)"
            >
              <div class="correction-person-copy">
                <strong>{{ person.name }}</strong>
                <small>{{ person.linked_cluster_count }} 个人脸簇</small>
                <span>{{ person.linked_photo_count }} 张相关图片</span>
              </div>
            </button>
          </div>

          <el-empty
            v-else
            :description="peopleLoading ? '正在读取人物档案...' : '还没有可校正的人物档案'"
          />
        </aside>

        <div class="correction-main">
          <section class="glass-panel">
            <div class="section-head">
              <h4>{{ selectedPerson?.name || '选择人物后开始校正' }}</h4>
              <span class="section-tip">
                当前展示的是与所选人物最接近的人脸簇，以及已经绑定到该人物的人脸簇。
              </span>
            </div>

            <div class="tag-cloud" v-if="selectedPerson">
              <span class="photo-tag">{{ selectedPerson.sample_count }} 张参考图</span>
              <span class="photo-tag">{{ selectedPerson.linked_cluster_count }} 个人脸簇</span>
              <span class="photo-tag">{{ selectedPerson.linked_photo_count }} 张识别图片</span>
              <span class="photo-tag">已选择 {{ selectedCount }} 个候选</span>
            </div>

            <div class="correction-toolbar">
              <el-input v-model="keyword" placeholder="搜索簇名、当前人物或标签" clearable />
              <el-slider
                v-model="minScore"
                :min="0"
                :max="1"
                :step="0.01"
                show-input
                input-size="small"
              />
              <el-segmented
                v-model="filterMode"
                :options="[
                  { label: '推荐', value: 'recommended' },
                  { label: '全部', value: 'all' },
                  { label: '已绑定', value: 'linked' },
                  { label: '未绑定', value: 'unlinked' },
                  { label: '待改派', value: 'reassign' },
                ]"
              />
            </div>

            <div class="correction-actions">
              <el-button plain :icon="Check" @click="selectRecommended">选择推荐项</el-button>
              <el-button plain @click="clearSelection">清空选择</el-button>
              <el-button plain :icon="Refresh" :loading="candidateLoading" @click="handleRefresh">
                刷新候选
              </el-button>
              <el-button
                type="primary"
                :loading="actionLoading"
                :disabled="!selectedLabels.length"
                @click="handleApply('bind')"
              >
                批量绑定到当前人物
              </el-button>
              <el-button
                type="danger"
                plain
                :loading="actionLoading"
                :disabled="!selectedLabels.length"
                @click="handleApply('unbind')"
              >
                从当前人物批量解绑
              </el-button>
            </div>
          </section>

          <section class="page-section inner-section">
            <div class="section-head">
              <h4>校正候选</h4>
              <span class="section-tip">
                推荐项表示该簇与当前人物相似度高，且与其他人物拉开了足够 margin。
              </span>
            </div>

            <div v-if="filteredCandidates.length" class="candidate-grid">
              <article
                v-for="candidate in filteredCandidates"
                :key="candidate.label"
                class="candidate-card"
                :class="{ selected: isSelected(candidate.label) }"
              >
                <label class="candidate-head">
                  <el-checkbox
                    :model-value="isSelected(candidate.label)"
                    @update:model-value="toggleSelection(candidate.label, Boolean($event))"
                  />
                  <div class="candidate-head__copy">
                    <strong>{{ candidate.display_name || '未命名人脸簇' }}</strong>
                    <small>{{ candidate.label }}</small>
                  </div>
                </label>

                <div class="candidate-thumb">
                  <img
                    v-if="candidate.example_photo_id"
                    :src="examplePhotoUrl(candidate)"
                    :alt="candidate.display_name || candidate.label"
                  />
                  <div v-else class="candidate-empty">
                    <el-icon><UserFilled /></el-icon>
                  </div>
                </div>

                <div class="tag-cloud">
                  <span class="photo-tag">相似度 {{ candidate.score.toFixed(3) }}</span>
                  <span class="photo-tag">margin {{ candidate.margin.toFixed(3) }}</span>
                  <span class="photo-tag">{{ candidate.photo_count }} 张图</span>
                  <span v-if="candidate.recommended" class="photo-tag accent-tag">推荐</span>
                  <span v-if="candidate.linked_to_selected_person" class="photo-tag success-tag">
                    已绑定当前人物
                  </span>
                </div>

                <div class="candidate-meta">
                  <span>
                    当前绑定：
                    {{ candidate.current_person_name || '未绑定' }}
                  </span>
                  <span>竞争分数：{{ candidate.competitor_score.toFixed(3) }}</span>
                </div>
              </article>
            </div>

            <el-empty
              v-else
              :description="
                candidateLoading
                  ? '正在计算校正候选...'
                  : selectedPerson
                    ? '当前筛选条件下没有候选结果'
                    : '请先在左侧选择一个人物档案'
              "
            />
          </section>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.correction-layout {
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  gap: 18px;
}

.correction-sidebar {
  min-height: 560px;
}

.compact-head {
  margin-bottom: 12px;
}

.correction-person-list {
  display: grid;
  gap: 12px;
}

.correction-person-item {
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.03);
  padding: 14px;
  text-align: left;
  color: inherit;
  transition:
    transform 180ms ease,
    border-color 180ms ease,
    background 180ms ease;
}

.correction-person-item:hover,
.correction-person-item.active {
  transform: translateY(-1px);
  border-color: rgba(255, 184, 121, 0.28);
  background: rgba(255, 165, 90, 0.08);
}

.correction-person-copy {
  display: grid;
  gap: 6px;
}

.correction-person-copy small,
.correction-person-copy span,
.candidate-meta {
  color: var(--muted);
}

.correction-main {
  display: grid;
  gap: 18px;
}

.correction-toolbar {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(260px, 360px) auto;
  gap: 12px;
  margin-top: 18px;
}

.correction-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 14px;
}

.inner-section {
  padding: 0;
}

.candidate-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 14px;
}

.candidate-card {
  display: grid;
  gap: 12px;
  padding: 14px;
  border-radius: 20px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.03);
  transition:
    transform 180ms ease,
    border-color 180ms ease,
    background 180ms ease;
}

.candidate-card.selected {
  border-color: rgba(255, 184, 121, 0.32);
  background: rgba(255, 184, 121, 0.08);
}

.candidate-head {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 10px;
  align-items: start;
}

.candidate-head__copy {
  display: grid;
  gap: 4px;
}

.candidate-head__copy small {
  color: var(--muted);
}

.candidate-thumb {
  aspect-ratio: 1 / 1;
  border-radius: 18px;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.04);
}

.candidate-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.candidate-empty {
  width: 100%;
  height: 100%;
  display: grid;
  place-items: center;
  color: var(--muted);
}

.candidate-meta {
  display: grid;
  gap: 6px;
}

.accent-tag {
  background: rgba(255, 184, 121, 0.12);
}

.success-tag {
  background: rgba(112, 214, 171, 0.12);
}

@media (max-width: 1100px) {
  .correction-layout {
    grid-template-columns: 1fr;
  }

  .correction-toolbar {
    grid-template-columns: 1fr;
  }
}
</style>
