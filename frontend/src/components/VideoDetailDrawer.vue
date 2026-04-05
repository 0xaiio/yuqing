<script setup lang="ts">
import { computed } from 'vue'
import { Search } from '@element-plus/icons-vue'

import { getVideoAssetUrl, getVideoThumbnailUrl } from '../services/api'
import type { Video } from '../types'
import { formatDateTime, formatDuration } from '../utils/format'

const props = defineProps<{
  modelValue: boolean
  video: Video | null
  findingSimilar: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  findSimilar: []
}>()

const open = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value),
})

const assetUrl = computed(() => (props.video ? getVideoAssetUrl(props.video.id) : ''))
const thumbnailUrl = computed(() => (props.video ? getVideoThumbnailUrl(props.video.id) : ''))

const tagTexts = computed(() => {
  if (!props.video) return []
  return [
    ...props.video.people.map((item) => `人物 · ${item}`),
    ...props.video.scene_tags.map((item) => `场景 · ${item}`),
    ...props.video.object_tags.map((item) => `物体 · ${item}`),
  ]
})
</script>

<template>
  <el-drawer v-model="open" size="680px" :with-header="false" destroy-on-close>
    <div v-if="video" class="video-drawer">
      <div class="video-drawer__hero">
        <video
          class="video-player"
          controls
          preload="metadata"
          :poster="video.thumbnail_asset_url ? thumbnailUrl : undefined"
          :src="assetUrl"
        />
      </div>

      <div class="video-drawer__section">
        <p class="eyebrow">Video Detail</p>
        <h3>{{ video.caption || '未生成视频摘要' }}</h3>
        <p class="drawer-copy">{{ video.ocr_text || '当前视频还没有 OCR 文本。' }}</p>
      </div>

      <div class="tag-cloud">
        <span v-for="tag in tagTexts" :key="tag" class="photo-tag">{{ tag }}</span>
      </div>

      <div class="video-meta-grid">
        <article class="video-meta-card">
          <span>时长</span>
          <strong>{{ formatDuration(video.duration_seconds) }}</strong>
        </article>
        <article class="video-meta-card">
          <span>分辨率</span>
          <strong>{{ video.frame_width || 0 }}×{{ video.frame_height || 0 }}</strong>
        </article>
        <article class="video-meta-card">
          <span>采样帧</span>
          <strong>{{ video.sampled_frame_count }}</strong>
        </article>
        <article class="video-meta-card">
          <span>更新时间</span>
          <strong>{{ formatDateTime(video.created_at) }}</strong>
        </article>
      </div>

      <div class="video-drawer__actions">
        <el-button type="primary" :icon="Search" :loading="findingSimilar" @click="emit('findSimilar')">
          查找相似视频
        </el-button>
      </div>
    </div>

    <el-empty v-else description="请选择一个视频查看详情" />
  </el-drawer>
</template>

<style scoped>
.video-drawer {
  display: grid;
  gap: 18px;
}

.video-player {
  width: 100%;
  border-radius: 20px;
  background: rgba(12, 16, 22, 0.88);
}

.video-drawer__section {
  display: grid;
  gap: 10px;
}

.drawer-copy {
  margin: 0;
  color: var(--muted);
  line-height: 1.7;
}

.video-meta-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.video-meta-card {
  display: grid;
  gap: 6px;
  padding: 14px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.08);
}

.video-meta-card span {
  color: var(--muted);
}

.video-drawer__actions {
  display: flex;
  gap: 12px;
}
</style>
