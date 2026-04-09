<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Delete, MagicStick, Search } from '@element-plus/icons-vue'

import { getVideoAssetUrl, getVideoThumbnailUrl } from '../services/api'
import type { Video, VideoPersonMoment } from '../types'
import { formatDateTime, formatDuration, sourceKindLabel } from '../utils/format'

const props = withDefaults(
  defineProps<{
    modelValue: boolean
    video: Video | null
    reanalyzing?: boolean
    findingSimilar: boolean
    deleting: boolean
  }>(),
  {
    reanalyzing: false,
  },
)

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  reanalyze: []
  findSimilar: []
  delete: []
}>()

const videoRef = ref<HTMLVideoElement | null>(null)
const activePersonName = ref('')
const activeMoment = ref<VideoPersonMoment | null>(null)

const open = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value),
})

const assetUrl = computed(() => (props.video ? getVideoAssetUrl(props.video.id) : ''))
const thumbnailUrl = computed(() => (props.video ? getVideoThumbnailUrl(props.video.id) : ''))
const tagTexts = computed(() => {
  if (!props.video) return []
  return [
    ...props.video.people.map((item) => `人物 / ${item}`),
    ...props.video.scene_tags.map((item) => `场景 / ${item}`),
    ...props.video.object_tags.map((item) => `物体 / ${item}`),
  ]
})

const groupedMoments = computed(() => {
  if (!props.video) return []

  const groups = new Map<string, VideoPersonMoment[]>()
  const ordered = [...props.video.person_moments].sort((left, right) => left.timestamp_seconds - right.timestamp_seconds)
  for (const moment of ordered) {
    const list = groups.get(moment.person_name) || []
    list.push(moment)
    groups.set(moment.person_name, list)
  }

  return Array.from(groups.entries()).map(([personName, moments]) => ({
    personName,
    moments,
  }))
})

const selectedMoments = computed(() => {
  if (!activePersonName.value) return []
  return groupedMoments.value.find((group) => group.personName === activePersonName.value)?.moments || []
})

const activeBoxStyle = computed(() => {
  if (!activeMoment.value || activeMoment.value.bbox.length < 4) return null
  const [left, top, width, height] = activeMoment.value.bbox
  return {
    left: `${left * 100}%`,
    top: `${top * 100}%`,
    width: `${width * 100}%`,
    height: `${height * 100}%`,
  }
})

watch(
  () => props.video,
  (video) => {
    activeMoment.value = null
    activePersonName.value = video?.person_moments[0]?.person_name || ''
  },
  { immediate: true },
)

watch(groupedMoments, (groups) => {
  if (!groups.length) {
    activePersonName.value = ''
    return
  }
  if (!groups.some((group) => group.personName === activePersonName.value)) {
    activePersonName.value = groups[0].personName
  }
})

function selectPerson(personName: string) {
  activePersonName.value = personName
  activeMoment.value = null
}

function jumpToMoment(moment: VideoPersonMoment) {
  activeMoment.value = moment
  activePersonName.value = moment.person_name

  const element = videoRef.value
  if (!element) return

  const targetTime = Math.max(0, moment.timestamp_seconds)
  const handleSeeked = () => {
    element.pause()
    element.removeEventListener('seeked', handleSeeked)
  }

  element.pause()
  element.addEventListener('seeked', handleSeeked)
  element.currentTime = targetTime
}

function clearMomentOverlay() {
  activeMoment.value = null
}
</script>

<template>
  <el-drawer v-model="open" size="720px" :with-header="false" destroy-on-close>
    <div v-if="video" class="video-drawer">
      <div class="video-stage">
        <video
          ref="videoRef"
          class="video-player"
          controls
          preload="metadata"
          :poster="video.thumbnail_asset_url ? thumbnailUrl : undefined"
          :src="assetUrl"
          @play="clearMomentOverlay"
        />

        <div v-if="activeMoment && activeBoxStyle" class="video-target-overlay">
          <div class="video-target-box" :style="activeBoxStyle">
            <span class="video-target-label">
              {{ activeMoment.person_name }} · {{ formatDuration(activeMoment.timestamp_seconds) }}
            </span>
          </div>
        </div>
      </div>

      <div class="video-drawer__section">
        <p class="eyebrow">Video Detail</p>
        <h3>{{ video.caption || '尚未生成视频摘要' }}</h3>
        <p class="drawer-copy">{{ video.ocr_text || '当前视频还没有 OCR 文本。' }}</p>
      </div>

      <div v-if="groupedMoments.length" class="video-drawer__section">
        <div class="drawer-section-head">
          <h4>人物检出时间点</h4>
          <span class="section-tip">点击时间点会自动跳转、暂停，并用识别框标注当前命中目标。</span>
        </div>

        <div class="person-chip-row">
          <button
            v-for="group in groupedMoments"
            :key="group.personName"
            type="button"
            class="person-chip"
            :class="{ active: activePersonName === group.personName }"
            @click="selectPerson(group.personName)"
          >
            {{ group.personName }}
          </button>
        </div>

        <div class="moment-chip-row">
          <button
            v-for="moment in selectedMoments"
            :key="`${moment.person_name}-${moment.timestamp_seconds}-${moment.score}`"
            type="button"
            class="moment-chip"
            :class="{
              active:
                activeMoment?.person_name === moment.person_name &&
                activeMoment?.timestamp_seconds === moment.timestamp_seconds,
            }"
            @click="jumpToMoment(moment)"
          >
            <strong>{{ formatDuration(moment.timestamp_seconds) }}</strong>
            <span>{{ moment.score.toFixed(3) }}</span>
          </button>
        </div>
      </div>

      <div class="tag-cloud">
        <span v-for="tag in tagTexts" :key="tag" class="photo-tag">{{ tag }}</span>
      </div>

      <div class="video-meta-grid">
        <article class="video-meta-card">
          <span>来源类型</span>
          <strong>{{ sourceKindLabel(video.source_kind) }}</strong>
        </article>
        <article class="video-meta-card">
          <span>时长</span>
          <strong>{{ formatDuration(video.duration_seconds) }}</strong>
        </article>
        <article class="video-meta-card">
          <span>分辨率</span>
          <strong>{{ video.frame_width || 0 }} × {{ video.frame_height || 0 }}</strong>
        </article>
        <article class="video-meta-card">
          <span>采样帧</span>
          <strong>{{ video.sampled_frame_count }}</strong>
        </article>
        <article class="video-meta-card">
          <span>人脸数</span>
          <strong>{{ video.face_count }}</strong>
        </article>
        <article class="video-meta-card">
          <span>更新时间</span>
          <strong>{{ formatDateTime(video.created_at) }}</strong>
        </article>
      </div>

      <div class="video-drawer__actions">
        <el-button type="primary" plain :icon="MagicStick" :loading="reanalyzing" @click="emit('reanalyze')">
          重新分析视频
        </el-button>
        <el-button type="primary" :icon="Search" :loading="findingSimilar" @click="emit('findSimilar')">
          查找相似视频
        </el-button>
        <el-button type="danger" plain :icon="Delete" :loading="deleting" @click="emit('delete')">
          删除视频
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

.video-stage {
  position: relative;
  overflow: hidden;
  border-radius: 20px;
}

.video-player {
  width: 100%;
  border-radius: 20px;
  background: rgba(12, 16, 22, 0.88);
  display: block;
}

.video-target-overlay {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.video-target-box {
  position: absolute;
  border: 2px solid rgba(255, 177, 90, 0.98);
  border-radius: 14px;
  box-shadow:
    0 0 0 1px rgba(255, 177, 90, 0.2),
    0 0 22px rgba(255, 177, 90, 0.35);
}

.video-target-label {
  position: absolute;
  top: -34px;
  left: 0;
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(255, 177, 90, 0.96);
  color: #2f1907;
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
}

.video-drawer__section {
  display: grid;
  gap: 10px;
}

.drawer-section-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: baseline;
}

.drawer-copy {
  margin: 0;
  color: var(--muted);
  line-height: 1.7;
}

.section-tip {
  color: var(--muted);
  font-size: 13px;
}

.person-chip-row,
.moment-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.person-chip,
.moment-chip {
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.03);
  color: inherit;
}

.person-chip {
  padding: 8px 14px;
  border-radius: 999px;
}

.person-chip.active {
  border-color: rgba(255, 177, 90, 0.72);
  background: rgba(255, 177, 90, 0.16);
}

.moment-chip {
  display: grid;
  gap: 4px;
  padding: 10px 14px;
  border-radius: 16px;
  min-width: 92px;
  text-align: left;
}

.moment-chip span {
  color: var(--muted);
  font-size: 12px;
}

.moment-chip.active {
  border-color: rgba(255, 177, 90, 0.72);
  background: rgba(255, 177, 90, 0.14);
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
  flex-wrap: wrap;
}

@media (max-width: 720px) {
  .drawer-section-head {
    display: grid;
  }

  .video-meta-grid {
    grid-template-columns: 1fr;
  }
}
</style>
