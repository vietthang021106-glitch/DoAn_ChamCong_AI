"""Hardware-free checks for stable pose capture and identity validation."""

import unittest

import numpy as np

from ai1_standalone_core.config import POSES
from ai1_gui_core.enrollment_state import EnrollmentCaptureState


def basis(index):
    value = np.zeros(512, dtype=np.float32)
    value[index] = 1.0
    return value


def valid_outcome(pose, embedding=None):
    return {"status": "OK", "detected_pose": pose,
            "embedding": embedding if embedding is not None else basis(0)}


class EnrollmentStateTests(unittest.TestCase):
    def test_auto_capture_occurs_only_at_eight_distinct_valid_frames(self):
        state = EnrollmentCaptureState(ready_frames=8)
        for sequence in range(1, 8):
            result = state.observe(sequence, valid_outcome("frontal"))
            self.assertFalse(result["capture_due"])
            self.assertEqual(result["stable_frame_count"], sequence)
        result = state.observe(8, valid_outcome("frontal"))
        self.assertTrue(result["capture_due"])
        self.assertEqual(result["stable_frame_count"], 8)
        capture = state.capture(valid_outcome("frontal"))
        self.assertEqual(capture["pose"], "frontal")
        self.assertEqual(state.current_pose, "left")

    def test_invalid_frame_resets_stability(self):
        state = EnrollmentCaptureState(ready_frames=8)
        for sequence in range(1, 5):
            state.observe(sequence, valid_outcome("frontal"))
        result = state.observe(5, {"status": "RETRY", "code": "TOO BLURRY", "reason": "blur"})
        self.assertFalse(result["capture_due"])
        self.assertEqual(result["stable_frame_count"], 0)
        self.assertEqual(result["code"], "TOO BLURRY")

    def test_repeated_sequence_does_not_count_as_a_stable_frame(self):
        state = EnrollmentCaptureState(ready_frames=2)
        state.observe(7, valid_outcome("frontal"))
        result = state.observe(7, valid_outcome("frontal"))
        self.assertEqual(result["stable_frame_count"], 0)
        self.assertFalse(result["capture_due"])

    def test_pose_order_and_same_person_reference(self):
        state = EnrollmentCaptureState(ready_frames=1)
        for sequence, pose in enumerate(POSES, start=1):
            result = state.observe(sequence, valid_outcome(pose))
            self.assertTrue(result["capture_due"])
            state.capture(valid_outcome(pose))
        self.assertTrue(state.complete)
        self.assertIsNone(state.current_pose)
        self.assertTrue(state.validate_complete()["valid"])

    def test_wrong_person_is_rejected_against_frontal_sample(self):
        state = EnrollmentCaptureState(ready_frames=1, same_person_threshold=0.45)
        state.observe(1, valid_outcome("frontal", basis(0)))
        state.capture(valid_outcome("frontal", basis(0)))
        result = state.observe(2, valid_outcome("left", basis(1)))
        self.assertEqual(result["code"], "SAME PERSON")
        self.assertFalse(result["capture_due"])
        self.assertEqual(state.current_pose, "left")

    def test_retake_resets_stability_and_returns_to_missing_pose(self):
        state = EnrollmentCaptureState(ready_frames=1)
        for sequence, pose in enumerate(POSES[:3], start=1):
            outcome = valid_outcome(pose)
            state.observe(sequence, outcome)
            state.capture(outcome)
        state.clear_pose("left")
        self.assertEqual(state.current_pose, "left")
        self.assertEqual(state.stable_frame_count, 0)
        self.assertEqual(set(state.embeddings), {"frontal", "right"})

    def test_final_validation_rechecks_exactly_five_samples(self):
        state = EnrollmentCaptureState(ready_frames=1)
        self.assertFalse(state.validate_complete()["valid"])


if __name__ == "__main__":
    unittest.main()
