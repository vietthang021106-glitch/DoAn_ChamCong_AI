#!/usr/bin/env python
"""Calibrate duplicate-face max-over-5x5 cosine threshold from labeled images.

Input layout:
    DATASET/<identity>/<enrollment_session>/{frontal,left,right,up,down}.jpg

This tool reads only the supplied dataset and the production buffalo_l face
engine. It never reads the MariaDB gallery or writes a PHP environment file.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

POSES = ("frontal", "left", "right", "up", "down")
MODEL_NAME = "buffalo_l"
AGGREGATION = "max_5x5_cosine"
MIN_IDENTITIES = 10
MIN_GENUINE_PAIRS = 30
MIN_IMPOSTOR_PAIRS = 100
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}


def max_5x5_cosine(left: np.ndarray, right: np.ndarray) -> float:
    """Return the maximum cosine among every vector in two five-sample sets."""
    left = _normalized_batch(left)
    right = _normalized_batch(right)
    if left.shape[0] != 5 or right.shape[0] != 5:
        raise ValueError("Each enrollment session must contain exactly five embeddings.")
    return float(np.clip(left @ right.T, -1.0, 1.0).max())


def _normalized_batch(values: np.ndarray) -> np.ndarray:
    vectors = np.asarray(values, dtype=np.float32)
    if vectors.ndim != 2 or vectors.shape[1] != 512:
        raise ValueError("Expected a batch of 512D embeddings.")
    if not np.isfinite(vectors).all():
        raise ValueError("Embedding batch contains non-finite values.")
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    if np.any(norms <= 1e-12):
        raise ValueError("Embedding batch contains a zero-norm vector.")
    return vectors / norms


def rates_at_threshold(genuine_scores: Iterable[float], impostor_scores: Iterable[float], threshold: float) -> dict:
    genuine = np.asarray(list(genuine_scores), dtype=np.float64)
    impostor = np.asarray(list(impostor_scores), dtype=np.float64)
    if genuine.size == 0 or impostor.size == 0:
        raise ValueError("Both genuine and impostor session pairs are required.")
    if not np.isfinite(genuine).all() or not np.isfinite(impostor).all():
        raise ValueError("Pair scores must be finite.")
    false_match = int(np.count_nonzero(impostor >= threshold))
    false_non_match = int(np.count_nonzero(genuine < threshold))
    return {
        "threshold": float(threshold),
        "false_match_count": false_match,
        "false_non_match_count": false_non_match,
        "fmr": false_match / int(impostor.size),
        "fnmr": false_non_match / int(genuine.size),
        "far": false_match / int(impostor.size),
        "frr": false_non_match / int(genuine.size),
        "genuine_pair_count": int(genuine.size),
        "impostor_pair_count": int(impostor.size),
    }


def choose_threshold(genuine_scores, impostor_scores, max_fmr: float, max_fnmr: float) -> dict:
    """Choose the least restrictive threshold meeting both supplied error targets."""
    for name, value in (("max_fmr", max_fmr), ("max_fnmr", max_fnmr)):
        if not math.isfinite(float(value)) or not 0.0 <= float(value) <= 1.0:
            raise ValueError(f"{name} must be between 0 and 1.")
    genuine = np.asarray(list(genuine_scores), dtype=np.float64)
    impostor = np.asarray(list(impostor_scores), dtype=np.float64)
    if genuine.size == 0 or impostor.size == 0:
        raise ValueError("Both genuine and impostor session pairs are required.")
    candidates = sorted({0.0, 1.0, *[float(v) for v in genuine], *[float(v) for v in impostor]})
    candidates = [min(1.0, max(0.0, value)) for value in candidates]
    evaluations = [rates_at_threshold(genuine, impostor, threshold) for threshold in candidates]
    accepted = [item for item in evaluations
                if item["fmr"] <= max_fmr and item["fnmr"] <= max_fnmr]
    if accepted:
        selected = min(accepted, key=lambda item: item["threshold"])
        meets_targets = True
    else:
        def violation(item):
            fmr_ratio = item["fmr"] / max(max_fmr, 1e-12)
            fnmr_ratio = item["fnmr"] / max(max_fnmr, 1e-12)
            return max(fmr_ratio, fnmr_ratio), fmr_ratio + fnmr_ratio, item["threshold"]

        selected = min(evaluations, key=violation)
        meets_targets = False
    return {**selected, "meets_error_targets": meets_targets}


def _session_directories(dataset: Path) -> dict[str, list[Path]]:
    if not dataset.is_dir():
        raise ValueError(f"Calibration dataset directory does not exist: {dataset}")
    groups: dict[str, list[Path]] = {}
    for identity_dir in sorted(path for path in dataset.iterdir() if path.is_dir()):
        sessions = []
        for session_dir in sorted(path for path in identity_dir.iterdir() if path.is_dir()):
            files = [path for path in session_dir.iterdir()
                     if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES]
            names = {path.stem.lower() for path in files}
            if len(files) == 5 and names == set(POSES):
                sessions.append(session_dir)
        if sessions:
            groups[identity_dir.name] = sessions
    return groups


def _dataset_fingerprint(dataset: Path, sessions: dict[str, list[Path]]) -> str:
    digest = hashlib.sha256()
    for identity, identity_sessions in sorted(sessions.items()):
        for session in identity_sessions:
            for pose in POSES:
                image = next(path for path in session.iterdir()
                             if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
                             and path.stem.lower() == pose)
                digest.update(image.relative_to(dataset).as_posix().encode("utf-8"))
                with image.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
    return digest.hexdigest()


def _read_calibration_sessions(dataset: Path, groups, engine) -> tuple[dict[str, list[np.ndarray]], int, str]:
    import cv2
    import face_engine

    vectors: dict[str, list[np.ndarray]] = {}
    image_count = 0
    digest = hashlib.sha256()
    for identity, sessions in sorted(groups.items()):
        vectors[identity] = []
        for session in sessions:
            batch = []
            for pose in POSES:
                path = next(item for item in session.iterdir()
                            if item.is_file() and item.suffix.lower() in IMAGE_SUFFIXES
                            and item.stem.lower() == pose)
                data = np.fromfile(path, dtype=np.uint8)
                frame = cv2.imdecode(data, cv2.IMREAD_COLOR)
                if frame is None or frame.size == 0:
                    raise ValueError(f"Could not decode calibration image: {path}")
                faces = engine.detect_embeddings(frame)
                if len(faces) != 1:
                    raise ValueError(f"Expected exactly one face in calibration image: {path}")
                face = faces[0]
                quality = face_engine.assess_capture_quality(frame, face)
                if quality.get("ready") is not True:
                    raise ValueError(f"Calibration image failed production quality gate ({quality.get('instruction')}): {path}")
                vector = _normalized_batch(np.asarray(face.get("embedding"), dtype=np.float32).reshape(1, -1))[0]
                batch.append(vector)
                digest.update(path.relative_to(dataset).as_posix().encode("utf-8"))
                digest.update(hashlib.sha256(data.tobytes()).digest())
                image_count += 1
            vectors[identity].append(np.stack(batch))
    return vectors, image_count, digest.hexdigest()


def pair_scores(vectors: dict[str, list[np.ndarray]]) -> tuple[list[float], list[float]]:
    genuine: list[float] = []
    impostor: list[float] = []
    identities = sorted(vectors)
    for identity in identities:
        for left, right in itertools.combinations(vectors[identity], 2):
            genuine.append(max_5x5_cosine(left, right))
    for left_identity_index, left_identity in enumerate(identities):
        for right_identity in identities[left_identity_index + 1:]:
            for left in vectors[left_identity]:
                for right in vectors[right_identity]:
                    impostor.append(max_5x5_cosine(left, right))
    return genuine, impostor


def calibrate(dataset: Path, max_fmr: float, max_fnmr: float,
              min_identities: int = MIN_IDENTITIES,
              min_genuine_pairs: int = MIN_GENUINE_PAIRS,
              min_impostor_pairs: int = MIN_IMPOSTOR_PAIRS) -> dict:
    groups = _session_directories(dataset)
    session_count = sum(len(sessions) for sessions in groups.values())
    possible_genuine = sum(len(sessions) * (len(sessions) - 1) // 2
                           for sessions in groups.values())
    possible_impostor = sum(
        len(groups[left]) * len(groups[right])
        for index, left in enumerate(sorted(groups))
        for right in sorted(groups)[index + 1:]
    )
    enough_structure = (
        len(groups) >= min_identities
        and all(len(sessions) >= 2 for sessions in groups.values())
        and possible_genuine >= min_genuine_pairs
        and possible_impostor >= min_impostor_pairs
    )
    report = {
        "version": 1,
        "validated": False,
        "model": MODEL_NAME,
        "aggregation": AGGREGATION,
        "threshold": None,
        "targets": {"max_fmr": float(max_fmr), "max_fnmr": float(max_fnmr)},
        "sample_counts": {
            "identity_count": len(groups),
            "session_count": session_count,
            "image_count": 0,
            "genuine_pair_count": possible_genuine,
            "impostor_pair_count": possible_impostor,
        },
        "metrics": {"fmr": None, "fnmr": None, "far": None, "frr": None},
        "minimums": {
            "identity_count": int(min_identities),
            "genuine_pair_count": int(min_genuine_pairs),
            "impostor_pair_count": int(min_impostor_pairs),
            "sessions_per_identity": 2,
        },
        "dataset_sha256": None,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "method": "buffalo_l embeddings; max cosine over every pair in a 5x5 session comparison",
        "validation_reason": None,
    }
    if not groups or not enough_structure:
        report["dataset_sha256"] = _dataset_fingerprint(dataset, groups) if groups else None
        report["validation_reason"] = "INSUFFICIENT_LABELED_CALIBRATION_SESSIONS"
        return report

    from face_engine import FaceRecognitionEngine

    engine = FaceRecognitionEngine()
    engine.initialize()
    vectors, image_count, fingerprint = _read_calibration_sessions(dataset, groups, engine)
    genuine, impostor = pair_scores(vectors)
    selected = choose_threshold(genuine, impostor, max_fmr, max_fnmr)
    report["sample_counts"].update({
        "image_count": image_count,
        "genuine_pair_count": len(genuine),
        "impostor_pair_count": len(impostor),
    })
    report["threshold"] = selected["threshold"]
    report["metrics"] = {key: selected[key] for key in (
        "fmr", "fnmr", "far", "frr", "false_match_count", "false_non_match_count"
    )}
    report["metrics"].update({
        "genuine_pair_count": len(genuine),
        "impostor_pair_count": len(impostor),
    })
    report["dataset_sha256"] = fingerprint
    report["validated"] = bool(selected["meets_error_targets"])
    report["validation_reason"] = (
        "VALIDATED_WITHIN_EXPLICIT_TARGETS" if report["validated"]
        else "NO_THRESHOLD_MEETS_BOTH_ERROR_TARGETS"
    )
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path,
                        help="Labeled folder: identity/session/{frontal,left,right,up,down}.jpg")
    parser.add_argument("--output", required=True, type=Path,
                        help="JSON report output path; no images or embeddings are written.")
    parser.add_argument("--max-fmr", required=True, type=float,
                        help="Maximum acceptable impostor false-match rate, chosen by the project owner.")
    parser.add_argument("--max-fnmr", required=True, type=float,
                        help="Maximum acceptable genuine false-non-match rate, chosen by the project owner.")
    parser.add_argument("--min-identities", type=int, default=MIN_IDENTITIES)
    parser.add_argument("--min-genuine-pairs", type=int, default=MIN_GENUINE_PAIRS)
    parser.add_argument("--min-impostor-pairs", type=int, default=MIN_IMPOSTOR_PAIRS)
    args = parser.parse_args(argv)
    try:
        report = calibrate(args.dataset, args.max_fmr, args.max_fnmr,
                           args.min_identities, args.min_genuine_pairs,
                           args.min_impostor_pairs)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except Exception as exc:
        parser.error(str(exc))
    print(json.dumps({
        "report": str(args.output.resolve()),
        "validated": report["validated"],
        "validation_reason": report["validation_reason"],
        "sample_counts": report["sample_counts"],
        "threshold": report["threshold"],
        "metrics": report["metrics"],
    }, ensure_ascii=False, indent=2))
    return 0 if report["validated"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
