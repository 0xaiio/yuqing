from dataclasses import dataclass
import json
from pathlib import Path
import uuid

import numpy as np
from sqlmodel import Session

from app.config import Settings, get_settings
from app.embeddings import VectorEmbeddingService, cosine_similarity, deserialize_vector, serialize_vector
from app.face_engine import DeepFaceEngine
from app.models import FaceCluster, PersonProfile
from app.repository import GalleryRepository
from app.schemas import decode_json_list

FACE_EMBEDDING_DIM = 512
PERSON_MATCH_MARGIN = 0.04


@dataclass
class FaceClusteringResult:
    labels: list[str]
    names: list[str]
    face_count: int


class FaceClusteringService:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.repository = GalleryRepository(session)
        self.settings = settings or get_settings()
        self.engine = DeepFaceEngine(self.settings)

    def analyze_photo(self, photo_path: Path, example_photo_id: int | None = None) -> FaceClusteringResult:
        embeddings = self.extract_face_embeddings(photo_path)
        if not embeddings:
            return FaceClusteringResult(labels=[], names=[], face_count=0)

        labels: list[str] = []
        names: list[str] = []
        for embedding in embeddings:
            cluster = self._match_or_create_cluster(embedding, example_photo_id=example_photo_id)
            person_match = self._match_person_profile(embedding)
            if person_match is not None:
                if cluster.person_profile_id != person_match.id:
                    cluster.person_profile_id = person_match.id
                if not cluster.display_name or self._normalize_name(cluster.display_name) != person_match.normalized_name:
                    cluster.display_name = person_match.name
                cluster = self.repository.save_face_cluster(cluster)

            if cluster.label not in labels:
                labels.append(cluster.label)
            if cluster.display_name and cluster.display_name not in names:
                names.append(cluster.display_name)
            if person_match and person_match.name not in names:
                names.append(person_match.name)

        return FaceClusteringResult(labels=labels, names=names, face_count=len(embeddings))

    def resolve_labels(self, labels: list[str]) -> FaceClusteringResult:
        if not labels:
            return FaceClusteringResult(labels=[], names=[], face_count=0)

        clusters = self.repository.get_face_clusters_by_labels(labels)
        people = self.repository.get_person_profiles_by_ids(
            [cluster.person_profile_id for cluster in clusters.values() if cluster.person_profile_id]
        )
        names = [
            cluster.display_name
            for label in labels
            if (cluster := clusters.get(label)) and cluster.display_name
        ]
        names.extend(
            person.name
            for label in labels
            if (cluster := clusters.get(label))
            and cluster.person_profile_id
            and (person := people.get(cluster.person_profile_id))
        )
        return FaceClusteringResult(labels=labels, names=list(dict.fromkeys(names)), face_count=len(labels))

    def rename_cluster(self, label: str, display_name: str | None) -> FaceCluster | None:
        cluster = self.repository.get_face_cluster_by_label(label)
        if cluster is None:
            return None
        cluster.display_name = display_name or None
        return self.repository.save_face_cluster(cluster)

    def associate_person_with_clusters(self, person: PersonProfile) -> list[FaceCluster]:
        if not person.id:
            return []

        updated_clusters: list[FaceCluster] = []
        for cluster in self.repository.list_face_clusters(limit=5000):
            cluster_vector = deserialize_vector(cluster.centroid)
            if not self._is_current_embedding(cluster_vector):
                continue

            score = self._score_person_profile(person, cluster_vector)
            should_bind = score >= self.settings.person_recognition_similarity_threshold
            if should_bind and cluster.person_profile_id not in (None, person.id):
                continue

            if should_bind:
                cluster.person_profile_id = person.id
                cluster.display_name = person.name
                updated_clusters.append(self.repository.save_face_cluster(cluster))
                continue

            if cluster.person_profile_id == person.id:
                cluster.person_profile_id = None
                if cluster.display_name and self._normalize_name(cluster.display_name) == person.normalized_name:
                    cluster.display_name = None
                updated_clusters.append(self.repository.save_face_cluster(cluster))

        return updated_clusters

    def dissociate_person(self, person_id: int, person_name: str) -> list[FaceCluster]:
        normalized_name = self._normalize_name(person_name)
        updated_clusters: list[FaceCluster] = []
        for cluster in self.repository.list_face_clusters_by_person(person_id, limit=5000):
            cluster.person_profile_id = None
            if cluster.display_name and self._normalize_name(cluster.display_name) == normalized_name:
                cluster.display_name = None
            updated_clusters.append(self.repository.save_face_cluster(cluster))
        return updated_clusters

    def extract_face_embeddings(self, photo_path: Path) -> list[list[float]]:
        return self.engine.extract_face_embeddings(photo_path, max_faces=self.settings.face_detection_max_faces)

    def rank_person_profiles(
        self,
        embedding: list[float],
        limit: int = 5,
    ) -> list[tuple[PersonProfile, float]]:
        scores: list[tuple[PersonProfile, float]] = []
        for person in self.repository.list_person_profiles(limit=2000):
            score = self._score_person_profile(person, embedding)
            if score <= 0:
                continue
            scores.append((person, score))
        scores.sort(key=lambda item: item[1], reverse=True)
        return scores[:limit]

    def score_person_profile(
        self,
        person: PersonProfile,
        embedding: list[float],
    ) -> float:
        return self._score_person_profile(person, embedding)

    def refresh_face_index_if_needed(self) -> bool:
        if not self._has_legacy_embeddings():
            return False
        self.rebuild_face_index()
        return True

    def rebuild_face_index(self) -> None:
        self._refresh_person_sample_embeddings()

        for cluster in self.repository.list_face_clusters(limit=5000):
            self.repository.delete_face_cluster(cluster)

        person_name_keys = {
            self._normalize_name(person.name)
            for person in self.repository.list_person_profiles(limit=5000)
            if person.name
        }
        vectorizer = VectorEmbeddingService()

        for photo in self.repository.list_searchable_photos(limit=5000):
            photo_path = Path(photo.storage_path)
            if not photo_path.exists():
                continue

            face_result = self.analyze_photo(photo_path, example_photo_id=photo.id)
            base_people = [
                item
                for item in decode_json_list(photo.people)
                if self._normalize_name(item) not in person_name_keys
            ]
            merged_people = list(dict.fromkeys(base_people + face_result.names))

            photo.people = json.dumps(base_people, ensure_ascii=False)
            photo.face_clusters = json.dumps(face_result.labels, ensure_ascii=False)
            photo.face_count = face_result.face_count
            photo.vector_embedding = serialize_vector(
                vectorizer.embed_photo(
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

    def _refresh_person_sample_embeddings(self) -> None:
        for person in self.repository.list_person_profiles(limit=5000):
            samples = self.repository.list_person_samples(person.id or 0)
            for sample in samples:
                sample_path = Path(sample.storage_path)
                if not sample_path.exists():
                    continue
                embeddings = self.extract_face_embeddings(sample_path)
                if not embeddings:
                    continue
                sample.embedding = serialize_vector(embeddings[0])
                self.repository.save_person_sample(sample)

            person.sample_count = len(samples)
            person.example_sample_id = samples[0].id if samples else None
            person.centroid = self._average_embeddings([sample.embedding for sample in samples])
            self.repository.save_person_profile(person)

    def _match_or_create_cluster(
        self,
        embedding: list[float],
        *,
        example_photo_id: int | None,
    ) -> FaceCluster:
        best_cluster: FaceCluster | None = None
        best_score = -1.0

        for cluster in self.repository.list_face_clusters(limit=2000):
            centroid = deserialize_vector(cluster.centroid)
            if not self._is_current_embedding(centroid):
                continue
            score = cosine_similarity(embedding, centroid)
            if score > best_score:
                best_score = score
                best_cluster = cluster

        if best_cluster is not None and best_score >= self.settings.face_cluster_similarity_threshold:
            previous_centroid = np.asarray(deserialize_vector(best_cluster.centroid), dtype=np.float32)
            next_centroid = np.asarray(embedding, dtype=np.float32)
            if previous_centroid.size == next_centroid.size and previous_centroid.size > 0:
                merged = previous_centroid * 0.7 + next_centroid * 0.3
                best_cluster.centroid = serialize_vector(self._normalize(merged).tolist())
            if best_cluster.example_photo_id is None and example_photo_id is not None:
                best_cluster.example_photo_id = example_photo_id
            return self.repository.save_face_cluster(best_cluster)

        new_cluster = FaceCluster(
            label=f"face-{uuid.uuid4().hex[:8]}",
            centroid=serialize_vector(embedding),
            example_photo_id=example_photo_id,
        )
        return self.repository.create_face_cluster(new_cluster)

    def _match_person_profile(self, embedding: list[float]) -> PersonProfile | None:
        best_match: PersonProfile | None = None
        best_score = -1.0
        second_best = -1.0

        for person in self.repository.list_person_profiles(limit=2000):
            score = self._score_person_profile(person, embedding)
            if score > best_score:
                second_best = best_score
                best_score = score
                best_match = person
            elif score > second_best:
                second_best = score

        if best_match is None:
            return None
        if best_score < self.settings.person_recognition_similarity_threshold:
            return None
        if second_best > 0 and (best_score - second_best) < PERSON_MATCH_MARGIN:
            return None
        return best_match

    def _score_person_profile(self, person: PersonProfile, embedding: list[float]) -> float:
        centroid_vector = deserialize_vector(person.centroid)
        centroid_score = 0.0
        if self._is_current_embedding(centroid_vector):
            centroid_score = cosine_similarity(embedding, centroid_vector)

        sample_scores: list[float] = []
        for sample in self.repository.list_person_samples(person.id or 0):
            sample_vector = deserialize_vector(sample.embedding)
            if not self._is_current_embedding(sample_vector):
                continue
            sample_scores.append(cosine_similarity(embedding, sample_vector))

        if not sample_scores:
            return centroid_score

        ranked_scores = sorted(sample_scores, reverse=True)
        best_sample_score = ranked_scores[0]
        sample_mean = sum(ranked_scores[: min(3, len(ranked_scores))]) / min(3, len(ranked_scores))
        return max(centroid_score, 0.45 * best_sample_score + 0.35 * sample_mean + 0.2 * centroid_score)

    def _has_legacy_embeddings(self) -> bool:
        for person in self.repository.list_person_profiles(limit=5000):
            person_vector = deserialize_vector(person.centroid)
            if person_vector and not self._is_current_embedding(person_vector):
                return True
            for sample in self.repository.list_person_samples(person.id or 0):
                vector = deserialize_vector(sample.embedding)
                if vector and not self._is_current_embedding(vector):
                    return True

        for cluster in self.repository.list_face_clusters(limit=5000):
            vector = deserialize_vector(cluster.centroid)
            if vector and not self._is_current_embedding(vector):
                return True
        return False

    @staticmethod
    def _is_current_embedding(vector: list[float] | None) -> bool:
        return bool(vector) and len(vector) == FACE_EMBEDDING_DIM

    @staticmethod
    def _average_embeddings(values: list[str | None]) -> str | None:
        vectors = [deserialize_vector(value) for value in values if value]
        vectors = [vector for vector in vectors if len(vector) == FACE_EMBEDDING_DIM]
        if not vectors:
            return None
        matrix = np.asarray(vectors, dtype=np.float32)
        mean_vector = matrix.mean(axis=0)
        return serialize_vector(FaceClusteringService._normalize(mean_vector).tolist())

    @staticmethod
    def _normalize(vector: np.ndarray) -> np.ndarray:
        norm = float(np.linalg.norm(vector))
        if norm == 0:
            return vector
        return vector / norm

    @staticmethod
    def _normalize_name(value: str | None) -> str:
        if not value:
            return ""
        return " ".join(value.strip().lower().split())
