"""Thin adapter around production face_engine and pose/matching utilities."""

import time

import numpy as np

import face_engine as production_face_engine
import face_matching

from .config import EMBEDDING_DIMENSIONS


def initialize_ai1():
    """Initialize production buffalo_l once; it has no DB or attendance calls."""
    production_face_engine.face_engine.initialize()
    return production_face_engine.face_engine


def classify_pose(face):
    pose = face.get("head_pose") if isinstance(face, dict) else None
    if not pose:
        return "unknown"
    try:
        import ai_service

        return ai_service._classify_head_pose(float(pose["yaw"]), float(pose["pitch"]))
    except (ImportError, AttributeError):
        yaw, pitch = float(pose["yaw"]), float(pose["pitch"])
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


def extract_single_face_embedding(engine, frame):
    """Extract one validated, L2-normalized 512D production ArcFace vector."""
    started = time.perf_counter()
    try:
        faces = engine.detect_embeddings(frame)
    except Exception as exc:
        return {"status": "RETRY", "code": "AI ERROR", "reason": str(exc),
                "embedding": None, "face": None,
                "latency_ms": (time.perf_counter() - started) * 1000.0}
    latency = (time.perf_counter() - started) * 1000.0
    if len(faces) == 0:
        return {"status": "RETRY", "code": "NO FACE", "reason": "NO FACE",
                "embedding": None, "face": None, "latency_ms": latency}
    if len(faces) != 1:
        return {"status": "RETRY", "code": "MULTIPLE FACES", "reason": "MULTIPLE FACES",
                "embedding": None, "face": None, "latency_ms": latency}
    face = faces[0]
    try:
        detection_score = float(face.get("detection_score"))
        if not np.isfinite(detection_score) or detection_score < production_face_engine.DETECTION_MIN_SCORE:
            raise ValueError("Detection confidence is invalid.")
        embedding = face_matching.normalize_embedding(face.get("embedding"), EMBEDDING_DIMENSIONS)
    except (TypeError, ValueError) as exc:
        return {"status": "RETRY", "code": "INVALID EMBEDDING", "reason": str(exc),
                "embedding": None, "face": face, "latency_ms": latency}
    return {"status": "OK", "code": "OK", "reason": "Valid ArcFace embedding.",
            "embedding": embedding, "face": face, "latency_ms": latency}


def validate_enrollment_frame(engine, frame, expected_pose):
    """Apply production detection, quality, pose, and embedding checks to one pose."""
    extracted = extract_single_face_embedding(engine, frame)
    if extracted["status"] != "OK":
        return extracted
    face = extracted["face"]
    quality = production_face_engine.assess_capture_quality(frame, face)
    if not quality.get("ready"):
        message = str(quality.get("instruction", "Enrollment image quality failed."))
        lowered = message.lower()
        if "quá xa" in lowered:
            code = "FACE TOO SMALL"
        elif "quá gần" in lowered:
            code = "FACE TOO LARGE"
        elif "nét" in lowered or "chưa rõ" in lowered:
            code = "TOO BLURRY"
        elif "ánh sáng" in lowered:
            code = "BAD LIGHTING"
        elif "giữa" in lowered or "khung hình" in lowered:
            code = "FACE POSITION"
        else:
            code = "QUALITY CHECK"
        return {**extracted, "status": "RETRY", "code": code, "reason": message,
                "quality": quality, "detected_pose": classify_pose(face)}
    detected_pose = classify_pose(face)
    if detected_pose != expected_pose:
        return {**extracted, "status": "RETRY", "code": "WRONG POSE",
                "reason": f"WRONG POSE: detected {detected_pose}, expected {expected_pose}.",
                "quality": quality, "detected_pose": detected_pose}
    return {**extracted, "reason": "Enrollment frame valid.", "quality": quality,
            "detected_pose": detected_pose}
