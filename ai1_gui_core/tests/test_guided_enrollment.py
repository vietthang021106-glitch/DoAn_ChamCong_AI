"""Synthetic geometry and state tests for Smart Enrollment v2 pose guidance."""

import queue
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import cv2
import numpy as np
from unittest.mock import patch

import face_engine
from ai1_gui_core.enrollment_state import EnrollmentCaptureState
from ai1_gui_core.gui import AI1Gui, _draw_unicode_runs
from ai1_standalone_core.config import POSES
from ai1_standalone_core.pose_tracking import (
    GuidedPoseTracker,
    angular_delta_degrees,
    average_rotation_matrices,
    classify_relative_pose,
    relative_pose_angles,
    rotation_distance_degrees,
    wrap_degrees,
)


def axis_rotation(axis, radians):
    vector = np.zeros(3, dtype=np.float64)
    vector[axis] = radians
    return cv2.Rodrigues(vector)[0]


FRONTAL_ROTATION = axis_rotation(0, np.pi)
POSE_ROTATIONS = {
    "frontal": FRONTAL_ROTATION,
    "left": FRONTAL_ROTATION @ axis_rotation(1, np.deg2rad(24.0)),
    "right": FRONTAL_ROTATION @ axis_rotation(1, np.deg2rad(-24.0)),
    "up": FRONTAL_ROTATION @ axis_rotation(0, np.deg2rad(-24.0)),
    "down": FRONTAL_ROTATION @ axis_rotation(0, np.deg2rad(24.0)),
}


def projected_head_pose(rotation):
    camera = np.asarray([[640.0, 0.0, 320.0], [0.0, 640.0, 240.0],
                         [0.0, 0.0, 1.0]], dtype=np.float64)
    translation = np.asarray([[0.0], [0.0], [600.0]], dtype=np.float64)
    rotation_vector, _ = cv2.Rodrigues(rotation)
    points, _ = cv2.projectPoints(
        face_engine._POSE_MODEL_POINTS, rotation_vector, translation,
        camera, np.zeros((4, 1), dtype=np.float64),
    )
    return face_engine.estimate_head_pose(points.reshape(-1, 2), (480, 640, 3))


def valid_outcome(rotation, sharpness=10.0, embedding=None):
    vector = np.zeros(512, dtype=np.float32)
    vector[0] = 1.0
    return {
        "status": "OK",
        "embedding": vector if embedding is None else embedding,
        "quality": {"ready": True, "sharpness": float(sharpness)},
        "face": {
            "bbox": [200.0, 100.0, 440.0, 380.0],
            "detection_score": 0.99,
            "head_pose": {
                "rotation_matrix": np.asarray(rotation).tolist(),
                "reprojection_error_px": 1.0,
                "positive_depth": True,
                "yaw": 0.0, "pitch": 180.0,
            },
        },
        "faces": [],
        "face_count": 1,
        "diagnostics": {
            "quality_result": "PASS", "quality_code": "PASS", "face_count": 1,
            "detection_score": 0.99, "bbox": [200.0, 100.0, 440.0, 380.0],
            "brightness": 120.0, "sharpness": float(sharpness),
            "raw_yaw": 0.0, "raw_pitch": 180.0,
        },
    }


class _Var:
    def __init__(self):
        self.value = None

    def set(self, _value):
        self.value = _value

    def get(self):
        return self.value


class GuidedEnrollmentTests(unittest.TestCase):
    def test_raw_frontal_pitch_branch_is_near_180_but_relative_front_is_zero(self):
        raw = projected_head_pose(FRONTAL_ROTATION)
        self.assertGreater(abs(raw["pitch"]), 150.0)
        self.assertLess(raw["reprojection_error_px"], 1e-5)
        calibrated = relative_pose_angles(raw["rotation_matrix"], raw["rotation_matrix"])
        self.assertAlmostEqual(calibrated["yaw"], 0.0, places=6)
        self.assertAlmostEqual(calibrated["pitch"], 0.0, places=6)

    def test_synthetic_relative_rotations_classify_all_five_pose_directions(self):
        reference = POSE_ROTATIONS["frontal"]
        for target in POSES:
            angles = relative_pose_angles(reference, POSE_ROTATIONS[target])
            with self.subTest(target=target, angles=angles):
                self.assertEqual(
                    classify_relative_pose(angles["yaw"], angles["pitch"], angles["roll"]),
                    target,
                )

    def test_solvepnp_projected_landmarks_recover_all_relative_pose_directions(self):
        estimates = {pose: projected_head_pose(POSE_ROTATIONS[pose]) for pose in POSES}
        reference = estimates["frontal"]["rotation_matrix"]
        for pose in POSES:
            estimated = estimates[pose]
            angles = relative_pose_angles(reference, estimated["rotation_matrix"])
            with self.subTest(pose=pose, angles=angles):
                self.assertLess(estimated["reprojection_error_px"], 1e-5)
                self.assertEqual(
                    classify_relative_pose(angles["yaw"], angles["pitch"], angles["roll"]),
                    pose,
                )

    def test_relative_yaw_pitch_are_euler_decomposition_not_rodrigues_components(self):
        yaw, pitch, roll = np.deg2rad([27.0, 18.0, -9.0])
        relative = (axis_rotation(1, yaw) @ axis_rotation(0, -pitch)
                    @ axis_rotation(2, roll))
        angles = relative_pose_angles(np.eye(3), relative)
        self.assertAlmostEqual(angles["yaw"], 27.0, places=5)
        self.assertAlmostEqual(angles["pitch"], 18.0, places=5)
        self.assertAlmostEqual(angles["roll"], -9.0, places=5)
        with self.assertRaisesRegex(ValueError, "gimbal lock"):
            relative_pose_angles(np.eye(3), axis_rotation(0, -np.pi / 2))

    def test_frontal_calibration_ignores_raw_180_pitch_and_displays_no_fake_angles(self):
        tracker = GuidedPoseTracker(stable_frames=3)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        outputs = []
        for sequence in range(1, 4):
            outcome = valid_outcome(FRONTAL_ROTATION)
            outcome["face"]["head_pose"].update(yaw=16.22, pitch=171.42)
            outputs.append(tracker.observe(
                "frontal", outcome, frame, sequence, 50.0, now=50.0
            ))
        self.assertEqual(outputs[0]["status"], "STABILIZING")
        self.assertIsNone(outputs[0]["yaw"])
        self.assertIsNone(outputs[0]["pitch"])
        self.assertEqual(outputs[-1]["status"], "CAPTURE_READY")
        self.assertAlmostEqual(outputs[-1]["yaw"], 0.0, places=4)
        self.assertAlmostEqual(outputs[-1]["pitch"], 0.0, places=4)

    def test_frontal_calibration_rejects_large_raw_yaw_but_never_gates_on_raw_pitch(self):
        tracker = GuidedPoseTracker(stable_frames=2)
        outcome = valid_outcome(FRONTAL_ROTATION)
        outcome["face"]["head_pose"].update(yaw=23.0, pitch=179.0)
        result = tracker.observe("frontal", outcome, np.zeros((480, 640, 3), dtype=np.uint8),
                                 1, 10.0, now=10.0)
        self.assertEqual(result["status"], "POSE_NOT_READY")
        self.assertEqual(result["stable_count"], 0)
        self.assertIn("Raw pitch chỉ là thông tin debug", result["reason"])

    def test_timeout_falls_back_with_reason_and_reset_restarts_tracker(self):
        tracker = GuidedPoseTracker(stable_frames=2, pose_timeout_seconds=2.0)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        first = tracker.observe("frontal", valid_outcome(FRONTAL_ROTATION),
                                frame, 1, 10.0, now=10.0)
        self.assertEqual(first["status"], "STABILIZING")
        timed_out = tracker.observe("frontal", valid_outcome(FRONTAL_ROTATION),
                                    frame, 2, 12.1, now=12.1)
        self.assertEqual(timed_out["status"], "FALLBACK_MANUAL")
        self.assertIn("did not stabilize", timed_out["reason"])
        tracker.reset()
        restarted = tracker.observe("frontal", valid_outcome(FRONTAL_ROTATION),
                                    frame, 3, 13.0, now=13.0)
        self.assertEqual(restarted["status"], "STABILIZING")
        self.assertEqual(restarted["stable_count"], 1)

    def test_angle_wrap_and_rotation_geodesic_are_continuous_at_boundary(self):
        self.assertEqual(wrap_degrees(181.0), -179.0)
        self.assertAlmostEqual(angular_delta_degrees(179.0, -179.0), 2.0)
        first = axis_rotation(1, np.deg2rad(179.0))
        second = axis_rotation(1, np.deg2rad(-179.0))
        self.assertAlmostEqual(rotation_distance_degrees(first, second), 2.0, places=4)

    def test_rotation_average_returns_a_valid_rotation(self):
        average = average_rotation_matrices([
            axis_rotation(1, np.deg2rad(2.0)),
            axis_rotation(1, np.deg2rad(3.0)),
            axis_rotation(1, np.deg2rad(4.0)),
        ])
        self.assertAlmostEqual(np.linalg.det(average), 1.0, places=6)
        self.assertLess(np.linalg.norm(average.T @ average - np.eye(3)), 1e-6)

    def test_tracker_uses_eight_fresh_stable_frames_and_selects_sharpest(self):
        tracker = GuidedPoseTracker(stable_frames=8)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        now = 100.0
        results = []
        for sequence in range(1, 9):
            results.append(tracker.observe(
                "frontal", valid_outcome(FRONTAL_ROTATION, sharpness=sequence),
                frame, sequence, now, now=now,
            ))
        self.assertEqual([item["status"] for item in results[:-1]], ["STABILIZING"] * 7)
        self.assertEqual(results[-1]["status"], "CAPTURE_READY")
        self.assertEqual(results[-1]["candidate"]["sequence"], 8)
        duplicate = tracker.observe(
            "frontal", valid_outcome(FRONTAL_ROTATION, sharpness=20),
            frame, 9, now, now=now,
        )
        self.assertEqual(duplicate["status"], "CAPTURE_PENDING")
        tracker.capture_result(True, "left")
        self.assertEqual(tracker.stable_count, 0)
        self.assertEqual(tracker.expected_pose, "left")

    def test_bad_quality_stale_and_unreliable_pose_do_not_auto_capture(self):
        tracker = GuidedPoseTracker(stable_frames=2, unreliable_frame_limit=3)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        now = 100.0
        bad_quality = tracker.observe(
            "frontal", {"status": "RETRY", "reason": "TOO BLURRY"},
            frame, 1, now, now=now,
        )
        self.assertEqual(bad_quality["status"], "QUALITY_REJECTED")
        stale = tracker.observe(
            "frontal", valid_outcome(FRONTAL_ROTATION), frame, 2,
            now - 2.0, now=now,
        )
        self.assertEqual(stale["status"], "STALE_FRAME")
        missing_pose = {"status": "OK", "face": {"head_pose": None},
                        "quality": {"sharpness": 40.0}}
        self.assertEqual(tracker.observe("frontal", missing_pose, frame, 3, now,
                                         now=now)["status"], "POSE_UNRELIABLE")
        self.assertEqual(tracker.observe("frontal", missing_pose, frame, 4, now,
                                         now=now)["status"], "POSE_UNRELIABLE")
        fallback = tracker.observe("frontal", missing_pose, frame, 5, now, now=now)
        self.assertEqual(fallback["status"], "FALLBACK_MANUAL")

    def test_complete_auto_sequence_captures_exactly_five_compatible_samples(self):
        tracker = GuidedPoseTracker(stable_frames=3)
        enrollment = EnrollmentCaptureState(same_person_threshold=0.45)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        sequence = 0
        now = 200.0
        for expected in POSES:
            rotation = POSE_ROTATIONS[expected]
            for index in range(3):
                sequence += 1
                result = tracker.observe(
                    expected, valid_outcome(rotation, sharpness=10 + index),
                    frame, sequence, now, now=now,
                )
            self.assertEqual(result["status"], "CAPTURE_READY", (expected, result))
            capture = enrollment.capture(result["candidate"]["outcome"])
            tracker.capture_result(True, enrollment.current_pose)
            self.assertEqual(capture["pose"], expected)
        self.assertTrue(enrollment.complete)
        self.assertTrue(enrollment.validate_complete()["valid"])
        self.assertEqual(set(enrollment.embeddings), set(POSES))

    def test_space_is_ignored_in_auto_and_queues_one_manual_capture_after_fallback(self):
        gui = AI1Gui.__new__(AI1Gui)
        gui.active_operation = "enrollment"
        gui.enrollment = {"mode": "AUTO", "ready_to_save": False,
                          "requests": queue.Queue()}
        gui.space_is_down = False
        gui.space_capture_pending = False
        gui.capture_feedback = None
        gui.state_var = _Var()

        self.assertEqual(gui._on_space_press(), "break")
        self.assertTrue(gui.space_is_down)
        self.assertTrue(gui.enrollment["requests"].empty())
        gui._on_space_release()
        gui.enrollment["mode"] = "MANUAL"
        self.assertEqual(gui._on_space_press(), "break")
        self.assertEqual(gui.enrollment["requests"].get_nowait(), {"action": "capture"})
        self.assertEqual(gui._on_space_press(), "break")
        self.assertTrue(gui.enrollment["requests"].empty())

    def test_manual_fallback_reason_stays_visible_on_later_manual_progress(self):
        gui = AI1Gui.__new__(AI1Gui)
        gui.enrollment = {
            "mode": "MANUAL", "fallback_reason": "reprojection=24.2px, positive_depth=True",
            "state": EnrollmentCaptureState(),
        }
        gui.pose_var = _Var()
        gui.detected_pose_var = _Var()
        gui.enrollment_mode_var = _Var()
        gui.quality_var = _Var()
        gui.auto_status_var = _Var()
        gui.capture_hint_var = _Var()
        gui.capture_feedback = None
        gui.state_var = _Var()
        gui.preview_hint = _Var()
        gui.sharpness_var = _Var()
        gui.progress_var = _Var()
        gui.enrollment_progress_var = _Var()
        gui.latest_analysis = {}
        gui._update_pose_ring = lambda *_args: None
        gui._show_enrollment_progress({
            "mode": "MANUAL", "current_pose": "frontal", "captured": 0,
            "detected_pose": "between", "expected_pose": "frontal",
            "code": "OK", "reason": "Quality checks passed.",
            "quality_status": "PASS", "diagnostics": {"quality_result": "PASS"},
        })
        self.assertIn("reprojection=24.2px", gui.auto_status_var.get())

    def test_camera_preview_unicode_overlay_renders_vietnamese_with_true_type_font(self):
        frame = np.zeros((80, 320, 3), dtype=np.uint8)
        rendered = _draw_unicode_runs(
            frame, [("Nhìn thẳng · xoay trái · ngẩng lên", 8, 8, (245, 245, 245), 15)]
        )
        self.assertEqual(rendered.shape, frame.shape)
        self.assertTrue(np.any(rendered != frame))

    def test_auto_preview_scan_ring_tracks_live_face_bbox(self):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        gui = AI1Gui.__new__(AI1Gui)
        gui.latest_analysis = {
            "bbox": [100.0, 100.0, 300.0, 400.0],
            "bboxes": [[100.0, 100.0, 300.0, 400.0]],
            "frame_shape": [480, 640], "observed_at": time.monotonic(),
            "detection_scores": [0.98], "detection_score": 0.98,
            "quality_status": "PASS", "code": "OK", "expected_pose": "left",
            "detected_pose": "left", "auto_status": "STABILIZING",
            "stable_count": 4, "mode": "AUTO", "captured": 1,
            "diagnostics": {"face_count": 1, "bbox": [100, 100, 300, 400],
                            "quality_result": "PASS", "quality_code": "PASS"},
        }
        gui.active_operation = "enrollment"
        gui.enrollment = {"mode": "AUTO"}
        gui.progress_var = _Var()
        gui.progress_var.value = "Tiến độ: 1/5"
        gui.captured_pose_order = ["frontal"]
        original_ellipse = cv2.ellipse
        with patch("ai1_gui_core.gui.cv2.ellipse", wraps=original_ellipse) as ellipse:
            rendered = gui._draw_preview(frame, packet=None)
        centers = [call.args[1] for call in ellipse.call_args_list]
        self.assertIn((200, 250), centers)
        self.assertEqual(rendered.shape, frame.shape)
        self.assertTrue(np.any(rendered != frame))

    def test_auto_gui_worker_captures_five_poses_without_space_requests(self):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        class FakeController:
            engine = object()

            def __init__(self):
                self.sequence = 0

            def get_packet(self):
                self.sequence += 1
                return SimpleNamespace(sequence=self.sequence,
                                       captured_at=time.monotonic(), frame=frame)

            @staticmethod
            def find_duplicate_employee(*_args, **_kwargs):
                return None

        gui = AI1Gui.__new__(AI1Gui)
        gui.events = queue.Queue()
        gui.controller = FakeController()
        gui.enrollment = None
        vector = np.zeros(512, dtype=np.float32)
        vector[0] = 1.0
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]) as temp:
            stage = Path(temp) / "stage"
            stage.mkdir()
            state = EnrollmentCaptureState(same_person_threshold=0.45)
            session = {
                "identity": "TEST_1", "name": "Test", "overwrite": False,
                "stage": stage, "frames": {}, "state": state,
                "requests": queue.Queue(), "ready_to_save": False, "saved": False,
                "session_id": "test", "captured_order_ui": [], "mode": "AUTO",
                "capture_pending": False,
            }
            session["requests"].put({"action": "reset_all", "mode": "AUTO"})
            gui.enrollment = session

            def fake_validate(_engine, _frame, pose, **_kwargs):
                return valid_outcome(POSE_ROTATIONS[pose], sharpness=20 + POSES.index(pose),
                                     embedding=vector)

            with patch("ai1_gui_core.gui.validate_enrollment_frame", side_effect=fake_validate), \
                    patch("ai1_gui_core.gui._atomic_write_jpeg"):
                result = gui._enrollment_worker("test", __import__("threading").Event())

        self.assertEqual(result["status"], "READY_TO_SAVE")
        self.assertTrue(result["state"].complete)
        self.assertEqual(set(result["state"].embeddings), set(POSES))
        self.assertEqual(gui.controller.sequence, len(POSES) * 8)
        captured_events = []
        reset_events = 0
        progress_counts = []
        captured_so_far = 0
        while not gui.events.empty():
            item = gui.events.get_nowait()
            if item[0] == "enrollment_captured":
                captured_events.append(item[2]["pose"])
                captured_so_far += 1
            elif item[0] == "enrollment_reset":
                reset_events += 1
            elif item[0] == "enrollment_progress":
                count = item[2]["captured"]
                progress_counts.append(count)
                self.assertEqual(count, captured_so_far)
        self.assertEqual(captured_events, list(POSES))
        self.assertEqual(reset_events, 1)
        self.assertEqual(progress_counts[-1], 4)


if __name__ == "__main__":
    unittest.main()
