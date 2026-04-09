from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Source(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    kind: str = Field(index=True)
    root_path: str
    enabled: bool = True
    created_at: datetime = Field(default_factory=utc_now)


class Photo(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    source_id: Optional[int] = Field(default=None, foreign_key="source.id")
    source_kind: str | None = Field(default=None, index=True)
    source_name: str | None = None
    external_id: str | None = Field(default=None, index=True)
    original_path: str
    storage_path: str
    sha256: str = Field(index=True)
    phash: str | None = Field(default=None, index=True)
    caption: str | None = None
    ocr_text: str | None = None
    people: str | None = None
    scene_tags: str | None = None
    object_tags: str | None = None
    face_clusters: str | None = None
    face_count: int = 0
    vector_embedding: str | None = None
    taken_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)


class Video(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    source_id: Optional[int] = Field(default=None, foreign_key="source.id")
    source_kind: str | None = Field(default=None, index=True)
    source_name: str | None = None
    external_id: str | None = Field(default=None, index=True)
    original_path: str
    storage_path: str
    thumbnail_path: str | None = None
    sha256: str = Field(index=True)
    caption: str | None = None
    ocr_text: str | None = None
    people: str | None = None
    scene_tags: str | None = None
    object_tags: str | None = None
    face_clusters: str | None = None
    person_moments: str | None = None
    face_count: int = 0
    vector_embedding: str | None = None
    duration_seconds: float | None = None
    frame_width: int | None = None
    frame_height: int | None = None
    fps: float | None = None
    sampled_frame_count: int = 0
    taken_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)


class BackgroundTask(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    task_type: str = Field(index=True)
    title: str
    status: str = Field(default="queued", index=True)
    total_items: int = 0
    completed_items: int = 0
    failed_items: int = 0
    error_message: str | None = None
    payload: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    started_at: datetime | None = None
    finished_at: datetime | None = None


class ImportJob(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    source_id: Optional[int] = Field(default=None, foreign_key="source.id")
    source_name: str
    status: str = Field(index=True)
    scanned_count: int = 0
    imported_count: int = 0
    duplicate_count: int = 0
    error_message: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class FaceCluster(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    label: str = Field(index=True)
    display_name: str | None = None
    centroid: str | None = None
    person_profile_id: int | None = Field(default=None, foreign_key="personprofile.id")
    example_photo_id: int | None = Field(default=None, foreign_key="photo.id")
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class PersonProfile(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    normalized_name: str = Field(index=True)
    centroid: str | None = None
    example_sample_id: int | None = None
    sample_count: int = 0
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class PersonSample(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    person_id: int = Field(foreign_key="personprofile.id", index=True)
    original_filename: str
    storage_path: str
    embedding: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
