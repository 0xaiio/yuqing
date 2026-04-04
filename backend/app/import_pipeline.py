from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil

import imagehash
from PIL import Image
from sqlmodel import Session

from app.ai import AIAnalyzer
from app.config import get_settings
from app.connectors import ConnectorRegistry
from app.embeddings import VectorEmbeddingService, serialize_vector
from app.face_clustering import FaceClusteringService
from app.models import ImportJob, Photo, Source
from app.repository import GalleryRepository


class ImportPipeline:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = GalleryRepository(session)
        self.registry = ConnectorRegistry()
        self.analyzer = AIAnalyzer()
        self.vectorizer = VectorEmbeddingService()
        self.face_clusterer = FaceClusteringService(session)
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

            for photo_path in paths:
                scanned_count += 1
                sha256 = self._sha256(photo_path)
                existing = self.repository.find_photo_by_sha256(sha256)
                if existing is not None:
                    duplicate_count += 1
                    continue

                storage_path = self._copy_to_storage(photo_path)
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
