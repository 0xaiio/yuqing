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
    example_photo_id: int | None = Field(default=None, foreign_key="photo.id")
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
