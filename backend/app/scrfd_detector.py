from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import onnxruntime


@dataclass
class SCRFDDetection:
    bbox: np.ndarray
    landmarks: np.ndarray
    score: float


def _distance_to_bbox(points: np.ndarray, distance: np.ndarray) -> np.ndarray:
    x1 = points[:, 0] - distance[:, 0]
    y1 = points[:, 1] - distance[:, 1]
    x2 = points[:, 0] + distance[:, 2]
    y2 = points[:, 1] + distance[:, 3]
    return np.stack([x1, y1, x2, y2], axis=-1)


def _distance_to_kps(points: np.ndarray, distance: np.ndarray) -> np.ndarray:
    predictions = []
    for index in range(0, distance.shape[1], 2):
        predictions.append(points[:, index % 2] + distance[:, index])
        predictions.append(points[:, index % 2 + 1] + distance[:, index + 1])
    return np.stack(predictions, axis=-1)


class SCRFDDetector:
    def __init__(
        self,
        model_path: Path,
        *,
        providers: list[str] | None = None,
    ) -> None:
        self.model_path = Path(model_path)
        self.session = onnxruntime.InferenceSession(
            str(self.model_path),
            providers=providers or ["CPUExecutionProvider"],
        )
        self.nms_threshold = 0.4
        self.det_threshold = 0.45
        self.input_size: tuple[int, int] | None = None
        self._center_cache: dict[tuple[int, int, int], np.ndarray] = {}
        self._init_vars()

    def _init_vars(self) -> None:
        input_cfg = self.session.get_inputs()[0]
        input_shape = input_cfg.shape
        if isinstance(input_shape[2], str):
            self.input_size = None
        else:
            self.input_size = tuple(input_shape[2:4][::-1])

        outputs = self.session.get_outputs()
        self.input_name = input_cfg.name
        self.output_names = [output.name for output in outputs]
        self.input_mean = 127.5
        self.input_std = 128.0
        self.use_kps = False
        self.num_anchors = 1

        if len(outputs) == 6:
            self.fmc = 3
            self.feat_stride_fpn = [8, 16, 32]
            self.num_anchors = 2
        elif len(outputs) == 9:
            self.fmc = 3
            self.feat_stride_fpn = [8, 16, 32]
            self.num_anchors = 2
            self.use_kps = True
        elif len(outputs) == 10:
            self.fmc = 5
            self.feat_stride_fpn = [8, 16, 32, 64, 128]
            self.num_anchors = 1
        elif len(outputs) == 15:
            self.fmc = 5
            self.feat_stride_fpn = [8, 16, 32, 64, 128]
            self.num_anchors = 1
            self.use_kps = True
        else:
            raise RuntimeError(f"Unexpected SCRFD output count: {len(outputs)}")

    def prepare(
        self,
        *,
        input_size: tuple[int, int],
        det_threshold: float,
        nms_threshold: float,
    ) -> None:
        self.input_size = input_size
        self.det_threshold = det_threshold
        self.nms_threshold = nms_threshold

    def detect(self, image: np.ndarray, *, max_num: int = 0) -> tuple[np.ndarray, np.ndarray | None]:
        if self.input_size is None:
            raise RuntimeError("SCRFD detector is not prepared with an input size")

        image_height, image_width = image.shape[:2]
        model_width, model_height = self.input_size
        image_ratio = float(image_height) / max(image_width, 1)
        model_ratio = float(model_height) / max(model_width, 1)

        if image_ratio > model_ratio:
            new_height = model_height
            new_width = int(new_height / image_ratio)
        else:
            new_width = model_width
            new_height = int(new_width * image_ratio)

        scale = float(new_height) / max(image_height, 1)
        resized_image = cv2.resize(image, (new_width, new_height))
        padded = np.zeros((model_height, model_width, 3), dtype=np.uint8)
        padded[:new_height, :new_width, :] = resized_image

        scores_list, boxes_list, kps_list = self._forward(padded)
        if not scores_list or not boxes_list:
            return np.empty((0, 5), dtype=np.float32), None

        scores = np.vstack(scores_list)
        boxes = np.vstack(boxes_list) / scale
        order = scores.ravel().argsort()[::-1]
        pre_detections = np.hstack((boxes, scores)).astype(np.float32, copy=False)
        pre_detections = pre_detections[order, :]
        keep = self._nms(pre_detections)
        detections = pre_detections[keep, :]

        landmarks = None
        if self.use_kps and kps_list:
            landmarks = np.vstack(kps_list) / scale
            landmarks = landmarks[order, :, :]
            landmarks = landmarks[keep, :, :]

        if max_num > 0 and detections.shape[0] > max_num:
            areas = (detections[:, 2] - detections[:, 0]) * (detections[:, 3] - detections[:, 1])
            image_center = np.array([image_width / 2.0, image_height / 2.0], dtype=np.float32)
            centers = np.stack(
                [
                    (detections[:, 0] + detections[:, 2]) / 2.0,
                    (detections[:, 1] + detections[:, 3]) / 2.0,
                ],
                axis=1,
            )
            offset_distance = np.sum(np.square(centers - image_center), axis=1)
            metric = areas - offset_distance * 2.0
            best_indices = np.argsort(metric)[::-1][:max_num]
            detections = detections[best_indices, :]
            if landmarks is not None:
                landmarks = landmarks[best_indices, :, :]

        return detections, landmarks

    def _forward(self, image: np.ndarray) -> tuple[list[np.ndarray], list[np.ndarray], list[np.ndarray]]:
        blob = cv2.dnn.blobFromImage(
            image,
            scalefactor=1.0 / self.input_std,
            size=self.input_size,
            mean=(self.input_mean, self.input_mean, self.input_mean),
            swapRB=True,
        )
        outputs = self.session.run(self.output_names, {self.input_name: blob})

        scores_list: list[np.ndarray] = []
        boxes_list: list[np.ndarray] = []
        kps_list: list[np.ndarray] = []

        for index, stride in enumerate(self.feat_stride_fpn):
            if self.use_kps:
                scores = outputs[index]
                bbox_predictions = outputs[index + self.fmc] * stride
                kps_predictions = outputs[index + self.fmc * 2] * stride
            else:
                scores = outputs[index]
                bbox_predictions = outputs[index + self.fmc] * stride
                kps_predictions = None

            height = blob.shape[2] // stride
            width = blob.shape[3] // stride
            key = (height, width, stride)
            anchor_centers = self._center_cache.get(key)
            if anchor_centers is None:
                anchor_centers = np.stack(np.mgrid[:height, :width][::-1], axis=-1).astype(np.float32)
                anchor_centers = (anchor_centers * stride).reshape((-1, 2))
                if self.num_anchors > 1:
                    anchor_centers = np.stack([anchor_centers] * self.num_anchors, axis=1).reshape((-1, 2))
                self._center_cache[key] = anchor_centers

            positive_indices = np.where(scores.reshape(-1) >= self.det_threshold)[0]
            if positive_indices.size == 0:
                continue

            boxes = _distance_to_bbox(anchor_centers, bbox_predictions.reshape((-1, 4)))[positive_indices]
            scores_list.append(scores.reshape(-1, 1)[positive_indices])
            boxes_list.append(boxes)

            if self.use_kps and kps_predictions is not None:
                keypoints = _distance_to_kps(anchor_centers, kps_predictions.reshape((-1, 10))).reshape((-1, 5, 2))
                kps_list.append(keypoints[positive_indices])

        return scores_list, boxes_list, kps_list

    def _nms(self, detections: np.ndarray) -> list[int]:
        x1 = detections[:, 0]
        y1 = detections[:, 1]
        x2 = detections[:, 2]
        y2 = detections[:, 3]
        scores = detections[:, 4]
        areas = (x2 - x1 + 1) * (y2 - y1 + 1)
        order = scores.argsort()[::-1]

        keep: list[int] = []
        while order.size > 0:
            current = int(order[0])
            keep.append(current)
            xx1 = np.maximum(x1[current], x1[order[1:]])
            yy1 = np.maximum(y1[current], y1[order[1:]])
            xx2 = np.minimum(x2[current], x2[order[1:]])
            yy2 = np.minimum(y2[current], y2[order[1:]])

            width = np.maximum(0.0, xx2 - xx1 + 1)
            height = np.maximum(0.0, yy2 - yy1 + 1)
            intersection = width * height
            overlap = intersection / (areas[current] + areas[order[1:]] - intersection)
            remaining = np.where(overlap <= self.nms_threshold)[0]
            order = order[remaining + 1]

        return keep
