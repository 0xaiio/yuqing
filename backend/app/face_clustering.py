from dataclasses import dataclass
import json
from pathlib import Path
import uuid

import cv2
import numpy as np
from sqlmodel import Session

from app.config import Settings, get_settings
from app.embeddings import cosine_similarity, deserialize_vector, serialize_vector
from app.models import FaceCluster, PersonProfile
from app.repository import GalleryRepository


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
        self._cascade = cv2.CascadeClassifier(
            str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml")
        )

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
                if not cluster.display_name:
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
        deduped_names = list(dict.fromkeys(names))
        return FaceClusteringResult(labels=labels, names=deduped_names, face_count=len(labels))

    def rename_cluster(self, label: str, display_name: str | None) -> FaceCluster | None:
        cluster = self.repository.get_face_cluster_by_label(label)
        if cluster is None:
            return None
        cluster.display_name = display_name or None
        return self.repository.save_face_cluster(cluster)

    def associate_person_with_clusters(self, person: PersonProfile) -> list[FaceCluster]:
        if not person.centroid:
            return []

        person_vector = deserialize_vector(person.centroid)
        if not person_vector:
            return []

        updated_clusters: list[FaceCluster] = []
        for cluster in self.repository.list_face_clusters(limit=5000):
            cluster_vector = deserialize_vector(cluster.centroid)
            if not cluster_vector:
                continue
            score = cosine_similarity(person_vector, cluster_vector)
            if score < self.settings.person_recognition_similarity_threshold:
                continue
            if cluster.person_profile_id not in (None, person.id):
                continue
            cluster.person_profile_id = person.id
            if not cluster.display_name:
                cluster.display_name = person.name
            updated_clusters.append(self.repository.save_face_cluster(cluster))
        return updated_clusters

    def extract_face_embeddings(self, photo_path: Path) -> list[list[float]]:
        return self._extract_face_embeddings(photo_path)

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
            centroid=json.dumps(embedding, ensure_ascii=False),
            example_photo_id=example_photo_id,
        )
        return self.repository.create_face_cluster(new_cluster)

    def _match_person_profile(self, embedding: list[float]) -> PersonProfile | None:
        best_match: PersonProfile | None = None
        best_score = -1.0

        for person in self.repository.list_person_profiles(limit=2000):
            centroid = deserialize_vector(person.centroid)
            score = cosine_similarity(embedding, centroid)
            if score > best_score:
                best_score = score
                best_match = person

        if best_match is None:
            return None
        if best_score < self.settings.person_recognition_similarity_threshold:
            return None
        return best_match

    def _extract_face_embeddings(self, photo_path: Path) -> list[list[float]]:
        image = cv2.imread(str(photo_path))
        if image is None:
            return []

        grayscale = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        detections = self._cascade.detectMultiScale(
            grayscale,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(40, 40),
        )
        if len(detections) == 0:
            return []

        embeddings: list[list[float]] = []
        sorted_detections = sorted(detections, key=lambda item: item[2] * item[3], reverse=True)[:6]
        for x, y, width, height in sorted_detections:
            face_crop = grayscale[y : y + height, x : x + width]
            if face_crop.size == 0:
                continue
            embeddings.append(self._face_embedding(face_crop))
        return embeddings

    def _face_embedding(self, face_crop: np.ndarray) -> list[float]:
        normalized = cv2.equalizeHist(face_crop)
        resized = cv2.resize(normalized, (32, 32), interpolation=cv2.INTER_AREA)
        flat = resized.astype(np.float32).flatten() / 255.0
        histogram, _ = np.histogram(flat, bins=16, range=(0, 1), density=True)
        edges = np.asarray(
            [
                np.abs(np.diff(resized.astype(np.float32), axis=0)).mean() / 255.0,
                np.abs(np.diff(resized.astype(np.float32), axis=1)).mean() / 255.0,
            ],
            dtype=np.float32,
        )
        embedding = np.concatenate([flat, histogram.astype(np.float32), edges], dtype=np.float32)
        return self._normalize(embedding).tolist()

    @staticmethod
    def _normalize(vector: np.ndarray) -> np.ndarray:
        norm = float(np.linalg.norm(vector))
        if norm == 0:
            return vector
        return vector / norm
