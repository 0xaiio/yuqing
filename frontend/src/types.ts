export type SourceKind = 'local_folder' | 'wechat_folder' | 'qq_folder'
export type SearchMode = 'hybrid' | 'keyword' | 'vector'

export interface HealthStatus {
  status: string
  app_name: string
  import_root: string
  active_watchers: number
  queued_watch_tasks: number
  watch_worker_busy: boolean
}

export interface Source {
  id: number
  name: string
  kind: SourceKind
  root_path: string
  enabled: boolean
  watching: boolean
  watch_processing: boolean
  queued_file_count: number
  watch_error: string | null
  last_watch_event_at: string | null
  last_watch_completed_at: string | null
  created_at: string
}

export interface CreateSourcePayload {
  name: string
  kind: SourceKind
  root_path: string
  enabled: boolean
}

export interface ImportJob {
  id: number
  source_id: number | null
  source_name: string
  status: string
  scanned_count: number
  imported_count: number
  duplicate_count: number
  error_message: string | null
  created_at: string
  updated_at: string
}

export interface Photo {
  id: number
  source_id: number | null
  source_kind: SourceKind | null
  source_name: string | null
  original_path: string
  storage_path: string
  sha256: string
  phash: string | null
  caption: string | null
  ocr_text: string | null
  people: string[]
  scene_tags: string[]
  object_tags: string[]
  face_clusters: string[]
  face_names: string[]
  face_count: number
  vector_ready: boolean
  taken_at: string | null
  created_at: string
}

export interface SearchHit {
  score: number
  photo: Photo
}

export interface SearchQueryPayload {
  text: string
  people: string[]
  scene_tags: string[]
  object_tags: string[]
  source_kinds: SourceKind[]
  face_cluster_labels: string[]
  mode: SearchMode
  limit: number
}

export interface SearchResponse {
  total: number
  hits: SearchHit[]
}

export interface FaceCluster {
  id: number
  label: string
  display_name: string | null
  example_photo_id: number | null
  example_photo_asset_url: string | null
  photo_count: number
  named: boolean
  latest_photo_at: string | null
  created_at: string
  updated_at: string
}
