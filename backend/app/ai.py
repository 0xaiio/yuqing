import base64
from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from typing import Any

import httpx

from app.config import Settings, get_settings

try:
    from rapidocr_onnxruntime import RapidOCR
except ImportError:  # pragma: no cover - handled gracefully at runtime
    RapidOCR = None


SCENE_CANDIDATES = {"beach", "travel", "office", "home", "sunset", "food"}
OBJECT_CANDIDATES = {"cat", "dog", "car", "phone", "book", "lego"}


@dataclass
class AnalysisResult:
    caption: str | None = None
    ocr_text: str | None = None
    people: list[str] = field(default_factory=list)
    scene_tags: list[str] = field(default_factory=list)
    object_tags: list[str] = field(default_factory=list)


class AIAnalyzer:
    """Hybrid analyzer with local OCR and optional vision model calls."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._ocr_engine = None

    def analyze(self, photo_path: Path, source_kind: str) -> AnalysisResult:
        fallback = self._fallback_analysis(photo_path, source_kind)
        ocr_text = self._run_ocr(photo_path)
        if ocr_text:
            fallback.ocr_text = ocr_text

        vision_result = self._run_vision(photo_path, source_kind=source_kind, ocr_text=ocr_text)
        if vision_result is not None:
            fallback = self._merge_results(fallback, vision_result)

        fallback.people = self._dedupe_items(fallback.people)
        fallback.scene_tags = self._dedupe_items(fallback.scene_tags)
        fallback.object_tags = self._dedupe_items(fallback.object_tags)
        fallback.caption = (fallback.caption or "").strip() or f"Imported from {source_kind}"
        fallback.ocr_text = (fallback.ocr_text or "").strip() or None
        return fallback

    def analyze_video_frames(
        self,
        frame_paths: list[Path],
        *,
        source_kind: str,
        asset_name: str,
    ) -> AnalysisResult:
        if not frame_paths:
            return AnalysisResult(
                caption=f"Imported video from {source_kind}: {asset_name}",
                ocr_text=None,
                people=[],
                scene_tags=[],
                object_tags=[],
            )

        fallback = AnalysisResult(
            caption=f"Imported video from {source_kind}: {asset_name}",
            ocr_text=None,
            people=[],
            scene_tags=[],
            object_tags=[],
        )
        aggregated_ocr: list[str] = []
        for frame_path in frame_paths[:6]:
            ocr_text = self._run_ocr(frame_path)
            if ocr_text:
                aggregated_ocr.append(ocr_text)

        if aggregated_ocr:
            fallback.ocr_text = "\n".join(self._dedupe_items(aggregated_ocr))

        vision_result = self._run_video_vision(
            frame_paths[:6],
            source_kind=source_kind,
            asset_name=asset_name,
            ocr_text=fallback.ocr_text,
        )
        if vision_result is not None:
            fallback = self._merge_results(fallback, vision_result)

        fallback.people = self._dedupe_items(fallback.people)
        fallback.scene_tags = self._dedupe_items(fallback.scene_tags)
        fallback.object_tags = self._dedupe_items(fallback.object_tags)
        fallback.caption = (fallback.caption or "").strip() or f"Imported video from {source_kind}: {asset_name}"
        fallback.ocr_text = (fallback.ocr_text or "").strip() or None
        return fallback

    def _fallback_analysis(self, photo_path: Path, source_kind: str) -> AnalysisResult:
        stem_tokens = [token.lower() for token in re.split(r"[_\-\s]+", photo_path.stem) if token]
        scene_tags = sorted({token for token in stem_tokens if token in SCENE_CANDIDATES})
        object_tags = sorted({token for token in stem_tokens if token in OBJECT_CANDIDATES})

        caption = f"Imported from {source_kind}"
        if stem_tokens:
            caption = f"{caption}: {' '.join(stem_tokens[:6])}"

        return AnalysisResult(
            caption=caption,
            ocr_text=photo_path.stem.replace("_", " "),
            people=[],
            scene_tags=scene_tags,
            object_tags=object_tags,
        )

    def _run_ocr(self, photo_path: Path) -> str | None:
        if not self.settings.ai_enable_ocr:
            return None
        if self.settings.ai_ocr_engine.lower() != "rapidocr":
            return None
        if RapidOCR is None:
            return None

        try:
            if self._ocr_engine is None:
                self._ocr_engine = RapidOCR()

            result, _ = self._ocr_engine(str(photo_path))
        except Exception:
            return None

        if not result:
            return None

        lines: list[str] = []
        for item in result:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                text = str(item[1]).strip()
                if text:
                    lines.append(text)

        if not lines:
            return None
        return "\n".join(lines)

    def _run_vision(self, photo_path: Path, source_kind: str, ocr_text: str | None) -> AnalysisResult | None:
        if not self.settings.ai_enable_vision:
            return None
        if not self.settings.ai_vision_model or not self.settings.ai_vision_api_key:
            return None

        request_body = self._build_vision_payload(photo_path, source_kind=source_kind, ocr_text=ocr_text)
        endpoint = self.settings.ai_vision_base_url.rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.settings.ai_vision_api_key}",
            "Content-Type": "application/json",
        }

        try:
            with httpx.Client(timeout=self.settings.ai_vision_timeout_seconds) as client:
                response = client.post(endpoint, json=request_body, headers=headers)
                response.raise_for_status()
        except Exception:
            return None

        content = self._extract_message_content(response.json())
        parsed = self._parse_vision_json(content)
        if parsed is None:
            return None
        return parsed

    def _run_video_vision(
        self,
        frame_paths: list[Path],
        *,
        source_kind: str,
        asset_name: str,
        ocr_text: str | None,
    ) -> AnalysisResult | None:
        if not self.settings.ai_enable_vision:
            return None
        if not self.settings.ai_vision_model or not self.settings.ai_vision_api_key:
            return None

        request_body = self._build_video_vision_payload(
            frame_paths,
            source_kind=source_kind,
            asset_name=asset_name,
            ocr_text=ocr_text,
        )
        endpoint = self.settings.ai_vision_base_url.rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.settings.ai_vision_api_key}",
            "Content-Type": "application/json",
        }

        try:
            with httpx.Client(timeout=self.settings.ai_vision_timeout_seconds) as client:
                response = client.post(endpoint, json=request_body, headers=headers)
                response.raise_for_status()
        except Exception:
            return None

        content = self._extract_message_content(response.json())
        return self._parse_vision_json(content)

    def _build_vision_payload(self, photo_path: Path, source_kind: str, ocr_text: str | None) -> dict[str, Any]:
        image_base64 = base64.b64encode(photo_path.read_bytes()).decode("utf-8")
        suffix = photo_path.suffix.lower().replace(".", "") or "jpeg"
        mime_type = "image/jpeg" if suffix in {"jpg", "jpeg"} else f"image/{suffix}"
        prompt = (
            "Analyze this photo for an AI photo manager.\n"
            f"Source kind: {source_kind}\n"
            f"OCR preview: {ocr_text or 'none'}\n"
            "Return strict JSON only with keys: "
            "caption, people, scene_tags, object_tags.\n"
            "Rules:\n"
            "- caption is a concise Chinese sentence.\n"
            "- people, scene_tags, object_tags are arrays of short Chinese labels.\n"
            "- If uncertain, return empty arrays instead of guessing."
        )

        return {
            "model": self.settings.ai_vision_model,
            "temperature": 0.2,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a precise multimodal tagger for a desktop photo manager.",
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime_type};base64,{image_base64}"},
                        },
                    ],
                },
            ],
        }

    def _build_video_vision_payload(
        self,
        frame_paths: list[Path],
        *,
        source_kind: str,
        asset_name: str,
        ocr_text: str | None,
    ) -> dict[str, Any]:
        prompt = (
            "These images are sampled frames from one video for an AI media manager.\n"
            f"Source kind: {source_kind}\n"
            f"Asset name: {asset_name}\n"
            f"OCR preview: {ocr_text or 'none'}\n"
            "Return strict JSON only with keys: caption, people, scene_tags, object_tags.\n"
            "Rules:\n"
            "- caption is one concise Chinese sentence describing the whole video.\n"
            "- people, scene_tags, object_tags are arrays of short Chinese labels.\n"
            "- If uncertain, return empty arrays instead of guessing.\n"
            "- Focus on stable information across the sampled frames instead of single-frame noise."
        )
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for frame_path in frame_paths:
            suffix = frame_path.suffix.lower().replace(".", "") or "jpeg"
            mime_type = "image/jpeg" if suffix in {"jpg", "jpeg"} else f"image/{suffix}"
            image_base64 = base64.b64encode(frame_path.read_bytes()).decode("utf-8")
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{image_base64}"},
                }
            )

        return {
            "model": self.settings.ai_vision_model,
            "temperature": 0.2,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a precise multimodal tagger for a desktop media manager.",
                },
                {
                    "role": "user",
                    "content": content,
                },
            ],
        }

    @staticmethod
    def _extract_message_content(payload: dict[str, Any]) -> str:
        choices = payload.get("choices") or []
        if not choices:
            return ""

        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            texts: list[str] = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    texts.append(str(block.get("text", "")))
            return "\n".join(texts)
        return ""

    def _parse_vision_json(self, content: str) -> AnalysisResult | None:
        if not content.strip():
            return None

        json_text = self._extract_json_block(content)
        if not json_text:
            return None

        try:
            data = json.loads(json_text)
        except json.JSONDecodeError:
            return None

        return AnalysisResult(
            caption=self._normalize_text(data.get("caption")),
            ocr_text=None,
            people=self._normalize_list(data.get("people")),
            scene_tags=self._normalize_list(data.get("scene_tags")),
            object_tags=self._normalize_list(data.get("object_tags")),
        )

    @staticmethod
    def _extract_json_block(content: str) -> str | None:
        fenced = re.search(r"```json\s*(\{.*\})\s*```", content, re.DOTALL)
        if fenced:
            return fenced.group(1)

        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        return content[start : end + 1]

    @staticmethod
    def _normalize_text(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _normalize_list(self, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return self._dedupe_items([str(item).strip() for item in value if str(item).strip()])
        if isinstance(value, str):
            tokens = [item.strip() for item in re.split(r"[,\n，、/]+", value) if item.strip()]
            return self._dedupe_items(tokens)
        return []

    def _merge_results(self, fallback: AnalysisResult, vision_result: AnalysisResult) -> AnalysisResult:
        return AnalysisResult(
            caption=vision_result.caption or fallback.caption,
            ocr_text=fallback.ocr_text,
            people=self._dedupe_items([*fallback.people, *vision_result.people]),
            scene_tags=self._dedupe_items([*fallback.scene_tags, *vision_result.scene_tags]),
            object_tags=self._dedupe_items([*fallback.object_tags, *vision_result.object_tags]),
        )

    @staticmethod
    def _dedupe_items(values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            item = value.strip()
            if not item:
                continue
            key = item.lower()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(item)
        return normalized
