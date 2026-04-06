from __future__ import annotations

from pathlib import Path
import shutil

from sqlmodel import Session

from app.config import Settings, get_settings
from app.repository import GalleryRepository
from app.schemas import VideoSearchHit, VideoSearchResponse, decode_json_list
from app.serializers import build_video_read


class MediaLibraryService:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.repository = GalleryRepository(session)

    def delete_photo(self, photo_id: int, delete_source_file: bool = False) -> bool:
        photo = self.repository.get_photo(photo_id)
        if photo is None:
            return False

        photo_labels = decode_json_list(photo.face_clusters)
        storage_path = Path(photo.storage_path)
        if delete_source_file:
            self._delete_original_source_file(photo.original_path, photo.source_id, storage_path)

        self.repository.delete_photo(photo)
        storage_path.unlink(missing_ok=True)
        self._cleanup_face_clusters(photo_labels)
        return True

    def delete_video(self, video_id: int, delete_source_file: bool = False) -> bool:
        video = self.repository.get_video(video_id)
        if video is None:
            return False

        video_labels = decode_json_list(video.face_clusters)
        storage_path = Path(video.storage_path)
        thumbnail_path = Path(video.thumbnail_path) if video.thumbnail_path else None
        if delete_source_file:
            self._delete_original_source_file(video.original_path, video.source_id, storage_path)

        self.repository.delete_video(video)
        storage_path.unlink(missing_ok=True)
        if thumbnail_path:
            thumbnail_path.unlink(missing_ok=True)
            self._remove_video_artifacts(thumbnail_path.parent)
        self._cleanup_face_clusters(video_labels)
        return True

    def list_videos_by_face_clusters(
        self,
        cluster_labels: list[str],
        limit: int = 48,
    ) -> VideoSearchResponse:
        label_set = {label for label in cluster_labels if label}
        if not label_set:
            return VideoSearchResponse(total=0, hits=[])

        hits: list[VideoSearchHit] = []
        for video in self.repository.list_searchable_videos(limit=5000):
            video_labels = set(decode_json_list(video.face_clusters))
            if not video_labels.intersection(label_set):
                continue
            hits.append(
                VideoSearchHit(
                    score=1.0,
                    video=build_video_read(self.repository, video),
                )
            )

        hits.sort(key=lambda item: item.video.created_at, reverse=True)
        return VideoSearchResponse(total=len(hits), hits=hits[:limit])

    def list_videos_by_person(self, person_id: int, limit: int = 48) -> VideoSearchResponse:
        labels = [
            cluster.label
            for cluster in self.repository.list_face_clusters_by_person(person_id, limit=5000)
        ]
        return self.list_videos_by_face_clusters(labels, limit=limit)

    def _cleanup_face_clusters(self, preferred_labels: list[str]) -> None:
        labels_in_use: dict[str, int | None] = {}
        for photo in self.repository.list_searchable_photos(limit=5000):
            for label in decode_json_list(photo.face_clusters):
                if label not in labels_in_use:
                    labels_in_use[label] = photo.id

        for video in self.repository.list_searchable_videos(limit=5000):
            for label in decode_json_list(video.face_clusters):
                labels_in_use.setdefault(label, None)

        prioritized_labels = list(dict.fromkeys(preferred_labels + list(labels_in_use.keys())))
        clusters = self.repository.get_face_clusters_by_labels(prioritized_labels)
        for label, cluster in clusters.items():
            if label not in labels_in_use:
                self.repository.delete_face_cluster(cluster)
                continue

            preferred_example_photo_id = labels_in_use[label]
            if cluster.example_photo_id != preferred_example_photo_id:
                cluster.example_photo_id = preferred_example_photo_id
                self.repository.save_face_cluster(cluster)

    def _remove_video_artifacts(self, target_dir: Path) -> None:
        try:
            target_resolved = target_dir.resolve()
            frame_root_resolved = self.settings.video_frame_root.resolve()
        except FileNotFoundError:
            return

        if not self._is_within(target_resolved, frame_root_resolved):
            return
        if not target_dir.exists():
            return
        shutil.rmtree(target_dir, ignore_errors=True)

    def _delete_original_source_file(
        self,
        original_path_value: str,
        source_id: int | None,
        storage_path: Path,
    ) -> None:
        if source_id is None:
            return

        source = self.repository.get_source(source_id)
        if source is None:
            return

        original_path = Path(original_path_value)
        if not original_path.exists():
            return

        original_resolved = original_path.resolve()
        source_root = Path(source.root_path).resolve()
        storage_resolved = storage_path.resolve()

        if not self._is_within(original_resolved, source_root):
            return

        if original_resolved == storage_resolved:
            return

        original_path.unlink()
        self._prune_empty_source_directories(original_path.parent, source_root)

    def _prune_empty_source_directories(self, start_dir: Path, root_dir: Path) -> None:
        current = start_dir
        while True:
            try:
                current_resolved = current.resolve()
            except FileNotFoundError:
                break

            if current_resolved == root_dir:
                break
            if not self._is_within(current_resolved, root_dir):
                break
            if not current.exists() or any(current.iterdir()):
                break
            current.rmdir()
            current = current.parent

    @staticmethod
    def _is_within(target: Path, root: Path) -> bool:
        try:
            target.relative_to(root)
            return True
        except ValueError:
            return False
