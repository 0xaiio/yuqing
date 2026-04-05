<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { Refresh, Setting } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

import { getFaceTuning, previewFaceTuning, saveFaceTuning } from '../services/api'
import type { FaceThresholds, FaceTuningBand, FaceTuningBundle } from '../types'
import { formatCount, resolveErrorMessage } from '../utils/format'

const bundle = ref<FaceTuningBundle | null>(null)
const loading = ref(false)
const previewLoading = ref(false)
const saving = ref(false)
const rebuilding = ref(false)

const form = reactive<FaceThresholds>({
  face_detection_confidence_threshold: 0.45,
  face_detection_nms_threshold: 0.4,
  face_cluster_similarity_threshold: 0.5,
  person_recognition_similarity_threshold: 0.52,
})

const preview = computed(() => bundle.value?.preview || null)
const dirty = computed(() => {
  if (!bundle.value) return false
  return JSON.stringify(form) !== JSON.stringify(bundle.value.thresholds)
})

const clusterBandMax = computed(() =>
  Math.max(1, ...((preview.value?.cluster_similarity_bands || []).map((item) => item.count) || [1])),
)
const personBandMax = computed(() =>
  Math.max(1, ...((preview.value?.person_score_bands || []).map((item) => item.count) || [1])),
)

function assignThresholds(nextValues: FaceThresholds) {
  form.face_detection_confidence_threshold = nextValues.face_detection_confidence_threshold
  form.face_detection_nms_threshold = nextValues.face_detection_nms_threshold
  form.face_cluster_similarity_threshold = nextValues.face_cluster_similarity_threshold
  form.person_recognition_similarity_threshold = nextValues.person_recognition_similarity_threshold
}

function bandPercent(band: FaceTuningBand, maxValue: number): number {
  return Math.round((band.count / Math.max(maxValue, 1)) * 100)
}

function emitWorkspaceRefresh() {
  window.dispatchEvent(new Event('workspace:refresh'))
}

async function loadTuning(showBusy = true) {
  if (showBusy) loading.value = true
  try {
    const response = await getFaceTuning()
    bundle.value = response
    assignThresholds(response.thresholds)
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, '读取调参信息失败'))
  } finally {
    if (showBusy) loading.value = false
  }
}

async function handlePreview() {
  previewLoading.value = true
  try {
    bundle.value = await previewFaceTuning({ ...form })
    ElMessage.success('阈值预览已刷新')
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, '刷新阈值预览失败'))
  } finally {
    previewLoading.value = false
  }
}

function handleResetDefaults() {
  if (!bundle.value) return
  assignThresholds(bundle.value.defaults)
  void handlePreview()
}

async function handleSave(rebuildIndex = false) {
  if (rebuildIndex) {
    rebuilding.value = true
  } else {
    saving.value = true
  }

  try {
    const response = await saveFaceTuning({ ...form }, rebuildIndex)
    bundle.value = response
    assignThresholds(response.thresholds)
    emitWorkspaceRefresh()
    ElMessage.success(rebuildIndex ? '阈值已保存并完成索引重建' : '阈值已保存')
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, '保存阈值失败'))
  } finally {
    saving.value = false
    rebuilding.value = false
  }
}

onMounted(() => {
  void loadTuning()
})
</script>

<template>
  <div class="page-stack">
    <section class="page-section fade-in">
      <div class="section-head">
        <h4>阈值可视化调参</h4>
        <span class="section-tip">
          一边调整人物识别和聚类阈值，一边查看当前图库上“命中数、模糊区间、边界样本”的实时预览。
        </span>
      </div>

      <div class="tuning-actions">
        <el-button plain :icon="Refresh" :loading="previewLoading" @click="handlePreview">
          刷新预览
        </el-button>
        <el-button plain @click="handleResetDefaults">恢复默认</el-button>
        <el-button type="primary" :disabled="!dirty" :loading="saving" @click="handleSave(false)">
          保存阈值
        </el-button>
        <el-button
          type="warning"
          :disabled="!dirty"
          :loading="rebuilding"
          @click="handleSave(true)"
        >
          保存并重建索引
        </el-button>
      </div>
    </section>

    <section class="page-section fade-in">
      <div class="tuning-grid">
        <article class="glass-panel tuning-card">
          <div class="section-head compact-head">
            <h4>人物识别阈值</h4>
            <span class="section-tip">{{ form.person_recognition_similarity_threshold.toFixed(3) }}</span>
          </div>
          <el-slider
            v-model="form.person_recognition_similarity_threshold"
            :min="0.2"
            :max="0.95"
            :step="0.005"
            show-input
          />
          <p class="tuning-copy">越高越保守，误识别更少，但会漏掉模糊、侧脸或低清样本。</p>
        </article>

        <article class="glass-panel tuning-card">
          <div class="section-head compact-head">
            <h4>人脸聚类阈值</h4>
            <span class="section-tip">{{ form.face_cluster_similarity_threshold.toFixed(3) }}</span>
          </div>
          <el-slider
            v-model="form.face_cluster_similarity_threshold"
            :min="0.2"
            :max="0.95"
            :step="0.005"
            show-input
          />
          <p class="tuning-copy">越高越倾向拆分更多簇，越低越容易把相似人脸合并在一起。</p>
        </article>

        <article class="glass-panel tuning-card">
          <div class="section-head compact-head">
            <h4>检测置信度</h4>
            <span class="section-tip">{{ form.face_detection_confidence_threshold.toFixed(3) }}</span>
          </div>
          <el-slider
            v-model="form.face_detection_confidence_threshold"
            :min="0.1"
            :max="0.95"
            :step="0.01"
            show-input
          />
          <p class="tuning-copy">主要影响重建时哪些人脸框会被保留；建议与重建索引配合使用。</p>
        </article>

        <article class="glass-panel tuning-card">
          <div class="section-head compact-head">
            <h4>NMS 阈值</h4>
            <span class="section-tip">{{ form.face_detection_nms_threshold.toFixed(3) }}</span>
          </div>
          <el-slider
            v-model="form.face_detection_nms_threshold"
            :min="0.1"
            :max="0.95"
            :step="0.01"
            show-input
          />
          <p class="tuning-copy">控制相邻检测框的合并力度；越低越容易抑制重叠框。</p>
        </article>
      </div>
    </section>

    <section class="metric-grid">
      <article class="stat-card">
        <div class="stat-card__icon">
          <el-icon><Setting /></el-icon>
        </div>
        <div class="stat-card__copy">
          <strong>{{ preview ? formatCount(preview.total_clusters) : '0' }}</strong>
          <span>总人脸簇</span>
          <small>预览样本 {{ preview ? formatCount(preview.preview_cluster_count) : '0' }}</small>
        </div>
      </article>

      <article class="stat-card">
        <div class="stat-card__icon">
          <el-icon><Setting /></el-icon>
        </div>
        <div class="stat-card__copy">
          <strong>{{ preview ? formatCount(preview.person_candidate_count) : '0' }}</strong>
          <span>人物命中候选</span>
          <small>模糊命中 {{ preview ? formatCount(preview.ambiguous_person_match_count) : '0' }}</small>
        </div>
      </article>

      <article class="stat-card">
        <div class="stat-card__icon">
          <el-icon><Setting /></el-icon>
        </div>
        <div class="stat-card__copy">
          <strong>{{ preview ? formatCount(preview.merge_candidate_count) : '0' }}</strong>
          <span>潜在聚类合并</span>
          <small>模糊边界 {{ preview ? formatCount(preview.ambiguous_merge_count) : '0' }}</small>
        </div>
      </article>

      <article class="stat-card">
        <div class="stat-card__icon">
          <el-icon><Setting /></el-icon>
        </div>
        <div class="stat-card__copy">
          <strong>{{ preview ? preview.best_person_mean_score.toFixed(3) : '0.000' }}</strong>
          <span>平均最佳人物分数</span>
          <small>最近邻均值 {{ preview ? preview.nearest_neighbor_mean_score.toFixed(3) : '0.000' }}</small>
        </div>
      </article>
    </section>

    <section class="page-section fade-in">
      <div class="tuning-visual-grid">
        <article class="glass-panel">
          <div class="section-head compact-head">
            <h4>聚类分数分布</h4>
            <span class="section-tip">基于每个人脸簇与最近邻簇的相似度</span>
          </div>
          <div v-if="preview" class="band-stack">
            <div v-for="band in preview.cluster_similarity_bands" :key="band.label" class="band-row">
              <div class="band-row__copy">
                <strong>{{ band.label }}</strong>
                <span>{{ formatCount(band.count) }} 个</span>
              </div>
              <el-progress :percentage="bandPercent(band, clusterBandMax)" :show-text="false" />
            </div>
          </div>
          <el-empty v-else :description="loading ? '正在计算分布...' : '暂无预览数据'" />
        </article>

        <article class="glass-panel">
          <div class="section-head compact-head">
            <h4>人物匹配分布</h4>
            <span class="section-tip">基于每个人脸簇对应的最佳人物分数</span>
          </div>
          <div v-if="preview" class="band-stack">
            <div v-for="band in preview.person_score_bands" :key="band.label" class="band-row">
              <div class="band-row__copy">
                <strong>{{ band.label }}</strong>
                <span>{{ formatCount(band.count) }} 个</span>
              </div>
              <el-progress :percentage="bandPercent(band, personBandMax)" :show-text="false" />
            </div>
          </div>
          <el-empty v-else :description="loading ? '正在计算分布...' : '暂无预览数据'" />
        </article>
      </div>
    </section>

    <section class="page-section fade-in">
      <div class="tuning-table-grid">
        <article class="glass-panel">
          <div class="section-head compact-head">
            <h4>聚类边界样本</h4>
            <span class="section-tip">越靠前越接近当前聚类阈值</span>
          </div>
          <el-table v-if="preview" :data="preview.borderline_merges" stripe>
            <el-table-column prop="label" label="簇标签" min-width="120" />
            <el-table-column prop="display_name" label="当前名称" min-width="120" />
            <el-table-column prop="neighbor_label" label="最近邻簇" min-width="120" />
            <el-table-column label="分数" min-width="90">
              <template #default="{ row }">
                {{ row.score.toFixed(3) }}
              </template>
            </el-table-column>
            <el-table-column label="张数" min-width="80">
              <template #default="{ row }">
                {{ formatCount(row.photo_count) }}
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-else :description="loading ? '正在读取边界样本...' : '暂无边界样本'" />
        </article>

        <article class="glass-panel">
          <div class="section-head compact-head">
            <h4>人物边界样本</h4>
            <span class="section-tip">越靠前越接近当前人物识别阈值</span>
          </div>
          <el-table v-if="preview" :data="preview.borderline_person_matches" stripe>
            <el-table-column prop="label" label="簇标签" min-width="120" />
            <el-table-column prop="best_person_name" label="最佳人物" min-width="120" />
            <el-table-column prop="current_person_name" label="当前绑定" min-width="120" />
            <el-table-column label="分数" min-width="90">
              <template #default="{ row }">
                {{ row.score.toFixed(3) }}
              </template>
            </el-table-column>
            <el-table-column label="margin" min-width="90">
              <template #default="{ row }">
                {{ row.margin.toFixed(3) }}
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-else :description="loading ? '正在读取边界样本...' : '暂无边界样本'" />
        </article>
      </div>
    </section>

    <section class="page-section fade-in">
      <div class="glass-panel note-panel">
        <div class="section-head compact-head">
          <h4>调参提示</h4>
          <span class="section-tip">这些说明会跟着后端返回的预览一起变化</span>
        </div>
        <ul v-if="preview" class="note-list">
          <li v-for="note in preview.notes" :key="note">{{ note }}</li>
        </ul>
        <el-empty v-else :description="loading ? '正在读取提示...' : '暂无提示'" />
      </div>
    </section>
  </div>
</template>

<style scoped>
.tuning-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 16px;
}

.tuning-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.tuning-card {
  display: grid;
  gap: 12px;
}

.compact-head {
  margin-bottom: 8px;
}

.tuning-copy {
  margin: 0;
  color: var(--muted);
  line-height: 1.6;
}

.stat-card {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 12px;
  padding: 18px;
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
}

.stat-card__icon {
  width: 48px;
  height: 48px;
  border-radius: 16px;
  display: grid;
  place-items: center;
  background: rgba(255, 184, 121, 0.12);
}

.stat-card__copy {
  display: grid;
  gap: 6px;
}

.stat-card__copy strong {
  font-size: 28px;
}

.stat-card__copy span,
.stat-card__copy small {
  color: var(--muted);
}

.tuning-visual-grid,
.tuning-table-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.band-stack,
.note-list {
  display: grid;
  gap: 12px;
}

.band-row {
  display: grid;
  gap: 8px;
}

.band-row__copy {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.band-row__copy span {
  color: var(--muted);
}

.note-panel {
  display: grid;
  gap: 12px;
}

.note-list {
  margin: 0;
  padding-left: 18px;
  color: var(--muted);
}

@media (max-width: 1100px) {
  .tuning-grid,
  .tuning-visual-grid,
  .tuning-table-grid {
    grid-template-columns: 1fr;
  }
}
</style>
