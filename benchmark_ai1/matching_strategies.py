"""Benchmark-only sample aggregation strategies for ArcFace galleries."""

from __future__ import annotations

import math

import numpy as np


MAX = "MAX"
TOP2_MEAN = "TOP2_MEAN"
STRATEGIES = (MAX, TOP2_MEAN)


def aggregate_similarity_scores(scores, strategy: str) -> float:
    """Aggregate one identity's sample similarities using MAX or TOP2_MEAN."""
    values = np.asarray(list(scores), dtype=np.float64).reshape(-1)
    if values.size == 0 or not np.all(np.isfinite(values)):
        raise ValueError("Similarity scores must contain at least one finite value.")
    strategy = strategy.upper()
    if strategy == MAX:
        return float(np.max(values))
    if strategy == TOP2_MEAN:
        top = np.sort(values)[-2:]
        return float(np.mean(top))
    raise ValueError(f"Unsupported matching strategy: {strategy!r}.")


def identify_embedding(
    embedding,
    gallery: dict,
    threshold: float,
    strategy: str,
    production_max_matcher=None,
) -> dict:
    """Identify from a multi-sample gallery; MAX may delegate to AI1's production matcher."""
    strategy = strategy.upper()
    if strategy not in STRATEGIES:
        raise ValueError(f"strategy must be one of {STRATEGIES}.")
    threshold = float(threshold)
    if not math.isfinite(threshold):
        raise ValueError("threshold must be finite.")

    if strategy == MAX and production_max_matcher is not None:
        best = production_max_matcher(embedding, gallery, -1.0)
        candidate_id, score = best["MaNV"], best["similarity"]
    else:
        probe = _normalize(embedding)
        candidate_id, score = None, -math.inf
        for employee_id, person in gallery.items():
            samples = person.get("embeddings", ())
            if not samples:
                continue
            similarities = [float(np.dot(probe, _normalize(sample))) for sample in samples]
            person_score = aggregate_similarity_scores(similarities, strategy)
            if person_score > score:
                candidate_id, score = employee_id, person_score
        if candidate_id is None:
            score = None

    accepted = candidate_id is not None and score is not None and float(score) >= threshold
    return {
        "candidate_id": candidate_id,
        "predicted_id": candidate_id if accepted else "UNKNOWN",
        "score": float(score) if score is not None else None,
        "match": bool(accepted),
    }


def _normalize(vector) -> np.ndarray:
    values = np.asarray(vector, dtype=np.float32).reshape(-1)
    if values.size == 0 or not np.all(np.isfinite(values)):
        raise ValueError("Embedding must be a non-empty finite vector.")
    norm = float(np.linalg.norm(values))
    if norm <= 1e-12:
        raise ValueError("Embedding norm must be greater than zero.")
    return values / norm
