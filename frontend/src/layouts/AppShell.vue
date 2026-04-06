<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import {
  Brush,
  Camera,
  FolderOpened,
  Film,
  Operation,
  Refresh,
  Search,
  Setting,
  UploadFilled,
  UserFilled,
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { RouterLink, RouterView, useRoute } from 'vue-router'

import StatCard from '../components/StatCard.vue'
import { apiBaseUrl, getHealth, listPhotos, listSources, listVideos } from '../services/api'
import { formatCount } from '../utils/format'

const route = useRoute()
const loading = ref(true)
const backendOnline = ref(false)
const metrics = ref({
  sources: 0,
  photos: 0,
  videos: 0,
  queuedTasks: 0,
  watchers: 0,
})

const navItems = [
  { to: '/search', label: '图片搜索', caption: '自然语言、标签和以图搜图', icon: Search },
  { to: '/videos', label: '视频搜索', caption: '文本搜视频、相似视频与按人搜视频', icon: Film },
  { to: '/organize', label: '整理清理', caption: '删 thumb、低清晰度和低价值传输图', icon: Brush },
  { to: '/people', label: '人物库', caption: '上传参考图并做特定人物识别', icon: Camera },
  { to: '/people-corrections', label: '标注校正', caption: '批量修正人物绑定和误识别', icon: Operation },
  { to: '/faces', label: '人脸簇管理', caption: '命名聚类并查看相关图片和视频', icon: UserFilled },
  { to: '/face-tuning', label: '阈值调参', caption: '可视化预览并保存阈值', icon: Setting },
  { to: '/sources', label: '同步源配置', caption: '接入微信、QQ 和本地目录', icon: FolderOpened },
  { to: '/jobs', label: '导入任务', caption: '跟踪去重、归档与监听导入', icon: UploadFilled },
] as const

const currentTitle = computed(() => (route.meta.title as string) || '跨源媒体工作台')
const currentDescription = computed(
  () =>
    (route.meta.description as string) ||
    '把聊天图片、视频、本地图库和拍照内容统一纳入一个可搜索、可归档、可自动分析的桌面工作流。',
)

let refreshTimer: number | undefined

async function loadOverview(showBusy = true) {
  if (showBusy) loading.value = true

  try {
    const [health, sources, photos, videos] = await Promise.all([
      getHealth(),
      listSources(),
      listPhotos(200),
      listVideos(200),
    ])
    backendOnline.value = health.status === 'ok'
    metrics.value = {
      sources: sources.length,
      photos: photos.length,
      videos: videos.length,
      queuedTasks: health.queued_watch_tasks,
      watchers: health.active_watchers,
    }
  } catch {
    backendOnline.value = false
  } finally {
    if (showBusy) loading.value = false
  }
}

function triggerWorkspaceRefresh() {
  void loadOverview(false)
}

async function handleManualRefresh() {
  await loadOverview()
  ElMessage.success('工作台数据已刷新')
}

function isActive(path: string) {
  return route.path === path
}

onMounted(() => {
  void loadOverview()
  window.addEventListener('workspace:refresh', triggerWorkspaceRefresh)
  refreshTimer = window.setInterval(() => {
    void loadOverview(false)
  }, 20000)
})

onBeforeUnmount(() => {
  window.removeEventListener('workspace:refresh', triggerWorkspaceRefresh)
  if (refreshTimer) {
    window.clearInterval(refreshTimer)
  }
})
</script>

<template>
  <div class="app-shell">
    <aside class="shell-sidebar panel fade-in">
      <div class="brand-block">
        <div class="brand-mark">
          <el-icon><Camera /></el-icon>
        </div>
        <div>
          <p class="eyebrow">Cross Source Studio</p>
          <h1>跨源 AI 媒体智能管理</h1>
          <p class="sidebar-copy">面向图片和视频的一体化桌面工作台。</p>
        </div>
      </div>

      <nav class="shell-nav">
        <RouterLink
          v-for="item in navItems"
          :key="item.to"
          :to="item.to"
          class="nav-link"
          :class="{ active: isActive(item.to) }"
        >
          <span class="nav-link__icon">
            <component :is="item.icon" />
          </span>
          <span class="nav-link__body">
            <strong>{{ item.label }}</strong>
            <small>{{ item.caption }}</small>
          </span>
        </RouterLink>
      </nav>

      <div class="sidebar-footnote">
        <span class="status-pill" :class="{ offline: !backendOnline }">
          <i />
          {{ backendOnline ? '后端在线' : '等待后端' }}
        </span>
        <code class="endpoint-label">{{ apiBaseUrl }}</code>
      </div>
    </aside>

    <main class="shell-main">
      <section class="shell-hero panel fade-in">
        <div class="hero-copy">
          <p class="eyebrow">Desktop Shell</p>
          <h2>{{ currentTitle }}</h2>
          <p>{{ currentDescription }}</p>
        </div>

        <div class="hero-actions">
          <el-button class="ghost-button" :icon="Refresh" @click="handleManualRefresh">
            刷新概览
          </el-button>
        </div>
      </section>

      <section class="metric-grid">
        <StatCard
          tone="amber"
          label="同步源"
          :value="loading ? '...' : formatCount(metrics.sources)"
          helper="已接入目录数量"
        >
          <el-icon><FolderOpened /></el-icon>
        </StatCard>

        <StatCard
          tone="teal"
          label="图片规模"
          :value="loading ? '...' : formatCount(metrics.photos)"
          helper="当前已归档图片"
        >
          <el-icon><Camera /></el-icon>
        </StatCard>

        <StatCard
          tone="slate"
          label="视频规模"
          :value="loading ? '...' : formatCount(metrics.videos)"
          helper="当前已归档视频"
        >
          <el-icon><Film /></el-icon>
        </StatCard>

        <StatCard
          tone="coral"
          label="监听队列"
          :value="loading ? '...' : formatCount(metrics.queuedTasks)"
          helper="等待后台监听导入的任务"
        >
          <el-icon><UploadFilled /></el-icon>
        </StatCard>
      </section>

      <section class="shell-content">
        <RouterView />
      </section>
    </main>
  </div>
</template>
