import unittest
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ai_service


class _Future:
    def done(self):
        return False


class _Pool:
    def __init__(self):
        self.submissions = []

    def submit(self, callback, *args):
        self.submissions.append((callback, args))
        return _Future()


class _Engine:
    _initialized = True


class SmartEnrollmentSessionTests(unittest.TestCase):
    def test_enrollment_status_exposes_real_ui_progress_without_sample_payloads(self):
        summary = ai_service.AIRuntime._enrollment_session_summary({
            "session_id": "a" * 32,
            "state": "ENROLLING",
            "captured": 2,
            "total": 5,
            "expected_pose": "right",
            "detected_pose": "right",
            "stable_count": 3,
            "stable_frames_required": 5,
            "observation_status": "STABILIZING",
            "feedback_code": "STABILIZING",
            "quality_code": "PASS",
            "face_bbox": [100.0, 80.0, 220.0, 240.0],
            "frame_width": 640,
            "frame_height": 480,
            "face_count": 1,
            "detection_score": 0.91,
            "frame_sequence": 42,
            "frame_timestamp": 123.5,
            "frame_age_ms": 22.0,
            "samples": [{"vector": "private-vector", "image_jpeg": "private-image"}],
        })

        self.assertEqual(summary["stable_count"], 3)
        self.assertEqual(summary["stable_frames_required"], 5)
        self.assertEqual(summary["face_bbox"], [100.0, 80.0, 220.0, 240.0])
        self.assertEqual(summary["face_count"], 1)
        self.assertEqual(summary["detection_score"], 0.91)
        self.assertEqual(summary["frame_sequence"], 42)
        self.assertEqual(summary["frame_timestamp"], 123.5)
        self.assertEqual(summary["frame_age_ms"], 22.0)
        self.assertEqual(summary["observation_status"], "STABILIZING")
        self.assertNotIn("samples", summary)
        self.assertNotIn("private-vector", str(summary))

    def test_enrollment_geometry_tracks_single_face_and_hides_stale_boxes(self):
        frame = ai_service.np.zeros((480, 640, 3), dtype=ai_service.np.uint8)
        outcome = {
            "face_count": 1, "total_face_count": 1,
            "primary_face_safe": True,
            "face": {"bbox": [100, 80, 220, 240], "detection_score": 0.91},
            "faces": [{"bbox": [100, 80, 220, 240], "detection_score": 0.91}],
            "selected_primary_face": {"bbox": [100, 80, 220, 240], "detection_score": 0.91},
        }
        geometry = ai_service._enrollment_face_geometry(
            frame, outcome, "STABILIZING", frame_sequence=12,
            frame_timestamp=20.25, frame_age_ms=18.0,
        )
        self.assertEqual(geometry["face_bbox"], [100.0, 80.0, 220.0, 240.0])
        self.assertEqual(geometry["frame_width"], 640)
        self.assertEqual(geometry["frame_height"], 480)
        self.assertEqual(geometry["face_count"], 1)
        self.assertEqual(geometry["detection_score"], 0.91)
        self.assertEqual(geometry["frame_sequence"], 12)
        self.assertEqual(geometry["frame_timestamp"], 20.25)
        self.assertEqual(geometry["frame_age_ms"], 18.0)
        stale = ai_service._enrollment_face_geometry(frame, outcome, "STALE_FRAME")
        self.assertIsNone(stale["face_bbox"])

    def test_multiple_faces_only_draw_backend_selected_safe_primary(self):
        frame = ai_service.np.zeros((480, 640, 3), dtype=ai_service.np.uint8)
        smaller = {"bbox": [20, 30, 100, 130], "detection_score": 0.99}
        largest = {"bbox": [180, 80, 420, 400], "detection_score": 0.78}
        outcome = {
            "face_count": 2, "total_face_count": 2,
            "face": largest, "selected_primary_face": largest,
            "primary_face_safe": True,
            "faces": [smaller, largest],
        }
        geometry = ai_service._enrollment_face_geometry(frame, outcome, "STABILIZING")
        self.assertEqual(geometry["face_bbox"], [180.0, 80.0, 420.0, 400.0])
        self.assertEqual(geometry["face_count"], 2)
        self.assertEqual(geometry["detection_score"], 0.78)
        self.assertTrue(geometry["primary_face_safe"])

    def test_ambiguous_or_tracker_rejected_face_never_draws_confirmation_ring(self):
        frame = ai_service.np.zeros((480, 640, 3), dtype=ai_service.np.uint8)
        left = {"bbox": [30, 100, 150, 260], "detection_score": 0.95}
        center = {"bbox": [260, 100, 380, 260], "detection_score": 0.80}
        outcome = {"face_count": 2, "total_face_count": 2,
                   "face": center, "faces": [left, center], "primary_face_safe": False,
                   "primary_face_area_ratio": 1.4,
                   "primary_face_area_ratio_required": 2.0}
        ambiguous = ai_service._enrollment_face_geometry(frame, outcome, "QUALITY_REJECTED")
        self.assertIsNone(ambiguous["face_bbox"])
        self.assertFalse(ambiguous["primary_face_safe"])
        self.assertEqual(ambiguous["primary_face_area_ratio"], 1.4)
        self.assertEqual(ambiguous["primary_face_area_ratio_required"], 2.0)
        self.assertEqual(ambiguous["detection_score"], 0.80)
        safe_outcome = {**outcome, "face": left, "selected_primary_face": left,
                        "primary_face_safe": True}
        changed = ai_service._enrollment_face_geometry(frame, safe_outcome, "QUALITY_REJECTED")
        self.assertEqual(changed["face_bbox"], [30.0, 100.0, 150.0, 260.0])
        self.assertTrue(changed["primary_face_safe"])

    def test_quality_rejected_but_safely_selected_face_can_show_neutral_bbox(self):
        frame = ai_service.np.zeros((480, 640, 3), dtype=ai_service.np.uint8)
        face = {"bbox": [180, 80, 420, 400], "detection_score": 0.88}
        geometry = ai_service._enrollment_face_geometry(
            frame,
            {"face_count": 2, "total_face_count": 2, "primary_face_safe": True,
             "selected_primary_face": face, "face": face},
            "QUALITY_REJECTED",
        )
        self.assertEqual(geometry["face_bbox"], [180.0, 80.0, 420.0, 400.0])
        self.assertTrue(geometry["primary_face_safe"])

    def test_invalid_frame_clears_primary_selection_status(self):
        geometry = ai_service._enrollment_face_geometry(
            None, {"face_count": 2, "primary_face_safe": True}, "STABILIZING"
        )
        self.assertEqual(geometry["total_face_count"], 0)
        self.assertFalse(geometry["primary_face_safe"])
        self.assertIsNone(geometry["face_bbox"])

    def test_ambiguous_multiple_face_frame_is_rejected_by_pose_tracker(self):
        tracker = ai_service.GuidedPoseTracker(stable_frames=3)
        frame = ai_service.np.zeros((480, 640, 3), dtype=ai_service.np.uint8)
        outcome = {
            "status": "RETRY",
            "code": "MULTIPLE FACES",
            "face_count": 2,
            "face": {"bbox": [100, 80, 220, 240]},
            "faces": [
                {"bbox": [100, 80, 220, 240]},
                {"bbox": [350, 80, 470, 240]},
            ],
        }
        result = tracker.observe(
            "frontal", outcome, frame, sequence=1, captured_at=1.0,
            now=1.0, received_at=1.0,
        )
        self.assertEqual(result["status"], "QUALITY_REJECTED")
        self.assertEqual(result["rejected_code"], "MULTIPLE FACES")
        self.assertEqual(result["stable_count"], 0)
        self.assertEqual(result["face_count"], 2)
        self.assertEqual(result["total_face_count"], 2)
        self.assertFalse(result["primary_face_safe"])
        self.assertNotEqual(result["status"], "CAPTURE_READY")

    def test_multiple_face_rejection_without_count_reports_truthful_lower_bound(self):
        tracker = ai_service.GuidedPoseTracker(stable_frames=3)
        frame = ai_service.np.zeros((480, 640, 3), dtype=ai_service.np.uint8)
        outcome = {
            "status": "RETRY", "code": "MULTIPLE FACES",
            "reason": "Không xác định được mặt chính.",
        }
        result = tracker.observe(
            "frontal", outcome, frame, sequence=1, captured_at=1.0,
            now=1.0, received_at=1.0,
        )
        self.assertEqual(result["face_count"], 2)
        self.assertEqual(result["total_face_count"], 2)
        self.assertTrue(result["face_count_lower_bound"])
        self.assertFalse(result["primary_face_safe"])

    def test_auto_session_is_unique_and_blocks_recognition_until_released(self):
        runtime = ai_service.AIRuntime()
        runtime._recognition_pool.shutdown(wait=False)
        runtime._enrollment_pool.shutdown(wait=False)
        runtime._recognition_pool = _Pool()
        runtime._enrollment_pool = _Pool()
        runtime.engine = _Engine()

        started = runtime.start_enrollment_session()
        self.assertIsNotNone(started)
        self.assertEqual(started["state"], "ENROLLING")
        self.assertEqual(started["captured"], 0)
        self.assertIsNone(runtime.start_enrollment_session())
        self.assertIsNone(runtime.start_recognition_session())
        self.assertIsNone(runtime.get_enrollment_samples(started["session_id"]))
        cancelled = runtime.close_enrollment_session(started["session_id"], cancelled=True)
        self.assertEqual(cancelled["state"], "CANCELLED")

    def test_recognition_fails_closed_when_authoritative_gallery_refresh_fails(self):
        runtime = ai_service.AIRuntime()
        runtime._recognition_pool.shutdown(wait=False)
        runtime._enrollment_pool.shutdown(wait=False)
        pool = _Pool()
        runtime._recognition_pool = pool
        runtime.engine = _Engine()
        runtime._gallery_loaded = True
        runtime._gallery = {1: {"embeddings": []}}
        runtime._gallery_error = "previous refresh failed"

        with patch.object(runtime, "refresh_gallery", side_effect=RuntimeError("PHP unavailable")):
            with self.assertRaises(ai_service.GalleryUnavailableError):
                runtime.start_recognition_session()

        self.assertEqual(pool.submissions, [])
        self.assertIsNone(runtime._active_recognition_session)
        self.assertTrue(runtime._gallery_error)
        self.assertFalse(runtime.health()["gallery_ready"])

    def test_recognition_start_api_reports_gallery_unavailable_without_session(self):
        class RuntimeStub:
            def start_recognition_session(self):
                raise ai_service.GalleryUnavailableError("stale gallery")

        original = ai_service.runtime
        try:
            ai_service.runtime = RuntimeStub()
            response = ai_service.app.test_client().post("/api/ai/recognition-sessions")
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.get_json()["code"], "GALLERY_UNAVAILABLE")
            self.assertFalse(response.get_json()["success"])
        finally:
            ai_service.runtime = original

    def test_loopback_session_api_contract(self):
        class RuntimeStub:
            def start_enrollment_session(self):
                return {"session_id": "a" * 32, "state": "ENROLLING", "captured": 0, "total": 5}

            def get_enrollment_session(self, session_id):
                if session_id != "a" * 32:
                    return None
                return {"session_id": session_id, "state": "AWAITING_CONFIRMATION", "captured": 5, "total": 5}

            def get_enrollment_samples(self, session_id):
                return [{"pose": pose} for pose in ai_service.GUIDED_POSES] if session_id == "a" * 32 else None

            def close_enrollment_session(self, session_id, cancelled=False):
                if session_id != "a" * 32:
                    return None
                return {"session_id": session_id, "state": "CANCELLED" if cancelled else "COMPLETED"}

        original = ai_service.runtime
        try:
            ai_service.runtime = RuntimeStub()
            client = ai_service.app.test_client()
            started = client.post("/api/ai/enrollment-sessions")
            self.assertEqual(started.status_code, 202)
            self.assertEqual(started.get_json()["state"], "ENROLLING")
            status = client.get("/api/ai/enrollment-sessions/" + "a" * 32)
            self.assertEqual(status.status_code, 200)
            self.assertEqual(status.get_json()["captured"], 5)
            samples = client.get("/api/ai/enrollment-sessions/" + "a" * 32 + "/samples")
            self.assertEqual([item["pose"] for item in samples.get_json()["samples"]], list(ai_service.GUIDED_POSES))
            cancelled = client.post("/api/ai/enrollment-sessions/" + "a" * 32 + "/cancel")
            self.assertEqual(cancelled.get_json()["state"], "CANCELLED")
            invalid = client.get("/api/ai/enrollment-sessions/not-a-session")
            self.assertEqual(invalid.status_code, 404)
        finally:
            ai_service.runtime = original


if __name__ == "__main__":
    unittest.main()
