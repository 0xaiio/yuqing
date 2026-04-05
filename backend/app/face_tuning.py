from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

import numpy as np
from sqlmodel import Session

from app.config import Settings, get_settings
from app.embeddings import cosine_similarity, deserialize_vector
from app.face_clustering import FACE_EMBEDDING_DIM, PERSON_MATCH_MARGIN
from app.models import FaceCluster, PersonProfile
from app.repository import GalleryRepository
from app.schemas import decode_json_list


@dataclass
class PersonScoreProfile:
    person: PersonProfile
    centroid: list[float]
    samples: list[list[float]]


class FaceRuntimeConfigService:
    THRESHOLD_FIELDS = (
        "face_detection_confidence_threshold",
        "face_detection_nms_threshold",
        "face_cluster_similarity_threshold",
        "person_recognition_similarity_threshold",
    )

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def current_thresholds(self) -> dict[str, float]:
        return {
            field_name: float(getattr(self.settings, field_name))
            for field_name in self.THRESHOLD_FIELDS
        }

    def default_thresholds(self) -> dict[str, float]:
        return {
            field_name: float(Settings.model_fields[field_name].default)
            for field_name in self.THRESHOLD_FIELDS
        }

    def load_persisted_thresholds(self) -> dict[str, float]:
        payload = self.default_thresholds()
        config_path = self.settings.face_runtime_config_path
        if not config_path.exists():
            return payload

        try:
            raw_data = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return payload

        if not isinstance(raw_data, dict):
            return payload

        payload.update(self._sanitize_thresholds(raw_data))
        return payload

    def apply_persisted_thresholds(self) -> dict[str, float]:
        thresholds = self.load_persisted_thresholds()
        self._apply_thresholds(thresholds)
        return thresholds

    def save_thresholds(self, updates: dict[str, float]) -> dict[str, float]:
        merged = self.current_thresholds()
        merged.update(self._sanitize_thresholds(updates))
        self._persist_thresholds(merged)
        self._apply_thresholds(merged)
        return merged

    def reset_thresholds(self) -> dict[str, float]:
        thresholds = self.default_thresholds()
        self._persist_thresholds(thresholds)
        self._apply_thresholds(thresholds)
        return thresholds

    def _apply_thresholds(self, thresholds: dict[str, float]) -> None:
        for field_name, value in thresholds.items():
            setattr(self.settings, field_name, float(value))

    def _persist_thresholds(self, thresholds: dict[str, float]) -> None:
        config_path = self.settings.face_runtime_config_path
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps(thresholds, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _sanitize_thresholds(self, payload: dict[str, object]) -> dict[str, float]:
        thresholds: dict[str, float] = {}
        for field_name in self.THRESHOLD_FIELDS:
            if field_name not in payload:
                continue
            value = float(payload[field_name])
            if value < 0 or value > 1:
                raise ValueError(f"{field_name} must be between 0 and 1")
            thresholds[field_name] = value
        return thresholds


class FaceTuningService:
    SCORE_BANDS = (0.0, 0.35, 0.45, 0.5, 0.55, 0.6, 0.7, 1.01)

    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.repository = GalleryRepository(session)
        self.runtime = FaceRuntimeConfigService(self.settings)

    def build_bundle(self, threshold_overrides: dict[str, float] | None = None) -> dict[str, object]:
        thresholds = self.runtime.current_thresholds()
        if threshold_overrides:
            thresholds.update(self.runtime._sanitize_thresholds(threshold_overrides))
        return {
            "thresholds": thresholds,
            "defaults": self.runtime.default_thresholds(),
            "preview": self.preview(thresholds),
        }

    def update_thresholds(
        self,
        updates: dict[str, float],
        *,
        rebuild_index: bool = False,
    ) -> dict[str, object]:
        thresholds = self.runtime.save_thresholds(updates)
        if rebuild_index:
            from app.face_clustering import FaceClusteringService

            FaceClusteringService(self.session, self.settings).rebuild_face_index()
        return {
            "thresholds": thresholds,
            "defaults": self.runtime.default_thresholds(),
            "preview": self.preview(thresholds),
        }

    def preview(self, thresholds: dict[str, float]) -> dict[str, object]:
        face_cluster_stats = self._collect_face_cluster_stats()
        photos = self.repository.list_searchable_photos(limit=5000)
        all_clusters = self.repository.list_face_clusters(limit=5000)
        valid_clusters = [
            (cluster, vector)
            for cluster in all_clusters
            if (vector := deserialize_vector(cluster.centroid)) and len(vector) == FACE_EMBEDDING_DIM
        ]
        preview_clusters = valid_clusters[: self.settings.face_tuning_preview_cluster_limit]

        person_profiles = self._build_person_profiles()
        people_by_id = {profile.person.id or 0: profile.person for profile in person_profiles}
        linked_clusters = sum(1 for cluster, _ in valid_clusters if cluster.person_profile_id)

        merge_preview = self._build_merge_preview(preview_clusters, face_cluster_stats, thresholds)
        person_preview = self._build_person_preview(
            preview_clusters,
            face_cluster_stats,
            person_profiles,
            people_by_id,
            thresholds,
        )

        return {
            "total_clusters": len(valid_clusters),
            "preview_cluster_count": len(preview_clusters),
            "total_people": len(person_profiles),
            "total_photos": len(photos),
            "linked_clusters": linked_clusters,
            "merge_candidate_count": merge_preview["candidate_count"],
            "ambiguous_merge_count": merge_preview["ambiguous_count"],
            "person_candidate_count": person_preview["candidate_count"],
            "ambiguous_person_match_count": person_preview["ambiguous_count"],
            "nearest_neighbor_mean_score": merge_preview["mean_score"],
            "best_person_mean_score": person_preview["mean_score"],
            "cluster_similarity_bands": merge_preview["bands"],
            "person_score_bands": person_preview["bands"],
            "borderline_merges": merge_preview["borderline"],
            "borderline_person_matches": person_preview["borderline"],
            "notes": [
                "聚类阈值和人物识别阈值的可视化基于当前数据库中的 512 维人脸向量采样预览。",
                "检测置信度和 NMS 阈值会影响后续重建时的人脸检测结果，建议保存后执行一次重建索引。",
            ],
        }

    def _build_merge_preview(
        self,
        preview_clusters: list[tuple[FaceCluster, list[float]]],
        face_cluster_stats: dict[str, dict[str, object]],
        thresholds: dict[str, float],
    ) -> dict[str, object]:
        merge_threshold = thresholds["face_cluster_similarity_threshold"]
        if len(preview_clusters) < 2:
            return {
                "candidate_count": 0,
                "ambiguous_count": 0,
                "mean_score": 0.0,
                "bands": self._build_score_bands([]),
                "borderline": [],
            }

        matrix = np.asarray([vector for _, vector in preview_clusters], dtype=np.float32)
        similarity = matrix @ matrix.T
        np.fill_diagonal(similarity, -1.0)
        best_indices = similarity.argmax(axis=1)
        best_scores = similarity[np.arange(similarity.shape[0]), best_indices]

        rows: list[dict[str, object]] = []
        for index, ((cluster, _), neighbor_index) in enumerate(zip(preview_clusters, best_indices, strict=False)):
            neighbor_cluster = preview_clusters[int(neighbor_index)][0]
            score = float(best_scores[index])
            rows.append(
                {
                    "label": cluster.label,
                    "display_name": cluster.display_name,
                    "photo_count": int(face_cluster_stats.get(cluster.label, {}).get("photo_count", 0)),
                    "neighbor_label": neighbor_cluster.label,
                    "neighbor_display_name": neighbor_cluster.display_name,
                    "neighbor_photo_count": int(
                        face_cluster_stats.get(neighbor_cluster.label, {}).get("photo_count", 0)
                    ),
                    "score": score,
                    "distance_to_threshold": abs(score - merge_threshold),
                }
            )

        borderline = [
            row
            for row in sorted(rows, key=lambda item: float(item["distance_to_threshold"]))[:12]
            if float(row["score"]) > 0
        ]
        ambiguous_count = sum(
            1 for row in rows if merge_threshold - 0.03 <= float(row["score"]) < merge_threshold
        )
        mean_score = float(np.mean(best_scores)) if len(best_scores) else 0.0
        return {
            "candidate_count": sum(1 for row in rows if float(row["score"]) >= merge_threshold),
            "ambiguous_count": ambiguous_count,
            "mean_score": mean_score,
            "bands": self._build_score_bands([float(score) for score in best_scores if score >= 0]),
            "borderline": borderline,
        }

    def _build_person_preview(
        self,
        preview_clusters: list[tuple[FaceCluster, list[float]]],
        face_cluster_stats: dict[str, dict[str, object]],
        person_profiles: list[PersonScoreProfile],
        people_by_id: dict[int, PersonProfile],
        thresholds: dict[str, float],
    ) -> dict[str, object]:
        person_threshold = thresholds["person_recognition_similarity_threshold"]
        if not preview_clusters or not person_profiles:
            return {
                "candidate_count": 0,
                "ambiguous_count": 0,
                "mean_score": 0.0,
                "bands": self._build_score_bands([]),
                "borderline": [],
            }

        rows: list[dict[str, object]] = []
        best_scores: list[float] = []
        for cluster, embedding in preview_clusters:
            ranked_scores = self._rank_person_profiles(person_profiles, embedding, limit=3)
            best_person, best_score = ranked_scores[0] if ranked_scores else (None, 0.0)
            second_score = ranked_scores[1][1] if len(ranked_scores) > 1 else 0.0
            margin = best_score - second_score
            current_person = people_by_id.get(cluster.person_profile_id or 0)
            best_scores.append(best_score)
            rows.append(
                {
                    "label": cluster.label,
                    "display_name": cluster.display_name,
                    "photo_count": int(face_cluster_stats.get(cluster.label, {}).get("photo_count", 0)),
                    "current_person_id": current_person.id if current_person and current_person.id else None,
                    "current_person_name": current_person.name if current_person else None,
                    "best_person_id": best_person.id if best_person and best_person.id else None,
                    "best_person_name": best_person.name if best_person else None,
                    "score": best_score,
                    "second_score": second_score,
                    "margin": margin,
                    "distance_to_threshold": abs(best_score - person_threshold),
                }
            )

        borderline = [
            row
            for row in sorted(
                rows,
                key=lambda item: (
                    float(item["distance_to_threshold"]),
                    -float(item["score"]),
                ),
            )[:12]
            if float(row["score"]) > 0
        ]
        ambiguous_count = sum(
            1
            for row in rows
            if float(row["score"]) >= person_threshold and float(row["margin"]) < PERSON_MATCH_MARGIN
        )
        mean_score = float(np.mean(best_scores)) if best_scores else 0.0
        return {
            "candidate_count": sum(1 for row in rows if float(row["score"]) >= person_threshold),
            "ambiguous_count": ambiguous_count,
            "mean_score": mean_score,
            "bands": self._build_score_bands(best_scores),
            "borderline": borderline,
        }

    def _build_person_profiles(self) -> list[PersonScoreProfile]:
        profiles: list[PersonScoreProfile] = []
        for person in self.repository.list_person_profiles(limit=5000):
            centroid = deserialize_vector(person.centroid)
            samples = []
            for sample in self.repository.list_person_samples(person.id or 0):
                vector = deserialize_vector(sample.embedding)
                if vector and len(vector) == FACE_EMBEDDING_DIM:
                    samples.append(vector)
            profiles.append(
                PersonScoreProfile(
                    person=person,
                    centroid=centroid if centroid and len(centroid) == FACE_EMBEDDING_DIM else [],
                    samples=samples,
                )
            )
        return profiles

    def _rank_person_profiles(
        self,
        person_profiles: list[PersonScoreProfile],
        embedding: list[float],
        *,
        limit: int,
    ) -> list[tuple[PersonProfile, float]]:
        scores: list[tuple[PersonProfile, float]] = []
        for person_profile in person_profiles:
            score = self._score_person_profile(person_profile, embedding)
            if score <= 0:
                continue
            scores.append((person_profile.person, score))
        scores.sort(key=lambda item: item[1], reverse=True)
        return scores[:limit]

    @staticmethod
    def _score_person_profile(profile: PersonScoreProfile, embedding: list[float]) -> float:
        centroid_score = cosine_similarity(embedding, profile.centroid) if profile.centroid else 0.0
        if not profile.samples:
            return centroid_score

        sample_scores = sorted(
            (cosine_similarity(embedding, sample_vector) for sample_vector in profile.samples),
            reverse=True,
        )
        best_sample_score = sample_scores[0]
        sample_mean = sum(sample_scores[: min(3, len(sample_scores))]) / min(3, len(sample_scores))
        return max(centroid_score, 0.45 * best_sample_score + 0.35 * sample_mean + 0.2 * centroid_score)

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

    def _build_score_bands(self, scores: list[float]) -> list[dict[str, object]]:
        if not scores:
            return [
                {
                    "label": f"{start:.2f}-{end:.2f}",
                    "min_score": start,
                    "max_score": end,
                    "count": 0,
                }
                for start, end in zip(self.SCORE_BANDS[:-1], self.SCORE_BANDS[1:], strict=False)
            ]

        bands: list[dict[str, object]] = []
        for start, end in zip(self.SCORE_BANDS[:-1], self.SCORE_BANDS[1:], strict=False):
            if end >= 1:
                count = sum(1 for score in scores if start <= score <= 1.0)
            else:
                count = sum(1 for score in scores if start <= score < end)
            bands.append(
                {
                    "label": f"{start:.2f}-{min(end, 1.0):.2f}",
                    "min_score": start,
                    "max_score": min(end, 1.0),
                    "count": count,
                }
            )
        return bands
