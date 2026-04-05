<script setup lang="ts">
import { VideoPlay } from '@element-plus/icons-vue'
import { computed } from 'vue'

import { getVideoThumbnailUrl } from '../services/api'
import type { Video } from '../types'
import { formatDateTime, formatDuration, sourceKindLabel } from '../utils/format'

const props = defineProps<{
  video: Video
  score?: number
}>()

const emit = defineEmits<{
  select: [video: Video]
}>()

const thumbnailUrl = computed(() =>
  props.video.thumbnail_asset_url ? getVideoThumbnailUrl(props.video.id) : '',
)

const chipTexts = computed(() => [
  ...props.video.people.map((item) => `人物 · ${item}`),
  ...props.video.scene_tags.map((item) => `场景 · ${item}`),
  ...props.video.object_tags.map((item) => `物体 · ${item}`),
])

function openDetail() {
  emit('select', props.video)
}
</script>

<template>
  <article class="video-card fade-in" @click="openDetail">
    <div class="video-card__media">
      <img
        v-if="video.thumbnail_asset_url"
        :src="thumbnailUrl"
        :alt="video.caption || video.original_path"
      />
      <div v-else class="video-card__empty">
        <el-icon><VideoPlay /></el-icon>
      </div>

      <div class="video-overlay">
        <span class="video-badge">{{ formatDuration(video.duration_seconds) }}</span>
        <span v-if="typeof score === 'number' && score > 0" class="video-badge score-badge">
          {{ score.toFixed(3) }}
        </span>
      </div>
    </div>

    <div class="video-card__body">
      <div class="video-card__headline">
        <strong>{{ video.caption || '未生成视频摘要' }}</strong>
        <span>{{ sourceKindLabel(video.source_kind) }}</span>
      </div>

      <p class="video-card__meta">
        {{ video.frame_width || 0 }}×{{ video.frame_height || 0 }}
        · {{ video.fps ? video.fps.toFixed(1) : '0.0' }} fps
        · {{ video.sampled_frame_count }} 帧样本
      </p>

      <div class="tag-cloud">
        <span v-for="chip in chipTexts.slice(0, 6)" :key="chip" class="photo-tag">{{ chip }}</span>
      </div>

      <div class="video-card__foot">
        <span>{{ formatDateTime(video.created_at) }}</span>
        <span>{{ video.face_count }} 个人脸簇</span>
      </div>
    </div>
  </article>
</template>

<style scoped>
.video-card {
  overflow: hidden;
  border-radius: 26px;
  background: rgba(10, 16, 24, 0.82);
  border: 1px solid rgba(255, 255, 255, 0.12);
  box-shadow: 0 24px 52px rgba(4, 8, 15, 0.32);
  cursor: pointer;
  transition:
    transform 180ms ease,
    border-color 180ms ease;
}

.video-card:hover {
  transform: translateY(-2px);
  border-color: rgba(255, 176, 112, 0.26);
}

.video-card__media {
  position: relative;
  aspect-ratio: 16 / 9;
  background:
    radial-gradient(circle at top, rgba(255, 179, 92, 0.24), transparent 48%),
    linear-gradient(135deg, rgba(28, 40, 55, 0.98), rgba(16, 25, 37, 0.92));
}

.video-card__media img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.video-card__empty {
  position: absolute;
  inset: 0;
  display: grid;
  place-content: center;
  color: var(--muted);
}

.video-card__body {
  padding: 18px;
  display: grid;
  gap: 12px;
}

.video-card__headline {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.video-card__headline span,
.video-card__meta,
.video-card__foot {
  color: var(--muted);
  font-size: 13px;
}

.video-card__meta {
  margin: 0;
}

.video-card__foot {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.video-overlay {
  position: absolute;
  inset: auto 14px 14px 14px;
  display: flex;
  justify-content: space-between;
  gap: 8px;
}

.video-badge {
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(12, 16, 22, 0.72);
  color: #f3f6fb;
  font-size: 12px;
}

.score-badge {
  background: rgba(255, 173, 96, 0.78);
  color: #2d1908;
}
</style>
