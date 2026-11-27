"""Configuration isolated to the AI1 full-test tools."""

import os


def _production_threshold():
    """Read the same threshold helper used by AI1, without initializing its model."""
    try:
        import ai_service

        return float(ai_service._recognition_threshold())
    except ImportError:
        value = float(os.getenv("FACE_RECOGNITION_THRESHOLD", "0.45"))
        if not -1.0 <= value <= 1.0:
            raise ValueError("FACE_RECOGNITION_THRESHOLD must be between -1 and 1.")
        return value


RECOGNITION_THRESHOLD = _production_threshold()
FRAME_INTERVAL_MS = 300
CONSISTENCY_THRESHOLD = 0.35
CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480
EMBEDDING_DIMENSIONS = 512
MODEL_NAME = "buffalo_l"
ENROLLMENT_POSES = ("frontal", "left", "right", "up", "down")
