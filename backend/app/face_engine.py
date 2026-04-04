from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import threading
import zipfile

import cv2
from huggingface_hub import hf_hub_download
import httpx
import numpy as np
import torch
from torch.nn import functional as F

from app.adaface_model import AdaFaceBundle, load_adaface_bundle
from app.config import Settings, get_settings
from app.face_alignment import norm_crop
from app.scrfd_detector import SCRFDDetector

SCRFD_PACKS = {
    "buffalo_sc": {
        "url": "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_sc.zip",
        "default_model": "det_500m.onnx",
    },
    "buffalo_l": {
        "url": "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip",
        "default_model": "det_10g.onnx",
    },
}


@dataclass
class DetectedFace:
    bbox: list[float]
    landmarks: list[list[float]]
    score: float
    embedding: list[float]


class DeepFaceEngine:
    _lock = threading.Lock()
    _detector_cache: dict[str, SCRFDDetector] = {}
    _recognizer_cache: dict[str, AdaFaceBundle] = {}

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def extract_faces(self, photo_path: Path, max_faces: int | None = None) -> list[DetectedFace]:
        image = cv2.imread(str(photo_path))
        if image is None:
            return []

        detector = self._get_detector()
        detections, landmarks = detector.detect(
            image,
            max_num=max_faces or self.settings.face_detection_max_faces,
        )
        if detections.size == 0 or landmarks is None or len(landmarks) == 0:
            return []

        face_images: list[np.ndarray] = []
        metadata: list[tuple[list[float], list[list[float]], float]] = []
        for detection, face_landmarks in zip(detections, landmarks):
            score = float(detection[4])
            if score < self.settings.face_detection_confidence_threshold:
                continue
            aligned_face = norm_crop(image, face_landmarks.astype(np.float32), image_size=112)
            face_images.append(aligned_face)
            metadata.append(
                (
                    detection[:4].astype(np.float32).tolist(),
                    face_landmarks.astype(np.float32).tolist(),
                    score,
                )
            )

        embeddings = self._embed_faces(face_images)
        results: list[DetectedFace] = []
        for (bbox, face_landmarks, score), embedding in zip(metadata, embeddings):
            results.append(
                DetectedFace(
                    bbox=bbox,
                    landmarks=face_landmarks,
                    score=score,
                    embedding=embedding,
                )
            )
        return results

    def extract_face_embeddings(self, photo_path: Path, max_faces: int | None = None) -> list[list[float]]:
        return [face.embedding for face in self.extract_faces(photo_path, max_faces=max_faces)]

    def _embed_faces(self, faces: list[np.ndarray]) -> list[list[float]]:
        if not faces:
            return []

        bundle = self._get_recognizer()
        device = next(bundle.model.parameters()).device
        tensors = []
        for face in faces:
            prepared = face
            if bundle.color_space == "RGB":
                prepared = cv2.cvtColor(prepared, cv2.COLOR_BGR2RGB)
            tensors.append(bundle.transform(prepared))

        batch_size = max(1, self.settings.face_recognition_batch_size)
        outputs: list[list[float]] = []
        with torch.inference_mode():
            for start in range(0, len(tensors), batch_size):
                batch = torch.stack(tensors[start : start + batch_size], dim=0).to(device)
                embeddings = bundle.model(batch)
                embeddings = F.normalize(embeddings, dim=1)
                outputs.extend(embeddings.detach().cpu().numpy().astype(np.float32).tolist())
        return outputs

    def _get_detector(self) -> SCRFDDetector:
        model_path = self._ensure_scrfd_model()
        cache_key = str(model_path)
        with self._lock:
            detector = self._detector_cache.get(cache_key)
            if detector is None:
                detector = SCRFDDetector(model_path)
                detector.prepare(
                    input_size=(self.settings.face_detection_input_size, self.settings.face_detection_input_size),
                    det_threshold=self.settings.face_detection_confidence_threshold,
                    nms_threshold=self.settings.face_detection_nms_threshold,
                )
                self._detector_cache = {cache_key: detector}
            return detector

    def _get_recognizer(self) -> AdaFaceBundle:
        model_dir = self._ensure_adaface_model()
        cache_key = str(model_dir)
        with self._lock:
            bundle = self._recognizer_cache.get(cache_key)
            if bundle is None:
                bundle = load_adaface_bundle(
                    config_path=model_dir / "pretrained_model" / "model.yaml",
                    weights_path=model_dir / "pretrained_model" / self.settings.face_recognition_model_filename,
                    device_name=self.settings.face_recognition_device,
                )
                self._recognizer_cache = {cache_key: bundle}
            return bundle

    def _ensure_scrfd_model(self) -> Path:
        pack_name = self.settings.face_detection_pack_name.strip()
        pack = SCRFD_PACKS.get(pack_name)
        if pack is None:
            raise ValueError(f"Unsupported SCRFD pack name: {pack_name}")

        pack_root = self.settings.face_model_root / "scrfd" / pack_name
        model_filename = self.settings.face_detection_model_filename or pack["default_model"]
        model_path = pack_root / model_filename
        if model_path.exists():
            return model_path

        pack_root.mkdir(parents=True, exist_ok=True)
        zip_path = self.settings.face_model_root / "scrfd" / f"{pack_name}.zip"
        self._download_file(pack["url"], zip_path)
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(pack_root)
        zip_path.unlink(missing_ok=True)

        if not model_path.exists():
            raise FileNotFoundError(f"SCRFD model not found after extraction: {model_path}")
        return model_path

    def _ensure_adaface_model(self) -> Path:
        repo_id = self.settings.face_recognition_repo_id.strip()
        repo_name = repo_id.split("/")[-1]
        target_dir = self.settings.face_model_root / "adaface" / repo_name
        model_path = target_dir / "pretrained_model" / self.settings.face_recognition_model_filename
        config_path = target_dir / "pretrained_model" / "model.yaml"
        if model_path.exists() and config_path.exists():
            return target_dir

        target_dir.mkdir(parents=True, exist_ok=True)
        hf_hub_download(
            repo_id=repo_id,
            filename=f"pretrained_model/{self.settings.face_recognition_model_filename}",
            local_dir=target_dir,
        )
        hf_hub_download(
            repo_id=repo_id,
            filename="pretrained_model/model.yaml",
            local_dir=target_dir,
        )
        return target_dir

    @staticmethod
    def _download_file(url: str, target_path: Path) -> None:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with httpx.stream("GET", url, follow_redirects=True, timeout=300.0) as response:
            response.raise_for_status()
            with target_path.open("wb") as handle:
                for chunk in response.iter_bytes():
                    if chunk:
                        handle.write(chunk)
