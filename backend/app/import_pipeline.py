from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil

import imagehash
from PIL import Image
from sqlmodel import Session

from app.ai import AIAnalyzer
from app.connectors import BaseConnector
from app.config import get_settings
from app.connectors import ConnectorRegistry
from app.embeddings import VectorEmbeddingService, serialize_vector
from app.face_clustering import FaceClusteringService
from app.models import ImportJob, Photo, Source, Video
from app.repository import GalleryRepository
from app.video_processing import VideoProcessingService


class ImportPipeline:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = GalleryRepository(session)
        self.registry = ConnectorRegistry()
        self.analyzer = AIAnalyzer()
        self.vectorizer = VectorEmbeddingService()
        self.face_clusterer = FaceClusteringService(session)
        self.video_processor = VideoProcessingService(session)
        self.settings = get_settings()

    def run(
        self,
        source: Source,
        limit: int = 50,
        explicit_paths: list[Path] | None = None,
    ) -> ImportJob:
        job = self.repository.create_import_job(source)
        scanned_count = 0
        imported_count = 0
        duplicate_count = 0

        try:
            if explicit_paths is None:
                connector = self.registry.get(source.kind)
                paths = connector.discover(Path(source.root_path), limit=limit)
            else:
                paths = [path for path in explicit_paths if path.exists()][:limit]

            for media_path in paths:
                scanned_count += 1
                sha256 = self._sha256(media_path)
                existing_photo = self.repository.find_photo_by_sha256(sha256)
                existing_video = self.repository.find_video_by_sha256(sha256)
                if existing_photo is not None or existing_video is not None:
                    duplicate_count += 1
                    continue

                storage_path = self._copy_to_storage(media_path)
                if BaseConnector.is_supported_image(media_path):
                    self._process_photo(source, media_path, storage_path, sha256)
                elif BaseConnector.is_supported_video(media_path):
                    self._process_video(source, media_path, storage_path, sha256)
                imported_count += 1

            return self.repository.finish_import_job(
                job,
                scanned_count=scanned_count,
                imported_count=imported_count,
                duplicate_count=duplicate_count,
            )
        except Exception as exc:
            return self.repository.finish_import_job(
                job,
                scanned_count=scanned_count,
                imported_count=imported_count,
                duplicate_count=duplicate_count,
                error_message=str(exc),
            )

    def _process_photo(self, source: Source, photo_path: Path, storage_path: Path, sha256: str) -> None:
        phash = self._phash(storage_path)
        analysis = self.analyzer.analyze(storage_path, source_kind=source.kind)
        photo = Photo(
            source_id=source.id,
            source_kind=source.kind,
            source_name=source.name,
            external_id=str(photo_path),
            original_path=str(photo_path),
            storage_path=str(storage_path),
            sha256=sha256,
            phash=phash,
            caption=analysis.caption,
            ocr_text=analysis.ocr_text,
            people=json.dumps(analysis.people, ensure_ascii=False),
            scene_tags=json.dumps(analysis.scene_tags, ensure_ascii=False),
            object_tags=json.dumps(analysis.object_tags, ensure_ascii=False),
            taken_at=datetime.fromtimestamp(photo_path.stat().st_mtime),
        )
        photo = self.repository.save_photo(photo)

        face_result = self.face_clusterer.analyze_photo(storage_path, example_photo_id=photo.id)
        merged_people = list(dict.fromkeys(analysis.people + face_result.names))
        vector_embedding = self.vectorizer.embed_photo(
            storage_path,
            caption=analysis.caption,
            ocr_text=analysis.ocr_text,
            people=merged_people,
            scene_tags=analysis.scene_tags,
            object_tags=analysis.object_tags,
            phash=phash,
        )
        photo.people = json.dumps(merged_people, ensure_ascii=False)
        photo.face_clusters = json.dumps(face_result.labels, ensure_ascii=False)
        photo.face_count = face_result.face_count
        photo.vector_embedding = serialize_vector(vector_embedding)
        self.repository.save_photo(photo)

    def _process_video(self, source: Source, video_path: Path, storage_path: Path, sha256: str) -> None:
        analysis = self.video_processor.analyze_video(
            storage_path,
            asset_key=sha256,
            source_kind=source.kind,
        )
        video = Video(
            source_id=source.id,
            source_kind=source.kind,
            source_name=source.name,
            external_id=str(video_path),
            original_path=str(video_path),
            storage_path=str(storage_path),
            thumbnail_path=str(analysis.thumbnail_path) if analysis.thumbnail_path else None,
            sha256=sha256,
            caption=analysis.caption,
            ocr_text=analysis.ocr_text,
            people=json.dumps(analysis.people, ensure_ascii=False),
            scene_tags=json.dumps(analysis.scene_tags, ensure_ascii=False),
            object_tags=json.dumps(analysis.object_tags, ensure_ascii=False),
            face_clusters=json.dumps(analysis.face_clusters, ensure_ascii=False),
            face_count=analysis.face_count,
            vector_embedding=serialize_vector(analysis.vector_embedding),
            duration_seconds=analysis.metadata.duration_seconds,
            frame_width=analysis.metadata.frame_width,
            frame_height=analysis.metadata.frame_height,
            fps=analysis.metadata.fps,
            sampled_frame_count=analysis.sampled_frame_count,
            taken_at=datetime.fromtimestamp(video_path.stat().st_mtime),
        )
        self.repository.save_video(video)

    def _copy_to_storage(self, photo_path: Path) -> Path:
        day = datetime.now().strftime("%Y%m%d")
        target_dir = self.settings.import_root / day
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / photo_path.name

        if target_path.exists():
            stem = photo_path.stem
            suffix = photo_path.suffix
            counter = 1
            while target_path.exists():
                target_path = target_dir / f"{stem}_{counter}{suffix}"
                counter += 1

        shutil.copy2(photo_path, target_path)
        return target_path

    @staticmethod
    def _sha256(photo_path: Path) -> str:
        digest = hashlib.sha256()
        with photo_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _phash(photo_path: Path) -> str | None:
        try:
            with Image.open(photo_path) as image:
                return str(imagehash.phash(image))
        except Exception:
            return None
