from __future__ import annotations

from app.config import get_settings
from app.embeddings import cosine_similarity, deserialize_vector, tokenize_text
from app.face_clustering import FaceClusteringService
from app.repository import GalleryRepository
from app.schemas import SearchQuery, VideoSearchHit, VideoSearchResponse, decode_json_list
from app.serializers import build_video_read
from app.video_embeddings import VideoEmbeddingService


class VideoSearchService:
    def __init__(self, session) -> None:
        self.session = session
        self.repository = GalleryRepository(session)
        self.vectorizer = VideoEmbeddingService()
        self.settings = get_settings()
        self.face_service = FaceClusteringService(session, self.settings)

    def search(self, payload: SearchQuery) -> VideoSearchResponse:
        query_text = payload.text.strip().lower()
        query_terms = [term for term in tokenize_text(query_text) if term]
        query_people = list(dict.fromkeys(payload.people + self._detect_person_names(query_text)))
        people_filter = {item.lower() for item in query_people}
        scene_filter = {item.lower() for item in payload.scene_tags}
        object_filter = {item.lower() for item in payload.object_tags}
        source_filter = set(payload.source_kinds)

        query_vector = self.vectorizer.embed_text_query(
            text=payload.text,
            people=query_people,
            scene_tags=payload.scene_tags,
            object_tags=payload.object_tags,
        )
        has_vector_query = bool(payload.text.strip() or query_people or payload.scene_tags or payload.object_tags)

        hits: list[VideoSearchHit] = []
        for video in self.repository.list_searchable_videos(limit=1200):
            video_read = build_video_read(self.repository, video)
            normalized_people = {item.lower() for item in video_read.people}
            normalized_scene_tags = {item.lower() for item in video_read.scene_tags}
            normalized_object_tags = {item.lower() for item in video_read.object_tags}

            if people_filter and not people_filter.issubset(normalized_people):
                continue
            if scene_filter and not scene_filter.issubset(normalized_scene_tags):
                continue
            if object_filter and not object_filter.issubset(normalized_object_tags):
                continue
            if source_filter and video.source_kind not in source_filter:
                continue

            searchable_text = " ".join(
                filter(
                    None,
                    [
                        (video_read.caption or "").lower(),
                        (video_read.ocr_text or "").lower(),
                        " ".join(normalized_people),
                        " ".join(normalized_scene_tags),
                        " ".join(normalized_object_tags),
                        (video_read.original_path or "").lower(),
                    ],
                )
            )

            keyword_score = 0.0
            if not query_terms:
                keyword_score = 1.0
            else:
                keyword_matches = sum(1 for term in query_terms if term in searchable_text)
                if keyword_matches:
                    keyword_score = float(keyword_matches) / max(len(query_terms), 1)

            vector_score = 0.0
            if has_vector_query and video.vector_embedding:
                vector_score = cosine_similarity(query_vector, deserialize_vector(video.vector_embedding))

            score = self._merge_scores(
                mode=payload.mode,
                keyword_score=keyword_score,
                vector_score=vector_score,
                has_query=bool(query_terms or has_vector_query),
            )
            if score <= 0:
                continue

            hits.append(VideoSearchHit(score=score, video=video_read))

        hits.sort(key=lambda item: (item.score, item.video.created_at), reverse=True)
        return VideoSearchResponse(total=len(hits), hits=hits[: payload.limit])

    def search_by_vector(self, query_vector: list[float], limit: int = 20) -> VideoSearchResponse:
        hits: list[VideoSearchHit] = []
        for candidate in self.repository.list_searchable_videos(limit=1200):
            if not candidate.vector_embedding:
                continue
            score = cosine_similarity(query_vector, deserialize_vector(candidate.vector_embedding))
            if score <= 0:
                continue
            hits.append(VideoSearchHit(score=score, video=build_video_read(self.repository, candidate)))

        hits.sort(key=lambda item: (item.score, item.video.created_at), reverse=True)
        return VideoSearchResponse(total=len(hits), hits=hits[:limit])

    def similar_to_video(self, video_id: int, limit: int = 20) -> VideoSearchResponse:
        reference_video = self.repository.get_video(video_id)
        if reference_video is None or not reference_video.vector_embedding:
            return VideoSearchResponse(total=0, hits=[])

        hits = [
            hit
            for hit in self.search_by_vector(
                deserialize_vector(reference_video.vector_embedding),
                limit=limit + 1,
            ).hits
            if hit.video.id != video_id
        ]
        return VideoSearchResponse(total=len(hits), hits=hits[:limit])

    def search_by_person_embedding(
        self,
        query_embedding: list[float],
        limit: int = 20,
    ) -> VideoSearchResponse:
        cluster_scores: dict[str, float] = {}
        for person, score in self.face_service.rank_person_profiles(query_embedding, limit=3):
            if score < self.settings.person_recognition_similarity_threshold:
                continue
            for cluster in self.repository.list_face_clusters_by_person(person.id or 0, limit=5000):
                cluster_scores[cluster.label] = max(cluster_scores.get(cluster.label, 0.0), score)

        for cluster in self.repository.list_face_clusters(limit=5000):
            if not cluster.centroid:
                continue
            score = cosine_similarity(query_embedding, deserialize_vector(cluster.centroid))
            if score < self.settings.person_recognition_similarity_threshold:
                continue
            cluster_scores[cluster.label] = max(cluster_scores.get(cluster.label, 0.0), score)

        if not cluster_scores:
            return VideoSearchResponse(total=0, hits=[])

        hits: list[VideoSearchHit] = []
        for video in self.repository.list_searchable_videos(limit=5000):
            video_face_clusters = decode_json_list(video.face_clusters)
            best_score = max((cluster_scores.get(label, 0.0) for label in video_face_clusters), default=0.0)
            if best_score <= 0:
                continue
            hits.append(
                VideoSearchHit(
                    score=best_score,
                    video=build_video_read(self.repository, video),
                )
            )

        hits.sort(key=lambda item: (item.score, item.video.created_at), reverse=True)
        return VideoSearchResponse(total=len(hits), hits=hits[:limit])

    def _detect_person_names(self, query_text: str) -> list[str]:
        if not query_text:
            return []

        matches: list[str] = []
        for person in self.repository.list_person_profiles(limit=500):
            normalized_name = (person.normalized_name or "").strip().lower()
            if normalized_name and normalized_name in query_text:
                matches.append(person.name)
        return matches

    @staticmethod
    def _merge_scores(mode: str, keyword_score: float, vector_score: float, has_query: bool) -> float:
        if not has_query:
            return 1.0
        if mode == "keyword":
            return keyword_score if keyword_score > 0 else 0.0
        if mode == "vector":
            return vector_score if vector_score > 0.01 else 0.0

        combined = keyword_score * 0.55 + vector_score * 0.45
        if keyword_score <= 0 and vector_score <= 0.01:
            return 0.0
        return combined
