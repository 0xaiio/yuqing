<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'

import StatCard from '../components/StatCard.vue'
import { listImportJobs } from '../services/api'
import type { ImportJob } from '../types'
import {
  formatCount,
  formatDateTime,
  jobProgress,
  jobStatusLabel,
  jobStatusTagType,
  resolveErrorMessage,
} from '../utils/format'

const jobs = ref<ImportJob[]>([])
const loading = ref(false)

const completedCount = computed(() => jobs.value.filter((job) => job.status === 'completed').length)
const failedCount = computed(() => jobs.value.filter((job) => job.status === 'failed').length)
const importedTotal = computed(() => jobs.value.reduce((sum, job) => sum + job.imported_count, 0))
const duplicateTotal = computed(() => jobs.value.reduce((sum, job) => sum + job.duplicate_count, 0))

let refreshTimer: number | undefined

async function loadJobs(showBusy = true) {
  if (showBusy) loading.value = true

  try {
    jobs.value = await listImportJobs(200)
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, '读取导入任务失败。'))
  } finally {
    if (showBusy) loading.value = false
  }
}

function handleWorkspaceRefresh() {
  void loadJobs(false)
}

onMounted(() => {
  void loadJobs()
  window.addEventListener('workspace:refresh', handleWorkspaceRefresh)
  refreshTimer = window.setInterval(() => {
    void loadJobs(false)
  }, 15000)
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
        <h4>导入批次概览</h4>
        <span class="section-tip">当前导入链路为同步执行，监听任务会在后台队列里顺序处理。</span>
      </div>

      <div class="metric-grid compact-grid">
        <StatCard tone="teal" label="成功批次" :value="formatCount(completedCount)" helper="导入流程已完成" />
        <StatCard tone="coral" label="失败批次" :value="formatCount(failedCount)" helper="需要检查路径或文件权限" />
        <StatCard tone="amber" label="累计导入" :value="formatCount(importedTotal)" helper="真正新增入库的图片" />
        <StatCard tone="slate" label="累计去重" :value="formatCount(duplicateTotal)" helper="被判定为重复的图片" />
      </div>
    </section>

    <section class="page-section fade-in">
      <div class="section-head">
        <h4>任务明细</h4>
        <span class="section-tip">{{ jobs.length }} 条记录</span>
      </div>

      <el-table
        v-loading="loading"
        :data="jobs"
        stripe
        class="jobs-table"
        empty-text="还没有导入任务记录"
      >
        <el-table-column prop="source_name" label="来源" min-width="180" />

        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="jobStatusTagType(row.status)" effect="dark">
              {{ jobStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="进度" min-width="220">
          <template #default="{ row }">
            <el-progress
              :percentage="jobProgress(row)"
              :stroke-width="10"
              :show-text="false"
            />
            <div class="job-progress-copy">
              扫描 {{ formatCount(row.scanned_count) }} / 导入 {{ formatCount(row.imported_count) }}
            </div>
          </template>
        </el-table-column>

        <el-table-column label="去重" width="100" align="center">
          <template #default="{ row }">
            {{ formatCount(row.duplicate_count) }}
          </template>
        </el-table-column>

        <el-table-column label="创建时间" min-width="180">
          <template #default="{ row }">
            {{ formatDateTime(row.created_at) }}
          </template>
        </el-table-column>

        <el-table-column label="错误信息" min-width="220">
          <template #default="{ row }">
            <span class="error-copy">{{ row.error_message || '—' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </section>
  </div>
</template>
