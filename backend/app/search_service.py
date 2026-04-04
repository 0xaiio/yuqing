from app.embeddings import VectorEmbeddingService, cosine_similarity, deserialize_vector, tokenize_text
from app.repository import GalleryRepository
from app.schemas import SearchHit, SearchQuery, SearchResponse, decode_json_list
from app.serializers import build_photo_read


class SearchService:
    def __init__(self, session) -> None:
        self.repository = GalleryRepository(session)
        self.vectorizer = VectorEmbeddingService()

    def search(self, payload: SearchQuery) -> SearchResponse:
        query_text = payload.text.strip().lower()
        query_terms = [term for term in tokenize_text(query_text) if term]
        people_filter = {item.lower() for item in payload.people}
        scene_filter = {item.lower() for item in payload.scene_tags}
        object_filter = {item.lower() for item in payload.object_tags}
        source_filter = set(payload.source_kinds)
        face_cluster_filter = set(payload.face_cluster_labels)
        query_vector = self.vectorizer.embed_query(
            text=payload.text,
            people=payload.people,
            scene_tags=payload.scene_tags,
            object_tags=payload.object_tags,
        )
        has_vector_query = bool(payload.text.strip() or payload.people or payload.scene_tags or payload.object_tags)

        hits: list[SearchHit] = []
        for photo in self.repository.list_searchable_photos(limit=1200):
            photo_read = build_photo_read(self.repository, photo)
            photo_face_clusters = set(decode_json_list(photo.face_clusters))
            normalized_people = {item.lower() for item in photo_read.people}
            normalized_scene_tags = {item.lower() for item in photo_read.scene_tags}
            normalized_object_tags = {item.lower() for item in photo_read.object_tags}

            if people_filter and not people_filter.issubset(normalized_people):
                continue
            if scene_filter and not scene_filter.issubset(normalized_scene_tags):
                continue
            if object_filter and not object_filter.issubset(normalized_object_tags):
                continue
            if source_filter and photo.source_kind not in source_filter:
                continue
            if face_cluster_filter and not face_cluster_filter.issubset(photo_face_clusters):
                continue

            searchable_text = " ".join(
                filter(
                    None,
                    [
                        (photo_read.caption or "").lower(),
                        (photo_read.ocr_text or "").lower(),
                        " ".join(normalized_people),
                        " ".join(normalized_scene_tags),
                        " ".join(normalized_object_tags),
                        " ".join(photo_face_clusters).lower(),
                        (photo_read.original_path or "").lower(),
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
            if has_vector_query and photo.vector_embedding:
                vector_score = cosine_similarity(query_vector, deserialize_vector(photo.vector_embedding))

            score = self._merge_scores(
                mode=payload.mode,
                keyword_score=keyword_score,
                vector_score=vector_score,
                has_query=bool(query_terms or has_vector_query),
            )
            if score <= 0:
                continue

            hits.append(SearchHit(score=score, photo=photo_read))

        hits.sort(key=lambda item: (item.score, item.photo.created_at), reverse=True)
        return SearchResponse(total=len(hits), hits=hits[: payload.limit])

    def search_by_vector(self, query_vector: list[float], limit: int = 20) -> SearchResponse:
        hits: list[SearchHit] = []
        for candidate in self.repository.list_searchable_photos(limit=1200):
            if not candidate.vector_embedding:
                continue
            score = cosine_similarity(query_vector, deserialize_vector(candidate.vector_embedding))
            if score <= 0:
                continue
            hits.append(
                SearchHit(
                    score=score,
                    photo=build_photo_read(self.repository, candidate),
                )
            )

        hits.sort(key=lambda item: (item.score, item.photo.created_at), reverse=True)
        return SearchResponse(total=len(hits), hits=hits[:limit])

    def similar_to_photo(self, photo_id: int, limit: int = 20) -> SearchResponse:
        reference_photo = self.repository.get_photo(photo_id)
        if reference_photo is None or not reference_photo.vector_embedding:
            return SearchResponse(total=0, hits=[])

        hits = [
            hit
            for hit in self.search_by_vector(
                deserialize_vector(reference_photo.vector_embedding),
                limit=limit + 1,
            ).hits
            if hit.photo.id != photo_id
        ]
        return SearchResponse(total=len(hits), hits=hits[:limit])

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
