"""File-only gallery persistence. No database access is performed here."""

from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np

import face_matching
from .config import EMBEDDING_DIMENSIONS, MODEL_NAME
from .utils import GALLERY_ROOT, safe_identity_path, validate_identity


DEFAULT_GALLERY_PATH = GALLERY_ROOT / "gallery.npz"
DEFAULT_METADATA_PATH = GALLERY_ROOT / "gallery_meta.json"


def _validate_gallery(gallery):
    if not isinstance(gallery, dict) or not gallery:
        raise ValueError("Gallery rỗng hoặc không hợp lệ.")
    identities, vectors, poses = [], [], []
    for identity in sorted(gallery):
        validate_identity(identity)
        if identity.upper() == "UNKNOWN":
            raise ValueError("UNKNOWN không được thêm vào gallery.")
        person = gallery[identity]
        samples = person.get("embeddings") if isinstance(person, dict) else None
        sample_poses = person.get("poses", []) if isinstance(person, dict) else []
        if not isinstance(samples, (list, tuple)) or not samples:
            raise ValueError(f"{identity}: cần ít nhất một embedding.")
        if not sample_poses:
            sample_poses = ["unspecified"] * len(samples)
        if len(sample_poses) != len(samples):
            raise ValueError(f"{identity}: số pose không khớp số embedding.")
        for sample, pose in zip(samples, sample_poses):
            vector = face_matching.normalize_embedding(sample, EMBEDDING_DIMENSIONS)
            identities.append(identity)
            vectors.append(vector)
            poses.append(str(pose))
    return (np.asarray(identities, dtype=np.str_),
            np.stack(vectors).astype(np.float32), np.asarray(poses, dtype=np.str_))


def save_gallery(gallery, gallery_path=DEFAULT_GALLERY_PATH, metadata_path=None):
    """Save per-person samples as a safe, non-pickle NPZ and metadata JSON."""
    path = Path(gallery_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    meta_path = Path(metadata_path) if metadata_path else path.parent / "gallery_meta.json"
    identities, embeddings, poses = _validate_gallery(gallery)
    np.savez_compressed(path, identities=identities, embeddings=embeddings, poses=poses)
    identity_counts = {}
    for identity in identities.tolist():
        identity_counts[identity] = identity_counts.get(identity, 0) + 1
    metadata = {
        "identity": sorted(identity_counts),
        "identities": sorted(identity_counts),
        "poses": {identity: list(person.get("poses", [])) for identity, person in sorted(gallery.items())},
        "number_of_samples": int(len(embeddings)),
        "samples_per_identity": identity_counts,
        "embedding_dimension": EMBEDDING_DIMENSIONS,
        "model": MODEL_NAME,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return path, meta_path


def load_gallery(gallery_path=DEFAULT_GALLERY_PATH):
    """Load and strictly validate a local gallery without enabling pickle."""
    path = Path(gallery_path)
    if not path.is_file():
        raise FileNotFoundError(f"Không tìm thấy gallery: {path}")
    try:
        with np.load(path, allow_pickle=False) as data:
            identities = np.asarray(data["identities"])
            embeddings = np.asarray(data["embeddings"], dtype=np.float32)
            poses = np.asarray(data["poses"])
    except (OSError, ValueError, KeyError) as exc:
        raise ValueError(f"Không đọc được gallery hợp lệ: {exc}") from exc
    if identities.ndim != 1 or poses.ndim != 1 or embeddings.ndim != 2:
        raise ValueError("Gallery phải chứa identities/poses dạng 1D và embeddings dạng 2D.")
    if embeddings.shape[1:] != (EMBEDDING_DIMENSIONS,):
        raise ValueError(f"Gallery embedding phải có đúng {EMBEDDING_DIMENSIONS} chiều.")
    if not len(identities) or len(identities) != len(embeddings) or len(poses) != len(embeddings):
        raise ValueError("Gallery rỗng hoặc số identities/poses/embeddings không khớp.")

    gallery = {}
    for identity_value, pose_value, vector in zip(identities.tolist(), poses.tolist(), embeddings):
        if not isinstance(identity_value, str):
            raise ValueError("Identity trong gallery không hợp lệ.")
        identity = validate_identity(identity_value)
        if identity.upper() == "UNKNOWN":
            raise ValueError("UNKNOWN không được thêm vào gallery.")
        if not np.all(np.isfinite(vector)):
            raise ValueError(f"{identity}: embedding chứa giá trị không hữu hạn.")
        norm = float(np.linalg.norm(vector))
        if not np.isfinite(norm) or not np.isclose(norm, 1.0, atol=1e-3):
            raise ValueError(f"{identity}: embedding chưa L2 normalize (norm={norm}).")
        gallery.setdefault(identity, {"embeddings": [], "poses": []})
        gallery[identity]["embeddings"].append(vector.astype(np.float32, copy=True))
        gallery[identity]["poses"].append(str(pose_value))
    if not gallery:
        raise ValueError("Gallery không có identity hợp lệ.")
    return gallery


def gallery_info(gallery_path=DEFAULT_GALLERY_PATH):
    path = Path(gallery_path)
    meta_path = path.parent / "gallery_meta.json"
    if meta_path.is_file():
        return json.loads(meta_path.read_text(encoding="utf-8"))
    gallery = load_gallery(path)
    return {
        "identities": sorted(gallery),
        "number_of_samples": sum(len(value["embeddings"]) for value in gallery.values()),
        "embedding_dimension": EMBEDDING_DIMENSIONS,
        "model": MODEL_NAME,
    }
