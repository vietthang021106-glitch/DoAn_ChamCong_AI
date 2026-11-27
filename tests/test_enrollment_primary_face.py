"""Regression coverage for safe primary-face tracking in guided enrollment."""

import unittest
from unittest.mock import patch

import cv2
import numpy as np

from ai1_standalone_core.ai1_adapter import (
    select_primary_face,
    validate_enrollment_frame,
    validate_enrollment_pose_frame,
)
from ai1_standalone_core.config import POSES
from ai1_standalone_core.pose_tracking import GuidedPoseTracker


def _rotation(axis, degrees):
    vector = np.zeros(3, dtype=np.float64)
    vector[axis] = np.deg2rad(degrees)
    return cv2.Rodrigues(vector)[0]


_frontal = _rotation(0, 180)
_pose_rotations = {
    "frontal": _frontal,
    "left": _frontal @ _rotation(1, -24),
    "right": _frontal @ _rotation(1, 24),
    "up": _frontal @ _rotation(0, 24),
    "down": _frontal @ _rotation(0, -24),
}


def _face(bbox, rotation=_frontal, score=0.95):
    return {
        "bbox": list(bbox), "detection_score": score,
        "keypoints": [[270, 180], [370, 180], [320, 230], [285, 290], [355, 290]],
        "head_pose": {
            "rotation_matrix": np.asarray(rotation).tolist(),
            "reprojection_error_px": 1.0, "positive_depth": True,
            "yaw": 0.0, "pitch": 180.0,
        },
    }


def _safe_multi_outcome(rotation=_frontal, *, primary_box=(200, 100, 440, 380),
                        secondary_box=(20, 20, 80, 100), embedding=None):
    primary = _face(primary_box, rotation)
    secondary = _face(secondary_box, rotation, score=0.45)
    outcome = {
        "status": "OK", "code": "OK", "face": primary,
        "faces": [secondary, primary], "face_count": 2, "total_face_count": 2,
        "selected_primary_face": primary, "primary_face_safe": True,
        "quality": {"ready": True, "sharpness": 42.0},
        "diagnostics": {"face_count": 2, "total_face_count": 2},
    }
    if embedding is not None:
        outcome["embedding"] = embedding
    return outcome


class PrimaryFaceAdapterTests(unittest.TestCase):
    def setUp(self):
        self.frame = np.full((480, 640, 3), 120, dtype=np.uint8)

    def test_single_face_is_selected_and_keeps_existing_quality_gate(self):
        primary = _face((200, 100, 440, 380))

        class Engine:
            def detect_pose_faces(self, _frame, detection_threshold):
                return [primary]

        with patch("ai1_standalone_core.ai1_adapter.production_face_engine.assess_capture_quality",
                   return_value={"ready": True, "sharpness": 40.0, "brightness": 120.0}):
            outcome = validate_enrollment_pose_frame(Engine(), self.frame, "frontal")
        self.assertEqual(outcome["status"], "OK")
        self.assertEqual(outcome["face_count"], 1)
        self.assertEqual(outcome["total_face_count"], 1)
        self.assertTrue(outcome["primary_face_safe"])
        self.assertEqual(outcome["selected_primary_face"]["bbox"], primary["bbox"])

    def test_large_near_face_and_small_rear_face_accepts_only_dominant_candidate(self):
        primary = _face((200, 80, 440, 400), score=0.91)
        rear = _face((20, 25, 100, 125), score=0.42)

        class Engine:
            def detect_pose_faces(self, _frame, detection_threshold):
                return [rear, primary]

        with patch("ai1_standalone_core.ai1_adapter.production_face_engine.assess_capture_quality",
                   return_value={"ready": True, "sharpness": 60.0, "brightness": 120.0}):
            outcome = validate_enrollment_pose_frame(Engine(), self.frame, "frontal")
        self.assertEqual(outcome["status"], "OK", outcome)
        self.assertEqual(outcome["face_count"], 2)
        self.assertEqual(outcome["total_face_count"], 2)
        self.assertGreaterEqual(outcome["primary_face_area_ratio"], 2.0)
        self.assertEqual(outcome["selected_primary_face"]["bbox"], primary["bbox"])

    def test_two_near_equal_faces_are_rejected_without_primary_selection(self):
        first = _face((100, 100, 300, 340))
        second = _face((320, 100, 520, 340))
        primary, ratio, safe, reason = select_primary_face([first, second])
        self.assertIs(primary, first)
        self.assertAlmostEqual(ratio, 1.0)
        self.assertFalse(safe)
        self.assertEqual(reason, "MULTIPLE FACES")

        class Engine:
            def detect_pose_faces(self, _frame, detection_threshold):
                return [first, second]

        outcome = validate_enrollment_pose_frame(Engine(), self.frame, "frontal")
        self.assertEqual(outcome["status"], "RETRY")
        self.assertEqual(outcome["code"], "MULTIPLE FACES")
        self.assertEqual(outcome["face_count"], 2)
        self.assertFalse(outcome["primary_face_safe"])
        self.assertIsNone(outcome.get("selected_primary_face"))

    def test_exact_two_to_one_area_ratio_is_the_acceptance_boundary(self):
        larger = _face((0, 0, 200, 200))
        smaller = _face((300, 0, 400, 200))
        primary, ratio, safe, reason = select_primary_face([smaller, larger])
        self.assertIs(primary, larger)
        self.assertEqual(ratio, 2.0)
        self.assertTrue(safe)
        self.assertEqual(reason, "OK")

    def test_dominant_face_still_fails_if_quality_gate_fails(self):
        primary = _face((200, 80, 440, 400))
        rear = _face((20, 25, 100, 125))

        class Engine:
            def detect_pose_faces(self, _frame, detection_threshold):
                return [primary, rear]

        with patch("ai1_standalone_core.ai1_adapter.production_face_engine.assess_capture_quality",
                   return_value={"ready": False, "instruction": "Ảnh quá xa."}):
            outcome = validate_enrollment_pose_frame(Engine(), self.frame, "frontal")
        self.assertEqual(outcome["status"], "RETRY")
        self.assertEqual(outcome["code"], "FACE TOO SMALL")
        self.assertTrue(outcome["primary_face_safe"], "A quality failure may keep a safely selected face for a neutral guide.")
        self.assertEqual(outcome["selected_primary_face"]["bbox"], primary["bbox"])
        self.assertEqual(outcome["face_count"], 2)

    def test_final_embedding_is_bound_to_selected_primary_bbox(self):
        vector_primary = np.eye(1, 512, 0, dtype=np.float32).reshape(-1)
        vector_rear = np.eye(1, 512, 1, dtype=np.float32).reshape(-1)
        selected = _face((200, 80, 440, 400))
        rear = _face((20, 25, 100, 125), score=0.4)

        class Engine:
            def detect_enrollment_embeddings(self, _frame):
                # Deliberately return the small face first; selection must use bbox area.
                return [{**rear, "embedding": vector_rear},
                        {**selected, "embedding": vector_primary}]

        with patch("ai1_standalone_core.ai1_adapter.production_face_engine.assess_capture_quality",
                   return_value={"ready": True, "sharpness": 55.0, "brightness": 120.0}):
            outcome = validate_enrollment_frame(
                Engine(), self.frame, "frontal", enforce_pose=False,
                selected_primary_face=selected,
            )
        self.assertEqual(outcome["status"], "OK", outcome)
        self.assertEqual(outcome["face_count"], 2)
        self.assertEqual(outcome["selected_primary_face"]["bbox"], selected["bbox"])
        np.testing.assert_allclose(outcome["embedding"], vector_primary)

    def test_final_embedding_rejects_a_new_primary_face(self):
        selected = _face((200, 80, 440, 400))
        now_larger = _face((0, 0, 500, 460))

        class Engine:
            def detect_enrollment_embeddings(self, _frame):
                return [{**now_larger, "embedding": np.eye(1, 512, 1, dtype=np.float32).reshape(-1)},
                        {**selected, "embedding": np.eye(1, 512, 0, dtype=np.float32).reshape(-1)}]

        outcome = validate_enrollment_frame(
            Engine(), self.frame, "frontal", enforce_pose=False,
            selected_primary_face=selected,
        )
        self.assertEqual(outcome["code"], "PRIMARY_FACE_CHANGED")
        self.assertFalse(outcome["primary_face_safe"])


class PrimaryFaceTrackerTests(unittest.TestCase):
    def setUp(self):
        self.frame = np.zeros((480, 640, 3), dtype=np.uint8)

    def test_safe_dominant_secondary_does_not_force_face_count_to_one(self):
        tracker = GuidedPoseTracker(stable_frames=2)
        first = tracker.observe("frontal", _safe_multi_outcome(), self.frame, 1, 1.0, now=1.0)
        second = tracker.observe("frontal", _safe_multi_outcome(), self.frame, 2, 1.2, now=1.2)
        self.assertEqual(first["status"], "STABILIZING")
        self.assertEqual(first["total_face_count"], 2)
        self.assertEqual(second["status"], "CAPTURE_READY")
        self.assertEqual(second["candidate"]["total_face_count"], 2)
        self.assertTrue(second["candidate"]["primary_face_safe"])

    def test_quality_failed_candidate_can_guide_but_does_not_lock_identity_or_progress(self):
        tracker = GuidedPoseTracker(stable_frames=2)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        face = {"bbox": [180, 80, 420, 400], "detection_score": 0.88}
        result = tracker.observe(
            "frontal",
            {"status": "RETRY", "code": "FACE TOO SMALL", "reason": "Face too small.",
             "face": face, "selected_primary_face": face, "primary_face_safe": True,
             "face_count": 1, "total_face_count": 1},
            frame, sequence=1, captured_at=1.0, now=1.0, received_at=1.0,
        )
        self.assertEqual(result["status"], "QUALITY_REJECTED")
        self.assertTrue(result["primary_face_safe"])
        self.assertEqual(result["stable_count"], 0)
        self.assertIsNone(tracker.primary_face_anchor)

    def test_same_person_can_move_during_frontal_step_before_sample_is_captured(self):
        tracker = GuidedPoseTracker(stable_frames=2)
        tracker.observe("frontal", _safe_multi_outcome(), self.frame, 1, 1.0, now=1.0)
        # Same face-sized box moved beyond the old 0.28-frame spatial gate.
        moved = _safe_multi_outcome(
            primary_box=(390, 100, 630, 380), secondary_box=(20, 20, 80, 100)
        )
        accepted = tracker.observe("frontal", moved, self.frame, 2, 1.2, now=1.2)
        self.assertEqual(accepted["status"], "CAPTURE_READY")
        self.assertEqual(accepted["total_face_count"], 2)

    def test_same_person_can_change_distance_before_frontal_sample(self):
        tracker = GuidedPoseTracker(stable_frames=2)
        tracker.observe("frontal", _safe_multi_outcome(), self.frame, 1, 1.0, now=1.0)
        larger = _safe_multi_outcome(
            primary_box=(140, 40, 500, 440), secondary_box=(20, 20, 80, 100)
        )
        accepted = tracker.observe("frontal", larger, self.frame, 2, 1.2, now=1.2)
        self.assertEqual(accepted["status"], "CAPTURE_READY")

    def test_rear_face_becoming_dominant_is_rejected_by_identity_after_frontal(self):
        tracker = GuidedPoseTracker(stable_frames=2)
        anchor = np.eye(1, 512, 0, dtype=np.float32).reshape(-1)
        intruder = np.eye(1, 512, 1, dtype=np.float32).reshape(-1)
        tracker.set_primary_identity_reference(anchor)
        replacement = _safe_multi_outcome(
            primary_box=(0, 25, 250, 400), secondary_box=(360, 100, 500, 300),
            embedding=intruder,
        )
        rejected = tracker.observe("frontal", replacement, self.frame, 1, 1.2, now=1.2)
        self.assertEqual(rejected["status"], "IDENTITY_MISMATCH")
        self.assertEqual(rejected["stable_count"], 0)

    def test_identity_anchor_rejects_person_change_even_at_same_position(self):
        tracker = GuidedPoseTracker(stable_frames=2)
        anchor = np.eye(1, 512, 0, dtype=np.float32).reshape(-1)
        intruder = np.eye(1, 512, 1, dtype=np.float32).reshape(-1)
        tracker.set_primary_identity_reference(anchor)
        outcome = _safe_multi_outcome(embedding=intruder)
        rejected = tracker.observe("frontal", outcome, self.frame, 1, 2.0, now=2.0)
        self.assertEqual(rejected["status"], "IDENTITY_MISMATCH")
        self.assertEqual(rejected["stable_count"], 0)

    def test_primary_leaving_frame_does_not_unlock_tracker_for_rear_face(self):
        tracker = GuidedPoseTracker(stable_frames=2)
        anchor = np.eye(1, 512, 0, dtype=np.float32).reshape(-1)
        replacement_embedding = np.eye(1, 512, 1, dtype=np.float32).reshape(-1)
        tracker.set_primary_identity_reference(anchor)
        replacement = {
            "status": "OK", "face_count": 1, "total_face_count": 1,
            "primary_face_safe": True,
            "face": _face((5, 20, 115, 150)), "faces": [],
            "quality": {"ready": True, "sharpness": 50.0},
            "embedding": replacement_embedding,
        }
        rejected = tracker.observe("frontal", replacement, self.frame, 2, 3.2, now=3.2)
        self.assertEqual(rejected["status"], "IDENTITY_MISMATCH")
        self.assertEqual(rejected["stable_count"], 0)

    def test_temporary_face_loss_keeps_captured_pose_and_identity_reference(self):
        tracker = GuidedPoseTracker(stable_frames=2)
        identity = np.eye(1, 512, 0, dtype=np.float32).reshape(-1)
        outcome = _safe_multi_outcome(embedding=identity)
        tracker.observe("frontal", outcome, self.frame, 1, 4.0, now=4.0)
        ready = tracker.observe("frontal", outcome, self.frame, 2, 4.25, now=4.25)
        self.assertEqual(ready["status"], "CAPTURE_READY")
        tracker.capture_result(True, "left", now=4.3, embedding=identity)

        lost = tracker.observe(
            "left", {"status": "RETRY", "code": "NO FACE", "reason": "No face."},
            self.frame, 3, 4.5, now=4.5,
        )
        self.assertEqual(lost["status"], "QUALITY_REJECTED")
        self.assertEqual(tracker.expected_pose, "left")
        np.testing.assert_allclose(tracker.identity_reference, identity)

    def test_one_safe_person_can_complete_exactly_five_pose_samples(self):
        tracker = GuidedPoseTracker(stable_frames=2)
        vector = np.eye(1, 512, 0, dtype=np.float32).reshape(-1)
        sequence = 0
        timestamp = 10.0
        saved = []
        for index, pose in enumerate(POSES):
            observed = None
            for _ in range(2):
                sequence += 1
                timestamp += 0.25
                observed = tracker.observe(
                    pose, _safe_multi_outcome(_pose_rotations[pose]), self.frame,
                    sequence, timestamp, now=timestamp,
                )
            self.assertEqual(observed["status"], "CAPTURE_READY", (pose, observed))
            selected = _safe_multi_outcome(_pose_rotations[pose], embedding=vector)
            checked = tracker.validate_selected_candidate(observed["candidate"], selected, pose)
            self.assertEqual(checked["status"], "OK", (pose, checked))
            saved.append(checked["embedding"])
            next_pose = POSES[index + 1] if index + 1 < len(POSES) else None
            tracker.capture_result(True, next_pose, now=timestamp, embedding=checked["embedding"])
        self.assertEqual(len(saved), 5)
        self.assertTrue(all(value.shape == (512,) for value in saved))
        self.assertEqual(tracker.expected_pose, None)


if __name__ == "__main__":
    unittest.main()
