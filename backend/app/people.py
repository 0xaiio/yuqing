from pathlib import Path
from uuid import uuid4

import numpy as np
from sqlmodel import Session

from app.config import Settings, get_settings
from app.embeddings import deserialize_vector, serialize_vector
from app.face_clustering import FaceClusteringService
from app.models import PersonProfile, PersonSample
from app.repository import GalleryRepository


class PersonLibraryService:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.repository = GalleryRepository(session)
        self.face_service = FaceClusteringService(session, self.settings)

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
        self._sync_bound_cluster_names(profile.id or 0, previous_name=previous_name, next_name=profile.name)
        return profile

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

        sample_embedding = embeddings[0]
        sample = self.repository.create_person_sample(
            PersonSample(
                person_id=person_id,
                original_filename=filename or target_path.name,
                storage_path=str(target_path),
                embedding=serialize_vector(sample_embedding),
            )
        )

        samples = self.repository.list_person_samples(person_id)
        profile.centroid = self._average_embeddings([sample.embedding for sample in samples])
        profile.sample_count = len(samples)
        if profile.example_sample_id is None:
            profile.example_sample_id = sample.id
        profile = self.repository.save_person_profile(profile)
        self.face_service.associate_person_with_clusters(profile)
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

    def _sync_bound_cluster_names(self, person_id: int, *, previous_name: str, next_name: str) -> None:
        for cluster in self.repository.list_face_clusters_by_person(person_id):
            if cluster.display_name in (None, "", previous_name):
                cluster.display_name = next_name
                self.repository.save_face_cluster(cluster)
