import cv2
import numpy as np

ARCFACE_TEMPLATE = np.array(
    [
        [38.2946, 51.6963],
        [73.5318, 51.5014],
        [56.0252, 71.7366],
        [41.5493, 92.3655],
        [70.7299, 92.2041],
    ],
    dtype=np.float32,
)


def estimate_norm(landmarks: np.ndarray, image_size: int = 112) -> np.ndarray:
    if landmarks.shape != (5, 2):
        raise ValueError(f"Expected 5-point landmarks, got shape {landmarks.shape}")

    if image_size % 112 == 0:
        ratio = float(image_size) / 112.0
        diff_x = 0.0
    elif image_size % 128 == 0:
        ratio = float(image_size) / 128.0
        diff_x = 8.0 * ratio
    else:
        raise ValueError("image_size should be divisible by 112 or 128")

    destination = ARCFACE_TEMPLATE * ratio
    destination[:, 0] += diff_x
    matrix, _ = cv2.estimateAffinePartial2D(
        landmarks.astype(np.float32),
        destination,
        method=cv2.LMEDS,
    )
    if matrix is None:
        raise ValueError("Unable to estimate face alignment transform")
    return matrix


def norm_crop(image: np.ndarray, landmarks: np.ndarray, image_size: int = 112) -> np.ndarray:
    matrix = estimate_norm(landmarks, image_size=image_size)
    return cv2.warpAffine(
        image,
        matrix,
        (image_size, image_size),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0.0,
    )
