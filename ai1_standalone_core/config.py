"""Configuration for the standalone app; no production settings are modified."""

from pathlib import Path

import face_matching


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = PROJECT_ROOT / "ai1_standalone_data"
IMAGES_ROOT = DATA_ROOT / "images"
EMPLOYEES_PATH = DATA_ROOT / "employees.json"
EMBEDDINGS_PATH = DATA_ROOT / "embeddings.npz"

MODEL_NAME = "buffalo_l"
EMBEDDING_DIMENSIONS = 512
POSES = ("frontal", "left", "right", "up", "down")
CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480
FRAME_INTERVAL_MS = 250
STALE_FRAME_SECONDS = 0.75
RECOGNITION_TIMEOUT_SECONDS = 8.5
FRAME_CONSISTENCY_THRESHOLD = 0.60
RECOGNITION_COOLDOWN_SECONDS = 2.0
UNKNOWN_RETRY_INTERVAL_SECONDS = 0.75


RECOGNITION_THRESHOLD = 0.45
ENROLLMENT_IDENTITY_THRESHOLD = float(face_matching.ENROLLMENT_IDENTITY_THRESHOLD)
