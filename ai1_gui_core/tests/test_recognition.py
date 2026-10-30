"""Recognition-session logic tests that use generated in-memory frames only."""

import threading
import time
import unittest

import numpy as np

from camera_source import FramePacket
from ai1_standalone_core.config import FRAME_CONSISTENCY_THRESHOLD
from ai1_standalone_core.recognition import (
    check_three_frame_consistency,
    face_sharpness,
    recognize_sequence_from_source,
)


def basis(index=0):
    vector = np.zeros(512, dtype=np.float32)
    vector[index] = 1.0
    return vector


def sharp_frame(seed):
    rng = np.random.default_rng(seed)
    return rng.integers(0, 256, size=(180, 160, 3), dtype=np.uint8)


class FakeEngine:
    def __init__(self, embeddings=None):
        self.embeddings = list(embeddings or [basis()])
        self.calls = 0

    def detect_embeddings(self, _frame):
        index = min(self.calls, len(self.embeddings) - 1)
        self.calls += 1
        return [{"embedding": self.embeddings[index], "detection_score": 0.99,
                 "bbox": [10, 10, 145, 170]}]


class FreshSource:
    def __init__(self):
        self.sequence = 0

    def get_frame(self):
        self.sequence += 1
        return FramePacket(sharp_frame(self.sequence), self.sequence, time.monotonic())


class StaleSource:
    def get_frame(self):
        return FramePacket(sharp_frame(1), 1, time.monotonic() - 2.0)


class RecognitionTests(unittest.TestCase):
    def test_temporal_consistency_uses_point_six_threshold(self):
        self.assertEqual(FRAME_CONSISTENCY_THRESHOLD, 0.60)
        self.assertTrue(check_three_frame_consistency([basis(), basis(), basis()])["valid"])
        self.assertFalse(check_three_frame_consistency([basis(0), basis(0), basis(1)])["valid"])

    def test_laplacian_sharpness_distinguishes_flat_and_detailed_frame(self):
        flat = np.full((180, 160, 3), 127, dtype=np.uint8)
        detailed = sharp_frame(8)
        self.assertLess(face_sharpness(flat, [10, 10, 145, 170]),
                        face_sharpness(detailed, [10, 10, 145, 170]))

    def test_three_fresh_distinct_snapshots_and_progress(self):
        progress = []
        engine = FakeEngine()
        gallery = {"MaNV_1": {"HoTen": "Employee One", "embeddings": (basis(),) * 5}}
        result = recognize_sequence_from_source(
            engine, FreshSource(), gallery, threading.Event(),
            progress_callback=lambda count, total: progress.append((count, total)),
            timeout_seconds=2.0,
        )
        self.assertEqual(result["status"], "MATCH")
        self.assertEqual(result["captured_frames"], 3)
        self.assertEqual(progress, [(1, 3), (2, 3), (3, 3)])
        self.assertEqual(engine.calls, 3)
        self.assertEqual(result["threshold"], 0.45)
        self.assertIn("best_frame", result)

    def test_stale_frame_times_out_as_retry(self):
        result = recognize_sequence_from_source(
            FakeEngine(), StaleSource(), {}, threading.Event(), timeout_seconds=0.05,
        )
        self.assertEqual(result["status"], "RETRY")
        self.assertIn("STALE_FRAME", result["reason"])
        self.assertEqual(result["captured_frames"], 0)

    def test_inconsistent_snapshots_retry_without_gallery_match(self):
        engine = FakeEngine([basis(0), basis(0), basis(1)])
        gallery = {"MaNV_1": {"HoTen": "Employee One", "embeddings": (basis(0),) * 5}}
        result = recognize_sequence_from_source(
            engine, FreshSource(), gallery, threading.Event(), timeout_seconds=2.0,
        )
        self.assertEqual(result["status"], "RETRY")
        self.assertIn("INCONSISTENT", result["reason"])
        self.assertEqual(result["predicted_id"], "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
