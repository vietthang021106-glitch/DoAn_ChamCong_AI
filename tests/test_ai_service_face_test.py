import unittest
from concurrent.futures import ThreadPoolExecutor
import base64
import hashlib
import json
from pathlib import Path
import sys
import threading
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2
import numpy as np

import ai_service


class _Engine:
    _initialized = True

    def __init__(self, faces):
        self.faces = faces

    def detect_embeddings(self, frame):
        return self.faces


def _vector(index):
    vector = np.zeros(512, dtype=np.float32)
    vector[index] = 1.0
    return vector


class DeviceFaceRecognitionTests(unittest.TestCase):
    def _runtime(self, faces):
        runtime = ai_service.AIRuntime()
        runtime.engine = _Engine(faces)
        runtime._gallery_loaded = True
        runtime._gallery = {1: {"HoTen": "Nhan vien test", "embeddings": (_vector(0),), "n_samples": 1}}
        return runtime

    def test_single_frame_recognition_routes_require_three_fresh_snapshots(self):
        client = ai_service.app.test_client()
        camera_route = client.post("/api/ai/recognize")
        image_route = client.post("/api/ai/recognize-image", data=b"single jpeg", content_type="image/jpeg")
        for response in (camera_route, image_route):
            self.assertEqual(response.status_code, 409)
            self.assertFalse(response.get_json()["success"])
            self.assertEqual(response.get_json()["reason"], "THREE_FRESH_SNAPSHOTS_REQUIRED")

    def test_enrollment_pairs_image_and_vector_and_checks_identity(self):
        frame = np.random.default_rng(4).integers(65, 195, (480, 640, 3), dtype=np.uint8)
        ok, jpeg = cv2.imencode(".jpg", frame)
        self.assertTrue(ok)
        face = {"embedding": _vector(0), "vector_bytes": _vector(0).astype("<f4").tobytes(),
                "bbox": [220, 105, 420, 385], "detection_score": .99,
                "head_pose": {"yaw": 20.0, "pitch": 0.0}}
        runtime = self._runtime([face])
        sample = runtime.capture_enrollment_sample(frame, jpeg.tobytes(), "left", _vector(0))
        self.assertTrue(sample["success"])
        self.assertEqual(base64.b64decode(sample["vector"]), face["vector_bytes"])
        self.assertEqual(base64.b64decode(sample["image_jpeg"]), jpeg.tobytes())
        self.assertEqual(sample["image_sha256"], hashlib.sha256(jpeg.tobytes()).hexdigest())
        wrong = runtime.capture_enrollment_sample(frame, jpeg.tobytes(), "left", _vector(1))
        self.assertFalse(wrong["success"])
        with self.assertRaises(ValueError):
            runtime.capture_enrollment_sample(frame, jpeg.tobytes(), "left")
        self.assertFalse(runtime.capture_enrollment_sample(frame, jpeg.tobytes(), "up", _vector(0))["success"])
        self.assertFalse(runtime.inspect_enrollment_frame(np.zeros_like(frame), "left")["pose_ok"])
        self.assertFalse(self._runtime([face, face]).capture_enrollment_sample(frame, jpeg.tobytes(), "left")["success"])

    def test_enrollment_http_inspect_and_capture_contract(self):
        frame = np.random.default_rng(5).integers(65, 195, (480, 640, 3), dtype=np.uint8)
        ok, jpeg = cv2.imencode(".jpg", frame)
        self.assertTrue(ok)
        face = {"embedding": _vector(0), "vector_bytes": _vector(0).astype("<f4").tobytes(),
                "bbox": [220, 105, 420, 385], "detection_score": .99,
                "head_pose": {"yaw": 20.0, "pitch": 0.0}}
        body = {"image": base64.b64encode(jpeg.tobytes()).decode("ascii"), "expected_pose": "left"}
        original_runtime = ai_service.runtime
        try:
            ai_service.runtime = self._runtime([face])
            client = ai_service.app.test_client()
            inspected = client.post("/api/ai/enrollment/inspect", json=body)
            self.assertEqual(inspected.status_code, 200)
            self.assertTrue(inspected.get_json()["pose_ok"])
            self.assertEqual(client.post("/api/ai/enrollment/capture", json=body).status_code, 400)
            body["reference_vector"] = base64.b64encode(face["vector_bytes"]).decode("ascii")
            captured = client.post("/api/ai/enrollment/capture", json=body)
            self.assertEqual(captured.status_code, 200)
            self.assertEqual(base64.b64decode(captured.get_json()["image_jpeg"]), jpeg.tobytes())
            body["reference_vector"] = base64.b64encode(_vector(1).astype("<f4").tobytes()).decode("ascii")
            self.assertEqual(client.post("/api/ai/enrollment/capture", json=body).status_code, 409)
        finally:
            ai_service.runtime = original_runtime

    def test_gallery_refresh_keeps_samples_and_serializes_fetches(self):
        def payload(sample_id, index):
            raw = _vector(index).astype("<f4").tobytes()
            return json.dumps({"success": True, "embeddings": [{
                "ma_embedding": sample_id, "ma_nv": 1, "so_chieu": 512,
                "vector": base64.b64encode(raw).decode("ascii"),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }]}).encode("utf-8")

        class Response:
            def __init__(self, body): self.body = body
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def read(self): return self.body

        entered, release, second_started = threading.Event(), threading.Event(), threading.Event()
        calls = []

        def fetch(*_args, **_kwargs):
            calls.append(1)
            if len(calls) == 1:
                entered.set()
                if not release.wait(2):
                    raise TimeoutError("test fetch was not released")
                return Response(payload(1, 0))
            return Response(payload(2, 1))

        runtime = ai_service.AIRuntime()
        with patch("ai_service.urllib.request.urlopen", side_effect=fetch):
            with ThreadPoolExecutor(max_workers=2) as workers:
                first = workers.submit(runtime.refresh_gallery)
                self.assertTrue(entered.wait(1))
                def second_refresh():
                    second_started.set()
                    return runtime.refresh_gallery()
                second = workers.submit(second_refresh)
                self.assertTrue(second_started.wait(1))
                time.sleep(.05)
                self.assertEqual(len(calls), 1)
                release.set()
                self.assertEqual(first.result(3)["embedding_count"], 1)
                self.assertEqual(second.result(3)["embedding_count"], 1)
        self.assertEqual(runtime._gallery[1]["n_samples"], 1)
        self.assertAlmostEqual(float(runtime._gallery[1]["embeddings"][0][1]), 1.0)
        revision_before_duplicate = runtime._gallery_revision
        duplicate_document = json.loads(payload(1, 0).decode("utf-8"))
        duplicate_document["embeddings"].append(dict(duplicate_document["embeddings"][0]))
        duplicate_body = json.dumps(duplicate_document).encode("utf-8")
        with patch("ai_service.urllib.request.urlopen", return_value=Response(duplicate_body)):
            with self.assertRaisesRegex(ValueError, "invalid sample identity"):
                runtime.refresh_gallery()
        self.assertEqual(runtime._gallery_revision, revision_before_duplicate)
        self.assertEqual(runtime._gallery[1]["n_samples"], 1)
        with patch("ai_service.urllib.request.urlopen", side_effect=ValueError("bad response")):
            with self.assertRaises(ValueError):
                runtime.refresh_gallery()
        self.assertAlmostEqual(float(runtime._gallery[1]["embeddings"][0][1]), 1.0)


if __name__ == "__main__":
    unittest.main()
