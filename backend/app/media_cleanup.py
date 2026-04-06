from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
import re

from PIL import Image
from sqlmodel import Session

from app.embeddings import cosine_similarity, deserialize_vector, tokenize_text
from app.models import Photo, Video
from app.repository import GalleryRepository
from app.schemas import CleanupPhotoHitRead, CleanupResponse, CleanupVideoHitRead
from app.serializers import build_photo_read, build_video_read

THUMB_HINTS = (
    "thumb",
    "thumbnail",
    "thumbnails",
    "thumbs",
    "preview",
    "cover",
    "small",
)
TRANSFER_JUNK_HINTS = (
    "thumb",
    "thumbnail",
    "cache",
    "temp",
    "tmp",
    "avatar",
    "emoji",
    "emotion",
    "sticker",
    "appbrand",
    "miniapp",
)
GENERIC_MEDIA_TOKENS = {
    "img",
    "image",
    "photo",
    "picture",
    "video",
    "clip",
    "wechat",
    "weixin",
    "qq",
    "thumb",
    "thumbnail",
    "preview",
    "cache",
    "copy",
    "副本",
    "图片",
    "照片",
    "图像",
    "视频",
    "截图",
    "缩略图",
    "聊天",
    "传输",
    "导入",
}
COPY_TOKEN_PATTERN = re.compile(r"^(copy|副本)\d*$", re.IGNORECASE)
MAX_BUCKET_SIZE = 40


@dataclass(slots=True)
class _ImageMeta:
    width: int
    height: int

    @property
    def pixels(self) -> int:
        return self.width * self.height


@dataclass(slots=True)
class _PreparedPhoto:
    photo: Photo
    meta: _ImageMeta
    name_key: str
    caption_key: str
    vector: list[float]
    created_ts: float


@dataclass(slots=True)
class _PreparedVideo:
    video: Video
    width: int
    height: int
    duration_seconds: float
    name_key: str
    caption_key: str
    vector: list[float]
    created_ts: float

    @property
    def pixels(self) -> int:
        return self.width * self.height


class MediaCleanupService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = GalleryRepository(session)
        self._image_meta_cache: dict[int, _ImageMeta | None] = {}

    def list_candidates(self, category: str, limit: int = 80) -> CleanupResponse:
        normalized = category.strip().lower()
        if normalized == "thumbnail_images":
            photo_hits = self._thumbnail_image_candidates(limit)
            return CleanupResponse(category=normalized, total=len(photo_hits), photo_hits=photo_hits)
        if normalized == "low_resolution_images":
            photo_hits = self._low_resolution_image_candidates(limit)
            return CleanupResponse(category=normalized, total=len(photo_hits), photo_hits=photo_hits)
        if normalized == "junk_transfer_images":
            photo_hits = self._junk_transfer_image_candidates(limit)
            return CleanupResponse(category=normalized, total=len(photo_hits), photo_hits=photo_hits)
        if normalized == "duplicate_images":
            photo_hits = self._duplicate_image_candidates(limit)
            return CleanupResponse(category=normalized, total=len(photo_hits), photo_hits=photo_hits)
        if normalized == "low_resolution_videos":
            video_hits = self._low_resolution_video_candidates(limit)
            return CleanupResponse(category=normalized, total=len(video_hits), video_hits=video_hits)
        if normalized == "duplicate_videos":
            video_hits = self._duplicate_video_candidates(limit)
            return CleanupResponse(category=normalized, total=len(video_hits), video_hits=video_hits)
        raise ValueError(f"Unsupported cleanup category: {category}")

    def _thumbnail_image_candidates(self, limit: int) -> list[CleanupPhotoHitRead]:
        hits: list[CleanupPhotoHitRead] = []
        for photo in self.repository.list_searchable_photos(limit=5000):
            meta = self._read_image_meta(photo.id or 0, photo.storage_path)
            if meta is None:
                continue

            path_text = f"{photo.original_path} {photo.storage_path}".lower()
            matched_hints = [hint for hint in THUMB_HINTS if hint in path_text]
            score = 0.0
            reasons: list[str] = []
            if matched_hints:
                score += 0.62
                reasons.append(f"路径或文件名包含 {matched_hints[0]} 缩略图特征")
            if meta.width <= 480 or meta.height <= 480:
                score += 0.2
                reasons.append(f"分辨率仅 {meta.width}x{meta.height}")
            if meta.pixels <= 200_000:
                score += 0.16
                reasons.append("总像素明显偏小")
            if photo.source_kind in {"wechat_folder", "qq_folder"}:
                score += 0.04
                reasons.append("来自聊天同步目录")

            if score < 0.66:
                continue
            hits.append(
                self._build_photo_hit(
                    photo=photo,
                    score=min(score, 0.99),
                    reason="；".join(dict.fromkeys(reasons)),
                    width=meta.width,
                    height=meta.height,
                )
            )
            if len(hits) >= limit:
                break
        return hits

    def _low_resolution_image_candidates(self, limit: int) -> list[CleanupPhotoHitRead]:
        hits: list[CleanupPhotoHitRead] = []
        for photo in self.repository.list_searchable_photos(limit=5000):
            meta = self._read_image_meta(photo.id or 0, photo.storage_path)
            if meta is None:
                continue

            score = 0.0
            reason = ""
            if meta.width <= 640 or meta.height <= 640 or meta.pixels <= 300_000:
                score = 0.96
                reason = f"分辨率过低，仅 {meta.width}x{meta.height}"
            elif meta.width < 1280 or meta.height < 720:
                score = 0.76
                reason = f"分辨率偏低，为 {meta.width}x{meta.height}"

            if score <= 0:
                continue
            hits.append(
                self._build_photo_hit(
                    photo=photo,
                    score=score,
                    reason=reason,
                    width=meta.width,
                    height=meta.height,
                )
            )
            if len(hits) >= limit:
                break
        return hits

    def _junk_transfer_image_candidates(self, limit: int) -> list[CleanupPhotoHitRead]:
        hits: list[CleanupPhotoHitRead] = []
        for photo in self.repository.list_searchable_photos(limit=5000):
            if photo.source_kind not in {"wechat_folder", "qq_folder"}:
                continue

            meta = self._read_image_meta(photo.id or 0, photo.storage_path)
            if meta is None:
                continue

            path_text = f"{photo.original_path} {photo.storage_path}".lower()
            matched_hints = [hint for hint in TRANSFER_JUNK_HINTS if hint in path_text]
            people = decode_json_list(photo.people)
            scenes = decode_json_list(photo.scene_tags)
            objects = decode_json_list(photo.object_tags)
            has_ocr = bool((photo.ocr_text or "").strip())

            score = 0.2
            reasons = ["来自微信 / QQ 同步目录"]
            if matched_hints:
                score += 0.34
                reasons.append(f"路径或文件名包含 {matched_hints[0]} 缓存 / 缩略图特征")
            if meta.width <= 720 or meta.height <= 720:
                score += 0.16
                reasons.append(f"分辨率较小，仅 {meta.width}x{meta.height}")
            if meta.pixels <= 250_000:
                score += 0.12
                reasons.append("总像素较小")
            if photo.face_count == 0:
                score += 0.08
                reasons.append("未检测到人物")
            if not has_ocr:
                score += 0.05
                reasons.append("没有可保留的 OCR 文本")
            if not people and not scenes and not objects:
                score += 0.1
                reasons.append("AI 内容信号较弱")

            if score < 0.7:
                continue
            hits.append(
                self._build_photo_hit(
                    photo=photo,
                    score=min(score, 0.99),
                    reason="；".join(dict.fromkeys(reasons)),
                    width=meta.width,
                    height=meta.height,
                )
            )
            if len(hits) >= limit:
                break
        return hits

    def _duplicate_image_candidates(self, limit: int) -> list[CleanupPhotoHitRead]:
        prepared: list[_PreparedPhoto] = []
        for photo in self.repository.list_searchable_photos(limit=5000):
            meta = self._read_image_meta(photo.id or 0, photo.storage_path)
            if meta is None:
                continue
            prepared.append(
                _PreparedPhoto(
                    photo=photo,
                    meta=meta,
                    name_key=self._normalize_media_name(photo.original_path or photo.storage_path),
                    caption_key=self._caption_key(photo.caption),
                    vector=deserialize_vector(photo.vector_embedding),
                    created_ts=self._timestamp(photo.taken_at or photo.created_at),
                )
            )

        candidates: dict[int, CleanupPhotoHitRead] = {}
        self._collect_exact_photo_duplicates(prepared, candidates)
        seen_pairs: set[tuple[int, int]] = set()

        for bucket in self._build_photo_buckets(prepared):
            ordered = sorted(bucket, key=self._photo_quality_key, reverse=True)
            for index, current in enumerate(ordered):
                if index == 0:
                    continue
                if len(candidates) >= limit and (current.photo.id or 0) not in candidates:
                    continue
                if (current.photo.id or 0) in candidates and candidates[current.photo.id or 0].score >= 0.99:
                    continue

                for better in ordered[:index]:
                    pair_key = self._pair_key(current.photo.id or 0, better.photo.id or 0)
                    if pair_key in seen_pairs:
                        continue
                    seen_pairs.add(pair_key)

                    score, reason = self._score_photo_duplicate(current, better)
                    if score <= 0:
                        continue
                    self._register_photo_candidate(candidates, current, score, reason)
                    break

        return sorted(
            candidates.values(),
            key=lambda item: (item.score, item.width or 0, item.height or 0, item.photo.created_at),
            reverse=True,
        )[:limit]

    def _low_resolution_video_candidates(self, limit: int) -> list[CleanupVideoHitRead]:
        hits: list[CleanupVideoHitRead] = []
        for video in self.repository.list_searchable_videos(limit=5000):
            width = video.frame_width or 0
            height = video.frame_height or 0
            if width <= 0 or height <= 0:
                continue

            score = 0.0
            reason = ""
            if width <= 640 or height <= 360:
                score = 0.96
                reason = f"视频分辨率过低，仅 {width}x{height}"
            elif width < 960 or height < 540:
                score = 0.8
                reason = f"视频分辨率偏低，为 {width}x{height}"

            if score <= 0:
                continue
            hits.append(
                CleanupVideoHitRead(
                    score=score,
                    reason=reason,
                    width=width,
                    height=height,
                    video=build_video_read(self.repository, video),
                )
            )
            if len(hits) >= limit:
                break
        return hits

    def _duplicate_video_candidates(self, limit: int) -> list[CleanupVideoHitRead]:
        prepared: list[_PreparedVideo] = []
        for video in self.repository.list_searchable_videos(limit=5000):
            width = video.frame_width or 0
            height = video.frame_height or 0
            if width <= 0 or height <= 0:
                continue
            prepared.append(
                _PreparedVideo(
                    video=video,
                    width=width,
                    height=height,
                    duration_seconds=float(video.duration_seconds or 0.0),
                    name_key=self._normalize_media_name(video.original_path or video.storage_path),
                    caption_key=self._caption_key(video.caption),
                    vector=deserialize_vector(video.vector_embedding),
                    created_ts=self._timestamp(video.taken_at or video.created_at),
                )
            )

        candidates: dict[int, CleanupVideoHitRead] = {}
        self._collect_exact_video_duplicates(prepared, candidates)
        seen_pairs: set[tuple[int, int]] = set()

        for bucket in self._build_video_buckets(prepared):
            ordered = sorted(bucket, key=self._video_quality_key, reverse=True)
            for index, current in enumerate(ordered):
                if index == 0:
                    continue
                if len(candidates) >= limit and (current.video.id or 0) not in candidates:
                    continue
                if (current.video.id or 0) in candidates and candidates[current.video.id or 0].score >= 0.99:
                    continue

                for better in ordered[:index]:
                    pair_key = self._pair_key(current.video.id or 0, better.video.id or 0)
                    if pair_key in seen_pairs:
                        continue
                    seen_pairs.add(pair_key)

                    score, reason = self._score_video_duplicate(current, better)
                    if score <= 0:
                        continue
                    self._register_video_candidate(candidates, current, score, reason)
                    break

        return sorted(
            candidates.values(),
            key=lambda item: (item.score, item.width or 0, item.height or 0, item.video.created_at),
            reverse=True,
        )[:limit]

    def _collect_exact_photo_duplicates(
        self,
        prepared: list[_PreparedPhoto],
        candidates: dict[int, CleanupPhotoHitRead],
    ) -> None:
        groups: dict[str, list[_PreparedPhoto]] = defaultdict(list)
        for item in prepared:
            groups[item.photo.sha256].append(item)

        for group in groups.values():
            if len(group) < 2:
                continue
            ordered = sorted(group, key=self._photo_quality_key, reverse=True)
            keeper = ordered[0]
            for duplicate in ordered[1:]:
                reason = (
                    f"与保留项二进制完全一致（SHA256 相同）；建议保留更优版本 "
                    f"{keeper.meta.width}x{keeper.meta.height}"
                )
                self._register_photo_candidate(candidates, duplicate, 0.99, reason)

    def _collect_exact_video_duplicates(
        self,
        prepared: list[_PreparedVideo],
        candidates: dict[int, CleanupVideoHitRead],
    ) -> None:
        groups: dict[str, list[_PreparedVideo]] = defaultdict(list)
        for item in prepared:
            groups[item.video.sha256].append(item)

        for group in groups.values():
            if len(group) < 2:
                continue
            ordered = sorted(group, key=self._video_quality_key, reverse=True)
            keeper = ordered[0]
            for duplicate in ordered[1:]:
                reason = (
                    f"与保留项二进制完全一致（SHA256 相同）；建议保留更优版本 "
                    f"{keeper.width}x{keeper.height}"
                )
                self._register_video_candidate(candidates, duplicate, 0.99, reason)

    def _build_photo_buckets(self, prepared: list[_PreparedPhoto]) -> list[list[_PreparedPhoto]]:
        buckets: dict[str, list[_PreparedPhoto]] = defaultdict(list)
        for item in prepared:
            if item.name_key:
                buckets[f"name:{item.name_key}"].append(item)
            if item.caption_key:
                buckets[f"caption:{item.caption_key}"].append(item)

        results: list[list[_PreparedPhoto]] = []
        for bucket_key, items in buckets.items():
            if len(items) < 2:
                continue
            if bucket_key.startswith("caption:") and len(items) > MAX_BUCKET_SIZE:
                items = sorted(items, key=self._photo_quality_key, reverse=True)[:MAX_BUCKET_SIZE]
            results.append(items)
        return results

    def _build_video_buckets(self, prepared: list[_PreparedVideo]) -> list[list[_PreparedVideo]]:
        buckets: dict[str, list[_PreparedVideo]] = defaultdict(list)
        for item in prepared:
            if item.name_key:
                buckets[f"name:{item.name_key}"].append(item)
            if item.caption_key:
                duration_key = round(item.duration_seconds, 1) if item.duration_seconds > 0 else 0
                buckets[f"caption:{item.caption_key}:{duration_key}"].append(item)

        results: list[list[_PreparedVideo]] = []
        for bucket_key, items in buckets.items():
            if len(items) < 2:
                continue
            if bucket_key.startswith("caption:") and len(items) > MAX_BUCKET_SIZE:
                items = sorted(items, key=self._video_quality_key, reverse=True)[:MAX_BUCKET_SIZE]
            results.append(items)
        return results

    def _score_photo_duplicate(self, current: _PreparedPhoto, better: _PreparedPhoto) -> tuple[float, str]:
        same_name = bool(current.name_key and current.name_key == better.name_key)
        name_similarity = self._text_similarity(current.name_key, better.name_key)
        caption_similarity = self._text_similarity(current.caption_key, better.caption_key)
        vector_similarity = cosine_similarity(current.vector, better.vector)
        phash_similarity = self._phash_similarity(current.photo.phash, better.photo.phash)

        strong_semantic = vector_similarity >= 0.96 or (vector_similarity >= 0.92 and phash_similarity >= 0.84)
        strong_named = (same_name or name_similarity >= 0.94) and (
            vector_similarity >= 0.86 or phash_similarity >= 0.9 or caption_similarity >= 0.88
        )
        caption_semantic = caption_similarity >= 0.9 and vector_similarity >= 0.9
        if not (strong_semantic or strong_named or caption_semantic):
            return 0.0, ""

        score = max(
            0.16 if same_name else 0.12 if name_similarity >= 0.94 else 0.0,
            0.08 if caption_similarity >= 0.9 else 0.0,
        )
        score += min(vector_similarity, 1.0) * 0.48
        score += phash_similarity * 0.28
        score = min(score, 0.985)

        reasons = [f"与更高清版本高度重复，建议保留 {better.meta.width}x{better.meta.height}"]
        if same_name:
            reasons.append("规范化文件名一致")
        elif name_similarity >= 0.9:
            reasons.append(f"文件名高度相似 {name_similarity:.2f}")
        if vector_similarity >= 0.8:
            reasons.append(f"语义向量相似度 {vector_similarity:.2f}")
        if phash_similarity >= 0.8:
            reasons.append(f"感知哈希相似度 {phash_similarity:.2f}")
        if caption_similarity >= 0.88:
            reasons.append("AI 描述接近")
        return score, "；".join(dict.fromkeys(reasons))

    def _score_video_duplicate(self, current: _PreparedVideo, better: _PreparedVideo) -> tuple[float, str]:
        same_name = bool(current.name_key and current.name_key == better.name_key)
        name_similarity = self._text_similarity(current.name_key, better.name_key)
        caption_similarity = self._text_similarity(current.caption_key, better.caption_key)
        vector_similarity = cosine_similarity(current.vector, better.vector)
        duration_similarity = self._duration_similarity(current.duration_seconds, better.duration_seconds)

        strong_semantic = vector_similarity >= 0.95 and duration_similarity >= 0.97
        strong_named = (same_name or name_similarity >= 0.94) and (
            duration_similarity >= 0.98 or (vector_similarity >= 0.88 and duration_similarity >= 0.94)
        )
        caption_semantic = caption_similarity >= 0.9 and vector_similarity >= 0.9 and duration_similarity >= 0.94
        if not (strong_semantic or strong_named or caption_semantic):
            return 0.0, ""

        score = max(
            0.18 if same_name else 0.12 if name_similarity >= 0.94 else 0.0,
            0.08 if caption_similarity >= 0.9 else 0.0,
        )
        score += min(vector_similarity, 1.0) * 0.42
        score += duration_similarity * 0.28
        score = min(score, 0.985)

        reasons = [f"与更清晰版本高度重复，建议保留 {better.width}x{better.height}"]
        if same_name:
            reasons.append("规范化文件名一致")
        elif name_similarity >= 0.9:
            reasons.append(f"文件名高度相似 {name_similarity:.2f}")
        if duration_similarity >= 0.9:
            reasons.append(f"时长相近 {duration_similarity:.2f}")
        if vector_similarity >= 0.8:
            reasons.append(f"视频向量相似度 {vector_similarity:.2f}")
        if caption_similarity >= 0.88:
            reasons.append("AI 描述接近")
        return score, "；".join(dict.fromkeys(reasons))

    def _read_image_meta(self, photo_id: int, storage_path: str) -> _ImageMeta | None:
        if photo_id in self._image_meta_cache:
            return self._image_meta_cache[photo_id]

        path = Path(storage_path)
        if not path.exists():
            self._image_meta_cache[photo_id] = None
            return None

        try:
            with Image.open(path) as image:
                meta = _ImageMeta(width=image.width, height=image.height)
        except OSError:
            meta = None
        self._image_meta_cache[photo_id] = meta
        return meta

    def _register_photo_candidate(
        self,
        candidates: dict[int, CleanupPhotoHitRead],
        prepared: _PreparedPhoto,
        score: float,
        reason: str,
    ) -> None:
        photo_id = prepared.photo.id or 0
        current = candidates.get(photo_id)
        if current and current.score >= score:
            return
        candidates[photo_id] = self._build_photo_hit(
            photo=prepared.photo,
            score=score,
            reason=reason,
            width=prepared.meta.width,
            height=prepared.meta.height,
        )

    def _register_video_candidate(
        self,
        candidates: dict[int, CleanupVideoHitRead],
        prepared: _PreparedVideo,
        score: float,
        reason: str,
    ) -> None:
        video_id = prepared.video.id or 0
        current = candidates.get(video_id)
        if current and current.score >= score:
            return
        candidates[video_id] = CleanupVideoHitRead(
            score=score,
            reason=reason,
            width=prepared.width,
            height=prepared.height,
            video=build_video_read(self.repository, prepared.video),
        )

    def _build_photo_hit(
        self,
        photo: Photo,
        score: float,
        reason: str,
        width: int,
        height: int,
    ) -> CleanupPhotoHitRead:
        return CleanupPhotoHitRead(
            score=score,
            reason=reason,
            width=width,
            height=height,
            photo=build_photo_read(self.repository, photo),
        )

    @staticmethod
    def _photo_quality_key(item: _PreparedPhoto) -> tuple[int, int, int, float, int]:
        return (
            item.meta.pixels,
            item.photo.face_count,
            1 if (item.photo.ocr_text or "").strip() else 0,
            item.created_ts,
            item.photo.id or 0,
        )

    @staticmethod
    def _video_quality_key(item: _PreparedVideo) -> tuple[int, float, int, float, int]:
        return (
            item.pixels,
            item.duration_seconds,
            item.video.sampled_frame_count,
            item.created_ts,
            item.video.id or 0,
        )

    @staticmethod
    def _normalize_media_name(path_value: str) -> str:
        stem = Path(path_value or "").stem.lower()
        stem = re.sub(r"[_\-\(\)\[\]\{\}]+", " ", stem)
        tokens = tokenize_text(stem)
        while len(tokens) > 1 and (tokens[-1].isdigit() or COPY_TOKEN_PATTERN.match(tokens[-1])):
            tokens.pop()

        filtered = [
            token
            for token in tokens
            if token not in GENERIC_MEDIA_TOKENS and not COPY_TOKEN_PATTERN.match(token)
        ]
        if not filtered:
            filtered = [token for token in tokens if not COPY_TOKEN_PATTERN.match(token)]
        return " ".join(filtered[:6]).strip()

    @staticmethod
    def _caption_key(caption: str | None) -> str:
        if not caption:
            return ""
        tokens = [
            token
            for token in tokenize_text(caption)
            if not token.isdigit() and token not in GENERIC_MEDIA_TOKENS and len(token) > 1
        ]
        return " ".join(tokens[:6]).strip()

    @staticmethod
    def _timestamp(value: datetime | None) -> float:
        if value is None:
            return 0.0
        try:
            return float(value.timestamp())
        except (OverflowError, OSError, ValueError):
            return 0.0

    @staticmethod
    def _text_similarity(left: str, right: str) -> float:
        if not left or not right:
            return 0.0
        if left == right:
            return 1.0
        return float(SequenceMatcher(a=left, b=right).ratio())

    @staticmethod
    def _phash_similarity(left: str | None, right: str | None) -> float:
        if not left or not right:
            return 0.0
        try:
            left_value = int(left, 16)
            right_value = int(right, 16)
        except ValueError:
            return 0.0

        bit_length = max(len(left.strip()), len(right.strip())) * 4
        if bit_length <= 0:
            return 0.0
        distance = (left_value ^ right_value).bit_count()
        return max(0.0, 1.0 - distance / bit_length)

    @staticmethod
    def _duration_similarity(left: float, right: float) -> float:
        if left <= 0 or right <= 0:
            return 0.0
        baseline = max(left, right)
        if baseline <= 0:
            return 0.0
        return max(0.0, 1.0 - abs(left - right) / baseline)

    @staticmethod
    def _pair_key(left_id: int, right_id: int) -> tuple[int, int]:
        return (min(left_id, right_id), max(left_id, right_id))
