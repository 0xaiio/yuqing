<script setup lang="ts">
import { CloseBold, Delete, Finished, Select } from '@element-plus/icons-vue'
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    active: boolean
    selectedCount: number
    totalCount: number
    mediaLabel: string
    deleting?: boolean
  }>(),
  {
    deleting: false,
  },
)

const emit = defineEmits<{
  start: []
  cancel: []
  selectAll: []
  clear: []
  remove: []
}>()

const summaryText = computed(() => `已选 ${props.selectedCount} / ${props.totalCount} 个${props.mediaLabel}`)
</script>

<template>
  <div class="selection-toolbar">
    <template v-if="!active">
      <el-button plain :icon="Select" @click="emit('start')">批量多选{{ mediaLabel }}</el-button>
    </template>
    <template v-else>
      <span class="selection-toolbar__summary">{{ summaryText }}</span>
      <div class="selection-toolbar__actions">
        <el-button plain :icon="Finished" :disabled="!totalCount" @click="emit('selectAll')">
          全选当前结果
        </el-button>
        <el-button plain @click="emit('clear')">清空选择</el-button>
        <el-button
          type="danger"
          plain
          :icon="Delete"
          :disabled="!selectedCount"
          :loading="deleting"
          @click="emit('remove')"
        >
          删除选中
        </el-button>
        <el-button plain :icon="CloseBold" @click="emit('cancel')">退出多选</el-button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.selection-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
}

.selection-toolbar__summary {
  color: var(--muted);
}

.selection-toolbar__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
</style>
