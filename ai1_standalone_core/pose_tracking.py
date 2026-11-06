"""Calibrated relative-pose guidance for Smart Enrollment v2.

The legacy solvePnP yaw/pitch values use Euler angles in an uncalibrated model
frame and can report a frontal face near 180 degrees. Guided enrollment instead
uses the first stable, user-guided frontal rotation as its reference. This is
ordinary RGB landmark pose guidance; it is not depth sensing or liveness.
"""

import math
import time

import numpy as np

from .config import (
    GUIDED_CALIBRATION_MAX_RAW_YAW_DEG,
    GUIDED_FRONTAL_PITCH_MAX_DEG,
    GUIDED_FRONTAL_YAW_MAX_DEG,
    GUIDED_POSE_MAX_ROLL_DEG,
    GUIDED_POSE_MAX_STEP_DEG,
    GUIDED_POSE_REPROJECTION_MAX_PX,
    GUIDED_POSE_STABILITY_MAX_DEG,
    GUIDED_POSE_STABILITY_WINDOW_SECONDS,
    GUIDED_POSE_STABLE_FRAMES,
    GUIDED_POSE_TIMEOUT_SECONDS,
    GUIDED_POSE_UNRELIABLE_FRAME_LIMIT,
    GUIDED_SIDE_CROSS_AXIS_MAX_DEG,
    GUIDED_SIDE_YAW_MAX_DEG,
    GUIDED_SIDE_YAW_MIN_DEG,
    GUIDED_VERTICAL_CROSS_AXIS_MAX_DEG,
    GUIDED_VERTICAL_PITCH_MAX_DEG,
    GUIDED_VERTICAL_PITCH_MIN_DEG,
    POSES,
    STALE_FRAME_SECONDS,
)


POSE_DIRECTIONS = {
    "frontal": "Nhìn thẳng vào camera",
    "left": "Quay đầu sang trái",
    "right": "Quay đầu sang phải",
    "up": "Ngẩng đầu lên",
    "down": "Cúi đầu xuống",
}


def wrap_degrees(value):
    """Wrap an angle to [-180, 180), avoiding discontinuities at 360 degrees."""
    value = float(value)
    if not np.isfinite(value):
        raise ValueError("Angle must be finite.")
    return (value + 180.0) % 360.0 - 180.0


def angular_delta_degrees(first, second):
    """Smallest signed difference from first to second, with wrap handling."""
    return wrap_degrees(float(second) - float(first))


def normalize_rotation_matrix(value):
    matrix = np.asarray(value, dtype=np.float64)
    if matrix.shape != (3, 3) or not np.all(np.isfinite(matrix)):
        raise ValueError("Expected a finite 3x3 rotation matrix.")
    if np.linalg.det(matrix) <= 0.0:
        raise ValueError("Pose rotation matrix is reflected or singular.")
    if np.linalg.norm(matrix.T @ matrix - np.eye(3), ord="fro") > 0.05:
        raise ValueError("Pose rotation matrix is not orthonormal.")
    left, _singular, right = np.linalg.svd(matrix)
    correction = np.eye(3)
    correction[2, 2] = 1.0 if np.linalg.det(left @ right) >= 0.0 else -1.0
    result = left @ correction @ right
    if np.linalg.det(result) <= 0.0:
        raise ValueError("Could not normalize pose rotation matrix.")
    return result


def rotation_distance_degrees(first, second):
    """Geodesic SO(3) distance; stable around Euler angle wrap boundaries."""
    a = normalize_rotation_matrix(first)
    b = normalize_rotation_matrix(second)
    relative = a.T @ b
    cosine = float(np.clip((np.trace(relative) - 1.0) * 0.5, -1.0, 1.0))
    return math.degrees(math.acos(cosine))


def average_rotation_matrices(matrices):
    """Project the arithmetic matrix mean back onto SO(3) with SVD."""
    matrices = [normalize_rotation_matrix(item) for item in matrices]
    if not matrices:
        raise ValueError("At least one rotation is required for calibration.")
    mean = np.mean(np.stack(matrices), axis=0)
    left, _singular, right = np.linalg.svd(mean)
    correction = np.eye(3)
    correction[2, 2] = 1.0 if np.linalg.det(left @ right) >= 0.0 else -1.0
    return normalize_rotation_matrix(left @ correction @ right)


def relative_pose_angles(reference_rotation, current_rotation):
    """Decompose relative rotation into yaw(Y), pitch(X), then roll(Z).

    The order is ``R_y(yaw) @ R_x(-pitch) @ R_z(roll)`` in the face-model
    coordinate system. Positive yaw means turn left and positive pitch means
    look up. This is a proper Euler decomposition; Rodrigues axis-angle vector
    components are deliberately not treated as Euler angles.
    """
    reference = normalize_rotation_matrix(reference_rotation)
    current = normalize_rotation_matrix(current_rotation)
    relative = reference.T @ current
    # For R = Ry(yaw) Rx(a) Rz(roll), R[1,2] = -sin(a).
    # We define positive pitch as looking up, so pitch = -a.
    sin_a = float(np.clip(-relative[1, 2], -1.0, 1.0))
    a = math.asin(sin_a)
    cos_a = math.cos(a)
    if abs(cos_a) < 0.15:
        raise ValueError("Relative pose is near Euler gimbal lock.")
    yaw = math.degrees(math.atan2(relative[0, 2], relative[2, 2]))
    pitch = -math.degrees(a)
    roll = math.degrees(math.atan2(relative[1, 0], relative[1, 1]))
    yaw, pitch, roll = map(wrap_degrees, (yaw, pitch, roll))

    cy, sy = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    ca, sa = math.cos(math.radians(-pitch)), math.sin(math.radians(-pitch))
    cr, sr = math.cos(math.radians(roll)), math.sin(math.radians(roll))
    reconstructed = np.asarray([
        [cy * cr + sy * sa * sr, -cy * sr + sy * sa * cr, sy * ca],
        [ca * sr, ca * cr, -sa],
        [-sy * cr + cy * sa * sr, sy * sr + cy * sa * cr, cy * ca],
    ], dtype=np.float64)
    if np.linalg.norm(relative - reconstructed, ord="fro") > 1e-5:
        raise ValueError("Relative pose Euler decomposition is inconsistent.")
    return {"yaw": yaw, "pitch": pitch, "roll": roll,
            "relative_rotation": relative}


def classify_relative_pose(yaw, pitch, roll=0.0):
    """Classify configured guided zones; angle settings are bootstrap values."""
    yaw, pitch, roll = map(float, (yaw, pitch, roll))
    if not all(np.isfinite(value) for value in (yaw, pitch, roll)):
        return "unreliable"
    if abs(roll) > GUIDED_POSE_MAX_ROLL_DEG:
        return "between"
    if (abs(yaw) <= GUIDED_FRONTAL_YAW_MAX_DEG
            and abs(pitch) <= GUIDED_FRONTAL_PITCH_MAX_DEG):
        return "frontal"
    if (GUIDED_SIDE_YAW_MIN_DEG <= yaw <= GUIDED_SIDE_YAW_MAX_DEG
            and abs(pitch) <= GUIDED_SIDE_CROSS_AXIS_MAX_DEG):
        return "left"
    if (-GUIDED_SIDE_YAW_MAX_DEG <= yaw <= -GUIDED_SIDE_YAW_MIN_DEG
            and abs(pitch) <= GUIDED_SIDE_CROSS_AXIS_MAX_DEG):
        return "right"
    if (GUIDED_VERTICAL_PITCH_MIN_DEG <= pitch <= GUIDED_VERTICAL_PITCH_MAX_DEG
            and abs(yaw) <= GUIDED_VERTICAL_CROSS_AXIS_MAX_DEG):
        return "up"
    if (-GUIDED_VERTICAL_PITCH_MAX_DEG <= pitch <= -GUIDED_VERTICAL_PITCH_MIN_DEG
            and abs(yaw) <= GUIDED_VERTICAL_CROSS_AXIS_MAX_DEG):
        return "down"
    return "between"


class GuidedPoseTracker:
    """Calibrate from a stable frontal reference and emit one best frame per pose."""

    def __init__(self, stable_frames=GUIDED_POSE_STABLE_FRAMES,
                 max_stability_deg=GUIDED_POSE_STABILITY_MAX_DEG,
                 max_step_deg=GUIDED_POSE_MAX_STEP_DEG,
                 stability_window_seconds=GUIDED_POSE_STABILITY_WINDOW_SECONDS,
                 max_reprojection_px=GUIDED_POSE_REPROJECTION_MAX_PX,
                 unreliable_frame_limit=GUIDED_POSE_UNRELIABLE_FRAME_LIMIT,
                 pose_timeout_seconds=GUIDED_POSE_TIMEOUT_SECONDS,
                 stale_seconds=STALE_FRAME_SECONDS):
        self.stable_frames = int(stable_frames)
        self.max_stability_deg = float(max_stability_deg)
        self.max_step_deg = float(max_step_deg)
        self.stability_window_seconds = float(stability_window_seconds)
        self.max_reprojection_px = float(max_reprojection_px)
        self.unreliable_frame_limit = int(unreliable_frame_limit)
        self.pose_timeout_seconds = float(pose_timeout_seconds)
        self.stale_seconds = float(stale_seconds)
        if (self.stable_frames < 2 or self.max_stability_deg <= 0 or self.max_step_deg <= 0
                or self.stability_window_seconds <= 0):
            raise ValueError("Pose stability settings are invalid.")
        if (self.max_reprojection_px <= 0 or self.unreliable_frame_limit < 1
                or self.pose_timeout_seconds <= 0
                or self.stale_seconds <= 0):
            raise ValueError("Pose reliability settings are invalid.")
        self.reference_rotation = None
        self.expected_pose = None
        self.window = []
        self.last_sequence = -1
        self.unreliable_count = 0
        self.capture_issued = False
        self.manual_fallback = False
        self.pose_started_at = None
        self.stability_window_expirations = 0
        self.stale_frame_count = 0

    @property
    def stable_count(self):
        return len(self.window)

    def _clear_window(self):
        self.window = []
        self.capture_issued = False

    def reset(self):
        self.reference_rotation = None
        self.expected_pose = None
        self.unreliable_count = 0
        self.manual_fallback = False
        self.pose_started_at = None
        self.stability_window_expirations = 0
        self.stale_frame_count = 0
        self._clear_window()

    def force_manual_fallback(self, reason):
        self.manual_fallback = True
        self._clear_window()
        return {"status": "FALLBACK_MANUAL", "reason": str(reason), "stable_count": 0}

    def _unreliable(self, reason):
        self._clear_window()
        self.unreliable_count += 1
        if self.unreliable_count >= self.unreliable_frame_limit:
            return self.force_manual_fallback(
                f"Pose chưa đủ tin cậy sau {self.unreliable_count} frame: {reason}"
            )
        return {"status": "POSE_UNRELIABLE", "reason": str(reason),
                "stable_count": 0, "unreliable_count": self.unreliable_count}

    def _timeout_reason(self, expected_pose):
        reasons = []
        if self.stability_window_expirations:
            required_fps = (self.stable_frames - 1) / self.stability_window_seconds
            reasons.append(
                f"the {self.stable_frames}-frame/{self.stability_window_seconds:.1f}s "
                f"stability window expired {self.stability_window_expirations} times "
                f"(approximately {required_fps:.1f} fresh frames/s are required)"
            )
        if self.stale_frame_count:
            reasons.append(
                f"{self.stale_frame_count} frames were stale or repeated, possibly due to "
                "camera delay or slow inference"
            )
        if not reasons:
            return f"Pose {expected_pose} did not stabilize within {self.pose_timeout_seconds:.0f}s."
        return (
            f"Pose {expected_pose} timed out after {self.pose_timeout_seconds:.0f}s: "
            + "; ".join(reasons)
            + ". AUTO limits were not relaxed."
        )

    def observe(self, expected_pose, outcome, frame, sequence, captured_at, now=None):
        """Consume one unique fresh quality-valid frame from the FramePump."""
        now = time.monotonic() if now is None else float(now)
        if expected_pose not in POSES:
            self._clear_window()
            return {"status": "COMPLETE", "stable_count": 0}
        if expected_pose != self.expected_pose:
            self.expected_pose = expected_pose
            self.pose_started_at = now
            self.stability_window_expirations = 0
            self.stale_frame_count = 0
            self._clear_window()
            self.unreliable_count = 0
        if self.manual_fallback:
            return {"status": "FALLBACK_MANUAL", "reason": "Manual mode is active.",
                    "stable_count": 0}
        if (self.pose_started_at is not None
                and now - self.pose_started_at >= self.pose_timeout_seconds):
            return self.force_manual_fallback(self._timeout_reason(expected_pose))

        try:
            sequence = int(sequence)
            age = now - float(captured_at)
        except (TypeError, ValueError):
            self.stale_frame_count += 1
            self._clear_window()
            return {"status": "STALE_FRAME", "reason": "Timestamp/frame sequence invalid.",
                    "stable_count": 0, "stale_frame_count": self.stale_frame_count}
        if sequence <= self.last_sequence:
            self.stale_frame_count += 1
            self._clear_window()
            return {"status": "STALE_FRAME", "reason": "Frame sequence is not fresh.",
                    "stable_count": 0, "stale_frame_count": self.stale_frame_count}
        self.last_sequence = sequence
        if not np.isfinite(age) or age < -0.1 or age > self.stale_seconds:
            self.stale_frame_count += 1
            self._clear_window()
            return {"status": "STALE_FRAME", "reason": "Frame is outside the freshness window.",
                    "stable_count": 0, "stale_frame_count": self.stale_frame_count}
        if not isinstance(outcome, dict) or outcome.get("status") != "OK":
            self._clear_window()
            return {"status": "QUALITY_REJECTED",
                    "reason": str(outcome.get("reason", "Quality gate failed."))
                    if isinstance(outcome, dict) else "Quality gate failed.",
                    "stable_count": 0}

        face = outcome.get("face")
        pose_data = face.get("head_pose") if isinstance(face, dict) else None
        if not isinstance(pose_data, dict):
            return self._unreliable("solvePnP did not return a rotation.")
        try:
            rotation = normalize_rotation_matrix(pose_data["rotation_matrix"])
            reprojection_error = float(pose_data["reprojection_error_px"])
            positive_depth = bool(pose_data.get("positive_depth", True))
        except (KeyError, TypeError, ValueError) as exc:
            return self._unreliable(f"invalid rotation/reprojection ({exc}).")
        if (not positive_depth or not np.isfinite(reprojection_error)
                or reprojection_error > self.max_reprojection_px):
            raw_yaw = pose_data.get("raw_yaw", pose_data.get("yaw"))
            raw_pitch = pose_data.get("raw_pitch", pose_data.get("pitch"))
            return self._unreliable(
                f"reprojection={reprojection_error:.1f}px (limit {self.max_reprojection_px:.1f}px), "
                f"positive_depth={positive_depth}, raw_yaw={raw_yaw}, raw_pitch={raw_pitch}."
            )
        self.unreliable_count = 0

        if expected_pose == "frontal" and self.reference_rotation is None:
            try:
                raw_yaw = float(pose_data["yaw"])
            except (KeyError, TypeError, ValueError):
                return self._unreliable("raw yaw was not returned for frontal calibration.")
            if (not np.isfinite(raw_yaw)
                    or abs(raw_yaw) > GUIDED_CALIBRATION_MAX_RAW_YAW_DEG):
                self._clear_window()
                return {
                    "status": "POSE_NOT_READY", "detected_pose": "between",
                    "expected_pose": "frontal", "yaw": None, "pitch": None,
                    "roll": None, "raw_yaw": raw_yaw,
                    "raw_pitch": pose_data.get("pitch"),
                    "reprojection_error_px": reprojection_error,
                    "stable_count": 0, "calibrating": True,
                    "reason": (f"Nhìn thẳng để hiệu chỉnh frontal; raw yaw={raw_yaw:+.1f}° "
                               f"(giới hạn sơ bộ ±{GUIDED_CALIBRATION_MAX_RAW_YAW_DEG:.0f}°). "
                               "Raw pitch chỉ là thông tin debug."),
                }
            # There is no calibrated angle until a stable frontal reference has
            # been collected. Keep it unset instead of displaying fabricated 0°.
            angles = None
            detected_pose = "frontal"
            calibrating = True
        else:
            try:
                angles = relative_pose_angles(self.reference_rotation, rotation)
            except (TypeError, ValueError) as exc:
                return self._unreliable(f"relative Euler pose failed ({exc}).")
            detected_pose = classify_relative_pose(angles["yaw"], angles["pitch"], angles["roll"])
            calibrating = False
            if detected_pose != expected_pose:
                self._clear_window()
                return {
                    "status": "POSE_NOT_READY", "detected_pose": detected_pose,
                    "expected_pose": expected_pose, "yaw": angles["yaw"],
                    "pitch": angles["pitch"], "roll": angles["roll"],
                    "reprojection_error_px": reprojection_error, "stable_count": 0,
                }

        if self.capture_issued:
            return {"status": "CAPTURE_PENDING", "detected_pose": detected_pose,
                    "expected_pose": expected_pose,
                    "yaw": None if angles is None else angles["yaw"],
                    "pitch": None if angles is None else angles["pitch"],
                    "roll": None if angles is None else angles["roll"],
                    "stable_count": self.stable_count}

        window_expired = False
        if self.window:
            if float(captured_at) - self.window[0]["captured_at"] > self.stability_window_seconds:
                self.stability_window_expirations += 1
                window_expired = True
                self._clear_window()
        if self.window:
            max_delta = max(rotation_distance_degrees(item["rotation"], rotation)
                            for item in self.window)
            if max_delta > self.max_step_deg:
                self._clear_window()
        quality = outcome.get("quality") or {}
        try:
            sharpness = float(quality.get("sharpness", 0.0))
        except (TypeError, ValueError):
            sharpness = 0.0
        if not np.isfinite(sharpness):
            sharpness = 0.0
        reported_angles = {
            "yaw": None if angles is None else angles["yaw"],
            "pitch": None if angles is None else angles["pitch"],
            "roll": None if angles is None else angles["roll"],
        }
        self.window.append({
            "rotation": rotation,
            "sequence": sequence,
            "captured_at": float(captured_at),
            "sharpness": sharpness,
            "frame": np.asarray(frame).copy(),
            "outcome": outcome,
            **reported_angles,
            "reprojection_error_px": reprojection_error,
        })
        self.window = self.window[-self.stable_frames:]
        if self.stable_count < self.stable_frames:
            return {"status": "STABILIZING", "detected_pose": detected_pose,
                    "expected_pose": expected_pose,
                    "yaw": None if angles is None else angles["yaw"],
                    "pitch": None if angles is None else angles["pitch"],
                    "roll": None if angles is None else angles["roll"],
                    "reprojection_error_px": reprojection_error,
                    "stable_count": self.stable_count, "calibrating": calibrating,
                    "stability_window_expirations": self.stability_window_expirations,
                    "reason": (
                        f"Cửa sổ {self.stable_frames} frame / "
                        f"{self.stability_window_seconds:.1f}s vừa hết hạn; "
                        "camera hoặc AI xử lý frame chưa đủ nhanh. Giới hạn không thay đổi."
                        if window_expired else None
                    )}
        spread = max(
            rotation_distance_degrees(first["rotation"], second["rotation"])
            for index, first in enumerate(self.window)
            for second in self.window[index + 1:]
        )
        if spread > self.max_stability_deg:
            self._clear_window()
            self.window.append({
                "rotation": rotation, "sequence": sequence,
                "captured_at": float(captured_at), "sharpness": sharpness,
                "frame": np.asarray(frame).copy(), "outcome": outcome,
                **reported_angles,
                "reprojection_error_px": reprojection_error,
            })
            return {"status": "STABILIZING", "detected_pose": detected_pose,
                    "expected_pose": expected_pose,
                    "yaw": None if angles is None else angles["yaw"],
                    "pitch": None if angles is None else angles["pitch"],
                    "roll": None if angles is None else angles["roll"],
                    "reprojection_error_px": reprojection_error,
                    "stable_count": 1, "calibrating": calibrating}

        reference = (average_rotation_matrices([item["rotation"] for item in self.window])
                     if calibrating else self.reference_rotation)
        if calibrating:
            self.reference_rotation = reference
        candidate = max(self.window, key=lambda item: item["sharpness"])
        if calibrating:
            angles = relative_pose_angles(reference, candidate["rotation"])
        self.capture_issued = True
        return {
            "status": "CAPTURE_READY", "detected_pose": detected_pose,
            "expected_pose": expected_pose,
            "yaw": None if angles is None else angles["yaw"],
            "pitch": None if angles is None else angles["pitch"],
            "roll": None if angles is None else angles["roll"],
            "reprojection_error_px": reprojection_error,
            "stable_count": self.stable_count, "calibrating": calibrating,
            "candidate": candidate,
        }

    def capture_result(self, captured, next_pose=None, now=None):
        """Advance once after gallery state has accepted the candidate sample."""
        self.capture_issued = False
        if captured:
            self.expected_pose = next_pose
            self.pose_started_at = (
                (time.monotonic() if now is None else float(now))
                if next_pose in POSES else None
            )
            self.stability_window_expirations = 0
            self.stale_frame_count = 0
            self._clear_window()
            self.unreliable_count = 0
        else:
            self._clear_window()
