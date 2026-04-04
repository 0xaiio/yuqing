import { isTauri } from '@tauri-apps/api/core'
import { open } from '@tauri-apps/plugin-dialog'

declare global {
  interface Window {
    __TAURI__?: unknown
    __TAURI_INTERNALS__?: unknown
  }
}

function hasTauriRuntimeMarkers(): boolean {
  if (typeof window === 'undefined') {
    return false
  }

  const userAgent = typeof navigator !== 'undefined' ? navigator.userAgent || '' : ''
  return Boolean(window.__TAURI__ || window.__TAURI_INTERNALS__ || userAgent.includes('Tauri'))
}

export function canUseNativeDirectoryPicker(): boolean {
  try {
    return hasTauriRuntimeMarkers() || isTauri()
  } catch {
    return hasTauriRuntimeMarkers()
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
