import json
from pathlib import Path
import shutil
from uuid import uuid4

import numpy as np
from sqlmodel import Session

from app.config import Settings, get_settings
from app.embeddings import VectorEmbeddingService, deserialize_vector, serialize_vector
from app.face_clustering import FaceClusteringService
from app.models import PersonProfile, PersonSample
from app.repository import GalleryRepository
from app.schemas import decode_json_list


class PersonLibraryService:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.repository = GalleryRepository(session)
        self.face_service = FaceClusteringService(session, self.settings)
        self.vectorizer = VectorEmbeddingService()

    def create_person(self, name: str) -> PersonProfile:
        normalized_name = self.normalize_name(name)
        existing = self.repository.get_person_profile_by_name(normalized_name)
        if existing is not None:
            return existing

        profile = PersonProfile(
            name=name.strip(),
            normalized_name=normalized_name,
        )
        return self.repository.create_person_profile(profile)

    def rename_person(self, person_id: int, name: str) -> PersonProfile | None:
        profile = self.repository.get_person_profile(person_id)
        if profile is None:
            return None

        normalized_name = self.normalize_name(name)
        existing = self.repository.get_person_profile_by_name(normalized_name)
        if existing is not None and existing.id != person_id:
            raise ValueError("Another person already uses this name")

        previous_name = profile.name
        profile.name = name.strip()
        profile.normalized_name = normalized_name
        profile = self.repository.save_person_profile(profile)
        self.face_service.associate_person_with_clusters(profile)
        self._sync_bound_cluster_names(profile.id or 0, previous_name=previous_name, next_name=profile.name)
        self._refresh_photos_for_person(profile.id or 0, strip_names=[previous_name])
        return profile

    def delete_person(self, person_id: int) -> bool:
        profile = self.repository.get_person_profile(person_id)
        if profile is None:
            return False

        affected_labels = [
            cluster.label for cluster in self.repository.list_face_clusters_by_person(person_id, limit=5000)
        ]
        self.face_service.dissociate_person(person_id, profile.name)
        self._refresh_photos_for_cluster_labels(affected_labels, strip_names=[profile.name])

        for sample in self.repository.list_person_samples(person_id):
            Path(sample.storage_path).unlink(missing_ok=True)
            self.repository.delete_person_sample(sample)

        person_root = self.settings.person_library_root / f"person-{person_id}"
        if person_root.exists():
            shutil.rmtree(person_root, ignore_errors=True)

        self.repository.delete_person_profile(profile)
        return True

    def add_sample(
        self,
        person_id: int,
        *,
        file_bytes: bytes,
        filename: str,
    ) -> PersonProfile:
        profile = self.repository.get_person_profile(person_id)
        if profile is None:
            raise ValueError("Person not found")
        if not file_bytes:
            raise ValueError("Empty person sample upload")

        suffix = Path(filename or "sample.jpg").suffix.lower() or ".jpg"
        target_dir = self.settings.person_library_root / f"person-{person_id}"
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"{uuid4().hex}{suffix}"
        target_path.write_bytes(file_bytes)

        embeddings = self.face_service.extract_face_embeddings(target_path)
        if not embeddings:
            target_path.unlink(missing_ok=True)
            raise ValueError("No face detected in the uploaded reference image")

        sample = self.repository.create_person_sample(
            PersonSample(
                person_id=person_id,
                original_filename=filename or target_path.name,
                storage_path=str(target_path),
                embedding=serialize_vector(embeddings[0]),
            )
        )

        profile = self._refresh_profile_embeddings(person_id, fallback_example_sample_id=sample.id)
        self.face_service.associate_person_with_clusters(profile)
        self._refresh_photos_for_person(person_id, strip_names=[profile.name])
        return profile

    def delete_sample(self, person_id: int, sample_id: int) -> PersonProfile | None:
        profile = self.repository.get_person_profile(person_id)
        if profile is None:
            return None

        sample = self.repository.get_person_sample(sample_id)
        if sample is None or sample.person_id != person_id:
            raise ValueError("Person sample not found")

        Path(sample.storage_path).unlink(missing_ok=True)
        self.repository.delete_person_sample(sample)

        affected_labels = [
            cluster.label for cluster in self.repository.list_face_clusters_by_person(person_id, limit=5000)
        ]
        profile = self._refresh_profile_embeddings(person_id)
        if profile is None:
            return None
        self.face_service.associate_person_with_clusters(profile)
        affected_labels.extend(
            cluster.label for cluster in self.repository.list_face_clusters_by_person(person_id, limit=5000)
        )
        self._refresh_photos_for_cluster_labels(list(dict.fromkeys(affected_labels)), strip_names=[profile.name])
        return profile

    @staticmethod
    def normalize_name(name: str) -> str:
        return " ".join(name.strip().lower().split())

    @staticmethod
    def _average_embeddings(values: list[str | None]) -> str | None:
        vectors: list[list[float]] = []
        for value in values:
            vector = deserialize_vector(value)
            if vector:
                vectors.append(vector)
        if not vectors:
            return None
        matrix = np.asarray(vectors, dtype=np.float32)
        mean_vector = matrix.mean(axis=0)
        norm = float(np.linalg.norm(mean_vector))
        if norm > 0:
            mean_vector = mean_vector / norm
        return serialize_vector(mean_vector.tolist())

    def _refresh_profile_embeddings(
        self,
        person_id: int,
        *,
        fallback_example_sample_id: int | None = None,
    ) -> PersonProfile | None:
        profile = self.repository.get_person_profile(person_id)
        if profile is None:
            return None

        samples = self.repository.list_person_samples(person_id)
        profile.centroid = self._average_embeddings([sample.embedding for sample in samples])
        profile.sample_count = len(samples)
        profile.example_sample_id = samples[0].id if samples else fallback_example_sample_id
        if profile.example_sample_id is not None and not any(
            sample.id == profile.example_sample_id for sample in samples
        ):
            profile.example_sample_id = samples[0].id if samples else None
        return self.repository.save_person_profile(profile)

    def _sync_bound_cluster_names(self, person_id: int, *, previous_name: str, next_name: str) -> None:
        normalized_previous_name = self.normalize_name(previous_name)
        for cluster in self.repository.list_face_clusters_by_person(person_id):
            if cluster.display_name in (None, "", previous_name) or (
                cluster.display_name and self.normalize_name(cluster.display_name) == normalized_previous_name
            ):
                cluster.display_name = next_name
                self.repository.save_face_cluster(cluster)

    def _refresh_photos_for_person(self, person_id: int, strip_names: list[str] | None = None) -> None:
        cluster_labels = [
            cluster.label for cluster in self.repository.list_face_clusters_by_person(person_id, limit=5000)
        ]
        self._refresh_photos_for_cluster_labels(cluster_labels, strip_names=strip_names or [])

    def _refresh_photos_for_cluster_labels(self, cluster_labels: list[str], strip_names: list[str]) -> None:
        normalized_strip_names = {self.normalize_name(name) for name in strip_names if name.strip()}
        relevant_label_set = set(cluster_labels)

        for photo in self.repository.list_searchable_photos(limit=5000):
            photo_labels = decode_json_list(photo.face_clusters)
            current_people = decode_json_list(photo.people)
            should_refresh = bool(relevant_label_set.intersection(photo_labels))
            if not should_refresh and normalized_strip_names:
                should_refresh = any(
                    self.normalize_name(person_name) in normalized_strip_names for person_name in current_people
                )
            if not should_refresh:
                continue

            base_people = [
                person_name
                for person_name in current_people
                if self.normalize_name(person_name) not in normalized_strip_names
            ]
            resolved_face_names = self.face_service.resolve_labels(photo_labels).names
            merged_people = list(dict.fromkeys(base_people + resolved_face_names))
            photo.people = json.dumps(base_people, ensure_ascii=False)

            photo_path = Path(photo.storage_path)
            if photo_path.exists():
                photo.vector_embedding = serialize_vector(
                    self.vectorizer.embed_photo(
                        photo_path,
                        caption=photo.caption,
                        ocr_text=photo.ocr_text,
                        people=merged_people,
                        scene_tags=decode_json_list(photo.scene_tags),
                        object_tags=decode_json_list(photo.object_tags),
                        phash=photo.phash,
                    )
                )
            self.repository.save_photo(photo)
