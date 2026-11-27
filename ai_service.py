"""Loopback AI API; PHP remains the only owner of MariaDB access."""

import base64
import binascii
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import tempfile
import threading
import time
import urllib.request
import uuid

import cv2
import numpy as np
from flask import Flask, jsonify, request, Response

import face_engine
from ai1_standalone_core.ai1_adapter import validate_enrollment_frame, validate_enrollment_pose_frame
from ai1_standalone_core.config import (
    GUIDED_POSE_STABLE_FRAMES,
    GUIDED_POSE_TIMEOUT_SECONDS,
    POSES as GUIDED_POSES,
)
from ai1_standalone_core.pose_tracking import (
    GuidedPoseTracker,
    assess_frontal_camera_alignment,
)
from face_matching import (
    ENROLLMENT_IDENTITY_THRESHOLD,
    aggregate_gallery,
    cosine_similarity,
    decode_stored_embedding,
    identify_embedding,
    normalize_embedding,
)


PHP_GALLERY_URL = os.getenv(
    "PHP_FACE_GALLERY_URL",
    "http://127.0.0.1:8080/?action=internal_face_gallery",
)
FLASK_CAMERA_FRAME_URL = os.getenv(
    "FLASK_CAMERA_FRAME_URL",
    "http://127.0.0.1:5000/internal/camera/frame",
)
EMBEDDING_DIMENSIONS = 512
EMBEDDING_BYTES = EMBEDDING_DIMENSIONS * np.dtype("<f4").itemsize
ENROLLMENT_POSES = ("frontal", "left", "right", "up", "down")
POSE_LABELS = {
    "frontal": "Nhìn thẳng",
    "left": "Quay trái",
    "right": "Quay phải",
    "up": "Ngẩng lên",
    "down": "Cúi xuống",
}
MAX_ENROLLMENT_IMAGE_BYTES = 5 * 1024 * 1024
MAX_RECOGNITION_IMAGE_BYTES = 2 * 1024 * 1024
ENROLLMENT_SESSION_TTL_SECONDS = 600
DEFAULT_RECOGNITION_SESSION_TIMEOUT_SECONDS = 20.0
MAX_RECOGNITION_SESSION_TIMEOUT_SECONDS = 60.0


def _recognition_session_timeout_seconds():
    """Give the Web/Kiosk worker enough time for three serial CPU embeddings.

    This is a Web service session budget only; standalone AI1 recognition
    configuration and matching thresholds remain unchanged.
    """
    raw = os.getenv("AI1_RECOGNITION_SESSION_TIMEOUT_SECONDS")
    try:
        configured = float(raw) if raw is not None else DEFAULT_RECOGNITION_SESSION_TIMEOUT_SECONDS
    except (TypeError, ValueError):
        configured = DEFAULT_RECOGNITION_SESSION_TIMEOUT_SECONDS
    if not np.isfinite(configured):
        configured = DEFAULT_RECOGNITION_SESSION_TIMEOUT_SECONDS
    return min(MAX_RECOGNITION_SESSION_TIMEOUT_SECONDS, max(8.5, configured))


def _face_bbox_area(face):
    bbox = face.get("bbox")
    if bbox is None or len(bbox) != 4:
        return 0.0
    width = max(0.0, float(bbox[2]) - float(bbox[0]))
    height = max(0.0, float(bbox[3]) - float(bbox[1]))
    return width * height


def _face_sharpness(frame, bbox):
    if not isinstance(bbox, (list, tuple, np.ndarray)) or len(bbox) != 4:
        return 0.0
    height, width = frame.shape[:2]
    x1, y1, x2, y2 = [int(round(float(value))) for value in bbox]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(width, x2), min(height, y2)
    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        return 0.0
    gray = cv2.cvtColor(cv2.resize(crop, (128, 160)), cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _enrollment_face_geometry(
        frame, outcome, observation_status, *,
        frame_sequence=None, frame_timestamp=None, frame_age_ms=None):
    """Expose only the backend-selected safe primary face to the Kiosk guide."""
    empty = {
        "face_bbox": None, "frame_width": 0, "frame_height": 0,
        "face_count": 0, "total_face_count": 0,
        "primary_face_safe": False, "detection_score": None,
        "primary_face_area_ratio": None,
        "primary_face_area_ratio_required": None,
        "frame_sequence": frame_sequence,
        "frame_timestamp": frame_timestamp,
        "frame_age_ms": frame_age_ms,
    }
    if not isinstance(frame, np.ndarray) or frame.ndim < 2 or frame.size == 0:
        return empty
    height, width = frame.shape[:2]
    outcome = outcome if isinstance(outcome, dict) else {}
    faces = outcome.get("faces")
    candidates = [face for face in faces if isinstance(face, dict)] \
        if isinstance(faces, (list, tuple)) else []
    try:
        reported_count = int(outcome.get("total_face_count", outcome.get("face_count", len(candidates))))
    except (TypeError, ValueError):
        reported_count = len(candidates)
    face_count = max(0, reported_count, len(candidates))
    result = {
        "face_bbox": None, "frame_width": width, "frame_height": height,
        "face_count": face_count,
        "total_face_count": face_count,
        "primary_face_safe": False,
        "detection_score": None,
        "primary_face_area_ratio": None,
        "primary_face_area_ratio_required": None,
        "frame_sequence": frame_sequence,
        "frame_timestamp": frame_timestamp,
        "frame_age_ms": frame_age_ms,
    }
    ratio = outcome.get("primary_face_area_ratio")
    try:
        ratio = float(ratio)
        result["primary_face_area_ratio"] = ratio if np.isfinite(ratio) else None
    except (TypeError, ValueError):
        pass
    required_ratio = outcome.get("primary_face_area_ratio_required")
    try:
        required_ratio = float(required_ratio)
        result["primary_face_area_ratio_required"] = (
            required_ratio if np.isfinite(required_ratio) and required_ratio >= 1.0 else None
        )
    except (TypeError, ValueError):
        pass
    # On an ambiguous frame this is diagnostic confidence only. No bbox or
    # confirmation ring is exposed until the tracker accepts the primary face.
    diagnostic_face = outcome.get("selected_primary_face") or outcome.get("face")
    if isinstance(diagnostic_face, dict):
        try:
            score = float(diagnostic_face.get("detection_score"))
            if np.isfinite(score):
                result["detection_score"] = score
        except (TypeError, ValueError):
            pass
    if (str(observation_status).upper() in {
            "STALE_FRAME", "IDENTITY_MISMATCH", "PRIMARY_FACE_CHANGED"
        }
            or outcome.get("primary_face_safe") is not True):
        return result
    face = outcome.get("selected_primary_face")
    if not isinstance(face, dict):
        return result
    try:
        box = np.asarray(face.get("bbox"), dtype=np.float64).reshape(-1)
    except (AttributeError, TypeError, ValueError):
        box = np.empty(0, dtype=np.float64)
    if box.size != 4 or not np.all(np.isfinite(box)):
        return result
    x1, y1, x2, y2 = box.tolist()
    x1, x2 = max(0.0, min(float(width), x1)), max(0.0, min(float(width), x2))
    y1, y2 = max(0.0, min(float(height), y1)), max(0.0, min(float(height), y2))
    if x2 <= x1 or y2 <= y1:
        return result
    try:
        score = float(face.get("detection_score"))
        if not np.isfinite(score):
            score = None
    except (TypeError, ValueError):
        score = None
    result["face_bbox"] = [x1, y1, x2, y2]
    result["detection_score"] = score
    result["primary_face_safe"] = True
    return result


def _temporal_consistency_threshold():
    raw = os.getenv("FACE_TEMPORAL_CONSISTENCY_THRESHOLD", "0.60")
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("Temporal consistency threshold must be between 0 and 1.") from exc
    if not np.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError("Temporal consistency threshold must be between 0 and 1.")
    return value


def _recognition_threshold():
    value = os.getenv("FACE_RECOGNITION_THRESHOLD", "0.45")
    try:
        threshold = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Threshold must be a number between -1 and 1.") from exc
    if not -1.0 <= threshold <= 1.0:
        raise ValueError("Threshold must be a number between -1 and 1.")
    return threshold


class GalleryUnavailableError(RuntimeError):
    """Recognition must not proceed with an old in-memory gallery."""


class AIRuntime:
    def __init__(self):
        self.engine = face_engine.face_engine
        self._lock = threading.RLock()
        self._refresh_lock = threading.Lock()
        self._gallery = {}
        self._gallery_loaded = False
        self._embedding_count = 0
        self._invalid_count = 0
        self._model_error = None
        self._gallery_error = None
        self._gallery_revision = None
        self._recognition_sessions = {}
        self._active_recognition_session = None
        self._session_lock = threading.RLock()
        self._recognition_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ai1-recognition")
        self._enrollment_sessions = {}
        self._active_enrollment_session = None
        self._enrollment_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ai1-enrollment")

    def initialize(self):
        """Initialize buffalo_l and load the PHP-owned face gallery into RAM."""
        try:
            self.engine.initialize()
        except Exception as exc:
            self._model_error = str(exc)
        try:
            self.refresh_gallery()
        except Exception:
            self._gallery_error = "Could not load gallery from PHP."

    def refresh_gallery(self):
        """Fetch, validate, and replace the in-memory face gallery."""
        # Serialize before fetching: an older, slower response cannot replace a newer refresh.
        with self._refresh_lock:
            with urllib.request.urlopen(PHP_GALLERY_URL, timeout=10) as response:
                payload = response.read()
            document = json.loads(payload.decode("utf-8"))
            if not document.get("success") or not isinstance(document.get("embeddings"), list):
                raise RuntimeError("PHP face gallery response is invalid.")

            rows = []
            sample_ids = set()
            for item in document["embeddings"]:
                if not isinstance(item, dict):
                    raise ValueError("Face gallery contains an invalid sample.")
                sample_id, employee_id = item.get("ma_embedding"), item.get("ma_nv")
                dimensions = item.get("so_chieu")
                if (type(sample_id) is not int or sample_id <= 0 or sample_id in sample_ids
                        or type(employee_id) is not int or not 0 < employee_id <= 2_147_483_647
                        or dimensions != EMBEDDING_DIMENSIONS):
                    raise ValueError("Face gallery contains an invalid sample identity or dimension.")
                raw = base64.b64decode(item["vector"], validate=True)
                if len(raw) != EMBEDDING_BYTES:
                    raise ValueError("Face gallery contains an embedding with invalid dimensions or byte length.")
                expected_hash = item.get("sha256")
                if not isinstance(expected_hash, str) or hashlib.sha256(raw).hexdigest() != expected_hash:
                    raise ValueError("Face embedding checksum mismatch after HTTP/base64 decode.")
                employee_name = item.get("ho_ten", "")
                if not isinstance(employee_name, str):
                    raise ValueError("Face gallery contains an invalid employee name.")
                rows.append((sample_id, employee_id, raw, dimensions, employee_name))
                sample_ids.add(sample_id)

            gallery, invalid_rows = aggregate_gallery(rows)
            revision_rows = sorted((sample_id, hashlib.sha256(raw).hexdigest())
                                   for sample_id, _, raw, _, _ in rows)
            revision_bytes = json.dumps(revision_rows, separators=(",", ":")).encode("ascii")
            gallery_revision = hashlib.sha256(revision_bytes).hexdigest()
            with self._lock:
                self._gallery = gallery
                self._gallery_revision = gallery_revision
                self._embedding_count = len(rows) - len(invalid_rows)
                self._invalid_count = len(invalid_rows)
                self._gallery_loaded = True
                self._gallery_error = None

        return {
            "embedding_count": self._embedding_count,
            "employee_count": len(gallery),
            "invalid_count": self._invalid_count,
        }

    def health(self):
        with self._lock:
            model_ready = bool(self.engine._initialized)
            return {
                "success": True,
                "service": "python-ai",
                "model": face_engine.MODEL_NAME,
                "model_ready": model_ready,
                "gallery_ready": self._gallery_loaded and self._gallery_error is None,
                "embedding_count": self._embedding_count,
                "employee_count": len(self._gallery),
                "invalid_embeddings": self._invalid_count,
                "threshold": _recognition_threshold(),
                "gallery_revision": self._gallery_revision,
                "camera_source": "Flask camera singleton",
                "model_error": self._model_error,
                "gallery_error": self._gallery_error,
            }

    def fetch_camera_frame(self):
        with urllib.request.urlopen(FLASK_CAMERA_FRAME_URL, timeout=5) as response:
            content_type = response.headers.get_content_type()
            if content_type != "image/jpeg":
                raise RuntimeError("Camera relay did not return a JPEG frame.")
            raw = response.read()
        frame = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            raise RuntimeError("Camera relay returned an invalid frame.")
        return raw, frame

    def fetch_camera_snapshot(self):
        """Fetch one fresh frame from the shared camera owner with its sequence metadata."""
        with urllib.request.urlopen(FLASK_CAMERA_FRAME_URL, timeout=1.5) as response:
            if response.headers.get_content_type() != "image/jpeg":
                raise RuntimeError("Camera relay did not return a JPEG frame.")
            raw = response.read(MAX_RECOGNITION_IMAGE_BYTES + 1)
            sequence = response.headers.get("X-Frame-Sequence")
            captured_at = response.headers.get("X-Frame-Monotonic")
        if not raw or len(raw) > MAX_RECOGNITION_IMAGE_BYTES:
            raise RuntimeError("Camera relay returned an invalid or oversized frame.")
        try:
            sequence = int(sequence)
            captured_at = float(captured_at)
        except (TypeError, ValueError) as exc:
            raise RuntimeError("Camera relay is missing fresh-frame metadata.") from exc
        frame = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is None or frame.size == 0:
            raise RuntimeError("Camera relay returned an invalid frame.")
        return raw, frame, sequence, captured_at

    def start_recognition_session(self):
        """Start one asynchronous three-fresh-snapshot recognition session."""
        with self._session_lock:
            enrollment = self._enrollment_sessions.get(self._active_enrollment_session)
            if enrollment and time.time() - enrollment.get("created_at", 0) > ENROLLMENT_SESSION_TTL_SECONDS:
                enrollment["state"] = "EXPIRED"
                enrollment["cancel_event"].set()
                self._active_enrollment_session = None
                enrollment = None
            if enrollment and enrollment.get("state") in {"ENROLLING", "AWAITING_CONFIRMATION", "MANUAL"}:
                return None
            active = self._recognition_sessions.get(self._active_recognition_session)
            if active and active.get("future") is not None and not active["future"].done():
                return None

        # A failed enrollment refresh leaves _gallery_error set even if an old
        # cache is still present. Retry that refresh before recognition; never
        # match against the stale cache. The normal ready path keeps its
        # existing request latency and gallery snapshot behavior.
        with self._lock:
            gallery_needs_refresh = not self._gallery_loaded or self._gallery_error is not None
        if gallery_needs_refresh:
            try:
                self.refresh_gallery()
            except Exception as exc:
                with self._lock:
                    self._gallery_error = "Could not load gallery from PHP."
                raise GalleryUnavailableError("Face gallery is unavailable or stale.") from exc

        with self._session_lock:
            enrollment = self._enrollment_sessions.get(self._active_enrollment_session)
            if enrollment and time.time() - enrollment.get("created_at", 0) > ENROLLMENT_SESSION_TTL_SECONDS:
                enrollment["state"] = "EXPIRED"
                enrollment["cancel_event"].set()
                self._active_enrollment_session = None
                enrollment = None
            if enrollment and enrollment.get("state") in {"ENROLLING", "AWAITING_CONFIRMATION", "MANUAL"}:
                return None
            active = self._recognition_sessions.get(self._active_recognition_session)
            if active and active.get("future") is not None and not active["future"].done():
                return None
            if not self.engine._initialized:
                raise RuntimeError("Face recognition model is unavailable.")
            session_id = uuid.uuid4().hex
            timeout_seconds = _recognition_session_timeout_seconds()
            record = {
                "session_id": session_id,
                "state": "CAPTURING",
                "captured_frames": 0,
                "total_frames": 3,
                "timeout_seconds": timeout_seconds,
                "deadline_monotonic": time.monotonic() + timeout_seconds,
                "created_at": time.time(),
                "updated_at": time.time(),
                "result": None,
                "future": None,
                "watchdog": None,
            }
            self._recognition_sessions[session_id] = record
            self._active_recognition_session = session_id
            self._prune_recognition_sessions_locked()
            record["future"] = self._recognition_pool.submit(self._run_recognition_session, session_id)
            # Allow one second after the capture budget for the worker to publish
            # a terminal result before the watchdog marks a still-running inference.
            watchdog = threading.Timer(timeout_seconds + 1.0, self._expire_recognition_session,
                                       args=(session_id,))
            watchdog.daemon = True
            record["watchdog"] = watchdog
            watchdog.start()
            return {key: record[key] for key in (
                "session_id", "state", "captured_frames", "total_frames", "timeout_seconds"
            )}

    def start_enrollment_session(self):
        """Start one camera-owned Smart Enrollment v2 session without database access."""
        with self._session_lock:
            recognition = self._recognition_sessions.get(self._active_recognition_session)
            if recognition and recognition.get("future") is not None and not recognition["future"].done():
                return None
            enrollment = self._enrollment_sessions.get(self._active_enrollment_session)
            if enrollment and time.time() - enrollment.get("created_at", 0) > ENROLLMENT_SESSION_TTL_SECONDS:
                enrollment["state"] = "EXPIRED"
                enrollment["cancel_event"].set()
                self._active_enrollment_session = None
                enrollment = None
            if enrollment and enrollment.get("state") in {"ENROLLING", "AWAITING_CONFIRMATION", "MANUAL"}:
                return None
            if not self.engine._initialized:
                raise RuntimeError("Face recognition model is unavailable.")

            session_id = uuid.uuid4().hex
            record = {
                "session_id": session_id,
                "state": "ENROLLING",
                "captured": 0,
                "total": len(GUIDED_POSES),
                "expected_pose": GUIDED_POSES[0],
                "detected_pose": "unknown",
                "stable_count": 0,
                "stable_frames_required": GUIDED_POSE_STABLE_FRAMES,
                "inference_fps": None,
                "observation_status": "STARTING",
                "feedback_code": "STARTING",
                "quality_code": "",
                "face_bbox": None,
                "frame_width": 0,
                "frame_height": 0,
                "face_count": 0,
                "detection_score": None,
                "frame_sequence": None,
                "frame_timestamp": None,
                "frame_age_ms": None,
                "reason": "Đang khởi động Smart Enrollment.",
                "created_at": time.time(),
                "updated_at": time.time(),
                "samples": [],
                "cancel_event": threading.Event(),
                "future": None,
                "tracker": None,
            }
            self._enrollment_sessions[session_id] = record
            self._active_enrollment_session = session_id
            record["future"] = self._enrollment_pool.submit(self._run_enrollment_session, session_id)
            return self._enrollment_session_summary(record)

    def start_manual_enrollment_lock(self):
        """Reserve the shared camera while the authenticated Admin drives manual capture."""
        with self._session_lock:
            recognition = self._recognition_sessions.get(self._active_recognition_session)
            if recognition and recognition.get("future") is not None and not recognition["future"].done():
                return None
            enrollment = self._enrollment_sessions.get(self._active_enrollment_session)
            if enrollment and time.time() - enrollment.get("created_at", 0) > ENROLLMENT_SESSION_TTL_SECONDS:
                enrollment["state"] = "EXPIRED"
                enrollment["cancel_event"].set()
                self._active_enrollment_session = None
                enrollment = None
            if enrollment and enrollment.get("state") in {"ENROLLING", "AWAITING_CONFIRMATION", "MANUAL"}:
                return None
            if not self.engine._initialized:
                raise RuntimeError("Face recognition model is unavailable.")
            session_id = uuid.uuid4().hex
            record = {
                "session_id": session_id,
                "state": "MANUAL",
                "captured": 0,
                "total": len(GUIDED_POSES),
                "expected_pose": GUIDED_POSES[0],
                "detected_pose": "unknown",
                "stable_count": 0,
                "stable_frames_required": GUIDED_POSE_STABLE_FRAMES,
                "inference_fps": None,
                "observation_status": "MANUAL",
                "feedback_code": "MANUAL",
                "quality_code": "",
                "face_bbox": None,
                "frame_width": 0,
                "frame_height": 0,
                "face_count": 0,
                "detection_score": None,
                "frame_sequence": None,
                "frame_timestamp": None,
                "frame_age_ms": None,
                "reason": "Đang đăng ký MANUAL. Camera được khóa cho phiên này.",
                "created_at": time.time(),
                "updated_at": time.time(),
                "samples": [],
                "cancel_event": threading.Event(),
                "future": None,
                "tracker": None,
            }
            self._enrollment_sessions[session_id] = record
            self._active_enrollment_session = session_id
            return self._enrollment_session_summary(record)

    def get_enrollment_session(self, session_id):
        if not isinstance(session_id, str) or not re.fullmatch(r"[a-f0-9]{32}", session_id):
            return None
        with self._session_lock:
            record = self._enrollment_sessions.get(session_id)
            if record is None:
                return None
            if (time.time() - float(record.get("created_at", 0)) > ENROLLMENT_SESSION_TTL_SECONDS
                    and record.get("state") in {"ENROLLING", "AWAITING_CONFIRMATION", "MANUAL"}):
                record["state"] = "EXPIRED"
                record["reason"] = "Phiên đăng ký đã hết hạn."
                record["samples"] = []
                record["cancel_event"].set()
                if self._active_enrollment_session == session_id:
                    self._active_enrollment_session = None
            return self._enrollment_session_summary(record)

    def get_enrollment_samples(self, session_id):
        with self._session_lock:
            record = self._enrollment_sessions.get(session_id)
            if not record or record.get("state") != "AWAITING_CONFIRMATION":
                return None
            return [dict(sample) for sample in record.get("samples", [])]

    def close_enrollment_session(self, session_id, cancelled=False):
        if not isinstance(session_id, str) or not re.fullmatch(r"[a-f0-9]{32}", session_id):
            return None
        with self._session_lock:
            record = self._enrollment_sessions.get(session_id)
            if record is None:
                return None
            if cancelled:
                record["cancel_event"].set()
                record["state"] = "CANCELLED"
                record["reason"] = "Phiên đăng ký đã được hủy."
                record["samples"] = []
            else:
                if record.get("state") not in {"AWAITING_CONFIRMATION", "MANUAL"}:
                    return None
                record["state"] = "COMPLETED"
                record["reason"] = "Đã lưu đủ năm mẫu khuôn mặt."
                record["samples"] = []
            record["updated_at"] = time.time()
            if self._active_enrollment_session == session_id:
                self._active_enrollment_session = None
            return self._enrollment_session_summary(record)

    @staticmethod
    def _enrollment_session_summary(record):
        return {
            "session_id": record["session_id"],
            "state": record["state"],
            "captured": int(record.get("captured", 0)),
            "total": int(record.get("total", len(GUIDED_POSES))),
            "expected_pose": record.get("expected_pose"),
            "detected_pose": record.get("detected_pose", "unknown"),
            "stable_count": int(record.get("stable_count", 0)),
            "stable_frames_required": int(record.get(
                "stable_frames_required", GUIDED_POSE_STABLE_FRAMES
            )),
            "inference_fps": record.get("inference_fps"),
            "observation_status": str(record.get("observation_status", "")),
            "feedback_code": str(record.get("feedback_code", "")),
            "quality_code": str(record.get("quality_code", "")),
            "face_bbox": record.get("face_bbox"),
            "frame_width": int(record.get("frame_width", 0)),
            "frame_height": int(record.get("frame_height", 0)),
            "face_count": int(record.get("face_count", 0)),
            "total_face_count": int(record.get("total_face_count", record.get("face_count", 0))),
            "primary_face_safe": record.get("primary_face_safe") is True,
            "primary_face_area_ratio": record.get("primary_face_area_ratio"),
            "primary_face_area_ratio_required": record.get("primary_face_area_ratio_required"),
            "detection_score": record.get("detection_score"),
            "frame_sequence": record.get("frame_sequence"),
            "frame_timestamp": record.get("frame_timestamp"),
            "frame_age_ms": record.get("frame_age_ms"),
            "reason": str(record.get("reason", "")),
            "updated_at": float(record.get("updated_at", 0)),
        }

    def _update_enrollment_session(self, session_id, **updates):
        with self._session_lock:
            record = self._enrollment_sessions.get(session_id)
            if record is None or record.get("cancel_event").is_set():
                return None
            record.update(updates)
            record["updated_at"] = time.time()
            return self._enrollment_session_summary(record)

    def _run_enrollment_session(self, session_id):
        tracker = GuidedPoseTracker()
        tracker.expected_pose = GUIDED_POSES[0]
        tracker.pose_started_at = time.monotonic()
        self._update_enrollment_session(session_id, tracker=tracker,
                                        reason="Đưa mặt vào giữa khung hình.")
        expected_pose = GUIDED_POSES[0]
        last_status_time = 0.0
        try:
            while True:
                with self._session_lock:
                    record = self._enrollment_sessions.get(session_id)
                    if record is None or record["cancel_event"].is_set():
                        return
                    if record["state"] != "ENROLLING":
                        return
                    if time.time() - record["created_at"] > ENROLLMENT_SESSION_TTL_SECONDS:
                        record["state"] = "EXPIRED"
                        record["reason"] = "Phiên đăng ký đã hết hạn."
                        record["samples"] = []
                        if self._active_enrollment_session == session_id:
                            self._active_enrollment_session = None
                        return

                try:
                    _raw, frame, sequence, captured_at = self.fetch_camera_snapshot()
                    received_at = time.monotonic()
                except Exception as exc:
                    now = time.monotonic()
                    missing = tracker.note_missing_frame(now)
                    if (tracker.pose_started_at is not None
                            and now - tracker.pose_started_at >= GUIDED_POSE_TIMEOUT_SECONDS):
                        missing = tracker.force_manual_fallback(
                            "Không nhận được frame camera mới trong thời gian cho phép."
                        )
                    if missing.get("status") == "AUTO_PAUSED":
                        self._update_enrollment_session(
                            session_id, state="MANUAL_FALLBACK", reason=missing.get("reason", str(exc)),
                            stable_count=0, inference_fps=missing.get("inference_fps"),
                            observation_status=missing.get("status", "STALE_FRAME"),
                            feedback_code="NO_FRAME", quality_code="",
                            face_bbox=None, frame_width=0, frame_height=0,
                            face_count=0, total_face_count=0, primary_face_safe=False,
                            detection_score=None,
                            frame_sequence=None, frame_timestamp=None, frame_age_ms=None,
                        )
                        with self._session_lock:
                            if self._active_enrollment_session == session_id:
                                self._active_enrollment_session = None
                        return
                    self._update_enrollment_session(
                        session_id, expected_pose=expected_pose,
                        reason="Không nhận được frame camera mới; đang chờ kết nối lại.",
                        stable_count=missing.get("stable_count", 0),
                        inference_fps=missing.get("inference_fps"),
                        observation_status=missing.get("status", "STALE_FRAME"),
                        feedback_code="NO_FRAME", quality_code="",
                        face_bbox=None, frame_width=0, frame_height=0,
                        face_count=0, total_face_count=0, primary_face_safe=False,
                        detection_score=None,
                        frame_sequence=None, frame_timestamp=None, frame_age_ms=None,
                    )
                    time.sleep(0.2)
                    continue

                outcome = validate_enrollment_pose_frame(self.engine, frame, expected_pose)
                # Establish an ArcFace identity anchor from the first genuinely
                # camera-facing frontal observation. Subsequent pose-only frames
                # stay light; the selected sharp sample is checked against this
                # reference immediately before it can be appended to the batch.
                if (outcome.get("status") == "OK"
                        and outcome.get("primary_face_safe") is True
                        and expected_pose == "frontal"
                        and tracker.primary_identity_reference is None
                        and tracker.identity_reference is None):
                    face = outcome.get("selected_primary_face")
                    pose_data = face.get("head_pose") if isinstance(face, dict) else None
                    try:
                        reliable = (isinstance(pose_data, dict)
                                    and bool(pose_data.get("positive_depth", False))
                                    and float(pose_data.get("reprojection_error_px", float("inf")))
                                    <= tracker.max_reprojection_px)
                    except (TypeError, ValueError):
                        reliable = False
                    frontal_ok = False
                    if reliable:
                        frontal_ok, _frontal_reason, _frontal_metrics = \
                            assess_frontal_camera_alignment(face, pose_data)
                    if frontal_ok:
                        probe = validate_enrollment_frame(
                            self.engine, frame, expected_pose, enforce_pose=False,
                            selected_primary_face=face,
                        )
                        if probe.get("status") == "OK":
                            try:
                                tracker.set_primary_identity_reference(probe["embedding"])
                            except (TypeError, ValueError) as exc:
                                outcome = {**outcome, "status": "RETRY",
                                           "code": "INVALID EMBEDDING", "reason": str(exc),
                                           "primary_face_safe": False}
                            else:
                                outcome = {
                                    **outcome,
                                    "face": probe.get("face", face),
                                    "faces": probe.get("faces", outcome.get("faces", [])),
                                    "face_count": probe.get("face_count", outcome.get("face_count")),
                                    "total_face_count": probe.get("total_face_count", outcome.get("total_face_count")),
                                    "selected_primary_face": probe.get("selected_primary_face", face),
                                    "primary_face_safe": True,
                                    "embedding": probe["embedding"],
                                    "quality": probe.get("quality", outcome.get("quality")),
                                }
                        else:
                            outcome = {**outcome, "status": "RETRY",
                                       "code": probe.get("code", "QUALITY CHECK"),
                                       "reason": probe.get("reason", "Không thể xác minh danh tính khuôn mặt chính."),
                                       "primary_face_safe": False}
                elif (outcome.get("status") == "OK"
                        and outcome.get("primary_face_safe") is True
                        and int(outcome.get("total_face_count", outcome.get("face_count", 0)) or 0) > 1
                        and (tracker.primary_identity_reference is not None
                             or tracker.identity_reference is not None)):
                    # A secondary person is present: verify the selected primary
                    # against the pinned ArcFace identity before this frame can
                    # contribute stability. Single-face tracking stays SCRFD-only.
                    selected_primary = outcome.get("selected_primary_face")
                    identity_check = validate_enrollment_frame(
                        self.engine, frame, expected_pose, enforce_pose=False,
                        selected_primary_face=selected_primary,
                    )
                    if identity_check.get("status") == "OK":
                        outcome = {
                            **outcome,
                            "face": identity_check.get("face", selected_primary),
                            "faces": identity_check.get("faces", outcome.get("faces", [])),
                            "face_count": identity_check.get("face_count", outcome.get("face_count")),
                            "total_face_count": identity_check.get("total_face_count", outcome.get("total_face_count")),
                            "selected_primary_face": identity_check.get("selected_primary_face", selected_primary),
                            "primary_face_safe": True,
                            "embedding": identity_check["embedding"],
                            "quality": identity_check.get("quality", outcome.get("quality")),
                        }
                    else:
                        outcome = {**outcome, "status": "RETRY",
                                   "code": identity_check.get("code", "SAME PERSON"),
                                   "reason": identity_check.get("reason", "Không xác minh được cùng người."),
                                   "primary_face_safe": False}
                now = time.monotonic()
                observed = tracker.observe(
                    expected_pose, outcome, frame, sequence, captured_at,
                    now=now, received_at=received_at,
                )
                status = observed.get("status")
                try:
                    frame_timestamp = float(captured_at)
                    if not np.isfinite(frame_timestamp):
                        frame_timestamp = None
                except (TypeError, ValueError):
                    frame_timestamp = None
                frame_age_ms = (max(0.0, (received_at - frame_timestamp) * 1000.0)
                                if frame_timestamp is not None else None)
                geometry = _enrollment_face_geometry(
                    frame,
                    ({**outcome, "primary_face_safe": False}
                     if observed.get("primary_face_safe") is False else outcome),
                    status,
                    frame_sequence=sequence, frame_timestamp=frame_timestamp,
                    frame_age_ms=frame_age_ms,
                )
                diagnostics = outcome.get("diagnostics") if isinstance(outcome, dict) else None
                quality_code = str((diagnostics or {}).get("quality_code") or "")
                feedback_code = str(observed.get("rejected_code") or status or "")
                detected_pose = str(
                    observed.get("detected_pose") or outcome.get("detected_pose") or "unknown"
                )
                if status == "AUTO_PAUSED":
                    self._update_enrollment_session(
                        session_id, state="MANUAL_FALLBACK",
                        reason=observed.get("reason", "AUTO cần tiếp tục ở chế độ MANUAL."),
                        stable_count=0, inference_fps=observed.get("inference_fps"),
                        detected_pose=detected_pose,
                        observation_status=status, feedback_code=feedback_code,
                        quality_code=quality_code, **geometry,
                    )
                    with self._session_lock:
                        if self._active_enrollment_session == session_id:
                            self._active_enrollment_session = None
                    return

                if status == "CAPTURE_READY":
                    candidate = observed.get("candidate") or {}
                    selected_frame = candidate.get("frame")
                    selected = validate_enrollment_frame(
                        self.engine, selected_frame, expected_pose, enforce_pose=False,
                        selected_primary_face=candidate.get("selected_primary_face"),
                    )
                    checked = tracker.validate_selected_candidate(candidate, selected, expected_pose)
                    if checked.get("status") != "OK":
                        tracker.capture_result(False, now=now)
                        self._update_enrollment_session(
                            session_id, expected_pose=expected_pose,
                            reason=checked.get("reason", "Mẫu được chọn chưa đạt kiểm tra cuối."),
                            stable_count=0, inference_fps=observed.get("inference_fps"),
                            observation_status="CAPTURE_REJECTED",
                            feedback_code=str(checked.get("code") or "QUALITY CHECK"),
                            quality_code=quality_code,
                            detected_pose=detected_pose, **geometry,
                        )
                        continue

                    embedding = np.asarray(checked["embedding"], dtype=np.float32).reshape(-1)
                    norm = float(np.linalg.norm(embedding))
                    if (embedding.shape != (EMBEDDING_DIMENSIONS,) or not np.isfinite(embedding).all()
                            or not np.isfinite(norm) or norm <= 1e-12):
                        tracker.capture_result(False, now=now)
                        self._update_enrollment_session(
                            session_id, reason="Embedding ArcFace không hợp lệ; đang thu lại pose.",
                            stable_count=0, observation_status="CAPTURE_REJECTED",
                            feedback_code="INVALID EMBEDDING", quality_code=quality_code,
                            detected_pose=detected_pose, **geometry,
                        )
                        continue
                    embedding = (embedding / norm).astype("<f4", copy=False)
                    ok, encoded_image = cv2.imencode(".jpg", selected_frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
                    if not ok or encoded_image is None:
                        tracker.capture_result(False, now=now)
                        self._update_enrollment_session(
                            session_id, reason="Không thể mã hóa ảnh mẫu; đang thu lại pose.",
                            stable_count=0, observation_status="CAPTURE_REJECTED",
                            feedback_code="IMAGE ENCODE ERROR", quality_code=quality_code,
                            detected_pose=detected_pose, **geometry,
                        )
                        continue

                    sample = {
                        "pose": expected_pose,
                        "vector": base64.b64encode(embedding.tobytes()).decode("ascii"),
                        "image_jpeg": base64.b64encode(encoded_image.tobytes()).decode("ascii"),
                        "image_sha256": hashlib.sha256(encoded_image.tobytes()).hexdigest(),
                    }
                    with self._session_lock:
                        record = self._enrollment_sessions.get(session_id)
                        if record is None or record["cancel_event"].is_set():
                            return
                        record["samples"].append(sample)
                        captured = len(record["samples"])
                    next_pose = GUIDED_POSES[captured] if captured < len(GUIDED_POSES) else None
                    tracker.capture_result(True, next_pose=next_pose, now=now, embedding=embedding)
                    expected_pose = next_pose
                    state = "AWAITING_CONFIRMATION" if next_pose is None else "ENROLLING"
                    self._update_enrollment_session(
                        session_id, state=state, captured=captured,
                        expected_pose=next_pose,
                        stable_count=0,
                        inference_fps=observed.get("inference_fps"),
                        detected_pose=expected_pose or detected_pose,
                        observation_status="CAPTURED",
                        feedback_code="CAPTURED",
                        quality_code="PASS",
                        **geometry,
                        reason=("Đã thu đủ 5 hướng. Chờ Admin xác nhận lưu."
                                if next_pose is None else f"Đã thu {captured}/5. {POSE_LABELS[next_pose]}"),
                    )
                    if next_pose is None:
                        return
                    continue

                reason = observed.get("reason") or outcome.get("reason") or "Đang phân tích hướng khuôn mặt."
                current_time = time.monotonic()
                if current_time - last_status_time >= 0.2:
                    self._update_enrollment_session(
                        session_id, expected_pose=expected_pose,
                        detected_pose=observed.get("detected_pose", "unknown"),
                        stable_count=observed.get("stable_count", 0),
                        inference_fps=observed.get("inference_fps"),
                        observation_status=status,
                        feedback_code=feedback_code,
                        quality_code=quality_code,
                        **geometry,
                        reason=str(reason),
                    )
                    last_status_time = current_time
        except Exception:
            logging.getLogger("ai1.enrollment").exception("Smart Enrollment worker failed.")
            with self._session_lock:
                record = self._enrollment_sessions.get(session_id)
                if record and not record["cancel_event"].is_set():
                    record["state"] = "FAILED"
                    record["reason"] = "AI1 gặp lỗi trong khi đăng ký. Dữ liệu cũ vẫn được giữ nguyên."
                    record["samples"] = []
                    record["observation_status"] = "FAILED"
                    record["feedback_code"] = "FAILED"
                    record["quality_code"] = ""
                    record["face_bbox"] = None
                    record["frame_width"] = 0
                    record["frame_height"] = 0
                    record["face_count"] = 0
                    record["detection_score"] = None
                    record["frame_sequence"] = None
                    record["frame_timestamp"] = None
                    record["frame_age_ms"] = None
                    record["updated_at"] = time.time()
                if self._active_enrollment_session == session_id:
                    self._active_enrollment_session = None

    def get_recognition_session(self, session_id):
        if not isinstance(session_id, str) or not re.fullmatch(r"[a-f0-9]{32}", session_id):
            return None
        with self._session_lock:
            record = self._recognition_sessions.get(session_id)
            if record is None:
                return None
            return {key: value for key, value in record.items()
                    if key not in {"future", "watchdog", "deadline_monotonic"}}

    def _prune_recognition_sessions_locked(self):
        cutoff = time.time() - 300
        for session_id, record in list(self._recognition_sessions.items()):
            future = record.get("future")
            if record.get("updated_at", 0) < cutoff and (future is None or future.done()):
                self._recognition_sessions.pop(session_id, None)

    def _update_recognition_session(self, session_id, **updates):
        with self._session_lock:
            record = self._recognition_sessions.get(session_id)
            if record is None or record["state"] in {"COMPLETED", "ABORTED"}:
                return
            record.update(updates)
            record["updated_at"] = time.time()
            if record["state"] in {"COMPLETED", "ABORTED"} and record.get("watchdog") is not None:
                record["watchdog"].cancel()

    def _recognition_session_running(self, session_id):
        with self._session_lock:
            record = self._recognition_sessions.get(session_id)
            return record is not None and record["state"] not in {"COMPLETED", "ABORTED"}

    def _expire_recognition_session(self, session_id):
        with self._session_lock:
            record = self._recognition_sessions.get(session_id)
            if record is None or record["state"] in {"COMPLETED", "ABORTED"}:
                return
            result = {
                "recognized": False,
                "reason": "RETRY",
                "retry_reason": "TIMEOUT",
                "latency_ms": (time.time() - record["created_at"]) * 1000.0,
                "captured_frames": record["captured_frames"],
            }
            record.update(state="ABORTED", result=result, updated_at=time.time())
        self._log_recognition_session(session_id, result, result["captured_frames"], "RETRY", "TIMEOUT")

    def _run_recognition_session(self, session_id):
        started = time.perf_counter()
        captured = []
        last_sequence = -1
        last_capture_time = 0.0
        with self._session_lock:
            session_record = self._recognition_sessions.get(session_id)
            deadline = (float(session_record["deadline_monotonic"])
                        if session_record is not None else time.monotonic())
        failure = None
        try:
            if not self.engine._initialized:
                raise RuntimeError("MODEL_UNAVAILABLE")
            with self._lock:
                if not self._gallery_loaded:
                    raise RuntimeError("GALLERY_UNAVAILABLE")
                gallery = self._gallery

            for index in range(3):
                if not self._recognition_session_running(session_id):
                    raise RuntimeError("SESSION_ABORTED")
                if index and time.monotonic() - last_capture_time < 0.25:
                    time.sleep(max(0.0, 0.25 - (time.monotonic() - last_capture_time)))
                packet = None
                while time.monotonic() < deadline:
                    try:
                        raw, frame, sequence, captured_at = self.fetch_camera_snapshot()
                        age = time.monotonic() - captured_at
                        if (sequence > last_sequence and age <= 0.75 and age >= -0.1):
                            packet = raw, frame, sequence, captured_at
                            break
                    except Exception as exc:
                        failure = str(exc)
                    time.sleep(0.04)
                if packet is None:
                    raise RuntimeError("STALE_FRAME" if failure is None else "CAMERA_TIMEOUT")

                raw, frame, last_sequence, last_capture_time = packet
                faces = self.engine.detect_embeddings(frame)
                if not self._recognition_session_running(session_id):
                    raise RuntimeError("SESSION_ABORTED")
                if len(faces) != 1:
                    raise RuntimeError("NO_FACE" if len(faces) == 0 else "MULTIPLE_FACES")
                face = faces[0]
                embedding = normalize_embedding(face.get("embedding"))
                if embedding.shape != (EMBEDDING_DIMENSIONS,):
                    raise RuntimeError("INVALID_EMBEDDING")
                sharpness = _face_sharpness(frame, face.get("bbox"))
                if not np.isfinite(sharpness) or sharpness < 20.0:
                    raise RuntimeError("BLUR")
                captured.append({
                    "raw": raw,
                    "frame": frame.copy(),
                    "embedding": embedding,
                    "bbox": [float(value) for value in face["bbox"]],
                    "sharpness": sharpness,
                })
                self._update_recognition_session(
                    session_id, state="CAPTURING", captured_frames=len(captured),
                    progress=f"{len(captured)}/3",
                )

            self._update_recognition_session(session_id, state="PROCESSING")
            consistency_threshold = _temporal_consistency_threshold()
            similarities = []
            for left in range(3):
                for right in range(left + 1, 3):
                    similarities.append(cosine_similarity(captured[left]["embedding"], captured[right]["embedding"]))
            if not similarities or min(similarities) < consistency_threshold:
                raise RuntimeError("INCONSISTENT_FACES")

            best_index = max(range(3), key=lambda item: captured[item]["sharpness"])
            best = captured[best_index]
            if not self._recognition_session_running(session_id):
                raise RuntimeError("SESSION_ABORTED")
            match_result = identify_embedding(best["embedding"], gallery, _recognition_threshold())
            recognized = bool(match_result["match"])
            result = {
                "recognized": recognized,
                "reason": None if recognized else "UNKNOWN",
                "ma_nv": int(match_result["MaNV"]) if recognized else None,
                "ho_ten": match_result["HoTen"] if recognized else None,
                "score": match_result["similarity"],
                "threshold": match_result["threshold"],
                "temporal_consistency_min": min(similarities),
                "temporal_consistency_threshold": consistency_threshold,
                "best_frame_index": best_index + 1,
                "best_sharpness": best["sharpness"],
                "bbox": best["bbox"],
                "frame_width": int(best["frame"].shape[1]),
                "frame_height": int(best["frame"].shape[0]),
                "best_frame_jpeg": base64.b64encode(best["raw"]).decode("ascii"),
                "latency_ms": (time.perf_counter() - started) * 1000.0,
            }
            if not self._recognition_session_running(session_id):
                raise RuntimeError("SESSION_ABORTED")
            try:
                self._save_recognition_evidence(session_id, result, captured, best_index)
            except Exception:
                logging.getLogger("ai1.recognition").exception("Optional recognition evidence write failed.")
            self._log_recognition_session(session_id, result, len(captured), "MATCH" if recognized else "UNKNOWN", None)
            self._update_recognition_session(session_id, state="COMPLETED", result=result,
                                             captured_frames=len(captured), progress="3/3")
        except Exception as exc:
            reason = str(exc) or "INFERENCE_ERROR"
            with self._session_lock:
                record = self._recognition_sessions.get(session_id)
                already_terminal = record is None or record["state"] in {"COMPLETED", "ABORTED"}
            if already_terminal:
                return
            result = {
                "recognized": False,
                "reason": "RETRY",
                "retry_reason": reason,
                "latency_ms": (time.perf_counter() - started) * 1000.0,
                "captured_frames": len(captured),
            }
            self._log_recognition_session(session_id, result, len(captured), "RETRY", reason)
            self._update_recognition_session(session_id, state="ABORTED", result=result,
                                             captured_frames=len(captured), progress=f"{len(captured)}/3")

    def _save_recognition_evidence(self, session_id, result, captured, best_index):
        directory = os.getenv("AI1_EVIDENCE_DIR", "").strip()
        if not directory or len(captured) != 3:
            return
        identity = f"NV{result['ma_nv']}" if result.get("ma_nv") is not None else "Unknown"
        names = (("start", captured[0]["raw"]), ("best", captured[best_index]["raw"]),
                 ("end", captured[-1]["raw"]))
        root = Path(directory).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        for label, content in names:
            target = root / f"{identity}_{session_id}_{label}.jpg"
            descriptor, temporary = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=root)
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, target)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)

    @staticmethod
    def _log_recognition_session(session_id, result, captured_frames, outcome, reason):
        logging.getLogger("ai1.recognition").info(json.dumps({
            "session_id": session_id,
            "timestamp": time.time(),
            "camera_source": os.getenv("AI1_CAMERA_SOURCE", "webcam"),
            "captured_frames": captured_frames,
            "best_sharpness": result.get("best_sharpness"),
            "score": result.get("score"),
            "threshold": result.get("threshold"),
            "MaNV": result.get("ma_nv"),
            "outcome": outcome,
            "latency_ms": result.get("latency_ms"),
            "reason": reason or result.get("retry_reason"),
        }, ensure_ascii=False, separators=(",", ":")))

    def inspect_enrollment_frame(self, frame, expected_pose):
        """Validate face count and head pose for one guided-enrollment step."""
        if not self.engine._initialized:
            raise RuntimeError("Face recognition model is unavailable.")
        faces = self.engine.detect_embeddings(frame)
        if len(faces) > 1:
            return {
                "success": True,
                "pose_ok": False,
                "current_pose": "multiple_faces",
                "expected_pose": expected_pose,
                "instruction": "Chỉ để một người trong khung hình.",
                "yaw": None,
                "pitch": None,
            }
        pose = _pose_result(faces[0] if faces else None, expected_pose)
        if faces:
            quality = face_engine.assess_capture_quality(frame, faces[0])
            pose.update(
                quality_ok=bool(quality["ready"]),
                quality_instruction=quality["instruction"],
                detection_score=float(faces[0].get("detection_score", 0.0)),
                sharpness=quality.get("sharpness"),
                brightness=quality.get("brightness"),
            )
            if not quality["ready"]:
                pose.update(pose_ok=False, instruction=quality["instruction"])
        return pose

    def capture_enrollment_sample(self, frame, jpeg, expected_pose, reference=None):
        """Return a validated pose's embedding and its exact JPEG frame as one sample."""
        if not self.engine._initialized:
            raise RuntimeError("Face recognition model is unavailable.")
        faces = self.engine.detect_embeddings(frame)
        if len(faces) > 1:
            result = {
                "success": False,
                "pose_ok": False,
                "current_pose": "multiple_faces",
                "expected_pose": expected_pose,
                "instruction": "Chỉ để một người trong khung hình.",
                "yaw": None,
                "pitch": None,
            }
            return result

        pose = _pose_result(faces[0] if faces else None, expected_pose)
        if not pose["pose_ok"]:
            return {**pose, "success": False}

        quality = face_engine.assess_capture_quality(frame, faces[0])
        if not quality["ready"]:
            return {**pose, "success": False, "pose_ok": False, "instruction": quality["instruction"]}

        vector = faces[0].get("vector_bytes")
        if not isinstance(vector, bytes) or len(vector) != EMBEDDING_BYTES:
            raise RuntimeError("Face model returned an invalid 512D embedding.")
        probe = decode_stored_embedding(vector, EMBEDDING_DIMENSIONS)
        if expected_pose != "frontal" and reference is None:
            raise ValueError("Cần mẫu nhìn thẳng để xác minh cùng một người.")
        if reference is not None and cosine_similarity(probe, reference) < ENROLLMENT_IDENTITY_THRESHOLD:
            return {**pose, "success": False, "pose_ok": False,
                    "instruction": "Khuôn mặt không khớp mẫu nhìn thẳng đầu tiên."}

        return {
            **pose,
            "success": True,
            "so_chieu": EMBEDDING_DIMENSIONS,
            "vector": base64.b64encode(vector).decode("ascii"),
            "image_jpeg": base64.b64encode(jpeg).decode("ascii"),
            "image_sha256": hashlib.sha256(jpeg).hexdigest(),
        }


runtime = AIRuntime()
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 7 * 1024 * 1024


def _classify_head_pose(yaw, pitch):
    return face_engine.classify_head_pose(yaw, pitch)


def _decode_enrollment_image(encoded_image):
    if not isinstance(encoded_image, str) or not encoded_image:
        raise ValueError("Thiếu ảnh enrollment.")
    try:
        raw = base64.b64decode(encoded_image, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Ảnh enrollment không hợp lệ.") from exc
    if not raw or len(raw) > MAX_ENROLLMENT_IMAGE_BYTES:
        raise ValueError("Ảnh enrollment vượt giới hạn 5 MB.")
    if not raw.startswith(b"\xff\xd8") and not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Chỉ chấp nhận ảnh JPEG hoặc PNG.")

    frame = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError("Không giải mã được ảnh enrollment.")
    if frame.shape[0] * frame.shape[1] > 16_000_000:
        raise ValueError("Kích thước ảnh enrollment quá lớn.")
    if raw.startswith(b"\xff\xd8"):
        jpeg = raw
    else:
        encoded, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
        if not encoded:
            raise ValueError("Không thể chuẩn hóa ảnh thành JPEG.")
        jpeg = buffer.tobytes()
    return frame, jpeg


def _pose_result(face, expected_pose):
    if face is None:
        return {
            "success": True,
            "pose_ok": False,
            "current_pose": "no_face",
            "expected_pose": expected_pose,
            "instruction": "Đưa khuôn mặt vào giữa khung hình.",
            "yaw": None,
            "pitch": None,
        }

    pose = face.get("head_pose")
    if not pose:
        return {
            "success": True,
            "pose_ok": False,
            "current_pose": "unknown",
            "expected_pose": expected_pose,
            "instruction": "Không ước lượng được hướng đầu; nhìn rõ camera.",
            "yaw": None,
            "pitch": None,
        }

    yaw, pitch = float(pose["yaw"]), float(pose["pitch"])
    current_pose = _classify_head_pose(yaw, pitch)
    pose_ok = current_pose == expected_pose
    if pose_ok:
        instruction = "Đúng hướng, giữ yên."
    elif expected_pose == "frontal":
        instruction = "Nhìn thẳng camera và giữ đầu cân bằng."
    elif current_pose == "frontal":
        instruction = f"{POSE_LABELS[expected_pose]} thêm."
    else:
        instruction = f"Đang hướng {POSE_LABELS.get(current_pose, 'chưa đúng')}; {POSE_LABELS[expected_pose].lower()} thêm."

    return {
        "success": True,
        "pose_ok": pose_ok,
        "current_pose": current_pose,
        "expected_pose": expected_pose,
        "instruction": instruction,
        "yaw": yaw,
        "pitch": pitch,
    }


def _read_enrollment_request():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ValueError("Body JSON không hợp lệ.")
    expected_pose = payload.get("expected_pose")
    if expected_pose not in ENROLLMENT_POSES:
        raise ValueError("Pose enrollment không hợp lệ.")
    frame, jpeg = _decode_enrollment_image(payload.get("image"))
    encoded_reference = payload.get("reference_vector")
    if encoded_reference is None:
        reference = None
    else:
        if not isinstance(encoded_reference, str):
            raise ValueError("Mẫu tham chiếu enrollment không hợp lệ.")
        try:
            raw = base64.b64decode(encoded_reference, validate=True)
            reference = decode_stored_embedding(raw, EMBEDDING_DIMENSIONS)
        except (binascii.Error, TypeError, ValueError) as exc:
            raise ValueError("Mẫu tham chiếu enrollment không hợp lệ.") from exc
    return frame, jpeg, expected_pose, reference


@app.before_request
def allow_loopback_only():
    if request.remote_addr not in {"127.0.0.1", "::1"}:
        return jsonify({"success": False, "message": "Local requests only."}), 403


@app.get("/health")
def health():
    return jsonify(runtime.health())


@app.post("/api/ai/gallery/refresh")
def refresh_gallery():
    try:
        result = runtime.refresh_gallery()
        return jsonify({"success": True, **result})
    except Exception:
        with runtime._lock:
            runtime._gallery_error = "Could not load gallery from PHP."
        return jsonify({"success": False, "message": "Không thể tải gallery từ PHP."}), 503


@app.get("/api/ai/frame")
def camera_frame():
    try:
        raw, _ = runtime.fetch_camera_frame()
    except Exception:
        return jsonify({"success": False, "message": "Camera không khả dụng."}), 503
    return Response(raw, mimetype="image/jpeg", headers={"Cache-Control": "no-store"})


@app.post("/api/ai/recognize")
def recognize():
    return jsonify({
        "success": False,
        "match": False,
        "reason": "THREE_FRESH_SNAPSHOTS_REQUIRED",
        "message": "Nhận diện yêu cầu session ba snapshot mới.",
    }), 409


@app.post("/api/ai/recognize-image")
def recognize_image():
    return jsonify({
        "success": False,
        "reason": "THREE_FRESH_SNAPSHOTS_REQUIRED",
        "message": "Ảnh tĩnh không đủ để nhận diện; dùng session ba snapshot mới.",
    }), 409


@app.post("/api/ai/recognition-sessions")
def start_recognition_session():
    try:
        session = runtime.start_recognition_session()
    except GalleryUnavailableError:
        return jsonify({
            "success": False,
            "code": "GALLERY_UNAVAILABLE",
            "message": "Gallery khuôn mặt chưa đồng bộ. Nhận diện đang tạm dừng; hãy thử lại sau.",
        }), 503
    if session is None:
        return jsonify({"success": False, "busy": True, "message": "Một phiên nhận diện đang chạy."}), 409
    return jsonify({"success": True, **session}), 202


@app.get("/api/ai/recognition-sessions/<session_id>")
def recognition_session_status(session_id):
    session = runtime.get_recognition_session(session_id)
    if session is None:
        return jsonify({"success": False, "message": "Không tìm thấy phiên nhận diện."}), 404
    return jsonify({"success": True, **session})


@app.post("/api/ai/enrollment-sessions")
def start_enrollment_session():
    try:
        session = runtime.start_enrollment_session()
    except Exception:
        logging.getLogger("ai1.enrollment").exception("Smart Enrollment start failed.")
        return jsonify({"success": False, "message": "AI1 chưa sẵn sàng để đăng ký."}), 503
    if session is None:
        return jsonify({
            "success": False,
            "busy": True,
            "message": "Camera đang được sử dụng bởi một phiên nhận diện hoặc đăng ký khác.",
        }), 409
    return jsonify({"success": True, **session}), 202


@app.post("/api/ai/enrollment-manual-lock")
def start_manual_enrollment_lock():
    try:
        session = runtime.start_manual_enrollment_lock()
    except Exception:
        logging.getLogger("ai1.enrollment").exception("Manual Enrollment lock failed.")
        return jsonify({"success": False, "message": "AI1 chưa sẵn sàng để đăng ký."}), 503
    if session is None:
        return jsonify({"success": False, "busy": True,
                        "message": "Camera đang được sử dụng bởi một phiên nhận diện hoặc đăng ký khác."}), 409
    return jsonify({"success": True, **session}), 202


@app.get("/api/ai/enrollment-sessions/<session_id>")
def enrollment_session_status(session_id):
    session = runtime.get_enrollment_session(session_id)
    if session is None:
        return jsonify({"success": False, "message": "Không tìm thấy phiên đăng ký."}), 404
    return jsonify({"success": True, **session})


@app.get("/api/ai/enrollment-sessions/<session_id>/samples")
def enrollment_session_samples(session_id):
    samples = runtime.get_enrollment_samples(session_id)
    if samples is None:
        return jsonify({"success": False, "message": "Phiên chưa sẵn sàng để xác nhận lưu."}), 409
    return jsonify({"success": True, "samples": samples})


@app.post("/api/ai/enrollment-sessions/<session_id>/cancel")
def cancel_enrollment_session(session_id):
    session = runtime.close_enrollment_session(session_id, cancelled=True)
    if session is None:
        return jsonify({"success": False, "message": "Không tìm thấy phiên đăng ký."}), 404
    return jsonify({"success": True, **session})


@app.post("/api/ai/enrollment-sessions/<session_id>/close")
def close_enrollment_session(session_id):
    session = runtime.close_enrollment_session(session_id, cancelled=False)
    if session is None:
        return jsonify({"success": False, "message": "Phiên không ở trạng thái chờ xác nhận."}), 409
    return jsonify({"success": True, **session})


@app.post("/api/ai/enrollment/inspect")
def inspect_enrollment():
    try:
        frame, _, expected_pose, _ = _read_enrollment_request()
        return jsonify(runtime.inspect_enrollment_frame(frame, expected_pose))
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except Exception:
        return jsonify({"success": False, "message": "AI service hoặc model chưa sẵn sàng."}), 503


@app.post("/api/ai/enrollment/capture")
def capture_enrollment():
    try:
        frame, jpeg, expected_pose, reference = _read_enrollment_request()
        result = runtime.capture_enrollment_sample(frame, jpeg, expected_pose, reference)
        return jsonify(result), 200 if result["success"] else 409
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except Exception:
        return jsonify({"success": False, "message": "AI service hoặc model chưa sẵn sàng."}), 503


def main():
    runtime.initialize()
    app.run(host="127.0.0.1", port=5001, debug=False, use_reloader=False, threaded=True)


if __name__ == "__main__":
    main()
