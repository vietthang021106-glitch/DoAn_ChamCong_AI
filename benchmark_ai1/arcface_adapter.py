"""Benchmark adapter that reuses the production AI1 buffalo_l and matcher."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import cv2


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import face_engine as production_face_engine  # noqa: E402
import face_matching as production_face_matching  # noqa: E402
from benchmark_ai1.matching_strategies import MAX, identify_embedding as benchmark_identify_embedding  # noqa: E402


ALGORITHM = "ArcFace"
MODEL = "InsightFace buffalo_l (production AI1)"
INITIAL_THRESHOLD = 0.45
THRESHOLD = INITIAL_THRESHOLD
SCORE_DESCRIPTION = "maximum cosine similarity across enrolled samples; higher is better"


def _employee_id(folder_name: str) -> int:
    prefix, separator, value = folder_name.partition("_")
    if prefix != "MaNV" or not separator or not value.isdigit():
        raise ValueError(f"Invalid employee folder name: {folder_name!r}; expected MaNV_<integer>.")
    return int(value)


class ArcFaceAdapter:
    """Extract embeddings with AI1 production code; keep the gallery in process memory."""

    algorithm = ALGORITHM
    threshold = THRESHOLD
    config = {
        "model": MODEL,
        "embedding_dimensions": 512,
        "initial_threshold": INITIAL_THRESHOLD,
        "matching": "production face_matching.identify_embedding, multi-sample max cosine",
        "score": SCORE_DESCRIPTION,
    }

    def __init__(self):
        self.engine = production_face_engine.face_engine
        self.gallery: dict[int, dict] = {}

    def initialize(self) -> None:
        self.engine.initialize()

    def enroll(self, train_images) -> None:
        """Build an in-memory gallery from image paths or (employee_id, image_path) pairs."""
        self.initialize()
        gallery: dict[int, dict] = {}
        for item in train_images:
            employee_id, path = item if isinstance(item, (tuple, list)) else (_employee_id(Path(item).parent.name), item)
            employee_id = int(employee_id)
            frame = cv2.imread(str(path), cv2.IMREAD_COLOR)
            if frame is None:
                raise ValueError(f"Could not read training image: {path}")
            faces = self.engine.detect_embeddings(frame)
            if len(faces) != 1:
                raise ValueError(f"Expected exactly one face in training image {path}; found {len(faces)}.")
            gallery.setdefault(employee_id, {"HoTen": "", "embeddings": [], "n_samples": 0})["embeddings"].append(
                faces[0]["embedding"]
            )
        if not gallery:
            raise ValueError("No training images were provided.")
        for person in gallery.values():
            person["embeddings"] = tuple(person["embeddings"])
            person["n_samples"] = len(person["embeddings"])
        self.gallery = gallery

    def identify(self, test_image, threshold: float | None = None) -> dict:
        embedding, embedding_latency = self.extract_embedding(test_image)
        result = self.identify_embedding(embedding, threshold=threshold, strategy=MAX)
        result["embedding_latency_ms"] = embedding_latency
        result["latency_ms"] = embedding_latency + result["matching_latency_ms"]
        return result

    def extract_embedding(self, image_path):
        """Return one production ArcFace embedding and image/decode/inference latency."""
        started = time.perf_counter()
        path = getattr(image_path, "path", image_path)
        frame = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError(f"Could not read image: {path}")
        faces = self.engine.detect_embeddings(frame)
        if len(faces) != 1:
            raise ValueError(f"Expected exactly one face in {path}; found {len(faces)}.")
        return faces[0]["embedding"], (time.perf_counter() - started) * 1000.0

    def identify_embedding(
        self,
        embedding,
        threshold: float | None = None,
        strategy: str = MAX,
    ) -> dict:
        """Match an embedding against the in-memory training gallery."""
        started = time.perf_counter()
        threshold = INITIAL_THRESHOLD if threshold is None else float(threshold)
        # MAX delegates to the production multi-sample matcher. TOP2_MEAN is implemented
        # only in benchmark_ai1.matching_strategies and does not alter production code.
        result = benchmark_identify_embedding(
            embedding,
            self.gallery,
            threshold,
            strategy,
            production_max_matcher=production_face_matching.identify_embedding,
        )
        result["matching_latency_ms"] = (time.perf_counter() - started) * 1000.0
        return result

    def warm_up(self, image_path) -> None:
        self.identify(image_path)
