import { isTauri } from '@tauri-apps/api/core'
import { open } from '@tauri-apps/plugin-dialog'

export function canUseNativeDirectoryPicker(): boolean {
  try {
    return isTauri()
  } catch {
    return false
  }
}

export async function pickDirectory(defaultPath?: string): Promise<string | null> {
  if (!canUseNativeDirectoryPicker()) {
    return null
  }

  const selected = await open({
    directory: true,
    multiple: false,
    title: 'Select photo directory',
    defaultPath,
  })

  return typeof selected === 'string' ? selected : null
}
