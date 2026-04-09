from __future__ import annotations

import json
from pathlib import Path

from sqlmodel import Session

from app.config import Settings, get_settings
from app.embeddings import serialize_vector
from app.models import Video
from app.repository import GalleryRepository
from app.serializers import build_video_read
from app.video_processing import VideoProcessingService


def reanalyze_video_record(
    session: Session,
    video: Video,
    settings: Settings | None = None,
) -> Video:
    runtime_settings = settings or get_settings()
    video_path = Path(video.storage_path)
    if not video_path.exists():
        raise FileNotFoundError(f"Video asset not found: {video_path}")

    analysis = VideoProcessingService(session, runtime_settings).analyze_video(
        video_path,
        asset_key=video.sha256,
        source_kind=video.source_kind or "local_folder",
    )

    video.thumbnail_path = str(analysis.thumbnail_path) if analysis.thumbnail_path else None
    video.caption = analysis.caption
    video.ocr_text = analysis.ocr_text
    video.people = json.dumps(analysis.people, ensure_ascii=False)
    video.scene_tags = json.dumps(analysis.scene_tags, ensure_ascii=False)
    video.object_tags = json.dumps(analysis.object_tags, ensure_ascii=False)
    video.face_clusters = json.dumps(analysis.face_clusters, ensure_ascii=False)
    video.person_moments = json.dumps(analysis.person_moments, ensure_ascii=False)
    video.face_count = analysis.face_count
    video.vector_embedding = serialize_vector(analysis.vector_embedding)
    video.duration_seconds = analysis.metadata.duration_seconds
    video.frame_width = analysis.metadata.frame_width
    video.frame_height = analysis.metadata.frame_height
    video.fps = analysis.metadata.fps
    video.sampled_frame_count = analysis.sampled_frame_count
    return GalleryRepository(session).save_video(video)


def build_reanalyzed_video_read(
    session: Session,
    video: Video,
    settings: Settings | None = None,
):
    saved = reanalyze_video_record(session, video, settings=settings)
    return build_video_read(GalleryRepository(session), saved)
