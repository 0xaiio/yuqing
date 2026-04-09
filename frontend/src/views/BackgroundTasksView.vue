<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'

import StatCard from '../components/StatCard.vue'
import { listBackgroundTasks, startVideoReanalysisAllTask } from '../services/api'
import type { BackgroundTask } from '../types'
import {
  backgroundTaskProgress,
  formatCount,
  formatDateTime,
  resolveErrorMessage,
  taskStatusLabel,
  taskStatusTagType,
} from '../utils/format'

const tasks = ref<BackgroundTask[]>([])
const loading = ref(false)
const starting = ref(false)

const runningCount = computed(() =>
  tasks.value.filter((task) => task.status === 'queued' || task.status === 'running').length,
)
const completedCount = computed(() => tasks.value.filter((task) => task.status === 'completed').length)
const failedCount = computed(() => tasks.value.filter((task) => task.status === 'failed').length)
const processedTotal = computed(() =>
  tasks.value.reduce((sum, task) => sum + task.completed_items + task.failed_items, 0),
)
const hasRunningVideoReanalysis = computed(() =>
  tasks.value.some(
    (task) =>
      task.task_type === 'video_reanalyze_all' &&
      (task.status === 'queued' || task.status === 'running'),
  ),
)

let refreshTimer: number | undefined

async function loadTasks(showBusy = true) {
  if (showBusy) loading.value = true
  try {
    tasks.value = await listBackgroundTasks(120)
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, '读取后台任务失败'))
  } finally {
    if (showBusy) loading.value = false
  }
}

async function handleStartVideoReanalysisAll() {
  starting.value = true
  try {
    const task = await startVideoReanalysisAllTask()
    await loadTasks(false)
    window.dispatchEvent(new Event('workspace:refresh'))
    if (task.status === 'queued' || task.status === 'running') {
      ElMessage.success('已开始批量重分析全部视频')
    } else {
      ElMessage.success('已返回现有任务状态')
    }
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, '启动批量视频重分析失败'))
  } finally {
    starting.value = false
  }
}

function handleWorkspaceRefresh() {
  void loadTasks(false)
}

onMounted(() => {
  void loadTasks()
  window.addEventListener('workspace:refresh', handleWorkspaceRefresh)
  refreshTimer = window.setInterval(() => {
    void loadTasks(false)
  }, 8000)
})

onBeforeUnmount(() => {
  window.removeEventListener('workspace:refresh', handleWorkspaceRefresh)
  if (refreshTimer) {
    window.clearInterval(refreshTimer)
  }
})
</script>

<template>
  <div class="page-stack">
    <section class="page-section fade-in">
      <div class="section-head">
        <h4>后台任务工作台</h4>
        <span class="section-tip">用于批量重分析全部视频，并持续观察进度、失败数和完成状态。</span>
      </div>

      <div class="metric-grid compact-grid">
        <StatCard tone="amber" label="运行中任务" :value="formatCount(runningCount)" helper="排队中和执行中的任务总数" />
        <StatCard tone="teal" label="已完成任务" :value="formatCount(completedCount)" helper="完整跑完的后台批处理" />
        <StatCard tone="coral" label="失败任务" :value="formatCount(failedCount)" helper="需要检查模型或视频文件的任务" />
        <StatCard tone="slate" label="累计处理视频" :value="formatCount(processedTotal)" helper="已处理完成或失败的视频数" />
      </div>
    </section>

    <section class="page-section fade-in">
      <div class="section-head">
        <h4>批量视频重分析</h4>
        <span class="section-tip">会使用当前最新的视频人物识别链路重新处理库中全部视频。</span>
      </div>

      <div class="task-action-card">
        <div class="task-action-copy">
          <strong>重新抽帧、重新做人脸检测识别、重新生成人物标签与视频向量</strong>
          <p>适合在升级视频人物识别算法后统一刷新历史数据。CPU 环境下会比较耗时，建议让任务在后台持续运行。</p>
        </div>
        <el-button
          type="primary"
          :loading="starting"
          :disabled="hasRunningVideoReanalysis"
          @click="handleStartVideoReanalysisAll"
        >
          {{ hasRunningVideoReanalysis ? '已有任务执行中' : '批量重分析全部视频' }}
        </el-button>
      </div>
    </section>

    <section class="page-section fade-in">
      <div class="section-head">
        <h4>任务明细</h4>
        <span class="section-tip">{{ tasks.length }} 条记录</span>
      </div>

      <el-table v-loading="loading" :data="tasks" stripe empty-text="还没有后台任务记录">
        <el-table-column prop="title" label="任务" min-width="220" />

        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="taskStatusTagType(row.status)" effect="dark">
              {{ taskStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="进度" min-width="240">
          <template #default="{ row }">
            <el-progress :percentage="backgroundTaskProgress(row)" :stroke-width="10" :show-text="false" />
            <div class="job-progress-copy">
              已完成 {{ formatCount(row.completed_items) }} / 总计 {{ formatCount(row.total_items) }}
              <span v-if="row.failed_items">，失败 {{ formatCount(row.failed_items) }}</span>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="创建时间" min-width="180">
          <template #default="{ row }">
            {{ formatDateTime(row.created_at) }}
          </template>
        </el-table-column>

        <el-table-column label="结束时间" min-width="180">
          <template #default="{ row }">
            {{ formatDateTime(row.finished_at) }}
          </template>
        </el-table-column>

        <el-table-column label="错误信息" min-width="260">
          <template #default="{ row }">
            <span class="error-copy">{{ row.error_message || '无' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </section>
  </div>
</template>

<style scoped>
.task-action-card {
  display: flex;
  justify-content: space-between;
  gap: 18px;
  align-items: center;
  padding: 18px 20px;
  border-radius: 22px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.03);
}

.task-action-copy {
  display: grid;
  gap: 8px;
}

.task-action-copy p {
  margin: 0;
  color: var(--muted);
  line-height: 1.7;
}

.job-progress-copy {
  color: var(--muted);
  font-size: 13px;
  margin-top: 8px;
}

.error-copy {
  color: var(--muted);
  word-break: break-word;
}

@media (max-width: 860px) {
  .task-action-card {
    display: grid;
  }
}
</style>
