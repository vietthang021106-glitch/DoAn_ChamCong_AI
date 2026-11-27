"""Interactive single-frame AI1 recognition test."""

import argparse
from datetime import datetime
from pathlib import Path
import secrets
import sys

import cv2

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from test_ai1_full.ai1_adapter import identify_frame, initialize_model
from test_ai1_full.camera_source import WebcamSource
from test_ai1_full.config import RECOGNITION_THRESHOLD
from test_ai1_full.gallery_io import DEFAULT_GALLERY_PATH, load_gallery
from test_ai1_full.result_logger import log_result
from test_ai1_full.utils import CAPTURES_ROOT, configure_console, ensure_test_directories, validate_identity


def _expected_arg(value):
    if value is None:
        return None
    return "UNKNOWN" if value.upper() == "UNKNOWN" else validate_identity(value)


def save_test_capture(frame):
    ensure_test_directories()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    for _ in range(1000):
        path = CAPTURES_ROOT / f"{stamp}_{secrets.randbelow(1000):03d}.jpg"
        if not path.exists() and cv2.imwrite(str(path), frame, [cv2.IMWRITE_JPEG_QUALITY, 95]):
            return path
    raise RuntimeError("Không tạo được tên file ảnh test duy nhất.")


def main(argv=None):
    configure_console()
    parser = argparse.ArgumentParser(description="Interactive single-frame AI1 recognition test.")
    parser.add_argument("--expected", help="Expected ID hoặc UNKNOWN; bỏ trống để không tính correct.")
    parser.add_argument("--gallery", default=str(DEFAULT_GALLERY_PATH))
    args = parser.parse_args(argv)
    try:
        expected = _expected_arg(args.expected)
        gallery = load_gallery(args.gallery)
        initialize_model()
        source = WebcamSource()
    except Exception as exc:
        print(f"Không thể bắt đầu single-frame test: {exc}", file=sys.stderr)
        return 2

    print(f"Webcam index {source.camera_index}, backend {source.backend_name}.")
    print("SPACE: nhận diện frame hiện tại | S: lưu ảnh test | Q/ESC: thoát")
    latest = None
    latest_expected = expected
    try:
        while True:
            frame = source.get_frame()
            if frame is None:
                continue
            preview = frame.copy()
            lines = ["SINGLE FRAME", "SPACE: recognize  S: save  Q: quit"]
            if latest is None:
                lines += [f"expected: {expected or '(khong tinh correct)'}", f"threshold: {RECOGNITION_THRESHOLD:.3f}"]
            else:
                lines += [f"predicted: {latest['predicted_id']}", f"score: {latest['score']:.4f}",
                          f"threshold: {RECOGNITION_THRESHOLD:.3f}", f"latency: {latest['latency_ms']:.1f} ms",
                          f"expected: {latest_expected or '(khong tinh correct)'}",
                          f"correct: {str(latest_expected is not None and latest['predicted_id'] == latest_expected).upper() if latest_expected is not None else 'N/A'}",
                          latest['reason'][:90]]
            for i, line in enumerate(lines):
                cv2.putText(preview, line, (12, 28 + 27 * i), cv2.FONT_HERSHEY_SIMPLEX,
                            0.62, (40, 240, 240), 2, cv2.LINE_AA)
            cv2.imshow("AI1 single-frame test", preview)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            if key == ord("s"):
                print(f"Đã lưu ảnh test: {save_test_capture(frame)}")
            elif key == ord(" "):
                latest = identify_frame(frame, gallery, RECOGNITION_THRESHOLD)
                latest_expected = expected
                log_result("SINGLE", expected, latest, RECOGNITION_THRESHOLD)
                print(latest)
    finally:
        source.release()
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
