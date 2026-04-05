from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import shutil
from uuid import uuid4

import cv2
import numpy as np
from sqlmodel import Session

from app.ai import AIAnalyzer, AnalysisResult
from app.config import Settings, get_settings
from app.face_clustering import FaceClusteringService
from app.video_embeddings import VideoEmbeddingService


@dataclass
class VideoMetadata:
    duration_seconds: float
    frame_width: int
    frame_height: int
    fps: float
    frame_count: int


@dataclass
class VideoAnalysisResult:
    metadata: VideoMetadata
    thumbnail_path: Path | None
    sampled_frame_count: int
    caption: str | None
    ocr_text: str | None
    people: list[str]
    scene_tags: list[str]
    object_tags: list[str]
    face_clusters: list[str]
    face_count: int
    vector_embedding: list[float]


class VideoProcessingService:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.ai = AIAnalyzer(self.settings)
        self.face_clusterer = FaceClusteringService(session, self.settings)
        self.video_embeddings = VideoEmbeddingService(self.settings)

    def analyze_video(
        self,
        video_path: Path,
        *,
        asset_key: str,
        source_kind: str,
    ) -> VideoAnalysisResult:
        work_root = self.settings.video_frame_root / f"video-{asset_key[:16]}"
        sampled_root = work_root / "_sampled"
        sampled_root.mkdir(parents=True, exist_ok=True)

        metadata = self._read_metadata(video_path)
        thumbnail_path, frame_paths = self._extract_frames(video_path, metadata, work_root, sampled_root)

        face_labels: list[str] = []
        face_names: list[str] = []
        face_count = 0
        for frame_path in frame_paths:
            result = self.face_clusterer.analyze_photo(frame_path, example_photo_id=None)
            face_count += result.face_count
            for label in result.labels:
                if label not in face_labels:
                    face_labels.append(label)
            for name in result.names:
                if name not in face_names:
                    face_names.append(name)

        vision_analysis = self.ai.analyze_video_frames(
            frame_paths,
            source_kind=source_kind,
            asset_name=video_path.stem,
        )
        scene_tags = list(
            dict.fromkeys(
                [
                    *self.video_embeddings.infer_scene_tags(frame_paths),
                    *vision_analysis.scene_tags,
                ]
            )
        )
        object_tags = list(
            dict.fromkeys(
                [
                    *self.video_embeddings.infer_object_tags(frame_paths),
                    *vision_analysis.object_tags,
                ]
            )
        )
        people = list(dict.fromkeys([*vision_analysis.people, *face_names]))
        vector_embedding = self.video_embeddings.embed_video(
            frame_paths=frame_paths,
            caption=vision_analysis.caption,
            ocr_text=vision_analysis.ocr_text,
            people=people,
            scene_tags=scene_tags,
            object_tags=object_tags,
            asset_name=video_path.stem,
        )

        shutil.rmtree(sampled_root, ignore_errors=True)
        return VideoAnalysisResult(
            metadata=metadata,
            thumbnail_path=thumbnail_path,
            sampled_frame_count=len(frame_paths),
            caption=vision_analysis.caption,
            ocr_text=vision_analysis.ocr_text,
            people=people,
            scene_tags=scene_tags,
            object_tags=object_tags,
            face_clusters=face_labels,
            face_count=len(face_labels) if face_labels else face_count,
            vector_embedding=vector_embedding,
        )

    def _read_metadata(self, video_path: Path) -> VideoMetadata:
        capture = cv2.VideoCapture(str(video_path))
        if not capture.isOpened():
            raise ValueError(f"Cannot open video: {video_path}")

        fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        frame_width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        frame_height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        duration_seconds = float(frame_count / fps) if fps > 0 and frame_count > 0 else 0.0
        capture.release()
        return VideoMetadata(
            duration_seconds=duration_seconds,
            frame_width=frame_width,
            frame_height=frame_height,
            fps=fps,
            frame_count=frame_count,
        )

    def _extract_frames(
        self,
        video_path: Path,
        metadata: VideoMetadata,
        work_root: Path,
        sampled_root: Path,
    ) -> tuple[Path | None, list[Path]]:
        frame_paths: list[Path] = []
        timestamps = self._build_sample_timestamps(metadata)

        for index, timestamp in enumerate(timestamps):
            target_path = sampled_root / f"frame_{index:03d}.jpg"
            if self._capture_frame(video_path, timestamp, target_path):
                frame_paths.append(target_path)

        if not frame_paths:
            fallback_path = sampled_root / "frame_000.jpg"
            if self._capture_frame(video_path, 0.0, fallback_path):
                frame_paths.append(fallback_path)

        thumbnail_path: Path | None = None
        if frame_paths:
            thumbnail_path = work_root / "thumbnail.jpg"
            thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(frame_paths[0], thumbnail_path)

        return thumbnail_path, frame_paths

    def _build_sample_timestamps(self, metadata: VideoMetadata) -> list[float]:
        if metadata.duration_seconds <= 0:
            return [0.0]

        interval = max(1, self.settings.video_frame_sample_interval_seconds)
        candidates = list(np.arange(0.0, metadata.duration_seconds, interval, dtype=np.float32))
        candidates.extend(
            [
                0.0,
                metadata.duration_seconds * 0.5,
                max(metadata.duration_seconds - 0.5, 0.0),
            ]
        )

        deduped: list[float] = []
        seen: set[int] = set()
        for value in sorted(candidates):
            normalized = max(0.0, min(float(value), max(metadata.duration_seconds - 0.05, 0.0)))
            key = int(round(normalized * 10))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(round(normalized, 3))

        return deduped[: self.settings.video_max_sampled_frames]

    @staticmethod
    def _capture_frame(video_path: Path, timestamp_seconds: float, target_path: Path) -> bool:
        capture = cv2.VideoCapture(str(video_path))
        if not capture.isOpened():
            return False
        capture.set(cv2.CAP_PROP_POS_MSEC, max(timestamp_seconds, 0.0) * 1000.0)
        ok, frame = capture.read()
        capture.release()
        if not ok or frame is None:
            return False
        target_path.parent.mkdir(parents=True, exist_ok=True)
        return bool(cv2.imwrite(str(target_path), frame))
