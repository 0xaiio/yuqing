<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import {
  CirclePlus,
  FolderOpened,
  Promotion,
  RefreshRight,
  VideoPause,
} from '@element-plus/icons-vue'
import { ElMessage, ElNotification } from 'element-plus'

import {
  createSource,
  importSource,
  listSources,
  startSourceWatch,
  stopSourceWatch,
} from '../services/api'
import { canUseNativeDirectoryPicker, pickDirectory } from '../services/desktop'
import type { Source, SourceKind } from '../types'
import {
  formatDateTime,
  resolveErrorMessage,
  sourceKindExamples,
  sourceKindLabel,
  sourceKindOptions,
  sourceKindTagType,
} from '../utils/format'

const sources = ref<Source[]>([])
const loading = ref(false)
const creating = ref(false)
const importingSourceId = ref<number | null>(null)
const togglingSourceId = ref<number | null>(null)
const choosingDirectory = ref(false)
const importLimit = ref(80)
const nativePickerReady = computed(() => canUseNativeDirectoryPicker())

const form = reactive<{
  name: string
  kind: SourceKind
  root_path: string
  enabled: boolean
}>({
  name: '',
  kind: 'local_folder',
  root_path: '',
  enabled: true,
})

const activeExample = computed(() => sourceKindExamples[form.kind])

async function loadSourceList() {
  loading.value = true

  try {
    sources.value = await listSources()
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, '加载图片源失败，请确认后端已经启动。'))
  } finally {
    loading.value = false
  }
}

async function chooseSourceDirectory() {
  choosingDirectory.value = true

  try {
    const selected = await pickDirectory(form.root_path.trim() || undefined)
    if (selected) {
      form.root_path = selected
      return
    }

    if (!canUseNativeDirectoryPicker()) {
      ElMessage.info('当前不是 Tauri 桌面壳，请直接粘贴目录路径。')
    }
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, '打开目录选择器失败。'))
  } finally {
    choosingDirectory.value = false
  }
}

async function handleCreateSource() {
  if (!form.name.trim() || !form.root_path.trim()) {
    ElMessage.warning('请先填写来源名称和目录路径。')
    return
  }

  creating.value = true

  try {
    const source = await createSource({
      name: form.name.trim(),
      kind: form.kind,
      root_path: form.root_path.trim(),
      enabled: form.enabled,
    })

    sources.value = [source, ...sources.value]
    ElMessage.success('图片源已创建。')
    window.dispatchEvent(new Event('workspace:refresh'))

    form.name = ''
    form.root_path = ''
    form.enabled = true
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, '创建图片源失败。'))
  } finally {
    creating.value = false
  }
}

async function handleImport(source: Source) {
  importingSourceId.value = source.id

  try {
    const job = await importSource(source.id, importLimit.value)
    ElNotification({
      title: '导入完成',
      message: `扫描 ${job.scanned_count} 张，导入 ${job.imported_count} 张，识别重复 ${job.duplicate_count} 张。`,
      type: 'success',
      duration: 5000,
    })
    await loadSourceList()
    window.dispatchEvent(new Event('workspace:refresh'))
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, '导入失败，请检查目录权限或路径是否正确。'))
  } finally {
    importingSourceId.value = null
  }
}

async function toggleWatch(source: Source) {
  togglingSourceId.value = source.id

  try {
    const updated = source.watching
      ? await stopSourceWatch(source.id)
      : await startSourceWatch(source.id)
    sources.value = sources.value.map((item) => (item.id === updated.id ? updated : item))
    ElMessage.success(updated.watching ? '实时监听已开启。' : '实时监听已关闭。')
    window.dispatchEvent(new Event('workspace:refresh'))
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, '切换实时监听失败。'))
  } finally {
    togglingSourceId.value = null
  }
}

onMounted(() => {
  void loadSourceList()
})
</script>

<template>
  <div class="page-stack">
    <section class="page-section search-board fade-in">
      <div class="page-heading">
        <p class="eyebrow">Source Intake</p>
        <h3>把聊天图、本地图库和导出目录接到同一个入口</h3>
        <p>
          首版建议使用用户主动授权的本地目录方式接入微信和 QQ，既合规也更稳定。
        </p>
      </div>

      <div class="sources-layout">
        <div class="glass-panel">
          <div class="section-head">
            <h4>新建图片源</h4>
            <span class="section-tip">面向 Windows 桌面场景</span>
          </div>

          <el-form label-position="top" class="stack-form">
            <el-form-item label="来源名称">
              <el-input
                v-model="form.name"
                placeholder="例如：家庭相册 / 微信聊天图 / QQ 工作群"
              />
            </el-form-item>

            <el-form-item label="来源类型">
              <el-segmented v-model="form.kind" :options="sourceKindOptions" />
            </el-form-item>

            <el-form-item label="目录路径">
              <div class="picker-row">
                <el-input
                  v-model="form.root_path"
                  :placeholder="activeExample"
                  type="textarea"
                  :rows="3"
                />
                <el-button
                  class="picker-button"
                  :icon="FolderOpened"
                  :loading="choosingDirectory"
                  @click="chooseSourceDirectory"
                >
                  目录选择器
                </el-button>
              </div>
            </el-form-item>

            <el-form-item label="创建后状态">
              <div class="switch-row">
                <span>创建后立即参与实时监听</span>
                <el-switch v-model="form.enabled" />
              </div>
            </el-form-item>

            <el-form-item label="单次导入上限">
              <el-input-number v-model="importLimit" :min="10" :max="1000" :step="10" />
            </el-form-item>

            <div class="action-row">
              <el-button
                type="primary"
                :icon="CirclePlus"
                :loading="creating"
                @click="handleCreateSource"
              >
                创建来源
              </el-button>
            </div>
          </el-form>
        </div>

        <div class="soft-panel hint-panel">
          <div class="section-head">
            <h4>目录建议</h4>
            <span class="section-tip">首版优先追求可落地</span>
          </div>

          <div class="hint-box">
            <strong>{{ sourceKindLabel(form.kind) }}</strong>
            <p>{{ activeExample }}</p>
          </div>

          <el-alert
            v-if="nativePickerReady"
            type="success"
            :closable="false"
            title="当前运行在 Tauri 桌面壳中，可以直接使用原生目录选择器。"
          />

          <el-alert
            v-else
            type="info"
            :closable="false"
            title="当前是浏览器调试模式。目录选择器会在 Tauri 桌面壳中自动启用。"
          />
        </div>
      </div>
    </section>

    <section class="page-section fade-in">
      <div class="section-head">
        <h4>已接入图片源</h4>
        <span class="section-tip">{{ sources.length }} 个来源</span>
      </div>

      <div v-if="sources.length" class="sources-grid">
        <article v-for="source in sources" :key="source.id" class="source-card">
          <div class="source-card__head">
            <div>
              <h5>{{ source.name }}</h5>
              <p>{{ source.root_path }}</p>
            </div>
            <el-tag :type="sourceKindTagType(source.kind)" effect="dark">
              {{ sourceKindLabel(source.kind) }}
            </el-tag>
          </div>

          <div class="source-card__meta">
            <span>创建于 {{ formatDateTime(source.created_at) }}</span>
            <span>监听状态：{{ source.watching ? '运行中' : '未运行' }}</span>
            <span>队列图片：{{ source.queued_file_count }}</span>
            <span v-if="source.watch_processing">当前正在处理监听队列</span>
            <span v-if="source.last_watch_event_at">
              最近监听事件：{{ formatDateTime(source.last_watch_event_at) }}
            </span>
            <span v-if="source.last_watch_completed_at">
              最近完成时间：{{ formatDateTime(source.last_watch_completed_at) }}
            </span>
            <span v-if="source.watch_error" class="error-copy">{{ source.watch_error }}</span>
          </div>

          <div class="action-row">
            <el-button
              type="primary"
              plain
              :icon="Promotion"
              :loading="importingSourceId === source.id"
              @click="handleImport(source)"
            >
              立即导入
            </el-button>
            <el-button
              plain
              :type="source.watching ? 'warning' : 'success'"
              :icon="source.watching ? VideoPause : RefreshRight"
              :loading="togglingSourceId === source.id"
              @click="toggleWatch(source)"
            >
              {{ source.watching ? '停止监听' : '开启监听' }}
            </el-button>
          </div>
        </article>
      </div>

      <el-empty v-else :description="loading ? '图片源加载中...' : '还没有创建图片源'" />
    </section>
  </div>
</template>
