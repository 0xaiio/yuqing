import json
from pathlib import Path
import shutil
from uuid import uuid4

import numpy as np
from sqlmodel import Session

from app.config import Settings, get_settings
from app.embeddings import VectorEmbeddingService, deserialize_vector, serialize_vector
from app.face_clustering import PERSON_MATCH_MARGIN, FaceClusteringService
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

    def list_cluster_correction_candidates(self, person_id: int, limit: int = 80) -> list[dict[str, object]]:
        profile = self.repository.get_person_profile(person_id)
        if profile is None:
            raise ValueError("Person not found")

        cluster_stats = self._collect_face_cluster_stats()
        people_by_id = self.repository.get_person_profiles_by_ids(
            [
                cluster.person_profile_id
                for cluster in self.repository.list_face_clusters(limit=5000)
                if cluster.person_profile_id
            ]
        )

        candidates: list[dict[str, object]] = []
        for cluster in self.repository.list_face_clusters(limit=5000):
            embedding = deserialize_vector(cluster.centroid)
            if not embedding:
                continue

            selected_score = self.face_service.score_person_profile(profile, embedding)
            ranked_people = self.face_service.rank_person_profiles(embedding, limit=3)
            competitor_score = 0.0
            if ranked_people:
                top_person, top_score = ranked_people[0]
                if top_person.id == person_id:
                    competitor_score = ranked_people[1][1] if len(ranked_people) > 1 else 0.0
                else:
                    competitor_score = top_score

            current_person = people_by_id.get(cluster.person_profile_id or 0)
            recommended = (
                selected_score >= self.settings.person_recognition_similarity_threshold
                and (selected_score - competitor_score) >= PERSON_MATCH_MARGIN
            )
            candidates.append(
                {
                    "label": cluster.label,
                    "display_name": cluster.display_name,
                    "example_photo_id": cluster.example_photo_id,
                    "photo_count": int(cluster_stats.get(cluster.label, {}).get("photo_count", 0)),
                    "score": selected_score,
                    "competitor_score": competitor_score,
                    "margin": selected_score - competitor_score,
                    "current_person_id": current_person.id if current_person and current_person.id else None,
                    "current_person_name": current_person.name if current_person else None,
                    "linked_to_selected_person": cluster.person_profile_id == person_id,
                    "recommended": recommended,
                }
            )

        candidates.sort(
            key=lambda item: (
                int(bool(item["linked_to_selected_person"])),
                int(bool(item["recommended"])),
                float(item["score"]),
                int(item["photo_count"]),
            ),
            reverse=True,
        )
        return candidates[:limit]

    def apply_cluster_correction(
        self,
        person_id: int,
        *,
        cluster_labels: list[str],
        action: str,
    ) -> tuple[PersonProfile | None, list[str]]:
        profile = self.repository.get_person_profile(person_id)
        if profile is None:
            return None, []
        if action not in {"bind", "unbind"}:
            raise ValueError("Unsupported correction action")

        labels = list(dict.fromkeys(label.strip() for label in cluster_labels if label.strip()))
        if not labels:
            raise ValueError("No face clusters selected")

        clusters_by_label = self.repository.get_face_clusters_by_labels(labels)
        previous_people = self.repository.get_person_profiles_by_ids(
            [
                cluster.person_profile_id
                for cluster in clusters_by_label.values()
                if cluster.person_profile_id and cluster.person_profile_id != person_id
            ]
        )

        strip_names = [profile.name]
        strip_names.extend(person.name for person in previous_people.values() if person.name)

        updated_labels: list[str] = []
        for label in labels:
            cluster = clusters_by_label.get(label)
            if cluster is None:
                continue

            changed = False
            if action == "bind":
                if cluster.person_profile_id != person_id:
                    cluster.person_profile_id = person_id
                    changed = True
                if cluster.display_name != profile.name:
                    cluster.display_name = profile.name
                    changed = True
            else:
                if cluster.person_profile_id != person_id:
                    continue
                cluster.person_profile_id = None
                if cluster.display_name and self.normalize_name(cluster.display_name) == profile.normalized_name:
                    cluster.display_name = None
                changed = True

            if not changed:
                continue

            self.repository.save_face_cluster(cluster)
            updated_labels.append(cluster.label)

        if updated_labels:
            self._refresh_photos_for_cluster_labels(updated_labels, strip_names=strip_names)

        return self.repository.get_person_profile(person_id), updated_labels

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

    def _collect_face_cluster_stats(self) -> dict[str, dict[str, object]]:
        stats: dict[str, dict[str, object]] = {}
        for photo in self.repository.list_searchable_photos(limit=5000):
            latest_time = photo.taken_at or photo.created_at
            for label in decode_json_list(photo.face_clusters):
                item = stats.setdefault(label, {"photo_count": 0, "latest_photo_at": None})
                item["photo_count"] = int(item["photo_count"]) + 1
                previous_latest = item["latest_photo_at"]
                if previous_latest is None or (latest_time and latest_time > previous_latest):
                    item["latest_photo_at"] = latest_time
        return stats
