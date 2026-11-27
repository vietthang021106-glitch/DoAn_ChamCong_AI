"""Interactive three-frame mean-fusion AI1 recognition test."""

import argparse
import time
from pathlib import Path
import sys

import cv2

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from test_ai1_full.ai1_adapter import extract_single_face_embedding, identify_embedding, initialize_model
from test_ai1_full.camera_source import WebcamSource
from test_ai1_full.config import CONSISTENCY_THRESHOLD, FRAME_INTERVAL_MS, RECOGNITION_THRESHOLD
from test_ai1_full.gallery_io import DEFAULT_GALLERY_PATH, load_gallery
from test_ai1_full.recognition import check_frame_consistency, fuse_three_embeddings
from test_ai1_full.result_logger import log_result
from test_ai1_full.test_single_frame import _expected_arg, save_test_capture
from test_ai1_full.utils import configure_console, ensure_test_directories


def capture_sequence_embeddings(source):
    """Capture and embed exactly three time-separated frames; partial sequences fail."""
    frames, embeddings, per_frame_ms = [], [], []
    extraction_ms = 0.0
    for index in range(3):
        frame = source.get_frame()
        if frame is None:
            return frames, embeddings, extraction_ms, per_frame_ms, f"Không đọc được frame {index + 1}/3."
        frames.append(frame)
        extracted = extract_single_face_embedding(frame)
        extraction_ms += extracted["latency_ms"]
        per_frame_ms.append(extracted["latency_ms"])
        if extracted["status"] != "OK":
            return frames, embeddings, extraction_ms, per_frame_ms, f"Frame {index + 1}/3: {extracted['reason']}"
        embeddings.append(extracted["embedding"])
        if index < 2:
            time.sleep(FRAME_INTERVAL_MS / 1000.0)
    return frames, embeddings, extraction_ms, per_frame_ms, None


def recognize_sequence(embeddings, gallery, extraction_ms=0.0, error=None):
    """Check consistency, mean exactly three embeddings, normalize, then production MAX match."""
    compute_started = time.perf_counter()
    if error:
        return {"status": "RETRY", "predicted_id": "UNKNOWN", "score": 0.0,
                "reason": error, "latency_ms": float(extraction_ms) +
                (time.perf_counter() - compute_started) * 1000.0}
    consistency = check_frame_consistency(embeddings, CONSISTENCY_THRESHOLD)
    if not consistency["valid"]:
        return {"status": "RETRY", "predicted_id": "UNKNOWN", "score": 0.0,
                "reason": consistency["reason"], "latency_ms": float(extraction_ms) +
                (time.perf_counter() - compute_started) * 1000.0}
    try:
        fused = fuse_three_embeddings(embeddings)
    except (TypeError, ValueError) as exc:
        return {"status": "RETRY", "predicted_id": "UNKNOWN", "score": 0.0,
                "reason": f"Không fusion được sequence: {exc}", "latency_ms": float(extraction_ms) +
                (time.perf_counter() - compute_started) * 1000.0}
    matched = identify_embedding(fused, gallery, RECOGNITION_THRESHOLD)
    matched["latency_ms"] = float(extraction_ms) + (time.perf_counter() - compute_started) * 1000.0
    matched["reason"] = f"{matched['reason']} Consistency min={consistency['min_similarity']:.3f}."
    return matched


def main(argv=None):
    configure_console()
    parser = argparse.ArgumentParser(description="Interactive 3-frame ArcFace mean-fusion test.")
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
        print(f"Không thể bắt đầu multi-frame test: {exc}", file=sys.stderr)
        return 2

    print(f"Webcam index {source.camera_index}, backend {source.backend_name}.")
    print("SPACE: capture + recognize 3 frames | S: lưu ảnh hiện tại | Q/ESC: thoát")
    latest = None
    try:
        while True:
            frame = source.get_frame()
            if frame is None:
                continue
            preview = frame.copy()
            lines = ["MULTI FRAME MEAN (3)", "SPACE: 3 frames, gap 300 ms | S: save | Q: quit",
                     f"expected: {expected or '(khong tinh correct)'}",
                     f"threshold: {RECOGNITION_THRESHOLD:.3f} | consistency: {CONSISTENCY_THRESHOLD:.2f}"]
            if latest:
                lines += [f"predicted: {latest['predicted_id']}", f"score: {latest['score']:.4f}",
                          f"latency: {latest['latency_ms']:.1f} ms", f"correct: {str(latest['predicted_id'] == expected).upper() if expected is not None else 'N/A'}",
                          latest['reason'][:90]]
            for i, line in enumerate(lines):
                cv2.putText(preview, line, (12, 28 + 27 * i), cv2.FONT_HERSHEY_SIMPLEX,
                            0.58, (40, 240, 240), 2, cv2.LINE_AA)
            cv2.imshow("AI1 multi-frame test", preview)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            if key == ord("s"):
                print(f"Đã lưu ảnh test: {save_test_capture(frame)}")
            elif key == ord(" "):
                frames, embeddings, extraction_ms, _, error = capture_sequence_embeddings(source)
                latest = recognize_sequence(embeddings, gallery, extraction_ms, error)
                log_result("MULTI_FRAME", expected, latest, RECOGNITION_THRESHOLD)
                print(latest)
    finally:
        source.release()
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
