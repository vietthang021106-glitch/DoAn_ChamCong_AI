"""Threshold calibration using validation predictions only."""

from __future__ import annotations

import math


def calibrate_threshold(
    algorithm: str,
    validation_rows: list[dict],
    *,
    initial_threshold: float,
    lower_is_better: bool = False,
) -> dict:
    """Select threshold by min balanced error, then max accuracy, then nearest initial value.

    FAR = rejected-set UNKNOWN samples accepted as a known candidate / UNKNOWN count.
    FRR = known samples rejected as UNKNOWN / known count. Wrong-known predictions are
    incorrect for accuracy but are neither FAR nor FRR under these definitions.
    """
    if not validation_rows:
        raise ValueError(f"{algorithm}: validation set has no scored samples.")
    unknown_count = sum(str(row["expected_id"]) == "UNKNOWN" for row in validation_rows)
    known_count = len(validation_rows) - unknown_count
    if unknown_count == 0 or known_count == 0:
        raise ValueError(f"{algorithm}: validation must contain both known identities and UNKNOWN samples.")

    scores = []
    for row in validation_rows:
        try:
            score = float(row["score"])
        except (TypeError, ValueError):
            continue
        if math.isfinite(score):
            scores.append(score)
    if not scores:
        raise ValueError(f"{algorithm}: validation produced no finite face scores; threshold is not meaningful.")
    candidates = {float(initial_threshold)}
    for score in scores:
        candidates.add(score)
        candidates.add(math.nextafter(score, -math.inf if lower_is_better else math.inf))
    if not candidates:
        raise ValueError(f"{algorithm}: no finite threshold candidates.")

    evaluated = []
    for threshold in candidates:
        correct = false_accept = false_reject = 0
        for row in validation_rows:
            expected = str(row["expected_id"])
            candidate = row.get("candidate_id")
            score = row.get("score")
            try:
                score = float(score)
            except (TypeError, ValueError):
                score = None
            accepted = (
                candidate is not None
                and score is not None
                and math.isfinite(score)
                and (score <= threshold if lower_is_better else score >= threshold)
            )
            predicted = str(candidate) if accepted else "UNKNOWN"
            correct += predicted == expected
            if expected == "UNKNOWN" and accepted:
                false_accept += 1
            elif expected != "UNKNOWN" and not accepted:
                false_reject += 1
        far = false_accept / unknown_count
        frr = false_reject / known_count
        accuracy = correct / len(validation_rows)
        evaluated.append({
            "algorithm": algorithm,
            "threshold": threshold,
            "accuracy": accuracy,
            "far": far,
            "frr": frr,
            "balanced_error_rate": (far + frr) / 2.0,
        })

    # Explicit selection rule: minimize balanced error (equal FAR/FRR weight),
    # then maximize overall exact-ID accuracy, then stay closest to the initial value.
    return min(
        evaluated,
        key=lambda row: (
            row["balanced_error_rate"],
            -row["accuracy"],
            abs(row["threshold"] - initial_threshold),
            row["threshold"],
        ),
    )
