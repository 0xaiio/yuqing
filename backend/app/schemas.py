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


class HealthRead(BaseModel):
    status: str
    app_name: str
    import_root: str
    active_watchers: int
    queued_watch_tasks: int
    watch_worker_busy: bool
