from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
from uuid import uuid4

import cv2
import numpy as np
from sqlmodel import Session

from app.ai import AIAnalyzer
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


@dataclass
class VideoFaceSummary:
    labels: list[str]
    names: list[str]
    face_count: int
    person_votes: dict[int, list[float]]


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
        thumbnail_path, frame_paths = self._extract_frames(
            video_path,
            metadata,
            work_root,
            sampled_root,
            interval_seconds=float(self.settings.video_frame_sample_interval_seconds),
            max_frames=self.settings.video_max_sampled_frames,
            write_thumbnail=True,
        )

        face_summary = self._analyze_face_frames(frame_paths)
        dense_frame_count = 0
        if self._should_retry_dense_face_scan(metadata, face_summary):
            dense_root = work_root / "_dense_faces"
            dense_root.mkdir(parents=True, exist_ok=True)
            try:
                _, dense_frame_paths = self._extract_frames(
                    video_path,
                    metadata,
                    work_root,
                    dense_root,
                    interval_seconds=float(self.settings.video_face_retry_interval_seconds),
                    max_frames=self.settings.video_face_retry_max_frames,
                    write_thumbnail=False,
                )
                dense_frame_count = len(dense_frame_paths)
                self._merge_face_summary(face_summary, self._analyze_face_frames(dense_frame_paths))
            finally:
                shutil.rmtree(dense_root, ignore_errors=True)

        video_level_names = self._resolve_video_people(face_summary.person_votes)
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
        people = list(dict.fromkeys([*vision_analysis.people, *face_summary.names, *video_level_names]))
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
            sampled_frame_count=len(frame_paths) + dense_frame_count,
            caption=vision_analysis.caption,
            ocr_text=vision_analysis.ocr_text,
            people=people,
            scene_tags=scene_tags,
            object_tags=object_tags,
            face_clusters=face_summary.labels,
            face_count=face_summary.face_count,
            vector_embedding=vector_embedding,
        )

    def build_query_video_embedding(self, video_path: Path) -> list[float]:
        temp_root = self.settings.video_frame_root / f"query-{uuid4().hex[:12]}"
        sampled_root = temp_root / "_sampled"
        sampled_root.mkdir(parents=True, exist_ok=True)
        try:
            metadata = self._read_metadata(video_path)
            _, frame_paths = self._extract_frames(
                video_path,
                metadata,
                temp_root,
                sampled_root,
                interval_seconds=float(self.settings.video_frame_sample_interval_seconds),
                max_frames=self.settings.video_max_sampled_frames,
                write_thumbnail=False,
            )
            return self.video_embeddings.embed_video_example(frame_paths)
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

    def _analyze_face_frames(self, frame_paths: list[Path]) -> VideoFaceSummary:
        labels: list[str] = []
        names: list[str] = []
        face_count = 0
        person_votes: dict[int, list[float]] = {}

        vote_floor = max(0.36, self.settings.person_recognition_similarity_threshold - 0.08)
        ambiguity_margin = 0.02

        for frame_path in frame_paths:
            embeddings = self.face_clusterer.extract_face_embeddings(frame_path)
            if not embeddings:
                continue

            result = self.face_clusterer.analyze_embeddings(embeddings, example_photo_id=None)
            face_count += result.face_count
            for label in result.labels:
                if label not in labels:
                    labels.append(label)
            for name in result.names:
                if name not in names:
                    names.append(name)

            for embedding in embeddings:
                ranked = self.face_clusterer.rank_person_profiles(embedding, limit=2)
                if not ranked:
                    continue
                best_person, best_score = ranked[0]
                second_score = ranked[1][1] if len(ranked) > 1 else -1.0
                if best_score < vote_floor:
                    continue
                if second_score > 0 and (best_score - second_score) < ambiguity_margin:
                    continue
                person_votes.setdefault(best_person.id or 0, []).append(best_score)

        return VideoFaceSummary(
            labels=labels,
            names=names,
            face_count=face_count,
            person_votes=person_votes,
        )

    def _resolve_video_people(self, person_votes: dict[int, list[float]]) -> list[str]:
        names: list[str] = []
        strong_threshold = self.settings.person_recognition_similarity_threshold
        aggregate_threshold = max(0.4, strong_threshold - 0.06)

        for person_id, scores in person_votes.items():
            if person_id <= 0 or not scores:
                continue
            person = self.face_clusterer.repository.get_person_profile(person_id)
            if person is None:
                continue

            ranked_scores = sorted(scores, reverse=True)
            best_score = ranked_scores[0]
            top_scores = ranked_scores[: min(4, len(ranked_scores))]
            mean_score = sum(top_scores) / len(top_scores)
            if best_score >= strong_threshold or (
                len(scores) >= self.settings.video_person_vote_min_hits and mean_score >= aggregate_threshold
            ):
                names.append(person.name)

        return list(dict.fromkeys(names))

    @staticmethod
    def _merge_face_summary(target: VideoFaceSummary, source: VideoFaceSummary) -> None:
        for label in source.labels:
            if label not in target.labels:
                target.labels.append(label)
        for name in source.names:
            if name not in target.names:
                target.names.append(name)
        target.face_count += source.face_count
        for person_id, scores in source.person_votes.items():
            existing = target.person_votes.setdefault(person_id, [])
            existing.extend(scores)

    def _should_retry_dense_face_scan(self, metadata: VideoMetadata, summary: VideoFaceSummary) -> bool:
        if metadata.duration_seconds <= 2:
            return False
        if summary.face_count == 0:
            return True
        if not summary.names and metadata.duration_seconds >= 6:
            return True
        if summary.face_count <= 2 and metadata.duration_seconds >= 12:
            return True
        return False

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
        *,
        interval_seconds: float,
        max_frames: int,
        write_thumbnail: bool,
    ) -> tuple[Path | None, list[Path]]:
        frame_paths: list[Path] = []
        timestamps = self._build_sample_timestamps(
            metadata,
            interval_seconds=interval_seconds,
            max_frames=max_frames,
        )

        for index, timestamp in enumerate(timestamps):
            target_path = sampled_root / f"frame_{index:03d}.jpg"
            if self._capture_frame(video_path, timestamp, target_path):
                frame_paths.append(target_path)

        if not frame_paths:
            fallback_path = sampled_root / "frame_000.jpg"
            if self._capture_frame(video_path, 0.0, fallback_path):
                frame_paths.append(fallback_path)

        thumbnail_path: Path | None = None
        if write_thumbnail and frame_paths:
            thumbnail_path = work_root / "thumbnail.jpg"
            thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(frame_paths[0], thumbnail_path)

        return thumbnail_path, frame_paths

    def _build_sample_timestamps(
        self,
        metadata: VideoMetadata,
        *,
        interval_seconds: float,
        max_frames: int,
    ) -> list[float]:
        if metadata.duration_seconds <= 0:
            return [0.0]

        interval = max(0.25, float(interval_seconds))
        candidates = list(np.arange(0.0, metadata.duration_seconds, interval, dtype=np.float32))
        candidates.extend(
            [
                0.0,
                metadata.duration_seconds * 0.25,
                metadata.duration_seconds * 0.5,
                metadata.duration_seconds * 0.75,
                max(metadata.duration_seconds - 0.5, 0.0),
            ]
        )

        deduped: list[float] = []
        seen: set[int] = set()
        for value in sorted(candidates):
            normalized = max(0.0, min(float(value), max(metadata.duration_seconds - 0.05, 0.0)))
            key = int(round(normalized * 20))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(round(normalized, 3))

        return deduped[: max(1, int(max_frames))]

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
