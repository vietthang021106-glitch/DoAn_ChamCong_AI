import unittest
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
import threading
from unittest.mock import patch
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

import face_engine
import face_evaluation
import face_matching
import app as flask_app
from tools import evaluate_face_recognition


class MatchingTests(unittest.TestCase):
    def test_normalization_and_cosine(self):
        first = np.zeros(512, dtype=np.float32)
        first[0] = 4
        second = np.zeros(512, dtype=np.float32)
        second[0] = 2
        self.assertAlmostEqual(float(np.linalg.norm(face_matching.normalize_embedding(first))), 1.0)
        self.assertAlmostEqual(face_matching.cosine_similarity(first, second), 1.0)

    def test_gallery_identify_verify_unknown(self):
        a = np.zeros(512, dtype="<f4"); a[0] = 1
        b = np.zeros(512, dtype="<f4"); b[1] = 1
        rows = [(1, 10, a.tobytes(), 512, "An"), (2, 20, b.tobytes(), 512, "Binh")]
        gallery, invalid = face_matching.aggregate_gallery(rows)
        self.assertFalse(invalid)
        self.assertEqual(face_matching.identify_embedding(a, gallery, 0.45)["MaNV"], 10)
        self.assertEqual(face_matching.verify_embedding(a, 10, gallery, 0.45)["status"], "MATCH")
        orthogonal = np.zeros(512, dtype=np.float32); orthogonal[2] = 1
        self.assertEqual(face_matching.identify_embedding(orthogonal, gallery, 0.45)["status"], "UNKNOWN")

    def test_five_samples_use_best_sample_not_centroid(self):
        probe = np.zeros(512, dtype="<f4"); probe[0] = 1
        other = np.zeros(512, dtype="<f4"); other[1] = 1
        third = np.zeros(512, dtype="<f4"); third[2] = 1
        rows = [(index, 10, vector.tobytes(), 512, "An")
                for index, vector in enumerate([probe, other, other, other, other], 1)]
        rows.append((6, 20, third.tobytes(), 512, "Binh"))
        gallery, invalid = face_matching.aggregate_gallery(rows)
        self.assertEqual(invalid, [])
        self.assertEqual(gallery[10]["n_samples"], 5)
        self.assertNotIn("embedding", gallery[10])
        self.assertEqual(face_matching.identify_embedding(probe, gallery, 0.45)["MaNV"], 10)
        self.assertEqual(face_matching.verify_embedding(probe, 10, gallery, 0.45)["similarity"], 1.0)
        self.assertEqual(face_matching.identify_embedding(third, gallery, 0.45)["MaNV"], 20)

    def test_invalid_rows_and_legacy_sample_count(self):
        good = np.zeros(512, dtype="<f4"); good[0] = 1
        nan = good.copy(); nan[0] = np.nan
        inf = good.copy(); inf[0] = np.inf
        rows = [(1, 7, good.tobytes(), 512, "Legacy"),
                (2, 7, good.tobytes(), 512, "Legacy"),
                (3, 7, good.tobytes()[:-1], 512, "Legacy"),
                (4, 7, good.tobytes(), 511, "Legacy"),
                (5, 7, nan.tobytes(), 512, "Legacy"),
                (6, 7, inf.tobytes(), 512, "Legacy"),
                (7, 7, bytes(2048), 512, "Legacy")]
        gallery, invalid = face_matching.aggregate_gallery(rows)
        self.assertEqual(gallery[7]["n_samples"], 2)
        self.assertEqual(len(invalid), 5)
        self.assertTrue(face_matching.verify_embedding(good, 7, gallery, 0.45)["match"])
        with self.assertRaises(ValueError):
            face_matching.normalize_embedding(np.zeros(511))

    def test_engine_512d_normalization_and_quality_gate(self):
        from types import SimpleNamespace
        frame = np.random.default_rng(3).integers(65, 195, (480, 640, 3), dtype=np.uint8)
        vector = np.zeros(512, dtype=np.float32); vector[0] = 4
        face = SimpleNamespace(normed_embedding=None, embedding=vector,
                               det_score=.99, bbox=[220, 105, 420, 385], kps=None)
        engine = face_engine.FaceRecognitionEngine()
        engine._initialized = True
        engine._app = SimpleNamespace(get=lambda _: [face])
        detected = engine.detect_embeddings(frame)
        self.assertEqual(len(detected), 1)
        self.assertEqual(len(detected[0]["vector_bytes"]), 2048)
        self.assertAlmostEqual(float(np.linalg.norm(detected[0]["embedding"])), 1.0)
        self.assertTrue(face_engine.assess_capture_quality(frame, detected[0])["ready"])
        self.assertFalse(face_engine.assess_capture_quality(np.zeros_like(frame), detected[0])["ready"])
        self.assertFalse(face_engine.assess_capture_quality(frame, {**detected[0], "detection_score": .5})["ready"])
        self.assertFalse(face_engine.assess_capture_quality(frame, {**detected[0], "bbox": [300, 200, 340, 260]})["ready"])
        face.embedding = np.zeros(511, dtype=np.float32)
        with self.assertRaises(RuntimeError):
            engine.detect_embeddings(frame)

    def test_enrollment_counts_low_confidence_secondary_without_changing_normal_threshold(self):
        from types import SimpleNamespace
        from ai1_standalone_core.ai1_adapter import validate_enrollment_frame

        frame = np.random.default_rng(7).integers(65, 195, (480, 640, 3), dtype=np.uint8)
        vector = np.eye(1, 512, 0, dtype=np.float32)[0]
        primary = SimpleNamespace(normed_embedding=vector, embedding=None, det_score=.98,
                                  bbox=[220, 105, 420, 385], kps=None)
        secondary = SimpleNamespace(normed_embedding=vector, embedding=None, det_score=.35,
                                    bbox=[20, 60, 120, 180], kps=None)
        detector = SimpleNamespace(det_thresh=.5)

        def get_faces(_frame):
            return [face for face in (primary, secondary)
                    if face.det_score >= detector.det_thresh]

        engine = face_engine.FaceRecognitionEngine()
        engine._initialized = True
        engine._app = SimpleNamespace(det_model=detector, get=get_faces)

        self.assertEqual(len(engine.detect_embeddings(frame)), 1)
        self.assertEqual(detector.det_thresh, .5)
        enrollment = validate_enrollment_frame(engine, frame, "frontal")
        self.assertEqual(enrollment["status"], "RETRY")
        self.assertEqual(enrollment["code"], "MULTIPLE FACES")
        self.assertEqual(enrollment["diagnostics"]["face_count"], 2)
        self.assertEqual(detector.det_thresh, .5)
        self.assertEqual(len(engine.detect_embeddings(frame)), 1)

    def test_face_engine_serializes_shared_model_inference(self):
        from types import SimpleNamespace
        state_lock = threading.Lock()
        active = 0
        max_active = 0
        face = SimpleNamespace(normed_embedding=np.eye(1, 512, 0, dtype=np.float32)[0],
                               embedding=None, det_score=.99, bbox=[220, 105, 420, 385], kps=None)

        def model_get(_frame):
            nonlocal active, max_active
            with state_lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep(.015)
            with state_lock:
                active -= 1
            return [face]

        engine = face_engine.FaceRecognitionEngine()
        engine._initialized = True
        engine._app = SimpleNamespace(get=model_get)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        with ThreadPoolExecutor(max_workers=4) as workers:
            results = list(workers.map(engine.detect_embeddings, [frame] * 8))
        self.assertEqual(len(results), 8)
        self.assertEqual(max_active, 1)

    def test_evaluation_metrics(self):
        result = face_evaluation.evaluate_scores([0.9, 0.95], [0.1, 0.2])
        self.assertEqual(result["far"], 0.0)
        self.assertEqual(result["frr"], 0.0)
        self.assertEqual(result["eer"], 0.0)
        self.assertEqual(result["genuine_count"], 2)

    def test_calibration_uses_the_same_max_sample_rule(self):
        first = np.zeros(512, dtype=np.float32); first[0] = 1
        other = np.zeros(512, dtype=np.float32); other[1] = 1
        second = np.zeros(512, dtype=np.float32); second[2] = 1
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as directory:
            for employee_id in ("10", "20"):
                for part in ("gallery", "probe"):
                    (Path(directory) / employee_id / part).mkdir(parents=True)

            def vectors(folder, _engine):
                if folder.parent.name == "10":
                    return [first, other, other, other, other] if folder.name == "gallery" else [first]
                return [second]

            with patch.object(evaluate_face_recognition, "load_embeddings", side_effect=vectors):
                metrics = evaluate_face_recognition.evaluate_dataset(directory, engine=object())
            self.assertEqual(metrics["genuine_mean"], 1.0)
            self.assertEqual(metrics["impostor_mean"], 0.0)


class FaceApiTests(unittest.TestCase):
    def setUp(self):
        flask_app.app.config["TESTING"] = True
        self.client = flask_app.app.test_client()
        with self.client.session_transaction() as session:
            session["MaNV"] = 1
            session["MaVaiTro"] = 1

    def test_legacy_enrollment_writer_is_retired(self):
        response = self.client.post("/api/employees/7/face/register", json={"action": "start"})
        self.assertEqual(response.status_code, 410)
        self.assertIn("PHP/MariaDB", response.json["message"])

    def test_flask_dashboard_renders_php_enrollment_link_and_three_snapshot_ui(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"/DoAn_ChamCong_AI/?action=index", response.data)
        self.assertIn(b"/api/face/recognition-sessions", response.data)
        self.assertNotIn(b"face-enrollment-preview", response.data)

    def test_single_frame_recognition_is_rejected(self):
        for path, body in (("/api/face/identify", {"image": "x"}),
                           ("/api/face/verify", {"image": "x", "MaNV": 7})):
            with self.subTest(path=path):
                response = self.client.post(path, json=body)
                self.assertEqual(response.status_code, 409)
                self.assertFalse(response.json["match"])

    def test_recognition_uses_the_central_three_snapshot_service(self):
        session_id = "a" * 32
        with patch.object(flask_app, "_request_ai1_json", return_value=(202, {
            "success": True, "session_id": session_id, "state": "CAPTURING",
            "captured_frames": 0, "total_frames": 3,
        })) as proxy:
            started = self.client.post("/api/face/recognition-sessions", json={})
        self.assertEqual(started.status_code, 202)
        self.assertEqual(started.json["session_id"], session_id)
        self.assertEqual(proxy.call_args.args, ("POST", "/api/ai/recognition-sessions", {}))

        with patch.object(flask_app, "_request_ai1_json", return_value=(200, {
            "success": True, "session_id": session_id, "state": "COMPLETED",
            "captured_frames": 3, "result": {"recognized": False, "reason": "UNKNOWN"},
        })) as proxy:
            status = self.client.get(f"/api/face/recognition-sessions/{session_id}")
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json["captured_frames"], 3)
        self.assertEqual(proxy.call_args.args, ("GET", f"/api/ai/recognition-sessions/{session_id}"))

        invalid = self.client.get("/api/face/recognition-sessions/not-a-session")
        self.assertEqual(invalid.status_code, 400)

    def test_legacy_camera_route_starts_multisnapshot_session(self):
        with patch.object(flask_app, "_request_ai1_json", return_value=(202, {
            "success": True, "session_id": "b" * 32, "state": "CAPTURING",
            "captured_frames": 0, "total_frames": 3,
        })) as proxy:
            response = self.client.post("/api/face/identify/camera", json={})
        self.assertEqual(response.status_code, 202)
        self.assertEqual(proxy.call_args.args, ("POST", "/api/ai/recognition-sessions", {}))


class HeadPoseTests(unittest.TestCase):
    def test_five_keypoint_solver_recovers_yaw_and_pitch(self):
        import cv2
        model = face_engine._POSE_MODEL_POINTS
        camera = np.asarray([[640.0, 0, 320], [0, 640.0, 240], [0, 0, 1]])
        translation = np.asarray([[0.0], [0.0], [600.0]])
        for axis_angle, expected_key in [([0, 0.35, 0], "yaw"), ([0, -0.35, 0], "yaw"),
                                         ([0.25, 0, 0], "pitch"), ([-0.25, 0, 0], "pitch")]:
            projected, _ = cv2.projectPoints(model, np.asarray(axis_angle, dtype=float),
                                             translation, camera, np.zeros((4, 1)))
            pose = face_engine.estimate_head_pose(projected.reshape(-1, 2), (480, 640, 3))
            self.assertGreater(abs(pose[expected_key]), 12.0)
            self.assertLess(abs(pose["pitch" if expected_key == "yaw" else "yaw"]), 1.0)

    def test_pose_classifier_requires_expected_direction(self):
        cases = [
            ({"yaw": 0, "pitch": 0}, "frontal"),
            ({"yaw": 20, "pitch": 0}, "left"),
            ({"yaw": -20, "pitch": 0}, "right"),
            ({"yaw": 0, "pitch": 20}, "up"),
            ({"yaw": 0, "pitch": -20}, "down"),
        ]
        for angles, expected in cases:
            with self.subTest(expected=expected):
                current = face_engine.classify_head_pose(angles["yaw"], angles["pitch"])
                self.assertEqual(current, expected)
                wrong = "down" if expected != "down" else "up"
                self.assertNotEqual(current, wrong)


if __name__ == "__main__":
    unittest.main()
