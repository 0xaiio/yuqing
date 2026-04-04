import axios from 'axios'

import type { ImportJob, SearchMode, SourceKind } from '../types'

export const sourceKindOptions: Array<{ label: string; value: SourceKind }> = [
  { label: '本地图库', value: 'local_folder' },
  { label: '微信目录', value: 'wechat_folder' },
  { label: 'QQ 目录', value: 'qq_folder' },
]

export const searchModeOptions: Array<{ label: string; value: SearchMode }> = [
  { label: '混合检索', value: 'hybrid' },
  { label: '关键词优先', value: 'keyword' },
  { label: '向量优先', value: 'vector' },
]

export const sourceKindExamples: Record<SourceKind, string> = {
  local_folder: '例如：D:\\Photos\\Family',
  wechat_folder: '例如：C:\\Users\\<用户名>\\Documents\\WeChat Files\\<微信号>\\FileStorage\\Image',
  qq_folder: '例如：C:\\Users\\<用户名>\\Documents\\Tencent Files\\<QQ号>\\Image',
}

export function sourceKindLabel(kind: SourceKind | null | undefined): string {
  if (kind === 'wechat_folder') return '微信目录'
  if (kind === 'qq_folder') return 'QQ 目录'
  return '本地图库'
}

export function sourceKindTagType(kind: SourceKind | null | undefined): 'success' | 'warning' | 'info' {
  if (kind === 'wechat_folder') return 'success'
  if (kind === 'qq_folder') return 'warning'
  return 'info'
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value

  return new Intl.DateTimeFormat('zh-CN', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date)
}

export function formatCount(value: number): string {
  return new Intl.NumberFormat('zh-CN').format(value)
}

export function parseTagInput(value: string): string[] {
  return Array.from(
    new Set(
      value
        .split(/[,\n，]/)
        .map((item) => item.trim())
        .filter(Boolean),
    ),
  )
}

export function jobStatusTagType(status: string): 'success' | 'danger' | 'info' | 'warning' {
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'running') return 'warning'
  return 'info'
}

export function jobStatusLabel(status: string): string {
  if (status === 'completed') return '已完成'
  if (status === 'failed') return '失败'
  if (status === 'running') return '执行中'
  return status
}

export function jobProgress(job: ImportJob): number {
  if (job.scanned_count <= 0) {
    return job.status === 'completed' ? 100 : 0
  }

  return Math.min(
    100,
    Math.round(((job.imported_count + job.duplicate_count) / job.scanned_count) * 100),
  )
}

export function resolveErrorMessage(error: unknown, fallback: string): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail
    if (typeof detail === 'string' && detail.trim()) {
      return detail
    }

    if (typeof error.message === 'string' && error.message.trim()) {
      return error.message
    }
  }

  if (error instanceof Error && error.message.trim()) {
    return error.message
  }

  return fallback
}
