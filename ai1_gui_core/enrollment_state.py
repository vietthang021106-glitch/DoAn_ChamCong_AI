"""Deterministic five-pose auto-capture state used by the desktop GUI."""

import numpy as np

import face_matching

from ai1_standalone_core.config import (
    EMBEDDING_DIMENSIONS,
    ENROLLMENT_IDENTITY_THRESHOLD,
    POSES,
)


class EnrollmentCaptureState:
    def __init__(self, ready_frames=8, same_person_threshold=ENROLLMENT_IDENTITY_THRESHOLD):
        if int(ready_frames) < 1:
            raise ValueError("ready_frames must be positive.")
        self.ready_frames = int(ready_frames)
        self.same_person_threshold = float(same_person_threshold)
        if not np.isfinite(self.same_person_threshold) or not -1.0 <= self.same_person_threshold <= 1.0:
            raise ValueError("same_person_threshold must be between -1 and 1.")
        self.current_pose_index = 0
        self.stable_frame_count = 0
        self.last_sequence = -1
        self.embeddings = {}

    @property
    def current_pose(self):
        if self.current_pose_index >= len(POSES):
            return None
        return POSES[self.current_pose_index]

    @property
    def complete(self):
        return set(self.embeddings) == set(POSES)

    def reset_stability(self):
        self.stable_frame_count = 0

    def observe(self, sequence, outcome):
        """Count only distinct valid frames for the current pose; reset on every failure."""
        if self.current_pose is None:
            self.reset_stability()
            return self._result(False, "COMPLETE", "Đã đủ 5 pose.")
        if not isinstance(sequence, int) or sequence <= self.last_sequence:
            self.reset_stability()
            return self._result(False, "STALE_FRAME", "Khung hình chưa mới, chờ frame mới.")
        self.last_sequence = sequence
        if not isinstance(outcome, dict) or outcome.get("status") != "OK":
            self.reset_stability()
            code = str(outcome.get("code", "QUALITY CHECK")) if isinstance(outcome, dict) else "QUALITY CHECK"
            reason = str(outcome.get("reason", code)) if isinstance(outcome, dict) else code
            return self._result(False, code, reason)

        detected_pose = outcome.get("detected_pose")
        if detected_pose != self.current_pose:
            self.reset_stability()
            return self._result(False, "WRONG POSE", f"Hướng hiện tại: {detected_pose or 'chưa xác định'}.")
        try:
            embedding = face_matching.normalize_embedding(
                outcome.get("embedding"), EMBEDDING_DIMENSIONS
            )
        except (TypeError, ValueError) as exc:
            self.reset_stability()
            return self._result(False, "INVALID EMBEDDING", str(exc))

        if self.current_pose != POSES[0]:
            reference = self.embeddings.get(POSES[0])
            if reference is None:
                self.reset_stability()
                return self._result(False, "MISSING FRONTAL", "Cần chụp mẫu nhìn thẳng trước.")
            similarity = face_matching.cosine_similarity(reference, embedding)
            if similarity < self.same_person_threshold:
                self.reset_stability()
                return self._result(
                    False, "SAME PERSON", "Khuôn mặt không khớp mẫu nhìn thẳng; hãy để đúng người trước camera."
                )

        self.stable_frame_count += 1
        ready = self.stable_frame_count >= self.ready_frames
        return self._result(ready, "READY" if ready else "STABILIZING",
                            "Đang tự chụp…" if ready else "Giữ yên…", embedding=embedding)

    def capture(self, outcome):
        """Commit one in-memory pose sample after its 8-frame stability gate."""
        pose = self.current_pose
        if pose is None or self.stable_frame_count < self.ready_frames:
            raise RuntimeError("The current pose is not stable enough to capture.")
        if not isinstance(outcome, dict) or outcome.get("status") != "OK":
            raise ValueError("Only a valid enrollment result can be captured.")
        if outcome.get("detected_pose") != pose:
            raise ValueError("The detected pose changed before auto-capture.")
        embedding = face_matching.normalize_embedding(outcome.get("embedding"), EMBEDDING_DIMENSIONS)
        if pose != POSES[0]:
            reference = self.embeddings.get(POSES[0])
            if reference is None or face_matching.cosine_similarity(reference, embedding) < self.same_person_threshold:
                raise ValueError("The pose sample does not match the frontal reference.")
        self.embeddings[pose] = embedding
        self.current_pose_index = next(
            (index for index, candidate in enumerate(POSES) if candidate not in self.embeddings),
            len(POSES),
        )
        self.reset_stability()
        return {"pose": pose, "captured": len(self.embeddings), "complete": self.complete}

    def clear_pose(self, pose):
        if pose not in POSES:
            raise ValueError("Unknown enrollment pose.")
        self.embeddings.pop(pose, None)
        self.current_pose_index = next(
            (index for index, candidate in enumerate(POSES) if candidate not in self.embeddings),
            len(POSES),
        )
        self.reset_stability()

    def validate_complete(self):
        """Revalidate all five 512D vectors, frontal identity, and pairwise consistency."""
        if not self.complete:
            return {"valid": False, "bad_poses": list(POSES),
                    "reason": "All five enrollment poses are required."}
        normalized = {}
        try:
            for pose in POSES:
                normalized[pose] = face_matching.normalize_embedding(
                    self.embeddings[pose], EMBEDDING_DIMENSIONS
                )
        except (TypeError, ValueError) as exc:
            return {"valid": False, "bad_poses": list(POSES), "reason": str(exc)}
        reference = normalized[POSES[0]]
        bad_poses = [pose for pose in POSES[1:]
                     if face_matching.cosine_similarity(reference, normalized[pose])
                     < self.same_person_threshold]
        if bad_poses:
            return {"valid": False, "bad_poses": bad_poses,
                    "reason": "A pose does not match the frontal sample."}
        from ai1_standalone_core.enrollment import five_pose_consistency

        consistency = five_pose_consistency(normalized, self.same_person_threshold)
        if not consistency["valid"]:
            return consistency
        self.embeddings = normalized
        return consistency

    def _result(self, capture_due, code, reason, embedding=None):
        return {
            "capture_due": bool(capture_due),
            "current_pose": self.current_pose,
            "stable_frame_count": self.stable_frame_count,
            "ready_frames": self.ready_frames,
            "captured": len(self.embeddings),
            "progress": len(self.embeddings),
            "code": code,
            "reason": reason,
            "embedding": embedding,
        }
