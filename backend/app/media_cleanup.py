from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image
from sqlmodel import Session

from app.repository import GalleryRepository
from app.schemas import CleanupPhotoHitRead, CleanupResponse, CleanupVideoHitRead, decode_json_list
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


@dataclass
class _ImageMeta:
    width: int
    height: int

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
        if normalized == "low_resolution_videos":
            video_hits = self._low_resolution_video_candidates(limit)
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

    def _build_photo_hit(
        self,
        photo,
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
