import hashlib
import json
import re
from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image

TEXT_VECTOR_DIM = 128
IMAGE_VECTOR_DIM = 112
EMBEDDING_DIM = TEXT_VECTOR_DIM + IMAGE_VECTOR_DIM
TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff]+")


def serialize_vector(vector: list[float]) -> str:
    return json.dumps([round(float(item), 6) for item in vector], ensure_ascii=False)


def deserialize_vector(value: str | None) -> list[float]:
    if not value:
        return []
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [float(item) for item in data]


def cosine_similarity(vector_a: list[float] | None, vector_b: list[float] | None) -> float:
    if not vector_a or not vector_b:
        return 0.0
    array_a = np.asarray(vector_a, dtype=np.float32)
    array_b = np.asarray(vector_b, dtype=np.float32)
    if array_a.size != array_b.size or array_a.size == 0:
        return 0.0

    denom = float(np.linalg.norm(array_a) * np.linalg.norm(array_b))
    if denom == 0:
        return 0.0
    return float(np.dot(array_a, array_b) / denom)


def tokenize_text(text: str) -> list[str]:
    tokens: list[str] = []
    for chunk in TOKEN_PATTERN.findall(text.lower()):
        tokens.append(chunk)
        if _is_cjk(chunk):
            tokens.extend(chunk[index : index + 2] for index in range(len(chunk) - 1))
    return tokens


class VectorEmbeddingService:
    def embed_photo(
        self,
        photo_path: Path,
        *,
        caption: str | None,
        ocr_text: str | None,
        people: Iterable[str],
        scene_tags: Iterable[str],
        object_tags: Iterable[str],
        phash: str | None,
    ) -> list[float]:
        text_vector = self._build_text_vector(
            [
                caption or "",
                ocr_text or "",
                " ".join(people),
                " ".join(scene_tags),
                " ".join(object_tags),
                photo_path.stem,
            ]
        )
        image_vector = self._build_image_vector(photo_path, phash=phash)
        return self._normalize(np.concatenate([text_vector, image_vector], dtype=np.float32)).tolist()

    def embed_query(
        self,
        *,
        text: str,
        people: Iterable[str],
        scene_tags: Iterable[str],
        object_tags: Iterable[str],
    ) -> list[float]:
        text_vector = self._build_text_vector(
            [
                text,
                " ".join(people),
                " ".join(scene_tags),
                " ".join(object_tags),
            ]
        )
        empty_image_vector = np.zeros(IMAGE_VECTOR_DIM, dtype=np.float32)
        return self._normalize(np.concatenate([text_vector, empty_image_vector], dtype=np.float32)).tolist()

    def _build_text_vector(self, chunks: Iterable[str]) -> np.ndarray:
        vector = np.zeros(TEXT_VECTOR_DIM, dtype=np.float32)
        for chunk in chunks:
            for token in tokenize_text(chunk):
                digest = hashlib.sha1(token.encode("utf-8")).digest()
                index = int.from_bytes(digest[:4], "big") % TEXT_VECTOR_DIM
                sign = 1.0 if digest[4] % 2 == 0 else -1.0
                weight = 1.0 + min(len(token), 10) / 10.0
                vector[index] += sign * weight
        return self._normalize(vector)

    def _build_image_vector(self, photo_path: Path, phash: str | None) -> np.ndarray:
        try:
            with Image.open(photo_path) as image:
                rgb = image.convert("RGB").resize((128, 128))
                gray = image.convert("L").resize((64, 64))
        except Exception:
            return np.zeros(IMAGE_VECTOR_DIM, dtype=np.float32)

        rgb_array = np.asarray(rgb, dtype=np.float32) / 255.0
        gray_array = np.asarray(gray, dtype=np.float32) / 255.0

        histograms: list[np.ndarray] = []
        for channel in range(3):
            histogram, _ = np.histogram(rgb_array[:, :, channel], bins=8, range=(0, 1), density=True)
            histograms.append(histogram.astype(np.float32))

        grayscale_histogram, _ = np.histogram(gray_array, bins=16, range=(0, 1), density=True)
        channel_means = rgb_array.mean(axis=(0, 1)).astype(np.float32)
        channel_stds = rgb_array.std(axis=(0, 1)).astype(np.float32)
        edge_strength = np.asarray(
            [
                np.abs(np.diff(gray_array, axis=0)).mean(),
                np.abs(np.diff(gray_array, axis=1)).mean(),
            ],
            dtype=np.float32,
        )
        phash_vector = self._phash_bits(phash)

        image_vector = np.concatenate(
            [
                *histograms,
                grayscale_histogram.astype(np.float32),
                channel_means,
                channel_stds,
                edge_strength,
                phash_vector,
            ],
            dtype=np.float32,
        )
        return self._normalize(image_vector)

    @staticmethod
    def _normalize(vector: np.ndarray) -> np.ndarray:
        norm = float(np.linalg.norm(vector))
        if norm == 0:
            return vector
        return vector / norm

    @staticmethod
    def _phash_bits(phash: str | None) -> np.ndarray:
        if not phash:
            return np.zeros(64, dtype=np.float32)

        try:
            bit_string = "".join(f"{int(character, 16):04b}" for character in phash.strip().lower())
        except ValueError:
            return np.zeros(64, dtype=np.float32)

        trimmed = bit_string[:64].ljust(64, "0")
        return np.asarray([1.0 if bit == "1" else -1.0 for bit in trimmed], dtype=np.float32)


def _is_cjk(token: str) -> bool:
    return any("\u4e00" <= character <= "\u9fff" for character in token)
