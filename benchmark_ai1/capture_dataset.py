"""Manually capture independent benchmark face images from a webcam (no AI or DB)."""

from __future__ import annotations

import argparse
import os
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path


HERE = Path(__file__).resolve().parent
DATASET_ROOT = HERE / "dataset"
SPLITS = ("train", "validation", "test")
POSES = ("frontal", "left", "right", "up", "down")
VARIATIONS = (
    "natural distance / expression",
    "slightly closer",
    "slightly farther",
    "slightly different light",
    "subtle expression change",
)


def validate_identity(value: str) -> str:
    if value == "UNKNOWN" or re.fullmatch(r"MaNV_[1-9][0-9]*", value):
        return value
    raise ValueError("ID must be UNKNOWN or match MaNV_<positive integer>, for example MaNV_1.")


def dataset_path_for(identity: str, split: str, dataset_root: Path = DATASET_ROOT) -> Path:
    """Resolve a permitted dataset folder and verify it stays inside dataset_root."""
    identity = validate_identity(identity)
    if split not in SPLITS:
        raise ValueError(f"split must be one of: {', '.join(SPLITS)}")
    if identity == "UNKNOWN" and split == "train":
        raise ValueError("UNKNOWN identities cannot be enrolled in the training split.")
    root = Path(dataset_root).resolve()
    target = (root / split / identity).resolve()
    if not target.is_relative_to(root):
        raise ValueError("Dataset path escapes the benchmark dataset directory.")
    return target


def ensure_dataset_structure(dataset_root: Path = DATASET_ROOT) -> None:
    """Create the requested known/unknown split folders without copying any images."""
    for split, identities in (
        ("train", ("MaNV_1", "MaNV_2")),
        ("validation", ("MaNV_1", "MaNV_2", "UNKNOWN")),
        ("test", ("MaNV_1", "MaNV_2", "UNKNOWN")),
    ):
        for identity in identities:
            dataset_path_for(identity, split, dataset_root).mkdir(parents=True, exist_ok=True)


def open_webcam(cv2_module):
    """Try MSMF, DSHOW, then default backend over camera indexes 0 through 5."""
    backends = (
        ("MSMF", getattr(cv2_module, "CAP_MSMF", None)),
        ("DSHOW", getattr(cv2_module, "CAP_DSHOW", None)),
        ("default", None),
    )
    for backend_name, backend in backends:
        for index in range(6):
            capture = None
            try:
                capture = (
                    cv2_module.VideoCapture(index)
                    if backend is None
                    else cv2_module.VideoCapture(index, backend)
                )
                if not capture.isOpened():
                    capture.release()
                    continue
                capture.set(cv2_module.CAP_PROP_FRAME_WIDTH, 640)
                capture.set(cv2_module.CAP_PROP_FRAME_HEIGHT, 480)
                ok, frame = capture.read()
                if ok and frame is not None and getattr(frame, "ndim", 0) == 3 and frame.size:
                    print(f"Webcam opened: index={index}, backend={backend_name}, frame={frame.shape[1]}x{frame.shape[0]}")
                    return capture, frame, index, backend_name
            except Exception:
                pass
            if capture is not None:
                capture.release()
    return None, None, None, None


def _pose_instruction(captured: int) -> str:
    pose = POSES[captured % len(POSES)]
    variation = VARIATIONS[(captured // len(POSES)) % len(VARIATIONS)]
    return f"{pose} | {variation}"


def _draw_overlay(cv2_module, frame, identity: str, split: str, captured: int, count: int) -> None:
    pose = _pose_instruction(captured)
    lines = (
        f"ID: {identity}    split: {split}",
        f"Captured: {captured}/{count}",
        f"Pose guide: {pose}",
        "SPACE: save one frame    Q / ESC: quit",
        "Pose guide is manual; no face recognition is running.",
    )
    cv2_module.rectangle(frame, (8, 8), (min(frame.shape[1] - 8, 760), 132), (20, 20, 20), -1)
    for index, line in enumerate(lines):
        cv2_module.putText(
            frame,
            line,
            (18, 32 + index * 23),
            cv2_module.FONT_HERSHEY_SIMPLEX,
            0.56,
            (235, 245, 255),
            1,
            cv2_module.LINE_AA,
        )


def _save_unique(cv2_module, frame, output_dir: Path, identity: str, split: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    for _ in range(10):
        filename = f"{identity}_{split}_{timestamp}_{uuid.uuid4().hex[:8]}.jpg"
        path = output_dir / filename
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            continue
        os.close(descriptor)
        try:
            if not cv2_module.imwrite(str(path), frame, [cv2_module.IMWRITE_JPEG_QUALITY, 95]):
                raise OSError("OpenCV could not encode the captured frame.")
            return path
        except Exception:
            path.unlink(missing_ok=True)
            raise
    raise FileExistsError("Could not allocate a unique image filename after 10 attempts.")


def capture(identity: str, split: str, count: int, dataset_root: Path = DATASET_ROOT) -> int:
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("OpenCV is required. Install it with: python -m pip install opencv-python") from exc

    output_dir = dataset_path_for(identity, split, dataset_root)
    ensure_dataset_structure(dataset_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    camera, frame, _, _ = open_webcam(cv2)
    if camera is None:
        raise RuntimeError("Could not open a webcam with MSMF, DSHOW, or the default backend at indexes 0..5.")

    captured = 0
    window = f"Benchmark dataset capture - {identity} - {split}"
    print("Preview started. Press SPACE to save one current frame; Q or ESC exits.")
    try:
        while captured < count:
            ok, current = camera.read()
            if not ok or current is None or current.ndim != 3 or not current.size:
                print("Warning: webcam frame read failed; retrying.")
                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), 27):
                    break
                continue
            preview = current.copy()
            _draw_overlay(cv2, preview, identity, split, captured, count)
            cv2.imshow(window, preview)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            if key == 32:
                saved = _save_unique(cv2, current, output_dir, identity, split)
                captured += 1
                print(f"Saved {captured}/{count}: {saved}")
        return captured
    finally:
        camera.release()
        cv2.destroyAllWindows()


def positive_count(value: str) -> int:
    try:
        count = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("count must be a positive integer") from exc
    if count < 1:
        raise argparse.ArgumentTypeError("count must be a positive integer")
    return count


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--id", required=True, help="MaNV_<positive integer> or UNKNOWN")
    parser.add_argument("--split", required=True, choices=SPLITS)
    parser.add_argument("--count", required=True, type=positive_count, help="Number of manually captured images")
    args = parser.parse_args(argv)
    try:
        identity = validate_identity(args.id)
        saved = capture(identity, args.split, args.count)
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"Capture failed: {exc}", file=sys.stderr)
        return 2
    print(f"Finished: captured {saved}/{args.count} image(s) for {identity} in {args.split}.")
    return 0 if saved == args.count else 1


if __name__ == "__main__":
    raise SystemExit(main())
