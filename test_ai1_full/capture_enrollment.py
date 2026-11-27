"""Capture five guided, production-validated ArcFace enrollment poses to disk."""

import argparse
from pathlib import Path
import sys

import cv2

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from test_ai1_full.ai1_adapter import initialize_model, production_pose_label
from test_ai1_full.config import ENROLLMENT_POSES
from test_ai1_full.camera_source import WebcamSource
from test_ai1_full.utils import (ENROLLMENT_ROOT, configure_console, ensure_test_directories,
                                 safe_identity_path, validate_identity)
import face_engine
import face_matching


def _inspect_enrollment_frame(engine, frame, expected_pose):
    faces = engine.detect_embeddings(frame)
    if not faces:
        return None, "Không phát hiện được khuôn mặt hợp lệ."
    if len(faces) != 1:
        return None, "Cần đúng một khuôn mặt trong ảnh."
    face = faces[0]
    quality = face_engine.assess_capture_quality(frame, face)
    if not quality.get("ready"):
        return None, quality.get("instruction", "Ảnh không đạt kiểm tra chất lượng AI1.")
    try:
        embedding = face_matching.normalize_embedding(face.get("embedding"), 512)
    except (TypeError, ValueError) as exc:
        return None, f"Embedding không hợp lệ: {exc}"
    if embedding.shape != (512,):
        return None, "Embedding phải có đúng 512 chiều."
    pose = production_pose_label(face)
    if pose != expected_pose:
        return None, f"Hướng hiện tại: {pose}; cần: {expected_pose}."
    return {"face": face, "embedding": embedding, "pose": pose}, "Ảnh đạt kiểm tra."


def capture(identity, overwrite=False):
    identity = validate_identity(identity)
    if identity.upper() == "UNKNOWN":
        raise ValueError("UNKNOWN không được enrollment vào gallery.")
    ensure_test_directories()
    destination = safe_identity_path(ENROLLMENT_ROOT, identity)
    destination.mkdir(parents=True, exist_ok=True)
    targets = [destination / f"{pose}.jpg" for pose in ENROLLMENT_POSES]
    existing = [path for path in targets if path.exists()]
    if existing and not overwrite:
        raise FileExistsError(
            "Ảnh enrollment đã tồn tại; không ghi đè âm thầm. Dùng --overwrite nếu muốn chụp lại: "
            + ", ".join(path.name for path in existing)
        )

    engine = initialize_model()
    source = WebcamSource()
    print(f"Webcam index {source.camera_index}, backend {source.backend_name}.")
    print("SPACE: chụp pose hiện tại | R: chụp lại pose vừa lưu | Q/ESC: thoát")
    captured = (set() if overwrite else
                {pose for pose in ENROLLMENT_POSES if (destination / f"{pose}.jpg").is_file()})
    current_index = (0 if overwrite else
                     next((i for i, pose in enumerate(ENROLLMENT_POSES) if pose not in captured), len(ENROLLMENT_POSES) - 1))
    latest_message = "Đặt khuôn mặt theo hướng yêu cầu rồi nhấn SPACE."
    latest_detected_pose = "unknown"
    try:
        while True:
            frame = source.get_frame()
            if frame is None:
                latest_message = "Không đọc được frame từ webcam."
                key = cv2.waitKey(30) & 0xFF
                if key in (ord("q"), 27):
                    break
                continue

            current_pose = ENROLLMENT_POSES[current_index]
            preview = frame.copy()
            cv2.putText(preview, f"ID: {identity}", (14, 28), cv2.FONT_HERSHEY_SIMPLEX,
                        0.7, (30, 240, 240), 2, cv2.LINE_AA)
            cv2.putText(preview, f"POSE: {current_pose.upper()}", (14, 58), cv2.FONT_HERSHEY_SIMPLEX,
                        0.7, (30, 240, 240), 2, cv2.LINE_AA)
            cv2.putText(preview, f"CAPTURED {len(captured)}/5", (14, 88), cv2.FONT_HERSHEY_SIMPLEX,
                        0.7, (30, 240, 240), 2, cv2.LINE_AA)
            cv2.putText(preview, f"DETECTED: {latest_detected_pose}", (14, 118), cv2.FONT_HERSHEY_SIMPLEX,
                        0.62, (255, 210, 40), 2, cv2.LINE_AA)
            cv2.putText(preview, latest_message[:85], (14, preview.shape[0] - 18), cv2.FONT_HERSHEY_SIMPLEX,
                        0.48, (40, 255, 80) if "đạt" in latest_message.lower() else (40, 180, 255),
                        1, cv2.LINE_AA)
            cv2.imshow("AI1 enrollment capture", preview)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break

            if key not in (ord(" "), ord("r")):
                continue
            retake = key == ord("r")
            target_pose = current_pose
            target_path = destination / f"{target_pose}.jpg"
            if target_path.exists() and not (overwrite or retake):
                latest_message = "File đã tồn tại; dùng --overwrite hoặc R để chụp lại pose vừa lưu."
                continue
            valid, latest_message = _inspect_enrollment_frame(engine, frame, target_pose)
            latest_detected_pose = valid["pose"] if valid else "unknown"
            if valid is None:
                continue
            if not cv2.imwrite(str(target_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 95]):
                latest_message = f"Không lưu được {target_path.name}."
                continue
            captured.add(target_pose)
            missing = [i for i, pose in enumerate(ENROLLMENT_POSES) if pose not in captured]
            if missing:
                current_index = missing[0]
            else:
                current_index = len(ENROLLMENT_POSES) - 1
                latest_message = "Đã đủ 5 pose. R chụp lại pose down; Q/ESC thoát."
            print(f"Đã lưu {target_path}")
    finally:
        source.release()
        cv2.destroyAllWindows()
    print(f"Enrollment của {identity}: {len(captured)}/5 ảnh.")
    return len(captured) == 5


def main(argv=None):
    configure_console()
    parser = argparse.ArgumentParser(description="Capture five guided poses for the standalone AI1 test.")
    parser.add_argument("--id", required=True, help="Mã định danh an toàn, ví dụ MaNV_1")
    parser.add_argument("--overwrite", action="store_true", help="Cho phép ghi lại file enrollment đã tồn tại.")
    args = parser.parse_args(argv)
    try:
        complete = capture(args.id, overwrite=args.overwrite)
        return 0 if complete else 1
    except Exception as exc:
        print(f"Lỗi enrollment: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
