from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import threading
from typing import Iterable

import numpy as np
from PIL import Image
import torch
from torch.nn import functional as F

from app.config import Settings, get_settings
from app.embeddings import TEXT_VECTOR_DIM, tokenize_text

try:
    from transformers import AutoModel, AutoProcessor
except ImportError:  # pragma: no cover - graceful fallback at runtime
    AutoModel = None
    AutoProcessor = None


DEFAULT_DEEP_VECTOR_DIM = 768

SCENE_CANDIDATE_MAP = {
    "beach": "海边",
    "travel": "旅行",
    "office": "办公室",
    "home": "家里",
    "classroom": "教室",
    "night view": "夜景",
    "sunset": "日落",
    "indoor": "室内",
    "street": "街道",
    "food": "食物",
    "sport": "运动",
    "concert": "演出",
    "family gathering": "家庭聚会",
    "group photo": "合影",
}

OBJECT_CANDIDATE_MAP = {
    "cat": "猫",
    "dog": "狗",
    "car": "汽车",
    "phone": "手机",
    "book": "书",
    "laptop": "电脑",
    "document": "文档",
    "lego bricks": "乐高",
    "child": "孩子",
    "whiteboard": "白板",
    "food": "食物",
}


@dataclass
class Siglip2Bundle:
    model: object
    processor: object
    feature_dim: int


class VideoEmbeddingService:
    _lock = threading.Lock()
    _bundle_cache: dict[str, Siglip2Bundle] = {}

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def embed_video(
        self,
        *,
        frame_paths: list[Path],
        caption: str | None,
        ocr_text: str | None,
        people: Iterable[str],
        scene_tags: Iterable[str],
        object_tags: Iterable[str],
        asset_name: str,
    ) -> list[float]:
        text_hash_vector = self._build_text_hash_vector(
            [
                caption or "",
                ocr_text or "",
                " ".join(people),
                " ".join(scene_tags),
                " ".join(object_tags),
                asset_name,
            ]
        )
        deep_frame_vector = self._embed_frame_paths(frame_paths)
        semantic_text = " ".join(
            filter(
                None,
                [
                    caption or "",
                    ocr_text or "",
                    " ".join(people),
                    " ".join(scene_tags),
                    " ".join(object_tags),
                    asset_name,
                ],
            )
        )
        deep_text_vector = self._embed_text([semantic_text])[0] if semantic_text.strip() else self._zeros_deep_vector()
        deep_vector = self._normalize(0.65 * deep_frame_vector + 0.35 * deep_text_vector)
        return self._normalize(np.concatenate([text_hash_vector, deep_vector], dtype=np.float32)).tolist()

    def embed_text_query(
        self,
        *,
        text: str,
        people: Iterable[str],
        scene_tags: Iterable[str],
        object_tags: Iterable[str],
    ) -> list[float]:
        text_hash_vector = self._build_text_hash_vector(
            [
                text,
                " ".join(people),
                " ".join(scene_tags),
                " ".join(object_tags),
            ]
        )
        deep_text_vector = self._embed_text(
            [
                " ".join(
                    filter(
                        None,
                        [
                            text,
                            " ".join(people),
                            " ".join(scene_tags),
                            " ".join(object_tags),
                        ],
                    )
                )
            ]
        )[0]
        return self._normalize(np.concatenate([text_hash_vector, deep_text_vector], dtype=np.float32)).tolist()

    def embed_video_example(self, frame_paths: list[Path]) -> list[float]:
        text_hash_vector = np.zeros(TEXT_VECTOR_DIM, dtype=np.float32)
        deep_vector = self._embed_frame_paths(frame_paths)
        return self._normalize(np.concatenate([text_hash_vector, deep_vector], dtype=np.float32)).tolist()

    def infer_scene_tags(self, frame_paths: list[Path], top_k: int | None = None) -> list[str]:
        top_k = top_k or self.settings.video_scene_candidate_limit
        return self._infer_candidate_tags(frame_paths, SCENE_CANDIDATE_MAP, top_k=top_k)

    def infer_object_tags(self, frame_paths: list[Path], top_k: int | None = None) -> list[str]:
        top_k = top_k or self.settings.video_scene_candidate_limit
        return self._infer_candidate_tags(frame_paths, OBJECT_CANDIDATE_MAP, top_k=top_k)

    def _infer_candidate_tags(
        self,
        frame_paths: list[Path],
        candidates: dict[str, str],
        *,
        top_k: int,
    ) -> list[str]:
        if not frame_paths:
            return []

        frame_embeddings = self._embed_frame_matrix(frame_paths)
        if frame_embeddings.size == 0:
            return []

        prompt_texts = [f"a video frame about {token}" for token in candidates]
        text_embeddings = np.asarray(self._embed_text(prompt_texts), dtype=np.float32)
        if text_embeddings.size == 0:
            return []

        similarities = frame_embeddings @ text_embeddings.T
        mean_scores = similarities.mean(axis=0)
        top_indices = np.argsort(mean_scores)[::-1][:top_k]
        tags = [list(candidates.values())[index] for index in top_indices if mean_scores[index] > 0]
        return list(dict.fromkeys(tags))

    def _embed_frame_paths(self, frame_paths: list[Path]) -> np.ndarray:
        matrix = self._embed_frame_matrix(frame_paths)
        if matrix.size == 0:
            return self._zeros_deep_vector()
        return self._normalize(matrix.mean(axis=0))

    def _embed_frame_matrix(self, frame_paths: list[Path]) -> np.ndarray:
        if not frame_paths:
            return np.zeros((0, self._deep_vector_dim()), dtype=np.float32)
        if AutoModel is None or AutoProcessor is None:
            return np.zeros((0, self._deep_vector_dim()), dtype=np.float32)

        bundle = self._get_bundle()
        device = next(bundle.model.parameters()).device
        images = [Image.open(path).convert("RGB") for path in frame_paths if path.exists()]
        if not images:
            return np.zeros((0, bundle.feature_dim), dtype=np.float32)

        try:
            inputs = bundle.processor(images=images, return_tensors="pt")
            tensor_inputs = {
                key: value.to(device)
                for key, value in inputs.items()
                if hasattr(value, "to")
            }
            with torch.inference_mode():
                features = bundle.model.get_image_features(**tensor_inputs)
                features = F.normalize(features, dim=1)
            return features.detach().cpu().numpy().astype(np.float32)
        except Exception:
            return np.zeros((0, bundle.feature_dim), dtype=np.float32)

    def _embed_text(self, texts: list[str]) -> list[np.ndarray]:
        if not texts:
            return []
        if AutoModel is None or AutoProcessor is None:
            return [self._zeros_deep_vector() for _ in texts]

        bundle = self._get_bundle()
        device = next(bundle.model.parameters()).device
        try:
            inputs = bundle.processor(text=texts, padding=True, return_tensors="pt")
            tensor_inputs = {
                key: value.to(device)
                for key, value in inputs.items()
                if hasattr(value, "to")
            }
            with torch.inference_mode():
                features = bundle.model.get_text_features(**tensor_inputs)
                features = F.normalize(features, dim=1)
            return [row.astype(np.float32) for row in features.detach().cpu().numpy()]
        except Exception:
            return [self._zeros_deep_vector() for _ in texts]

    def _get_bundle(self) -> Siglip2Bundle:
        model_id = self.settings.video_embedding_model_id.strip()
        with self._lock:
            cached = self._bundle_cache.get(model_id)
            if cached is not None:
                return cached

            if AutoModel is None or AutoProcessor is None:
                raise RuntimeError("transformers is not installed")

            processor = AutoProcessor.from_pretrained(model_id)
            model = AutoModel.from_pretrained(model_id)
            device = torch.device(self.settings.video_embedding_device)
            model = model.to(device)
            model.eval()

            feature_dim = int(
                getattr(model.config, "projection_dim", 0)
                or getattr(model.config, "hidden_size", 0)
                or DEFAULT_DEEP_VECTOR_DIM
            )
            bundle = Siglip2Bundle(model=model, processor=processor, feature_dim=feature_dim)
            self._bundle_cache[model_id] = bundle
            return bundle

    def _build_text_hash_vector(self, chunks: Iterable[str]) -> np.ndarray:
        vector = np.zeros(TEXT_VECTOR_DIM, dtype=np.float32)
        for chunk in chunks:
            for token in tokenize_text(chunk):
                digest = hashlib.sha1(token.encode("utf-8")).digest()
                index = int.from_bytes(digest[:4], "big") % TEXT_VECTOR_DIM
                sign = 1.0 if digest[4] % 2 == 0 else -1.0
                weight = 1.0 + min(len(token), 10) / 10.0
                vector[index] += sign * weight
        return self._normalize(vector)

    def _zeros_deep_vector(self) -> np.ndarray:
        return np.zeros(self._deep_vector_dim(), dtype=np.float32)

    def _deep_vector_dim(self) -> int:
        model_id = self.settings.video_embedding_model_id.strip()
        cached = self._bundle_cache.get(model_id)
        if cached is not None:
            return cached.feature_dim
        return DEFAULT_DEEP_VECTOR_DIM

    @staticmethod
    def _normalize(vector: np.ndarray) -> np.ndarray:
        norm = float(np.linalg.norm(vector))
        if norm == 0:
            return vector
        return vector / norm
