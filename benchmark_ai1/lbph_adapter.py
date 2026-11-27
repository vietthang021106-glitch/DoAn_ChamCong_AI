"""OpenCV LBPH benchmark adapter with Haar face detection and in-memory training."""

from __future__ import annotations

import time
from pathlib import Path

import cv2
import numpy as np


ALGORITHM = "LBPH"
MODEL = "OpenCV cv2.face.LBPHFaceRecognizer_create"
INITIAL_THRESHOLD = 80.0  # Starting value only; runner calibrates from validation data.
THRESHOLD = INITIAL_THRESHOLD
SCORE_DESCRIPTION = "LBPH distance; lower is better"
FACE_SIZE = (160, 160)


def _employee_id(folder_name: str) -> int:
    prefix, separator, value = folder_name.partition("_")
    if prefix != "MaNV" or not separator or not value.isdigit():
        raise ValueError(f"Invalid employee folder name: {folder_name!r}; expected MaNV_<integer>.")
    return int(value)


class LBPHAdapter:
    algorithm = ALGORITHM
    threshold = THRESHOLD
    config = {
        "model": MODEL,
        "initial_threshold": INITIAL_THRESHOLD,
        "threshold_status": "provisional; calibrate on a separate validation set",
        "score": SCORE_DESCRIPTION,
        "preprocessing": f"Haar frontal-face crop, grayscale, resized to {FACE_SIZE[0]}x{FACE_SIZE[1]}",
    }

    def __init__(self):
        face_module = getattr(cv2, "face", None)
        factory = getattr(face_module, "LBPHFaceRecognizer_create", None) if face_module else None
        if factory is None:
            raise RuntimeError(
                "OpenCV LBPH is unavailable. Install the contrib build in the benchmark environment: "
                "python -m pip install opencv-contrib-python"
            )
        self.recognizer = factory()
        cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
        self.detector = cv2.CascadeClassifier(str(cascade_path))
        if self.detector.empty():
            raise RuntimeError(f"Could not load OpenCV Haar cascade: {cascade_path}")

    def _face(self, image_path) -> np.ndarray:
        frame = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError(f"Could not read image: {image_path}")
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self.detector.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40))
        if len(faces) != 1:
            raise ValueError(f"LBPH expected exactly one Haar-detected face in {image_path}; found {len(faces)}.")
        x, y, width, height = faces[0]
        crop = gray[y:y + height, x:x + width]
        return cv2.resize(crop, FACE_SIZE, interpolation=cv2.INTER_AREA)

    def enroll(self, train_images) -> None:
        images, labels = [], []
        for item in train_images:
            employee_id, path = item if isinstance(item, (tuple, list)) else (_employee_id(Path(item).parent.name), item)
            images.append(self._face(path))
            labels.append(int(employee_id))
        if not images:
            raise ValueError("No training images were provided.")
        self.recognizer.train(images, np.asarray(labels, dtype=np.int32))

    def identify(self, test_image, threshold: float | None = None) -> dict:
        started = time.perf_counter()
        threshold = INITIAL_THRESHOLD if threshold is None else float(threshold)
        face = self._face(getattr(test_image, "path", test_image))
        predicted_id, distance = self.recognizer.predict(face)
        matched = float(distance) <= threshold
        return {
            "candidate_id": int(predicted_id),
            "predicted_id": int(predicted_id) if matched else "UNKNOWN",
            "score": float(distance),
            "match": bool(matched),
            "latency_ms": (time.perf_counter() - started) * 1000.0,
        }

    def warm_up(self, image_path) -> None:
        self.identify(image_path)
