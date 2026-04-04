<script setup lang="ts">
import { computed, ref } from 'vue'
import { Document, PictureFilled, User } from '@element-plus/icons-vue'

import { getPhotoAssetUrl } from '../services/api'
import type { Photo } from '../types'
import { formatDateTime, sourceKindLabel } from '../utils/format'

const props = withDefaults(
  defineProps<{
    photo: Photo
    score?: number | null
  }>(),
  {
    score: null,
  },
)

const emit = defineEmits<{
  select: []
}>()

const failed = ref(false)

const assetUrl = computed(() => getPhotoAssetUrl(props.photo.id))
const visualTags = computed(() =>
  [
    ...props.photo.people.map((item) => `人物 · ${item}`),
    ...props.photo.scene_tags.map((item) => `场景 · ${item}`),
    ...props.photo.object_tags.map((item) => `物体 · ${item}`),
  ].slice(0, 6),
)
const summary = computed(
  () => props.photo.caption || props.photo.ocr_text || '图片已导入，等待更完整的 AI 分析结果。',
)

function handleSelect() {
  emit('select')
}
</script>

<template>
  <article
    class="photo-card fade-in"
    role="button"
    tabindex="0"
    @click="handleSelect"
    @keydown.enter.prevent="handleSelect"
    @keydown.space.prevent="handleSelect"
  >
    <div class="photo-card__media">
      <img
        v-if="!failed"
        :src="assetUrl"
        :alt="photo.caption || `photo-${photo.id}`"
        loading="lazy"
        @error="failed = true"
      />
      <div v-else class="photo-card__fallback">
        <el-icon><PictureFilled /></el-icon>
        <span>预览暂不可用</span>
      </div>
      <span v-if="score !== null" class="photo-card__score">匹配度 {{ score.toFixed(2) }}</span>
    </div>

    <div class="photo-card__body">
      <div class="photo-card__meta">
        <span>{{ sourceKindLabel(photo.source_kind) }}</span>
        <span>{{ formatDateTime(photo.taken_at || photo.created_at) }}</span>
      </div>

      <h3 class="photo-card__title">
        {{ photo.source_name || '未命名来源' }}
      </h3>

      <p class="photo-card__summary">{{ summary }}</p>

      <div class="photo-card__flags">
        <span v-if="photo.face_count" class="photo-card__flag">
          <el-icon><User /></el-icon>
          {{ photo.face_count }} 张人脸
        </span>
        <span v-if="photo.vector_ready" class="photo-card__flag">
          向量就绪
        </span>
      </div>

      <div v-if="visualTags.length" class="tag-cloud">
        <span v-for="tag in visualTags" :key="tag" class="photo-tag">
          {{ tag }}
        </span>
      </div>

      <div v-if="photo.ocr_text" class="photo-card__ocr">
        <el-icon><Document /></el-icon>
        <span>{{ photo.ocr_text }}</span>
      </div>
    </div>
  </article>
</template>

<style scoped>
.photo-card {
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

.photo-card:hover,
.photo-card:focus-visible {
  transform: translateY(-2px);
  border-color: rgba(255, 176, 112, 0.26);
  outline: none;
}

.photo-card__media {
  position: relative;
  aspect-ratio: 4 / 3;
  background:
    radial-gradient(circle at top, rgba(255, 179, 92, 0.24), transparent 48%),
    linear-gradient(135deg, rgba(28, 40, 55, 0.98), rgba(16, 25, 37, 0.92));
}

.photo-card__media img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.photo-card__fallback {
  position: absolute;
  inset: 0;
  display: grid;
  place-content: center;
  gap: 10px;
  color: var(--muted);
}

.photo-card__fallback .el-icon {
  font-size: 32px;
  margin: 0 auto;
}

.photo-card__score {
  position: absolute;
  right: 16px;
  bottom: 16px;
  padding: 6px 12px;
  border-radius: 999px;
  background: rgba(7, 10, 14, 0.72);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #fff3d1;
  font-size: 12px;
  letter-spacing: 0.04em;
}

.photo-card__body {
  padding: 18px;
  display: grid;
  gap: 12px;
}

.photo-card__meta {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  color: var(--muted);
  font-size: 12px;
}

.photo-card__title {
  margin: 0;
  font-size: 18px;
}

.photo-card__summary {
  margin: 0;
  color: rgba(240, 243, 247, 0.84);
  line-height: 1.6;
}

.photo-card__flags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.photo-card__flag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.04);
  color: var(--muted);
  font-size: 12px;
}

.photo-card__ocr {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding-top: 4px;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.5;
}
</style>
