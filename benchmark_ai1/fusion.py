"""Benchmark-only temporal grouping and equal-weight embedding fusion."""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

import numpy as np


SEQUENCE_FILENAME = re.compile(r"^(seq\d+)_(\d{2})$", re.IGNORECASE)


def mean_l2_normalize(embeddings) -> np.ndarray:
    """Compute E' = mean(E1..En) / ||mean(E1..En)||2."""
    matrix = np.asarray(list(embeddings), dtype=np.float32)
    if matrix.ndim != 2 or matrix.shape[0] == 0 or matrix.shape[1] == 0:
        raise ValueError("Expected a non-empty list of equally-sized embedding vectors.")
    if not np.all(np.isfinite(matrix)):
        raise ValueError("Embeddings contain non-finite values.")
    mean_vector = np.mean(matrix, axis=0, dtype=np.float32)
    norm = float(np.linalg.norm(mean_vector))
    if norm <= 1e-12:
        raise ValueError("Mean embedding has zero norm and cannot be normalized.")
    return np.asarray(mean_vector / norm, dtype=np.float32)


def group_sequence_images(rows):
    """Group exact 3-frame consecutive filename sequences by identity and sequence id.

    rows are (expected_id, image_path). Incomplete/malformed sequence-named groups are
    returned separately for explicit diagnostics; ordinary non-sequence files are ignored.
    """
    grouped = defaultdict(list)
    invalid = []
    for expected_id, image_path in rows:
        path = Path(image_path)
        match = SEQUENCE_FILENAME.fullmatch(path.stem)
        if not match:
            continue
        sequence_id, frame_text = match.groups()
        key = (str(expected_id), path.parent.name, sequence_id.lower())
        grouped[key].append((int(frame_text), path))

    sequences = []
    for (expected_text, _folder, sequence_id), frames in sorted(grouped.items()):
        frames.sort(key=lambda item: (item[0], item[1].name.lower()))
        numbers = [number for number, _ in frames]
        if len(frames) != 3 or numbers[1:] != [numbers[0] + 1, numbers[0] + 2]:
            invalid.append({"sequence": sequence_id, "frames": [path.name for _, path in frames]})
            continue
        expected_id = "UNKNOWN" if expected_text == "UNKNOWN" else int(expected_text)
        sequences.append({
            "expected_id": expected_id,
            "sequence_id": sequence_id,
            "paths": [path for _, path in frames],
        })
    return sequences, invalid
