from datetime import datetime
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


def decode_json_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return []
    if isinstance(data, list):
        return [str(item) for item in data]
    return []


class SourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    kind: str = Field(pattern="^(local_folder|wechat_folder|qq_folder)$")
    root_path: Path
    enabled: bool = True


class SourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    kind: str
    root_path: str
    enabled: bool
    watching: bool = False
    watch_processing: bool = False
    queued_file_count: int = 0
    watch_error: str | None = None
    last_watch_event_at: datetime | None = None
    last_watch_completed_at: datetime | None = None
    created_at: datetime


class ImportRequest(BaseModel):
    limit: int = Field(default=50, ge=1, le=1000)


class ImportJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_id: int | None = None
    source_name: str
    status: str
    scanned_count: int
    imported_count: int
    duplicate_count: int
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class PhotoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_id: int | None = None
    source_kind: str | None = None
    source_name: str | None = None
    original_path: str
    storage_path: str
    sha256: str
    phash: str | None = None
    caption: str | None = None
    ocr_text: str | None = None
    people: list[str] = Field(default_factory=list)
    scene_tags: list[str] = Field(default_factory=list)
    object_tags: list[str] = Field(default_factory=list)
    face_clusters: list[str] = Field(default_factory=list)
    face_names: list[str] = Field(default_factory=list)
    face_count: int = 0
    vector_ready: bool = False
    taken_at: datetime | None = None
    created_at: datetime


class SearchQuery(BaseModel):
    text: str = ""
    people: list[str] = Field(default_factory=list)
    scene_tags: list[str] = Field(default_factory=list)
    object_tags: list[str] = Field(default_factory=list)
    source_kinds: list[str] = Field(default_factory=list)
    face_cluster_labels: list[str] = Field(default_factory=list)
    mode: str = Field(default="hybrid", pattern="^(hybrid|keyword|vector)$")
    limit: int = Field(default=20, ge=1, le=100)


class SearchHit(BaseModel):
    score: float
    photo: PhotoRead


class SearchResponse(BaseModel):
    total: int
    hits: list[SearchHit]


class FaceClusterRead(BaseModel):
    id: int
    label: str
    display_name: str | None = None
    example_photo_id: int | None = None
    example_photo_asset_url: str | None = None
    photo_count: int = 0
    named: bool = False
    latest_photo_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class FaceClusterRenameRequest(BaseModel):
    display_name: str = Field(default="", max_length=40)


class PersonCreate(BaseModel):
    name: str = Field(min_length=1, max_length=40)


class PersonRenameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=40)


class PersonSampleRead(BaseModel):
    id: int
    person_id: int
    original_filename: str
    asset_url: str | None = None
    created_at: datetime


class PersonRead(BaseModel):
    id: int
    name: str
    example_sample_id: int | None = None
    example_sample_asset_url: str | None = None
    sample_count: int = 0
    linked_cluster_count: int = 0
    linked_photo_count: int = 0
    created_at: datetime
    updated_at: datetime


class PersonClusterCorrectionCandidateRead(BaseModel):
    label: str
    display_name: str | None = None
    example_photo_id: int | None = None
    example_photo_asset_url: str | None = None
    photo_count: int = 0
    score: float
    competitor_score: float = 0
    margin: float = 0
    current_person_id: int | None = None
    current_person_name: str | None = None
    linked_to_selected_person: bool = False
    recommended: bool = False


class PersonClusterCorrectionRequest(BaseModel):
    cluster_labels: list[str] = Field(default_factory=list)
    action: str = Field(pattern="^(bind|unbind)$")


class PersonClusterCorrectionResult(BaseModel):
    person: PersonRead
    updated_cluster_count: int = 0
    updated_labels: list[str] = Field(default_factory=list)


class FaceThresholds(BaseModel):
    face_detection_confidence_threshold: float = Field(ge=0, le=1)
    face_detection_nms_threshold: float = Field(ge=0, le=1)
    face_cluster_similarity_threshold: float = Field(ge=0, le=1)
    person_recognition_similarity_threshold: float = Field(ge=0, le=1)


class FaceTuningBandRead(BaseModel):
    label: str
    min_score: float
    max_score: float
    count: int


class FaceTuningMergePreviewRead(BaseModel):
    label: str
    display_name: str | None = None
    photo_count: int = 0
    neighbor_label: str
    neighbor_display_name: str | None = None
    neighbor_photo_count: int = 0
    score: float
    distance_to_threshold: float


class FaceTuningPersonPreviewRead(BaseModel):
    label: str
    display_name: str | None = None
    photo_count: int = 0
    current_person_id: int | None = None
    current_person_name: str | None = None
    best_person_id: int | None = None
    best_person_name: str | None = None
    score: float
    second_score: float = 0
    margin: float = 0
    distance_to_threshold: float


class FaceTuningPreviewRead(BaseModel):
    total_clusters: int
    preview_cluster_count: int
    total_people: int
    total_photos: int
    linked_clusters: int
    merge_candidate_count: int
    ambiguous_merge_count: int
    person_candidate_count: int
    ambiguous_person_match_count: int
    nearest_neighbor_mean_score: float
    best_person_mean_score: float
    cluster_similarity_bands: list[FaceTuningBandRead] = Field(default_factory=list)
    person_score_bands: list[FaceTuningBandRead] = Field(default_factory=list)
    borderline_merges: list[FaceTuningMergePreviewRead] = Field(default_factory=list)
    borderline_person_matches: list[FaceTuningPersonPreviewRead] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class FaceTuningBundleRead(BaseModel):
    thresholds: FaceThresholds
    defaults: FaceThresholds
    preview: FaceTuningPreviewRead


class FaceThresholdUpdateRequest(FaceThresholds):
    rebuild_index: bool = False


class HealthRead(BaseModel):
    status: str
    app_name: str
    import_root: str
    active_watchers: int
    queued_watch_tasks: int
    watch_worker_busy: bool
