"""AI1-compatible matching helpers for the isolated test gallery."""

import itertools

import numpy as np

import face_matching
from .config import CONSISTENCY_THRESHOLD, EMBEDDING_DIMENSIONS, RECOGNITION_THRESHOLD


def _production_gallery(gallery):
    converted = {}
    for identity, person in gallery.items():
        converted[identity] = {
            "HoTen": identity,
            "embeddings": tuple(face_matching.normalize_embedding(sample) for sample in person["embeddings"]),
            "n_samples": len(person["embeddings"]),
        }
    return converted


def identify_embedding(embedding, gallery, threshold=None):
    """Use production cosine/MAX matching against an in-memory file gallery."""
    threshold = RECOGNITION_THRESHOLD if threshold is None else float(threshold)
    query = face_matching.normalize_embedding(embedding, EMBEDDING_DIMENSIONS)
    result = face_matching.identify_embedding(query, _production_gallery(gallery), threshold)
    return {
        "status": result["status"],
        "predicted_id": result["MaNV"] if result["match"] else "UNKNOWN",
        "score": float(result["similarity"]) if result["similarity"] is not None else 0.0,
        "threshold": threshold,
        "reason": "MAX cosine đạt threshold." if result["match"] else "MAX cosine thấp hơn threshold.",
    }


def fuse_three_embeddings(embeddings):
    """Mean exactly three valid vectors, then L2-normalize the result."""
    if len(embeddings) != 3:
        raise ValueError("Multi-frame cần đúng 3 embedding hợp lệ.")
    normalized = [face_matching.normalize_embedding(value, EMBEDDING_DIMENSIONS) for value in embeddings]
    mean_vector = np.mean(np.stack(normalized, axis=0), axis=0, dtype=np.float64)
    return face_matching.normalize_embedding(mean_vector, EMBEDDING_DIMENSIONS)


def check_frame_consistency(embeddings, threshold=None):
    """Reject incomplete or inconsistent three-frame sequences."""
    threshold = CONSISTENCY_THRESHOLD if threshold is None else float(threshold)
    if len(embeddings) != 3:
        return {"valid": False, "pairwise": [], "min_similarity": None,
                "reason": "Sequence phải có đúng 3 frame hợp lệ."}
    try:
        vectors = [face_matching.normalize_embedding(value, EMBEDDING_DIMENSIONS) for value in embeddings]
    except (TypeError, ValueError) as exc:
        return {"valid": False, "pairwise": [], "min_similarity": None,
                "reason": f"Embedding không hợp lệ: {exc}"}
    pairwise = [
        face_matching.cosine_similarity(vectors[left], vectors[right])
        for left, right in itertools.combinations(range(3), 2)
    ]
    minimum = min(pairwise)
    valid = minimum >= threshold
    return {
        "valid": valid,
        "pairwise": pairwise,
        "min_similarity": minimum,
        "reason": "Embedding nhất quán." if valid else
                  f"Embedding không nhất quán (min={minimum:.3f}, cần >= {threshold:.3f}).",
    }
