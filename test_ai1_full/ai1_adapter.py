"""Thin adapter over the production buffalo_l engine and face matcher."""

import time

import numpy as np

import face_engine
import face_matching
from .config import EMBEDDING_DIMENSIONS, RECOGNITION_THRESHOLD
from .recognition import identify_embedding as _identify_embedding


def initialize_model():
    """Initialize the production singleton; this does not access the database."""
    face_engine.face_engine.initialize()
    return face_engine.face_engine


def _result(status, predicted_id="UNKNOWN", score=0.0, reason="", latency_ms=0.0):
    return {
        "status": status,
        "predicted_id": predicted_id,
        "score": float(score),
        "reason": str(reason),
        "latency_ms": float(latency_ms),
    }


def extract_single_face_embedding(frame):
    """Return one normalized 512D production embedding, or a RETRY result."""
    started = time.perf_counter()
    try:
        faces = face_engine.face_engine.detect_embeddings(frame)
    except Exception as exc:
        return {"status": "RETRY", "embedding": None, "reason": str(exc),
                "latency_ms": (time.perf_counter() - started) * 1000.0, "face": None}
    latency = (time.perf_counter() - started) * 1000.0
    if len(faces) == 0:
        return {"status": "RETRY", "embedding": None, "reason": "Không phát hiện được khuôn mặt hợp lệ.",
                "latency_ms": latency, "face": None}
    if len(faces) != 1:
        return {"status": "RETRY", "embedding": None, "reason": "Cần đúng một khuôn mặt trong ảnh.",
                "latency_ms": latency, "face": None}
    face = faces[0]
    try:
        score = float(face.get("detection_score"))
        if not np.isfinite(score) or score < face_engine.DETECTION_MIN_SCORE:
            raise ValueError("Điểm phát hiện khuôn mặt không hợp lệ.")
        embedding = face_matching.normalize_embedding(face.get("embedding"), EMBEDDING_DIMENSIONS)
    except (TypeError, ValueError) as exc:
        return {"status": "RETRY", "embedding": None, "reason": f"Embedding không hợp lệ: {exc}",
                "latency_ms": latency, "face": face}
    return {"status": "OK", "embedding": embedding, "reason": "Embedding ArcFace hợp lệ.",
            "latency_ms": latency, "face": face}


def identify_embedding(embedding, gallery, threshold=None):
    started = time.perf_counter()
    try:
        result = _identify_embedding(embedding, gallery, threshold)
    except (TypeError, ValueError) as exc:
        return _result("RETRY", reason=f"Embedding hoặc gallery không hợp lệ: {exc}",
                       latency_ms=(time.perf_counter() - started) * 1000.0)
    return _result(result["status"], result["predicted_id"], result["score"], result["reason"],
                   (time.perf_counter() - started) * 1000.0)


def identify_frame(frame, gallery, threshold=None):
    """Detect, embed, and recognize a frame using the production MAX matcher."""
    started = time.perf_counter()
    extracted = extract_single_face_embedding(frame)
    if extracted["status"] != "OK":
        return _result("RETRY", reason=extracted["reason"],
                       latency_ms=(time.perf_counter() - started) * 1000.0)
    result = identify_embedding(extracted["embedding"], gallery, threshold)
    result["latency_ms"] = (time.perf_counter() - started) * 1000.0
    return result


def production_pose_label(face):
    """Use the current AI1 pose classifier with face_engine's production solvePnP result."""
    pose = face.get("head_pose") if isinstance(face, dict) else None
    if not pose:
        return "unknown"
    try:
        from ai_service import _classify_head_pose

        return _classify_head_pose(float(pose["yaw"]), float(pose["pitch"]))
    except (ImportError, KeyError, TypeError, ValueError):
        # Exact classifier boundaries from current AI1 for venvs without Flask.
        yaw, pitch = float(pose.get("yaw", float("nan"))), float(pose.get("pitch", float("nan")))
        if abs(yaw) <= 12 and abs(pitch) <= 12:
            return "frontal"
        if 15 <= yaw <= 40 and abs(pitch) <= 18:
            return "left"
        if -40 <= yaw <= -15 and abs(pitch) <= 18:
            return "right"
        if 12 <= pitch <= 35 and abs(yaw) <= 15:
            return "up"
        if -35 <= pitch <= -12 and abs(yaw) <= 15:
            return "down"
        return "between"
