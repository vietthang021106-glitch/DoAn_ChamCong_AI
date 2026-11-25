"""Unit tests for landmark pose classification and eight-frame capture state."""

import unittest

import numpy as np

import face_engine
from enrollment_capture_state import (
    ENROLLMENT_POSES,
    STABLE_FRAMES_REQUIRED,
    current_pose_index,
    new_capture_state,
    observe_frame,
    record_sample,
)


class PoseEvaluatorTests(unittest.TestCase):
    def test_yaw_pitch_classify_the_five_requested_poses(self):
        self.assertEqual(face_engine.classify_head_pose(0, 0), "frontal")
        self.assertEqual(face_engine.classify_head_pose(22, 0), "left")
        self.assertEqual(face_engine.classify_head_pose(-22, 0), "right")
        self.assertEqual(face_engine.classify_head_pose(0, 20), "up")
        self.assertEqual(face_engine.classify_head_pose(0, -20), "down")
        self.assertEqual(face_engine.classify_head_pose(70, 0), "between")

    def test_pose_is_estimated_from_landmarks(self):
        keypoints = np.asarray([
            [270.0, 190.0], [370.0, 190.0], [320.0, 250.0],
            [285.0, 320.0], [355.0, 320.0],
        ])
        pose = face_engine.estimate_head_pose(keypoints, (480, 640, 3))
        self.assertTrue(np.isfinite(pose["yaw"]))
        self.assertTrue(np.isfinite(pose["pitch"]))

    def test_capture_quality_accepts_clear_centered_face_and_rejects_bad_gates(self):
        rng = np.random.default_rng(11)
        frame = rng.integers(55, 190, size=(480, 640, 3), dtype=np.uint8)
        face = {"bbox": [230, 135, 410, 355], "detection_score": 0.9}
        self.assertTrue(face_engine.assess_capture_quality(frame, face)["ready"])
        self.assertFalse(face_engine.assess_capture_quality(
            frame, {**face, "detection_score": 0.4}
        )["ready"])
        self.assertFalse(face_engine.assess_capture_quality(
            frame, {**face, "bbox": [310, 230, 330, 250]}
        )["ready"])
        self.assertFalse(face_engine.assess_capture_quality(
            frame, {**face, "bbox": [20, 20, 200, 240]}
        )["ready"])
        self.assertFalse(face_engine.assess_capture_quality(
            np.zeros_like(frame), face
        )["ready"])


class CaptureStateTests(unittest.TestCase):
    def test_capture_only_after_eight_consecutive_ready_frames(self):
        state = new_capture_state(7, created=1.0)
        for count in range(1, STABLE_FRAMES_REQUIRED):
            result = observe_frame(state, True)
            self.assertFalse(result["capture_due"])
            self.assertEqual(result["stable_frame_count"], count)

        result = observe_frame(state, True)
        self.assertTrue(result["capture_due"])
        self.assertEqual(result["stable_frame_count"], 8)

    def test_any_rejected_frame_resets_count_and_sample_advances_pose(self):
        state = new_capture_state(7, created=1.0)
        for _ in range(6):
            observe_frame(state, True)
        result = observe_frame(state, False)
        self.assertEqual(result["stable_frame_count"], 0)
        self.assertFalse(result["capture_due"])

        for _ in range(STABLE_FRAMES_REQUIRED):
            observe_frame(state, True)
        progress = record_sample(state, "frontal", b"vector", b"jpeg")
        self.assertEqual(progress["captured"], 1)
        self.assertEqual(progress["next_pose"], ENROLLMENT_POSES[1])
        self.assertEqual(current_pose_index(state), 1)
        self.assertEqual(state["sample_images"], [b"jpeg"])
        self.assertEqual(state["stable_frame_count"], 0)

    def test_full_five_pose_state_machine_stages_pairs_before_completion(self):
        state = new_capture_state(7, created=1.0)
        for index, pose in enumerate(ENROLLMENT_POSES):
            for _ in range(STABLE_FRAMES_REQUIRED - 1):
                self.assertFalse(observe_frame(state, True)["capture_due"])
            self.assertTrue(observe_frame(state, True)["capture_due"])
            progress = record_sample(state, pose, f"vector-{pose}".encode(), f"jpeg-{pose}".encode())
            self.assertEqual(progress["captured"], index + 1)
        self.assertTrue(progress["complete"])
        self.assertIsNone(progress["next_pose"])
        self.assertEqual(current_pose_index(state), len(ENROLLMENT_POSES))
        self.assertEqual(len(state["embeddings"]), 5)
        self.assertEqual(len(state["sample_images"]), 5)

    def test_state_rejects_capture_before_stability_and_out_of_order_pose(self):
        state = new_capture_state(7, created=1.0)
        with self.assertRaises(ValueError):
            record_sample(state, "frontal", b"vector", b"jpeg")
        for _ in range(STABLE_FRAMES_REQUIRED):
            observe_frame(state, True)
        with self.assertRaises(ValueError):
            record_sample(state, "left", b"vector", b"jpeg")


if __name__ == "__main__":
    unittest.main()
