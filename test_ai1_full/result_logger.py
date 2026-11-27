"""Append recognition decisions to a local CSV without writing embeddings."""

import csv
from datetime import datetime
from pathlib import Path
import threading

from .utils import RESULTS_ROOT


RESULTS_CSV = RESULTS_ROOT / "recognition_results.csv"
CSV_COLUMNS = (
    "timestamp", "mode", "expected_id", "predicted_id", "score", "threshold",
    "latency_ms", "correct", "status", "reason",
)
_LOCK = threading.Lock()


def log_result(mode, expected_id, result, threshold):
    if mode not in {"SINGLE", "MULTI_FRAME"}:
        raise ValueError("mode phải là SINGLE hoặc MULTI_FRAME.")
    RESULTS_CSV.parent.mkdir(parents=True, exist_ok=True)
    expected = "" if expected_id is None else str(expected_id)
    correct = ("" if expected_id is None or result.get("status") == "RETRY" else
               str(str(result.get("predicted_id")) == expected).lower())
    row = {
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "mode": mode,
        "expected_id": expected,
        "predicted_id": result.get("predicted_id", "UNKNOWN"),
        "score": result.get("score", ""),
        "threshold": threshold,
        "latency_ms": result.get("latency_ms", ""),
        "correct": correct,
        "status": result.get("status", "RETRY"),
        "reason": result.get("reason", ""),
    }
    with _LOCK:
        needs_header = not RESULTS_CSV.exists() or RESULTS_CSV.stat().st_size == 0
        with RESULTS_CSV.open("a", newline="", encoding="utf-8-sig") as stream:
            writer = csv.DictWriter(stream, fieldnames=CSV_COLUMNS)
            if needs_header:
                writer.writeheader()
            writer.writerow(row)
    return RESULTS_CSV
