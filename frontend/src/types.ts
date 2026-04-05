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

export interface Video {
  id: number
  source_id: number | null
  source_kind: SourceKind | null
  source_name: string | null
  original_path: string
  storage_path: string
  thumbnail_path: string | null
  thumbnail_asset_url: string | null
  sha256: string
  caption: string | null
  ocr_text: string | null
  people: string[]
  scene_tags: string[]
  object_tags: string[]
  face_clusters: string[]
  face_names: string[]
  face_count: number
  vector_ready: boolean
  duration_seconds: number | null
  frame_width: number | null
  frame_height: number | null
  fps: number | null
  sampled_frame_count: number
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

export interface VideoSearchHit {
  score: number
  video: Video
}

export interface VideoSearchResponse {
  total: number
  hits: VideoSearchHit[]
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

export interface PersonProfile {
  id: number
  name: string
  example_sample_id: number | null
  example_sample_asset_url: string | null
  sample_count: number
  linked_cluster_count: number
  linked_photo_count: number
  created_at: string
  updated_at: string
}

export interface PersonSample {
  id: number
  person_id: number
  original_filename: string
  asset_url: string | null
  created_at: string
}

export interface PersonClusterCorrectionCandidate {
  label: string
  display_name: string | null
  example_photo_id: number | null
  example_photo_asset_url: string | null
  photo_count: number
  score: number
  competitor_score: number
  margin: number
  current_person_id: number | null
  current_person_name: string | null
  linked_to_selected_person: boolean
  recommended: boolean
}

export interface PersonClusterCorrectionResult {
  person: PersonProfile
  updated_cluster_count: number
  updated_labels: string[]
}

export interface FaceThresholds {
  face_detection_confidence_threshold: number
  face_detection_nms_threshold: number
  face_cluster_similarity_threshold: number
  person_recognition_similarity_threshold: number
}

export interface FaceTuningBand {
  label: string
  min_score: number
  max_score: number
  count: number
}

export interface FaceTuningMergePreview {
  label: string
  display_name: string | null
  photo_count: number
  neighbor_label: string
  neighbor_display_name: string | null
  neighbor_photo_count: number
  score: number
  distance_to_threshold: number
}

export interface FaceTuningPersonPreview {
  label: string
  display_name: string | null
  photo_count: number
  current_person_id: number | null
  current_person_name: string | null
  best_person_id: number | null
  best_person_name: string | null
  score: number
  second_score: number
  margin: number
  distance_to_threshold: number
}

export interface FaceTuningPreview {
  total_clusters: number
  preview_cluster_count: number
  total_people: number
  total_photos: number
  linked_clusters: number
  merge_candidate_count: number
  ambiguous_merge_count: number
  person_candidate_count: number
  ambiguous_person_match_count: number
  nearest_neighbor_mean_score: number
  best_person_mean_score: number
  cluster_similarity_bands: FaceTuningBand[]
  person_score_bands: FaceTuningBand[]
  borderline_merges: FaceTuningMergePreview[]
  borderline_person_matches: FaceTuningPersonPreview[]
  notes: string[]
}

export interface FaceTuningBundle {
  thresholds: FaceThresholds
  defaults: FaceThresholds
  preview: FaceTuningPreview
}
