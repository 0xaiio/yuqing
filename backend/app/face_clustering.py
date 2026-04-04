from dataclasses import dataclass
import json
from pathlib import Path
import uuid

import cv2
import numpy as np
from sqlmodel import Session

from app.config import Settings, get_settings
from app.embeddings import VectorEmbeddingService, cosine_similarity, deserialize_vector, serialize_vector
from app.models import FaceCluster, PersonProfile
from app.repository import GalleryRepository
from app.schemas import decode_json_list

FACE_EMBEDDING_DIM = 482
PERSON_MATCH_MARGIN = 0.02


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
        self._eye_cascade = cv2.CascadeClassifier(
            str(Path(cv2.data.haarcascades) / "haarcascade_eye_tree_eyeglasses.xml")
        )
        self._clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))

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
        deduped_names = list(dict.fromkeys(names))
        return FaceClusteringResult(labels=labels, names=deduped_names, face_count=len(labels))

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
        return self._extract_face_embeddings(photo_path)

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

    def refresh_face_index_if_needed(self) -> bool:
        if not self._has_legacy_embeddings():
            return False
        self.rebuild_face_index()
        return True

    def rebuild_face_index(self) -> None:
        self._refresh_person_sample_embeddings()

        existing_clusters = self.repository.list_face_clusters(limit=5000)
        for cluster in existing_clusters:
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
                merged = previous_centroid * 0.65 + next_centroid * 0.35
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
                continue
            if score > second_best:
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
        return max(centroid_score, 0.5 * best_sample_score + 0.3 * sample_mean + 0.2 * centroid_score)

    def _extract_face_embeddings(self, photo_path: Path) -> list[list[float]]:
        image = cv2.imread(str(photo_path))
        if image is None:
            return []

        grayscale = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        detections = self._detect_faces(grayscale)
        if len(detections) == 0:
            return []

        embeddings: list[list[float]] = []
        for x, y, width, height in self._rank_detections(detections, grayscale.shape)[:6]:
            face_crop = self._extract_face_crop(grayscale, x, y, width, height)
            if face_crop.size == 0:
                continue
            embeddings.append(self._face_embedding(face_crop))
        return embeddings

    def _detect_faces(self, grayscale: np.ndarray) -> list[tuple[int, int, int, int]]:
        min_face = max(36, min(grayscale.shape[:2]) // 12)
        for candidate in (grayscale, self._clahe.apply(grayscale)):
            detections = self._cascade.detectMultiScale(
                candidate,
                scaleFactor=1.08,
                minNeighbors=5,
                minSize=(min_face, min_face),
            )
            if len(detections) > 0:
                return [tuple(map(int, detection)) for detection in detections]
        return []

    def _rank_detections(
        self,
        detections: list[tuple[int, int, int, int]],
        image_shape: tuple[int, int],
    ) -> list[tuple[int, int, int, int]]:
        image_height, image_width = image_shape[:2]
        center_x = image_width / 2.0
        center_y = image_height / 2.0

        def rank_key(item: tuple[int, int, int, int]) -> float:
            x, y, width, height = item
            area = float(width * height)
            face_center_x = x + width / 2.0
            face_center_y = y + height / 2.0
            normalized_distance = (
                ((face_center_x - center_x) / max(image_width, 1)) ** 2
                + ((face_center_y - center_y) / max(image_height, 1)) ** 2
            )
            position_bonus = max(0.55, 1.15 - normalized_distance * 2.1)
            return area * position_bonus

        return sorted(detections, key=rank_key, reverse=True)

    def _extract_face_crop(
        self,
        grayscale: np.ndarray,
        x: int,
        y: int,
        width: int,
        height: int,
    ) -> np.ndarray:
        pad_x = int(width * 0.18)
        pad_top = int(height * 0.24)
        pad_bottom = int(height * 0.14)

        x1 = max(0, x - pad_x)
        y1 = max(0, y - pad_top)
        x2 = min(grayscale.shape[1], x + width + pad_x)
        y2 = min(grayscale.shape[0], y + height + pad_bottom)

        face_crop = grayscale[y1:y2, x1:x2]
        if face_crop.size == 0:
            return face_crop
        return self._align_face(face_crop)

    def _align_face(self, face_crop: np.ndarray) -> np.ndarray:
        if face_crop.size == 0:
            return face_crop

        enhanced = self._clahe.apply(face_crop)
        upper_half = enhanced[: max(1, enhanced.shape[0] // 2), :]
        eyes = self._eye_cascade.detectMultiScale(
            upper_half,
            scaleFactor=1.08,
            minNeighbors=4,
            minSize=(10, 10),
        )
        if len(eyes) < 2:
            return enhanced

        best_pair: tuple[tuple[float, float], tuple[float, float]] | None = None
        best_score = -1.0
        eye_centers = [
            (eye_x + eye_width / 2.0, eye_y + eye_height / 2.0)
            for eye_x, eye_y, eye_width, eye_height in eyes
        ]
        for left_eye in eye_centers:
            for right_eye in eye_centers:
                if right_eye[0] <= left_eye[0]:
                    continue
                horizontal_distance = right_eye[0] - left_eye[0]
                vertical_offset = abs(right_eye[1] - left_eye[1])
                candidate_score = horizontal_distance - vertical_offset * 2.2
                if candidate_score > best_score:
                    best_score = candidate_score
                    best_pair = (left_eye, right_eye)

        if best_pair is None:
            return enhanced

        left_eye, right_eye = best_pair
        angle = np.degrees(np.arctan2(right_eye[1] - left_eye[1], right_eye[0] - left_eye[0]))
        rotation = cv2.getRotationMatrix2D(
            (enhanced.shape[1] / 2.0, enhanced.shape[0] / 2.0),
            -angle,
            1.0,
        )
        return cv2.warpAffine(
            enhanced,
            rotation,
            (enhanced.shape[1], enhanced.shape[0]),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REPLICATE,
        )

    def _face_embedding(self, face_crop: np.ndarray) -> list[float]:
        prepared = self._prepare_face(face_crop)
        intensity_histogram = self._intensity_histogram(prepared)
        gradient_descriptor = self._gradient_descriptor(prepared)
        lbp_descriptor = self._lbp_descriptor(prepared)
        dct_descriptor = self._dct_descriptor(prepared)
        symmetry_descriptor = self._symmetry_descriptor(prepared)

        embedding = np.concatenate(
            [
                self._normalize(intensity_histogram) * 0.08,
                self._normalize(gradient_descriptor) * 0.32,
                self._normalize(lbp_descriptor) * 0.38,
                self._normalize(dct_descriptor) * 0.16,
                self._normalize(symmetry_descriptor) * 0.06,
            ],
            dtype=np.float32,
        )
        return self._normalize(embedding).tolist()

    def _prepare_face(self, face_crop: np.ndarray) -> np.ndarray:
        enhanced = self._clahe.apply(face_crop)
        blurred = cv2.GaussianBlur(enhanced, (3, 3), 0)
        return cv2.resize(blurred, (96, 96), interpolation=cv2.INTER_AREA)

    @staticmethod
    def _intensity_histogram(face_crop: np.ndarray) -> np.ndarray:
        histogram, _ = np.histogram(face_crop, bins=16, range=(0, 256), density=True)
        return histogram.astype(np.float32)

    def _gradient_descriptor(self, face_crop: np.ndarray) -> np.ndarray:
        resized = cv2.resize(face_crop, (64, 64), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
        gradient_x = cv2.Sobel(resized, cv2.CV_32F, 1, 0, ksize=3)
        gradient_y = cv2.Sobel(resized, cv2.CV_32F, 0, 1, ksize=3)
        magnitude, angle = cv2.cartToPolar(gradient_x, gradient_y, angleInDegrees=True)
        angle = np.mod(angle, 180.0)

        cell_size = 16
        bins = 9
        features: list[np.ndarray] = []
        for row in range(4):
            for column in range(4):
                y1 = row * cell_size
                y2 = y1 + cell_size
                x1 = column * cell_size
                x2 = x1 + cell_size
                cell_magnitude = magnitude[y1:y2, x1:x2].flatten()
                cell_angle = angle[y1:y2, x1:x2].flatten()
                histogram, _ = np.histogram(
                    cell_angle,
                    bins=bins,
                    range=(0, 180),
                    weights=cell_magnitude,
                    density=False,
                )
                features.append(histogram.astype(np.float32))

        return np.concatenate(features, dtype=np.float32)

    def _lbp_descriptor(self, face_crop: np.ndarray) -> np.ndarray:
        resized = cv2.resize(face_crop, (64, 64), interpolation=cv2.INTER_AREA)
        center = resized[1:-1, 1:-1]
        lbp = np.zeros(center.shape, dtype=np.uint8)
        neighbors = [
            (-1, -1),
            (-1, 0),
            (-1, 1),
            (0, 1),
            (1, 1),
            (1, 0),
            (1, -1),
            (0, -1),
        ]
        for bit, (offset_y, offset_x) in enumerate(neighbors):
            lbp |= (
                (
                    resized[
                        1 + offset_y : 1 + offset_y + center.shape[0],
                        1 + offset_x : 1 + offset_x + center.shape[1],
                    ]
                    >= center
                ).astype(np.uint8)
                << bit
            )

        reduced = (lbp >> 4).astype(np.int32)
        trimmed = reduced[:60, :60]
        cell_size = 15
        features: list[np.ndarray] = []
        for row in range(4):
            for column in range(4):
                y1 = row * cell_size
                y2 = y1 + cell_size
                x1 = column * cell_size
                x2 = x1 + cell_size
                histogram, _ = np.histogram(
                    trimmed[y1:y2, x1:x2],
                    bins=16,
                    range=(0, 16),
                    density=True,
                )
                features.append(histogram.astype(np.float32))

        return np.concatenate(features, dtype=np.float32)

    @staticmethod
    def _dct_descriptor(face_crop: np.ndarray) -> np.ndarray:
        resized = cv2.resize(face_crop, (32, 32), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
        coefficients = cv2.dct(resized)
        block = np.abs(coefficients[:8, :8]).flatten()
        return block[1:].astype(np.float32)

    @staticmethod
    def _symmetry_descriptor(face_crop: np.ndarray) -> np.ndarray:
        resized = cv2.resize(face_crop, (48, 48), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
        left = resized[:, :24]
        right = np.flip(resized[:, 24:], axis=1)
        symmetry = 1.0 - float(np.mean(np.abs(left - right)))
        center_focus = float(resized[:, 18:30].mean())
        contrast = float(resized.std())
        return np.asarray([symmetry, center_focus, contrast], dtype=np.float32)

    def _has_legacy_embeddings(self) -> bool:
        for person in self.repository.list_person_profiles(limit=5000):
            person_vector = deserialize_vector(person.centroid)
            if person_vector and not self._is_current_embedding(person_vector):
                return True
            for person_sample in self.repository.list_person_samples(person.id or 0):
                vector = deserialize_vector(person_sample.embedding)
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
        vectors: list[list[float]] = []
        for value in values:
            vector = deserialize_vector(value)
            if vector and len(vector) == FACE_EMBEDDING_DIM:
                vectors.append(vector)
        if not vectors:
            return None
        matrix = np.asarray(vectors, dtype=np.float32)
        mean_vector = matrix.mean(axis=0)
        norm = float(np.linalg.norm(mean_vector))
        if norm > 0:
            mean_vector = mean_vector / norm
        return serialize_vector(mean_vector.tolist())

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
