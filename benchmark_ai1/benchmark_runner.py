"""Run model, ArcFace matching-strategy, and ArcFace frame-fusion benchmarks."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if __package__:
    from .calibration import calibrate_threshold
    from .fusion import group_sequence_images, mean_l2_normalize
    from .matching_strategies import MAX, TOP2_MEAN
else:
    from calibration import calibrate_threshold
    from fusion import group_sequence_images, mean_l2_normalize
    from matching_strategies import MAX, TOP2_MEAN

ALGORITHMS = ("ArcFace", "FaceNet", "LBPH")
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
LOG = logging.getLogger("benchmark_ai1")


def _identity(folder_name: str) -> int | str:
    if folder_name == "UNKNOWN":
        return "UNKNOWN"
    prefix, separator, value = folder_name.partition("_")
    if prefix != "MaNV" or not separator or not value.isdigit():
        raise ValueError(f"Invalid dataset folder {folder_name!r}; use MaNV_<integer> or UNKNOWN.")
    return int(value)


def _images(directory: Path, *, allow_unknown: bool) -> list[tuple[int | str, Path]]:
    if not directory.is_dir():
        raise FileNotFoundError(f"Dataset directory does not exist: {directory}")
    rows = []
    for folder in sorted(path for path in directory.iterdir() if path.is_dir()):
        identity = _identity(folder.name)
        if identity == "UNKNOWN" and not allow_unknown:
            raise ValueError(f"UNKNOWN is not allowed under {directory}.")
        rows.extend(
            (identity, path)
            for path in sorted(folder.rglob("*"))
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
        )
    return rows


def _verify_no_split_leakage(splits: dict[str, list[tuple[int | str, Path]]]) -> None:
    seen: dict[str, tuple[str, Path]] = {}
    for split_name, images in splits.items():
        for _, path in images:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest in seen:
                old_split, old_path = seen[digest]
                raise ValueError(f"Exact image leakage between {old_split} and {split_name}: {old_path} == {path}.")
            seen[digest] = (split_name, path)


def _validate_dataset(dataset_dir: Path):
    splits = {name: _images(dataset_dir / name, allow_unknown=name != "train")
              for name in ("train", "validation", "test")}
    train, validation, tests = splits["train"], splits["validation"], splits["test"]
    problems = [f"{name}: no image files" for name, items in splits.items() if not items]
    train_ids = {identity for identity, _ in train}
    if "UNKNOWN" in train_ids:
        problems.append("train: UNKNOWN must not be enrolled")
    for employee_id in sorted(train_ids):
        count = sum(identity == employee_id for identity, _ in train)
        if count < 2:
            problems.append(f"train/MaNV_{employee_id}: need at least 2 samples for multi-sample matching")

    for split_name, items in (("validation", validation), ("test", tests)):
        known_ids = {identity for identity, _ in items if identity != "UNKNOWN"}
        if not known_ids:
            problems.append(f"{split_name}: needs known identity images")
        if not any(identity == "UNKNOWN" for identity, _ in items):
            problems.append(f"{split_name}: needs UNKNOWN images to calculate FAR")
        if known_ids != train_ids:
            problems.append(
                f"{split_name}: known identities must match train (expected {sorted(train_ids)}, got {sorted(known_ids)})"
            )

    validation_sequences, invalid_validation = group_sequence_images(validation)
    test_sequences, invalid_test = group_sequence_images(tests)
    for split_name, sequences, invalid in (
        ("validation", validation_sequences, invalid_validation),
        ("test", test_sequences, invalid_test),
    ):
        if not sequences:
            problems.append(
                f"{split_name}: needs sequence triplets named seq001_01.jpg, seq001_02.jpg, seq001_03.jpg"
            )
        sequence_ids = {row["expected_id"] for row in sequences if row["expected_id"] != "UNKNOWN"}
        missing_ids = train_ids - sequence_ids
        if missing_ids:
            problems.append(f"{split_name}: missing sequence triplets for identities {sorted(missing_ids)}")
        if not any(row["expected_id"] == "UNKNOWN" for row in sequences):
            problems.append(f"{split_name}: needs at least one UNKNOWN sequence triplet")
        if invalid:
            LOG.warning("%s: incomplete sequence groups will be skipped: %s", split_name, invalid)

    _verify_no_split_leakage(splits)
    if problems:
        raise ValueError("Dataset is not ready:\n- " + "\n- ".join(problems))
    return splits, validation_sequences, test_sequences


def _adapter_instances():
    if __package__:
        from .arcface_adapter import ArcFaceAdapter
        from .facenet_adapter import FaceNetAdapter
        from .lbph_adapter import LBPHAdapter
    else:
        from arcface_adapter import ArcFaceAdapter
        from facenet_adapter import FaceNetAdapter
        from lbph_adapter import LBPHAdapter
    return {"ArcFace": ArcFaceAdapter, "FaceNet": FaceNetAdapter, "LBPH": LBPHAdapter}


def _write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _summary_values(strategy: str, rows: list[dict]) -> dict:
    if not rows:
        raise ValueError(f"No evaluated samples for {strategy}; refusing to write an empty summary.")
    known = [row for row in rows if str(row["expected_id"]) != "UNKNOWN"]
    unknown = [row for row in rows if str(row["expected_id"]) == "UNKNOWN"]
    correct = sum(str(row["expected_id"]) == str(row["predicted_id"]) for row in rows)
    false_accept = sum(str(row["predicted_id"]) != "UNKNOWN" for row in unknown)
    false_reject = sum(str(row["predicted_id"]) == "UNKNOWN" for row in known)
    latencies = [float(row["latency_ms"]) for row in rows if row.get("latency_ms") is not None]
    average = sum(latencies) / len(latencies) if latencies else None
    return {
        "strategy": strategy,
        "accuracy": correct / len(rows),
        "far": false_accept / len(unknown) if unknown else "",
        "frr": false_reject / len(known) if known else "",
        "avg_latency_ms": average if average is not None else "",
        "fps": 1000.0 / average if average and average > 0 else "",
    }


def _safe_extract(adapter, image_path):
    started = time.perf_counter()
    try:
        embedding, elapsed_ms = adapter.extract_embedding(image_path)
        return embedding, float(elapsed_ms), ""
    except Exception as exc:
        return None, (time.perf_counter() - started) * 1000.0, f"{type(exc).__name__}: {exc}"


def _matching_result(adapter, embedding, strategy, threshold, expected_id, embedding_latency):
    if embedding is None:
        return {
            "expected_id": expected_id, "predicted_id": "UNKNOWN", "candidate_id": None,
            "score": None, "latency_ms": embedding_latency,
        }
    result = adapter.identify_embedding(embedding, threshold=threshold, strategy=strategy)
    return {
        "expected_id": expected_id,
        "predicted_id": result["predicted_id"],
        "candidate_id": result["candidate_id"],
        "score": result["score"],
        "latency_ms": embedding_latency + result["matching_latency_ms"],
    }


def _calibrate(name, rows, initial_threshold, lower_is_better=False):
    return calibrate_threshold(
        name, rows, initial_threshold=float(initial_threshold), lower_is_better=lower_is_better
    )


def _fused_calibration_rows(adapter, sequences, embeddings):
    rows = []
    for sequence in sequences:
        vectors = [embeddings[path][0] for path in sequence["paths"]]
        if any(vector is None for vector in vectors):
            rows.append({"expected_id": sequence["expected_id"], "candidate_id": None, "score": None})
            continue
        fused = mean_l2_normalize(vectors)
        result = adapter.identify_embedding(fused, threshold=-1.0, strategy=MAX)
        rows.append({
            "expected_id": sequence["expected_id"],
            "candidate_id": result["candidate_id"],
            "score": result["score"],
        })
    return rows


def _threshold_row(name, result):
    return {"algorithm": name, **{key: result[key] for key in ("threshold", "accuracy", "far", "frr")}}


def run_benchmark(dataset_dir: Path, results_dir: Path) -> Path:
    # Validate all splits and sequence metadata before model initialization/inference.
    splits, validation_sequences, test_sequences = _validate_dataset(dataset_dir)
    train, validation, tests = splits["train"], splits["validation"], splits["test"]
    adapters, configs = {}, {}
    for name, factory in _adapter_instances().items():
        LOG.info("Training %s from dataset/train", name)
        adapter = factory()
        adapter.enroll([(identity, path) for identity, path in train])
        adapters[name] = adapter
        configs[name] = dict(adapter.config)
        try:
            adapter.warm_up(validation[0][1])
        except Exception as exc:
            LOG.warning("%s validation warm-up failed: %s", name, exc)

    arcface = adapters["ArcFace"]
    validation_embeddings = {
        path: _safe_extract(arcface, path)
        for _, path in validation
    }

    max_validation, top2_validation = [], []
    for expected_id, path in validation:
        embedding = validation_embeddings[path][0]
        if embedding is None:
            failure = {"expected_id": expected_id, "candidate_id": None, "score": None}
            max_validation.append(failure.copy())
            top2_validation.append(failure.copy())
            continue
        max_validation.append(
            arcface.identify_embedding(embedding, threshold=-1.0, strategy=MAX) | {"expected_id": expected_id}
        )
        top2_validation.append(
            arcface.identify_embedding(embedding, threshold=-1.0, strategy=TOP2_MEAN) | {"expected_id": expected_id}
        )

    thresholds, threshold_rows = {}, []
    calibrated = _calibrate("ArcFace", max_validation, arcface.config["initial_threshold"])
    thresholds["ArcFace"] = calibrated["threshold"]
    threshold_rows.append(_threshold_row("ArcFace", calibrated))

    calibrated = _calibrate("ArcFace_TOP2_MEAN", top2_validation, arcface.config["initial_threshold"])
    thresholds["ArcFace_TOP2_MEAN"] = calibrated["threshold"]
    threshold_rows.append(_threshold_row("ArcFace_TOP2_MEAN", calibrated))

    for name in ("FaceNet", "LBPH"):
        adapter = adapters[name]
        validation_rows = []
        for expected_id, path in validation:
            try:
                prediction = adapter.identify(path, threshold=adapter.config["initial_threshold"])
                validation_rows.append({
                    "expected_id": expected_id,
                    "candidate_id": prediction.get("candidate_id"),
                    "score": prediction.get("score"),
                })
            except Exception as exc:
                LOG.error("%s validation failed on %s: %s", name, path, exc)
                validation_rows.append({"expected_id": expected_id, "candidate_id": None, "score": None})
        calibrated = _calibrate(
            name, validation_rows, adapter.config["initial_threshold"], lower_is_better=name == "LBPH"
        )
        thresholds[name] = calibrated["threshold"]
        threshold_rows.append(_threshold_row(name, calibrated))

    fused_validation = _fused_calibration_rows(arcface, validation_sequences, validation_embeddings)
    calibrated = _calibrate(
        "ArcFace_MULTI_FRAME_MEAN", fused_validation, arcface.config["initial_threshold"]
    )
    thresholds["ArcFace_MULTI_FRAME_MEAN"] = calibrated["threshold"]
    threshold_rows.append(_threshold_row("ArcFace_MULTI_FRAME_MEAN", calibrated))

    configs["ArcFace"].update({
        "threshold": thresholds["ArcFace"],
        "threshold_status": "calibrated on validation",
        "matching_strategy": MAX,
    })
    configs["ArcFace_TOP2_MEAN"] = {
        **arcface.config, "threshold": thresholds["ArcFace_TOP2_MEAN"], "matching_strategy": TOP2_MEAN,
        "threshold_status": "calibrated on validation",
    }
    configs["ArcFace_MULTI_FRAME_MEAN"] = {
        **arcface.config, "threshold": thresholds["ArcFace_MULTI_FRAME_MEAN"],
        "fusion": "mean of 3 embeddings then L2 normalize", "threshold_status": "calibrated on validation sequences",
    }
    for name in ("FaceNet", "LBPH"):
        configs[name].update({"threshold": thresholds[name], "threshold_status": "calibrated on validation"})

    results_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(results_dir / "thresholds.csv", ["algorithm", "threshold", "accuracy", "far", "frr"], threshold_rows)
    (results_dir / "config.json").write_text(
        json.dumps(configs, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # Test images are inferred once per model; ArcFace embeddings feed all ArcFace experiments.
    test_embeddings = {path: _safe_extract(arcface, path) for _, path in tests}
    model_rows, matching_max, matching_top2, fusion_single = [], [], [], []
    for expected_id, path in tests:
        embedding, embed_ms, error = test_embeddings[path]
        max_row = _matching_result(arcface, embedding, MAX, thresholds["ArcFace"], expected_id, embed_ms)
        top2_row = _matching_result(
            arcface, embedding, TOP2_MEAN, thresholds["ArcFace_TOP2_MEAN"], expected_id, embed_ms
        )
        matching_max.append(max_row)
        matching_top2.append(top2_row)
        fusion_single.append(max_row)
        model_rows.append({
            "algorithm": "ArcFace",
            "image": path.relative_to(dataset_dir).as_posix(),
            "expected_id": expected_id,
            "predicted_id": max_row["predicted_id"],
            "score": max_row["score"],
            "match": max_row["predicted_id"] != "UNKNOWN",
            "correct": max_row["predicted_id"] == expected_id,
            "latency_ms": max_row["latency_ms"],
            "error": error,
        })
        for name in ("FaceNet", "LBPH"):
            try:
                result = adapters[name].identify(path, threshold=thresholds[name])
                model_rows.append({
                    "algorithm": name,
                    "image": path.relative_to(dataset_dir).as_posix(),
                    "expected_id": expected_id,
                    "predicted_id": result["predicted_id"],
                    "score": result.get("score"),
                    "match": result["predicted_id"] != "UNKNOWN",
                    "correct": result["predicted_id"] == expected_id,
                    "latency_ms": result["latency_ms"],
                    "error": "",
                })
            except Exception as exc:
                LOG.error("%s test failed on %s: %s", name, path, exc)
                model_rows.append({
                    "algorithm": name,
                    "image": path.relative_to(dataset_dir).as_posix(),
                    "expected_id": expected_id,
                    "predicted_id": "UNKNOWN",
                    "score": None,
                    "match": False,
                    "correct": expected_id == "UNKNOWN",
                    "latency_ms": None,
                    "error": f"{type(exc).__name__}: {exc}",
                })

    fusion_multi = []
    for sequence in test_sequences:
        vectors = [test_embeddings[path] for path in sequence["paths"]]
        expected_id = sequence["expected_id"]
        latency_ms = sum(row[1] for row in vectors)
        error = next((row[2] for row in vectors if row[2]), "")
        if error:
            fusion_multi.append({
                "expected_id": expected_id, "predicted_id": "UNKNOWN", "score": None,
                "latency_ms": latency_ms, "error": error,
            })
            continue
        started = time.perf_counter()
        fused = mean_l2_normalize([row[0] for row in vectors])
        result = arcface.identify_embedding(
            fused, threshold=thresholds["ArcFace_MULTI_FRAME_MEAN"], strategy=MAX
        )
        latency_ms += (time.perf_counter() - started) * 1000.0 + result["matching_latency_ms"]
        fusion_multi.append({
            "expected_id": expected_id, "predicted_id": result["predicted_id"],
            "score": result["score"], "latency_ms": latency_ms, "error": "",
        })

    results_path = results_dir / "results.csv"
    _write_csv(
        results_path,
        ["algorithm", "image", "expected_id", "predicted_id", "score", "match", "correct", "latency_ms", "error"],
        model_rows,
    )
    summary_fields = ["strategy", "accuracy", "far", "frr", "avg_latency_ms", "fps"]
    matching_rows = [
        _summary_values(MAX, matching_max),
        _summary_values(TOP2_MEAN, matching_top2),
    ]
    fusion_rows = [
        _summary_values("SINGLE_FRAME", fusion_single),
        _summary_values("MULTI_FRAME_MEAN", fusion_multi),
    ]
    _write_csv(results_dir / "matching_summary.csv", summary_fields, matching_rows)
    _write_csv(results_dir / "fusion_summary.csv", summary_fields, fusion_rows)

    if __package__:
        from .metrics import summarize
    else:
        from metrics import summarize
    summarize(results_path, results_dir / "summary.csv", results_dir / "config.json")
    LOG.info("Wrote model, matching, and fusion results under %s", results_dir)
    return results_path


def _summary_values(strategy: str, rows: list[dict]) -> dict:
    if not rows:
        raise ValueError(f"No evaluated samples for {strategy}; refusing to write an empty summary.")
    known = [row for row in rows if str(row["expected_id"]) != "UNKNOWN"]
    unknown = [row for row in rows if str(row["expected_id"]) == "UNKNOWN"]
    correct = sum(str(row["expected_id"]) == str(row["predicted_id"]) for row in rows)
    false_accept = sum(str(row["predicted_id"]) != "UNKNOWN" for row in unknown)
    false_reject = sum(str(row["predicted_id"]) == "UNKNOWN" for row in known)
    latencies = [float(row["latency_ms"]) for row in rows if row.get("latency_ms") is not None]
    average = sum(latencies) / len(latencies) if latencies else None
    return {
        "strategy": strategy,
        "accuracy": correct / len(rows),
        "far": false_accept / len(unknown) if unknown else "",
        "frr": false_reject / len(known) if known else "",
        "avg_latency_ms": average if average is not None else "",
        "fps": 1000.0 / average if average and average > 0 else "",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=HERE / "dataset")
    parser.add_argument("--results", type=Path, default=HERE / "results")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s: %(message)s",
    )
    try:
        run_benchmark(args.dataset.resolve(), args.results.resolve())
    except Exception as exc:
        LOG.error("Benchmark not run: %s", exc)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
