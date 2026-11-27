"""Realtime, read-only webcam diagnostic for the project's AI1 face matcher."""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PHP_CLI = os.getenv("PHP_CLI", r"C:\xampp\php\php.exe")
THRESHOLD = 0.45
CAMERA_INDICES = tuple(range(6))
CAMERA_BACKENDS = (
    ("MSMF", cv2.CAP_MSMF),
    ("DSHOW", cv2.CAP_DSHOW),
    ("DEFAULT", None),
)
CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480
DETECT_EVERY_N_FRAMES = 3
PREVIEW_WIDTH = 480
PREVIEW_HEIGHT = 360
WINDOW_TITLE = "AI1 Webcam Test - Q/ESC to quit"

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)


def load_read_only_gallery():
    """Load FaceEmbedding rows through the project's PHP PDO config and AI1 matcher."""
    php_script = r'''require_once "Model/Database.php";
$sql = "SELECT fe.MaEmbedding, fe.MaNV, fe.VectorData, fe.SoChieu, nv.HoTen " .
       "FROM FaceEmbedding fe JOIN NhanVien nv ON nv.MaNV = fe.MaNV " .
       "ORDER BY fe.MaNV, fe.MaEmbedding";
$rows = Database::getConnection()->query($sql)->fetchAll(PDO::FETCH_ASSOC);
$payload = [];
foreach ($rows as $row) {
    $payload[] = [
        (int)$row["MaEmbedding"],
        (int)$row["MaNV"],
        base64_encode($row["VectorData"]),
        (int)$row["SoChieu"],
        base64_encode($row["HoTen"]),
    ];
}
echo json_encode($payload, JSON_THROW_ON_ERROR);'''

    try:
        result = subprocess.run(
            [PHP_CLI, "-r", php_script],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(
            "Không đọc được gallery bằng PHP PDO. Hãy kiểm tra PHP CLI và MariaDB."
        ) from exc

    try:
        payload = json.loads(result.stdout)
        rows = [
            (
                int(item[0]),
                int(item[1]),
                base64.b64decode(item[2], validate=True),
                int(item[3]),
                base64.b64decode(item[4], validate=True).decode("utf-8"),
            )
            for item in payload
        ]
    except (ValueError, TypeError, IndexError, UnicodeDecodeError) as exc:
        raise RuntimeError("Dữ liệu gallery từ PHP không hợp lệ.") from exc

    # Import from the project root without duplicating the AI1 matching implementation.
    sys.path.insert(0, str(PROJECT_ROOT))
    from face_matching import aggregate_gallery

    gallery, invalid_rows = aggregate_gallery(rows)
    if invalid_rows:
        bad_ids = ", ".join(str(row.get("MaEmbedding")) for row in invalid_rows)
        raise RuntimeError(f"Gallery có embedding không hợp lệ (MaEmbedding: {bad_ids}).")

    return gallery, len(rows)


def open_camera():
    """Try each Windows backend/index and accept only a camera yielding five frames."""
    for backend_name, backend_id in CAMERA_BACKENDS:
        for camera_index in CAMERA_INDICES:
            if backend_id is None:
                capture = cv2.VideoCapture(camera_index)
            else:
                capture = cv2.VideoCapture(camera_index, backend_id)

            opened = capture.isOpened()
            frames_read = 0
            last_frame = None
            if opened:
                _configure_camera(capture)
                for _ in range(5):
                    ok, frame = capture.read()
                    if ok and isinstance(frame, np.ndarray) and frame.size > 0 and frame.ndim >= 2:
                        frames_read += 1
                        last_frame = frame

            frame_status = "PASS" if frames_read == 5 else "FAIL"
            print(
                f"backend={backend_name} index={camera_index} "
                f"opened={'YES' if opened else 'NO'} "
                f"frame read={frame_status} ({frames_read}/5)"
            )
            if opened and frames_read == 5:
                return backend_name, camera_index, capture, last_frame
            capture.release()

    raise RuntimeError("OpenCV không thấy thiết bị camera: không tổ hợp backend/index nào đọc đủ 5 frame.")


def _configure_camera(capture):
    """Request the low-latency preview size and a one-frame camera buffer."""
    capture.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
    capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)


def detect_preview_faces(engine, frame, min_score=0.0):
    """Run only buffalo_l's detector on a smaller preview, returning full-size boxes."""
    preview = cv2.resize(frame, (PREVIEW_WIDTH, PREVIEW_HEIGHT), interpolation=cv2.INTER_AREA)
    detector = engine._app.det_model
    boxes, _ = detector.detect(preview, input_size=(640, 640), max_num=0)
    if boxes is None or len(boxes) == 0:
        return []

    scale_x = frame.shape[1] / PREVIEW_WIDTH
    scale_y = frame.shape[0] / PREVIEW_HEIGHT
    results = []
    for row in boxes:
        x1, y1, x2, y2, score = [float(value) for value in row[:5]]
        if score < min_score or x2 <= x1 or y2 <= y1:
            continue
        results.append({
            "bbox": np.asarray(
                [x1 * scale_x, y1 * scale_y, x2 * scale_x, y2 * scale_y],
                dtype=np.float32,
            ),
            "detection_score": score,
        })
    return results


def draw_hud(frame, lines):
    """Draw a lightweight OpenCV HUD without per-frame PIL image conversion."""
    for text, y, color, scale in lines:
        cv2.putText(
            frame,
            text,
            (14, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            scale,
            color,
            2,
            cv2.LINE_AA,
        )


def draw_face_box(frame, face, color, label=None):
    """Draw one detected face's bounding box and optional result label."""
    height, width = frame.shape[:2]
    x1, y1, x2, y2 = [int(round(value)) for value in face["bbox"]]
    x1, x2 = max(0, min(width - 1, x1)), max(0, min(width - 1, x2))
    y1, y2 = max(0, min(height - 1, y1)), max(0, min(height - 1, y2))
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
    if label:
        cv2.putText(frame, label, (x1, max(24, y1 - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2, cv2.LINE_AA)


def main():
    """Open AI1 and the SQL-backed gallery, then run live recognition until Q/ESC."""
    sys.path.insert(0, str(PROJECT_ROOT))
    import face_engine
    from face_matching import identify_embedding

    camera_backend, camera_index, camera, first_frame = open_camera()
    try:
        face_engine.face_engine.initialize()
        gallery, embedding_count = load_read_only_gallery()
        if not gallery:
            raise RuntimeError("MariaDB chưa có embedding khuôn mặt hợp lệ.")

        print(f"Gallery employees: {len(gallery)}")
        print(f"Gallery embeddings: {embedding_count}")
        print(f"Model: {face_engine.MODEL_NAME}")
        print(f"Threshold: {THRESHOLD:.2f}")
        print(f"Camera backend: {camera_backend}")
        print(f"Camera index: {camera_index}")
        print(f"Camera request: {CAMERA_WIDTH}x{CAMERA_HEIGHT}, buffer=1")
        print(f"Preview detection interval: every {DETECT_EVERY_N_FRAMES} frames")
        print("Q / ESC: thoát. Tool chỉ đọc database, không ghi dữ liệu.")

        cv2.namedWindow(WINDOW_TITLE, cv2.WINDOW_NORMAL)
        last_result = None
        faces = []
        frame_count = 0
        pending_frame = first_frame
        previous_frame_time = time.perf_counter()
        fps = 0.0
        while True:
            if pending_frame is not None:
                frame = pending_frame
                pending_frame = None
            else:
                ok, frame = camera.read()
                if not ok or frame is None:
                    print("Webcam không trả frame; đang dừng.")
                    break

            source_frame = frame
            if frame_count == 0:
                actual_width, actual_height = source_frame.shape[1], source_frame.shape[0]
                print(f"Camera actual resolution: {actual_width}x{actual_height}")
            frame_count += 1
            if frame_count % DETECT_EVERY_N_FRAMES == 1:
                faces = detect_preview_faces(
                    face_engine.face_engine,
                    source_frame,
                    min_score=face_engine.DETECTION_MIN_SCORE,
                )

            frame_time = time.perf_counter()
            instant_fps = 1.0 / max(frame_time - previous_frame_time, 1e-6)
            fps = instant_fps if fps == 0 else (0.85 * fps + 0.15 * instant_fps)
            previous_frame_time = frame_time

            if not faces:
                last_result = None
                face_status = "NO FACE"
                face_color = (0, 210, 255)
            elif len(faces) > 1:
                last_result = None
                face_status = f"MULTIPLE FACES: {len(faces)} - IDENTIFY DISABLED"
                face_color = (0, 165, 255)
            else:
                face_status = "SPACE: Identify"
                face_color = (0, 220, 0)

            display_frame = source_frame.copy()
            for index, face in enumerate(faces, start=1):
                confidence = float(face["detection_score"])
                draw_face_box(
                    display_frame,
                    face,
                    (0, int(220 * confidence), int(255 * (1.0 - confidence))),
                    f"Face {index} | Det: {confidence:.2f}",
                )

            text_rows = [
                ("PBL4 AI1 TEST", 28, (0, 220, 255), 0.7),
                (f"Model: {face_engine.MODEL_NAME} | FPS: {fps:.1f}",
                 55, (235, 235, 235), 0.58),
                (f"Faces: {len(faces)} | {face_status}", 82, face_color, 0.58),
                ("SPACE = Identify    Q / ESC = Quit", 109, (235, 235, 235), 0.5),
            ]

            if last_result:
                result_y = max(136, display_frame.shape[0] - 112)
                if last_result["match"]:
                    matched_id = last_result["MaNV"]
                    person = gallery[matched_id]
                    name = person["HoTen"] or "(chưa có họ tên)"
                    name = name if len(name) <= 38 else name[:35] + "..."
                    score = float(last_result["similarity"])
                    text_rows.extend([
                        ("MATCH", result_y, (0, 220, 0), 0.65),
                        (f"MaNV: {matched_id} | {name}", result_y + 27, (0, 220, 0), 0.55),
                        (f"Similarity: {score:.3f} | Threshold: {THRESHOLD:.2f}",
                         result_y + 52, (0, 220, 0), 0.52),
                    ])
                else:
                    score = last_result["similarity"]
                    score_text = "N/A" if score is None else f"{float(score):.3f}"
                    text_rows.extend([
                        ("UNKNOWN", result_y, (0, 165, 255), 0.65),
                        (f"Best similarity: {score_text} | Threshold: {THRESHOLD:.2f}",
                         result_y + 29, (0, 165, 255), 0.52),
                    ])

            draw_hud(display_frame, text_rows)
            cv2.imshow(WINDOW_TITLE, display_frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            if key == ord(" "):
                # Identify using the current full-resolution frame, never the cached preview.
                full_faces = face_engine.face_engine.detect_embeddings(source_frame)
                if len(full_faces) == 1:
                    last_result = identify_embedding(full_faces[0]["embedding"], gallery, THRESHOLD)
                    if last_result["match"]:
                        print(
                            f"MATCH MaNV={last_result['MaNV']} "
                            f"similarity={last_result['similarity']:.3f}"
                        )
                    else:
                        print(
                            f"UNKNOWN best_similarity={last_result['similarity']:.3f} "
                            f"threshold={THRESHOLD:.2f}"
                        )
                elif len(full_faces) > 1:
                    last_result = {"match": False, "similarity": None}
                    print("MULTIPLE FACES: identify skipped.")
                else:
                    last_result = {"match": False, "similarity": None}
                    print("NO FACE: identify skipped.")
    finally:
        camera.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"AI1 webcam test failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
