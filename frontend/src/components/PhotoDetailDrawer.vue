<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import { CopyDocument, MagicStick, PictureFilled, Search, User } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

import { getPhotoAssetUrl } from '../services/api'
import type { FaceCluster, Photo } from '../types'
import { formatDateTime, sourceKindLabel } from '../utils/format'

const props = defineProps<{
  modelValue: boolean
  photo: Photo | null
  faceClusters: FaceCluster[]
  reanalyzing: boolean
  renamingLabels: string[]
  findingSimilar: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [boolean]
  reanalyze: []
  findSimilar: []
  renameFaceCluster: [label: string, displayName: string]
}>()

const renameDrafts = reactive<Record<string, string>>({})

const assetUrl = computed(() => (props.photo ? getPhotoAssetUrl(props.photo.id) : ''))
const allTags = computed(() => {
  if (!props.photo) return []

  return [
    ...props.photo.people.map((item) => `人物 · ${item}`),
    ...props.photo.scene_tags.map((item) => `场景 · ${item}`),
    ...props.photo.object_tags.map((item) => `物体 · ${item}`),
  ]
})
const faceClusterMap = computed(() =>
  Object.fromEntries(props.faceClusters.map((cluster) => [cluster.label, cluster])),
)

watch(
  () => props.photo,
  (photo) => {
    Object.keys(renameDrafts).forEach((key) => delete renameDrafts[key])
    if (!photo) return
    for (const label of photo.face_clusters) {
      renameDrafts[label] = faceClusterMap.value[label]?.display_name || ''
    }
  },
  { immediate: true },
)

async function copyText(value: string, label: string) {
  try {
    await navigator.clipboard.writeText(value)
    ElMessage.success(`${label}已复制。`)
  } catch {
    ElMessage.warning(`复制${label}失败，请手动复制。`)
  }
}
</script>

<template>
  <el-drawer
    :model-value="modelValue"
    size="680px"
    class="photo-drawer"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <template #header>
      <div class="drawer-header">
        <div>
          <p class="eyebrow">Photo Detail</p>
          <h3>{{ photo?.source_name || '图片详情' }}</h3>
        </div>
        <div class="drawer-actions">
          <el-button
            plain
            :icon="Search"
            :loading="findingSimilar"
            @click="emit('findSimilar')"
          >
            查找相似图片
          </el-button>
          <el-button
            type="primary"
            :icon="MagicStick"
            :loading="reanalyzing"
            @click="emit('reanalyze')"
          >
            重新分析
          </el-button>
        </div>
      </div>
    </template>

    <template v-if="photo">
      <div class="drawer-preview">
        <img :src="assetUrl" :alt="photo.caption || `photo-${photo.id}`" />
      </div>

      <div class="drawer-section">
        <h4>AI 摘要</h4>
        <p class="drawer-copy">{{ photo.caption || '还没有图像描述。' }}</p>
      </div>

      <div v-if="photo.face_clusters.length" class="drawer-section">
        <div class="drawer-section__head">
          <h4>人脸簇命名</h4>
          <span class="section-tip">给同一个聚类分配名字后，搜索会自动可用</span>
        </div>
        <div class="cluster-editor-list">
          <div v-for="label in photo.face_clusters" :key="label" class="cluster-editor">
            <div class="cluster-editor__meta">
              <div class="cluster-editor__label">
                <el-icon><User /></el-icon>
                <strong>{{ faceClusterMap[label]?.display_name || '未命名人脸簇' }}</strong>
              </div>
              <small>{{ label }}</small>
            </div>
            <div class="cluster-editor__form">
              <el-input
                v-model="renameDrafts[label]"
                placeholder="例如：爸爸 / 小明 / 同学 A"
              />
              <el-button
                type="primary"
                plain
                :loading="renamingLabels.includes(label)"
                @click="emit('renameFaceCluster', label, renameDrafts[label] || '')"
              >
                保存命名
              </el-button>
            </div>
          </div>
        </div>
      </div>

      <div v-if="allTags.length" class="drawer-section">
        <h4>标签</h4>
        <div class="tag-cloud">
          <span v-for="tag in allTags" :key="tag" class="photo-tag">
            {{ tag }}
          </span>
        </div>
      </div>

      <div class="drawer-section">
        <h4>OCR 文本</h4>
        <p class="drawer-copy">{{ photo.ocr_text || '当前未识别到文字内容。' }}</p>
      </div>

      <div class="drawer-section">
        <h4>元数据</h4>
        <el-descriptions :column="1" border>
          <el-descriptions-item label="来源类型">
            {{ sourceKindLabel(photo.source_kind) }}
          </el-descriptions-item>
          <el-descriptions-item label="拍摄 / 导入时间">
            {{ formatDateTime(photo.taken_at || photo.created_at) }}
          </el-descriptions-item>
          <el-descriptions-item label="人脸数量">
            {{ photo.face_count || '0' }}
          </el-descriptions-item>
          <el-descriptions-item label="向量检索">
            {{ photo.vector_ready ? '已就绪' : '未生成' }}
          </el-descriptions-item>
          <el-descriptions-item label="SHA256">
            <div class="path-row">
              <span class="path-text">{{ photo.sha256 }}</span>
              <el-button text :icon="CopyDocument" @click="copyText(photo.sha256, 'SHA256')" />
            </div>
          </el-descriptions-item>
          <el-descriptions-item label="pHash">
            {{ photo.phash || '—' }}
          </el-descriptions-item>
          <el-descriptions-item label="原始路径">
            <div class="path-row">
              <span class="path-text">{{ photo.original_path }}</span>
              <el-button text :icon="CopyDocument" @click="copyText(photo.original_path, '原始路径')" />
            </div>
          </el-descriptions-item>
          <el-descriptions-item label="归档路径">
            <div class="path-row">
              <span class="path-text">{{ photo.storage_path }}</span>
              <el-button text :icon="CopyDocument" @click="copyText(photo.storage_path, '归档路径')" />
            </div>
          </el-descriptions-item>
        </el-descriptions>
      </div>
    </template>

    <template v-else>
      <div class="drawer-empty">
        <el-icon><PictureFilled /></el-icon>
        <span>选择一张图片后，这里会展示完整细节。</span>
      </div>
    </template>
  </el-drawer>
</template>

<style scoped>
.drawer-header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: center;
  width: 100%;
}

.drawer-header h3 {
  margin: 8px 0 0;
}

.drawer-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.drawer-preview {
  overflow: hidden;
  border-radius: 24px;
  margin-bottom: 22px;
  background: rgba(255, 255, 255, 0.04);
}

.drawer-preview img {
  display: block;
  width: 100%;
  max-height: 360px;
  object-fit: cover;
}

.drawer-section {
  display: grid;
  gap: 12px;
  margin-bottom: 22px;
}

.drawer-section h4 {
  margin: 0;
}

.drawer-section__head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: baseline;
}

.drawer-copy {
  margin: 0;
  color: var(--muted);
  line-height: 1.7;
  white-space: pre-wrap;
}

.cluster-editor-list {
  display: grid;
  gap: 12px;
}

.cluster-editor {
  display: grid;
  gap: 12px;
  padding: 14px;
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.04);
}

.cluster-editor__meta {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}

.cluster-editor__label {
  display: inline-flex;
  gap: 8px;
  align-items: center;
}

.cluster-editor__meta small {
  color: var(--muted);
}

.cluster-editor__form {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
}

.path-row {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}

.path-text {
  word-break: break-all;
}

.drawer-empty {
  display: grid;
  place-content: center;
  gap: 12px;
  color: var(--muted);
  min-height: 320px;
}

.drawer-empty .el-icon {
  margin: 0 auto;
  font-size: 34px;
}

@media (max-width: 720px) {
  .cluster-editor__form {
    grid-template-columns: 1fr;
  }
}
</style>
