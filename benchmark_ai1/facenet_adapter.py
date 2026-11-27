"""Independent FaceNet benchmark adapter backed by facenet-pytorch pretrained weights."""

from __future__ import annotations

import time
from pathlib import Path

import cv2
import numpy as np


ALGORITHM = "FaceNet"
MODEL = "InceptionResnetV1 pretrained on VGGFace2 via facenet-pytorch"
INITIAL_THRESHOLD = 0.60  # Starting value only; runner calibrates from validation data.
THRESHOLD = INITIAL_THRESHOLD
SCORE_DESCRIPTION = "maximum cosine similarity across enrolled samples; higher is better"


def _employee_id(folder_name: str) -> int:
    prefix, separator, value = folder_name.partition("_")
    if prefix != "MaNV" or not separator or not value.isdigit():
        raise ValueError(f"Invalid employee folder name: {folder_name!r}; expected MaNV_<integer>.")
    return int(value)


class FaceNetAdapter:
    """FaceNet embeddings and matching with no production database or model storage."""

    algorithm = ALGORITHM
    threshold = THRESHOLD
    config = {
        "model": MODEL,
        "embedding_dimensions": 512,
        "initial_threshold": INITIAL_THRESHOLD,
        "threshold_status": "provisional; calibrate on a separate validation set",
        "matching": "maximum cosine similarity across training samples",
        "score": SCORE_DESCRIPTION,
    }

    def __init__(self, device: str = "cpu"):
        try:
            import torch
            from facenet_pytorch import InceptionResnetV1, MTCNN
        except ImportError as exc:
            raise RuntimeError(
                "FaceNet dependency missing. Install in the benchmark environment with: "
                "python -m pip install facenet-pytorch"
            ) from exc
        self.torch = torch
        self.device = torch.device(device)
        self.mtcnn = MTCNN(image_size=160, margin=0, keep_all=False, device=self.device)
        self.model = InceptionResnetV1(pretrained="vggface2").eval().to(self.device)
        self.gallery: dict[int, list[np.ndarray]] = {}

    def _embedding(self, image_path) -> np.ndarray:
        frame = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError(f"Could not read image: {image_path}")
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        face = self.mtcnn(rgb)
        if face is None:
            raise ValueError(f"FaceNet MTCNN found no face in: {image_path}")
        with self.torch.inference_mode():
            vector = self.model(face.unsqueeze(0).to(self.device)).squeeze(0).cpu().numpy().astype(np.float32)
        norm = float(np.linalg.norm(vector))
        if not np.isfinite(norm) or norm <= 1e-12:
            raise ValueError(f"FaceNet returned an invalid embedding for: {image_path}")
        return vector / norm

    def enroll(self, train_images) -> None:
        gallery: dict[int, list[np.ndarray]] = {}
        for item in train_images:
            employee_id, path = item if isinstance(item, (tuple, list)) else (_employee_id(Path(item).parent.name), item)
            gallery.setdefault(int(employee_id), []).append(self._embedding(path))
        if not gallery:
            raise ValueError("No training images were provided.")
        self.gallery = gallery

    def identify(self, test_image, threshold: float | None = None) -> dict:
        started = time.perf_counter()
        threshold = INITIAL_THRESHOLD if threshold is None else float(threshold)
        vector = self._embedding(getattr(test_image, "path", test_image))
        best_id, best_score = None, -1.0
        for employee_id, samples in self.gallery.items():
            score = max(float(np.dot(vector, sample)) for sample in samples)
            if score > best_score:
                best_id, best_score = employee_id, score
        matched = best_id is not None and best_score >= threshold
        return {
            "candidate_id": best_id,
            "predicted_id": best_id if matched else "UNKNOWN",
            "score": best_score if best_id is not None else None,
            "match": bool(matched),
            "latency_ms": (time.perf_counter() - started) * 1000.0,
        }

    def warm_up(self, image_path) -> None:
        self.identify(image_path)
