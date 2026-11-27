"""Summarize benchmark predictions from results.csv into summary.csv."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path


def _number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def summarize_rows(rows: list[dict], configs: dict | None = None) -> list[dict]:
    configs = configs or {}
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["algorithm"]].append(row)
    summary = []
    for algorithm in sorted(grouped):
        samples = grouped[algorithm]
        expected = [str(row["expected_id"]) for row in samples]
        predicted = [str(row["predicted_id"]) for row in samples]
        labels = sorted(set(expected) | set(predicted))
        correct = sum(actual == guess for actual, guess in zip(expected, predicted))
        total = len(samples)
        # Macro precision/recall over identity labels plus UNKNOWN, zero-division=0.
        per_precision, per_recall = [], []
        for label in labels:
            tp = sum(actual == label and guess == label for actual, guess in zip(expected, predicted))
            fp = sum(actual != label and guess == label for actual, guess in zip(expected, predicted))
            fn = sum(actual == label and guess != label for actual, guess in zip(expected, predicted))
            per_precision.append(tp / (tp + fp) if tp + fp else 0.0)
            per_recall.append(tp / (tp + fn) if tp + fn else 0.0)
        unknown = [row for row in samples if str(row["expected_id"]) == "UNKNOWN"]
        known = [row for row in samples if str(row["expected_id"]) != "UNKNOWN"]
        false_accept = sum(str(row["predicted_id"]) != "UNKNOWN" for row in unknown)
        false_reject = sum(str(row["predicted_id"]) == "UNKNOWN" for row in known)
        latencies = [number for row in samples if (number := _number(row.get("latency_ms"))) is not None]
        config = configs.get(algorithm, {})
        summary.append({
            "algorithm": algorithm,
            "accuracy": correct / total if total else 0.0,
            "precision_macro": sum(per_precision) / len(per_precision) if per_precision else 0.0,
            "recall_macro": sum(per_recall) / len(per_recall) if per_recall else 0.0,
            "FAR": false_accept / len(unknown) if unknown else "",
            "FRR": false_reject / len(known) if known else "",
            "test_samples": total,
            "correct": correct,
            "incorrect": total - correct,
            "false_accept": false_accept,
            "false_reject": false_reject,
            "average_latency_ms": sum(latencies) / len(latencies) if latencies else "",
            "min_latency_ms": min(latencies) if latencies else "",
            "max_latency_ms": max(latencies) if latencies else "",
            "estimated_FPS": 1000.0 / (sum(latencies) / len(latencies)) if latencies and sum(latencies) > 0 else "",
            "threshold": config.get("threshold", ""),
            "threshold_status": config.get("threshold_status", ""),
            "model_and_score_config": json.dumps(config, ensure_ascii=False, sort_keys=True),
        })
    return summary


def summarize(results_csv: Path, output_csv: Path, config_path: Path | None = None) -> list[dict]:
    with results_csv.open("r", newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError(f"No benchmark prediction rows found in {results_csv}.")
    if config_path is None:
        config_path = results_csv.parent / "config.json"
    configs = json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
    summary = summarize_rows(rows, configs)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=Path(__file__).resolve().parent / "results" / "results.csv")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "results" / "summary.csv")
    args = parser.parse_args()
    try:
        summarize(args.results, args.output)
    except Exception as exc:
        parser.error(str(exc))
    print(f"Summary written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
