"""Compare single middle-frame and three-frame mean from one captured sequence."""

import argparse
from pathlib import Path
import sys

import cv2

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from test_ai1_full.ai1_adapter import identify_embedding, initialize_model
from test_ai1_full.camera_source import WebcamSource
from test_ai1_full.config import RECOGNITION_THRESHOLD
from test_ai1_full.gallery_io import DEFAULT_GALLERY_PATH, load_gallery
from test_ai1_full.result_logger import log_result
from test_ai1_full.test_multi_frame import capture_sequence_embeddings, recognize_sequence
from test_ai1_full.test_single_frame import _expected_arg, save_test_capture
from test_ai1_full.utils import configure_console, ensure_test_directories


def compare_sequence(embeddings, gallery, extraction_ms, frame_latencies=None, error=None):
    if error and len(embeddings) <= 1:
        retry = {"status": "RETRY", "predicted_id": "UNKNOWN", "score": 0.0,
                 "reason": error, "latency_ms": float(extraction_ms)}
        return retry, retry.copy()
    single = identify_embedding(embeddings[1], gallery, RECOGNITION_THRESHOLD)
    single["latency_ms"] += (frame_latencies[1] if frame_latencies and len(frame_latencies) > 1
                             else extraction_ms / 3.0)
    multi = recognize_sequence(embeddings, gallery, extraction_ms, error)
    return single, multi


def main(argv=None):
    configure_console()
    parser = argparse.ArgumentParser(description="Compare AI1 single vs 3-frame mean on the same frames.")
    parser.add_argument("--expected", help="Expected ID hoặc UNKNOWN; bỏ trống để không tính correct.")
    parser.add_argument("--gallery", default=str(DEFAULT_GALLERY_PATH))
    args = parser.parse_args(argv)
    try:
        expected = _expected_arg(args.expected)
        gallery = load_gallery(args.gallery)
        initialize_model()
        ensure_test_directories()
        source = WebcamSource()
    except Exception as exc:
        print(f"Không thể bắt đầu compare test: {exc}", file=sys.stderr)
        return 2

    print(f"Webcam index {source.camera_index}, backend {source.backend_name}.")
    print("SPACE: so sánh trên cùng 3 frame | S: lưu ảnh hiện tại | Q/ESC: thoát")
    single = multi = None
    try:
        while True:
            frame = source.get_frame()
            if frame is None:
                continue
            preview = frame.copy()
            lines = ["COMPARE SINGLE vs MULTI", "SPACE: capture sequence | S: save image | Q: quit",
                     f"expected: {expected or '(khong tinh correct)'}"]
            for name, result, offset in (("SINGLE", single, 0), ("MULTI", multi, 5)):
                if result is None:
                    lines.append(f"{name}: waiting")
                else:
                    is_correct = str(result["predicted_id"] == expected).upper() if expected is not None else "N/A"
                    lines.extend([f"{name} predicted: {result['predicted_id']}",
                                  f"{name} score: {result['score']:.4f} | {result['latency_ms']:.1f} ms",
                                  f"{name} correct: {is_correct}"])
            for i, line in enumerate(lines):
                cv2.putText(preview, line, (12, 28 + 25 * i), cv2.FONT_HERSHEY_SIMPLEX,
                            0.55, (40, 240, 240), 2, cv2.LINE_AA)
            cv2.imshow("AI1 single vs multi comparison", preview)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            if key == ord("s"):
                print(f"Đã lưu ảnh test: {save_test_capture(frame)}")
            elif key == ord(" "):
                frames, embeddings, extraction_ms, frame_latencies, error = capture_sequence_embeddings(source)
                single, multi = compare_sequence(embeddings, gallery, extraction_ms, frame_latencies, error)
                log_result("SINGLE", expected, single, RECOGNITION_THRESHOLD)
                log_result("MULTI_FRAME", expected, multi, RECOGNITION_THRESHOLD)
                print({"single": single, "multi_frame": multi})
    finally:
        source.release()
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
