"""Loopback AI API; PHP remains the only owner of MariaDB access."""

import base64
import binascii
import hashlib
import json
import os
import threading
import urllib.request

import cv2
import numpy as np
from flask import Flask, jsonify, request, Response

import face_engine
from face_matching import aggregate_gallery, identify_embedding


PHP_GALLERY_URL = os.getenv(
    "PHP_FACE_GALLERY_URL",
    "http://127.0.0.1:8080/?action=internal_face_gallery",
)
FLASK_CAMERA_FRAME_URL = os.getenv(
    "FLASK_CAMERA_FRAME_URL",
    "http://127.0.0.1:5000/internal/camera/frame",
)
EMBEDDING_DIMENSIONS = 512
EMBEDDING_BYTES = EMBEDDING_DIMENSIONS * np.dtype("<f4").itemsize
ENROLLMENT_POSES = ("frontal", "left", "right", "up", "down")
POSE_LABELS = {
    "frontal": "Nhìn thẳng",
    "left": "Quay trái",
    "right": "Quay phải",
    "up": "Ngẩng lên",
    "down": "Cúi xuống",
}
MAX_ENROLLMENT_IMAGE_BYTES = 5 * 1024 * 1024


def _face_bbox_area(face):
    bbox = face.get("bbox")
    if bbox is None or len(bbox) != 4:
        return 0.0
    width = max(0.0, float(bbox[2]) - float(bbox[0]))
    height = max(0.0, float(bbox[3]) - float(bbox[1]))
    return width * height


def _select_largest_face(faces):
    return max(faces, key=_face_bbox_area)


def _recognition_threshold():
    value = os.getenv("FACE_RECOGNITION_THRESHOLD", "0.45")
    try:
        threshold = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Threshold must be a number between -1 and 1.") from exc
    if not -1.0 <= threshold <= 1.0:
        raise ValueError("Threshold must be a number between -1 and 1.")
    return threshold


class AIRuntime:
    def __init__(self):
        self.engine = face_engine.face_engine
        self._lock = threading.RLock()
        self._gallery = {}
        self._gallery_loaded = False
        self._embedding_count = 0
        self._invalid_count = 0
        self._model_error = None
        self._gallery_error = None

    def initialize(self):
        """Initialize buffalo_l and load the PHP-owned face gallery into RAM."""
        try:
            self.engine.initialize()
        except Exception as exc:
            self._model_error = str(exc)
        try:
            self.refresh_gallery()
        except Exception:
            self._gallery_error = "Could not load gallery from PHP."

    def refresh_gallery(self):
        """Fetch, validate, and replace the in-memory face gallery."""
        with urllib.request.urlopen(PHP_GALLERY_URL, timeout=10) as response:
            payload = response.read()
        document = json.loads(payload.decode("utf-8"))
        if not document.get("success") or not isinstance(document.get("embeddings"), list):
            raise RuntimeError("PHP face gallery response is invalid.")

        rows = []
        for item in document["embeddings"]:
            dimensions = int(item.get("so_chieu", 0))
            raw = base64.b64decode(item["vector"], validate=True)
            if dimensions != EMBEDDING_DIMENSIONS or len(raw) != EMBEDDING_BYTES:
                raise ValueError("Face gallery contains an embedding with invalid dimensions or byte length.")
            expected_hash = item.get("sha256")
            if expected_hash and hashlib.sha256(raw).hexdigest() != expected_hash:
                raise ValueError("Face embedding checksum mismatch after HTTP/base64 decode.")
            rows.append((
                int(item["ma_embedding"]),
                int(item["ma_nv"]),
                raw,
                dimensions,
                "",
            ))

        gallery, invalid_rows = aggregate_gallery(rows)
        with self._lock:
            self._gallery = gallery
            self._embedding_count = len(rows) - len(invalid_rows)
            self._invalid_count = len(invalid_rows)
            self._gallery_loaded = True
            self._gallery_error = None

        return {
            "embedding_count": self._embedding_count,
            "employee_count": len(gallery),
            "invalid_count": self._invalid_count,
        }

    def health(self):
        with self._lock:
            model_ready = bool(self.engine._initialized)
            return {
                "success": True,
                "service": "python-ai",
                "model": face_engine.MODEL_NAME,
                "model_ready": model_ready,
                "gallery_ready": self._gallery_loaded,
                "embedding_count": self._embedding_count,
                "employee_count": len(self._gallery),
                "invalid_embeddings": self._invalid_count,
                "threshold": _recognition_threshold(),
                "camera_source": "Flask camera singleton",
                "model_error": self._model_error,
                "gallery_error": self._gallery_error,
            }

    def fetch_camera_frame(self):
        with urllib.request.urlopen(FLASK_CAMERA_FRAME_URL, timeout=5) as response:
            content_type = response.headers.get_content_type()
            if content_type != "image/jpeg":
                raise RuntimeError("Camera relay did not return a JPEG frame.")
            raw = response.read()
        frame = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            raise RuntimeError("Camera relay returned an invalid frame.")
        return raw, frame

    def recognize_frame(self, frame):
        """Recognize the largest face in a decoded BGR frame without writing attendance."""
        if not self.engine._initialized:
            raise RuntimeError("Face recognition model is unavailable.")
        with self._lock:
            if not self._gallery_loaded:
                raise RuntimeError("Face gallery is unavailable.")
            gallery = self._gallery

        faces = self.engine.detect_embeddings(frame)
        if not faces:
            return {
                "success": False,
                "match": False,
                "ma_nv": None,
                "score": None,
                "message": "Không phát hiện khuôn mặt",
            }

        selected_face = _select_largest_face(faces)
        result = identify_embedding(selected_face["embedding"], gallery, _recognition_threshold())
        return {
            "success": True,
            "match": bool(result["match"]),
            "ma_nv": int(result["MaNV"]) if result["MaNV"] is not None else None,
            "score": result["similarity"],
            "message": "Nhận diện thành công" if result["match"] else "Không nhận diện được nhân viên",
        }

    def inspect_enrollment_frame(self, frame, expected_pose):
        """Validate face count and head pose for one guided-enrollment step."""
        if not self.engine._initialized:
            raise RuntimeError("Face recognition model is unavailable.")
        faces = self.engine.detect_embeddings(frame)
        if len(faces) > 1:
            return {
                "success": True,
                "pose_ok": False,
                "current_pose": "multiple_faces",
                "expected_pose": expected_pose,
                "instruction": "Chỉ để một người trong khung hình.",
                "yaw": None,
                "pitch": None,
            }
        return _pose_result(faces[0] if faces else None, expected_pose)

    def capture_enrollment_sample(self, frame, jpeg, expected_pose):
        """Return a validated pose's embedding and its exact JPEG frame as one sample."""
        if not self.engine._initialized:
            raise RuntimeError("Face recognition model is unavailable.")
        faces = self.engine.detect_embeddings(frame)
        if len(faces) > 1:
            result = {
                "success": False,
                "pose_ok": False,
                "current_pose": "multiple_faces",
                "expected_pose": expected_pose,
                "instruction": "Chỉ để một người trong khung hình.",
                "yaw": None,
                "pitch": None,
            }
            return result

        pose = _pose_result(faces[0] if faces else None, expected_pose)
        if not pose["pose_ok"]:
            return {**pose, "success": False}

        vector = faces[0].get("vector_bytes")
        if not isinstance(vector, bytes) or len(vector) != EMBEDDING_BYTES:
            raise RuntimeError("Face model returned an invalid 512D embedding.")

        return {
            **pose,
            "success": True,
            "so_chieu": EMBEDDING_DIMENSIONS,
            "vector": base64.b64encode(vector).decode("ascii"),
            "image_jpeg": base64.b64encode(jpeg).decode("ascii"),
            "image_sha256": hashlib.sha256(jpeg).hexdigest(),
        }


runtime = AIRuntime()
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 7 * 1024 * 1024


def _classify_head_pose(yaw, pitch):
    if abs(yaw) <= 12 and abs(pitch) <= 12:
        return "frontal"
    if 15 <= yaw <= 40 and abs(pitch) <= 18:
        return "left"
    if -40 <= yaw <= -15 and abs(pitch) <= 18:
        return "right"
    if 12 <= pitch <= 35 and abs(yaw) <= 15:
        return "up"
    if -35 <= pitch <= -12 and abs(yaw) <= 15:
        return "down"
    return "between"


def _decode_enrollment_image(encoded_image):
    if not isinstance(encoded_image, str) or not encoded_image:
        raise ValueError("Thiếu ảnh enrollment.")
    try:
        raw = base64.b64decode(encoded_image, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Ảnh enrollment không hợp lệ.") from exc
    if not raw or len(raw) > MAX_ENROLLMENT_IMAGE_BYTES:
        raise ValueError("Ảnh enrollment vượt giới hạn 5 MB.")
    if not raw.startswith(b"\xff\xd8") and not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Chỉ chấp nhận ảnh JPEG hoặc PNG.")

    frame = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError("Không giải mã được ảnh enrollment.")
    if frame.shape[0] * frame.shape[1] > 16_000_000:
        raise ValueError("Kích thước ảnh enrollment quá lớn.")
    if raw.startswith(b"\xff\xd8"):
        jpeg = raw
    else:
        encoded, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
        if not encoded:
            raise ValueError("Không thể chuẩn hóa ảnh thành JPEG.")
        jpeg = buffer.tobytes()
    return frame, jpeg


def _pose_result(face, expected_pose):
    if face is None:
        return {
            "success": True,
            "pose_ok": False,
            "current_pose": "no_face",
            "expected_pose": expected_pose,
            "instruction": "Đưa khuôn mặt vào giữa khung hình.",
            "yaw": None,
            "pitch": None,
        }

    pose = face.get("head_pose")
    if not pose:
        return {
            "success": True,
            "pose_ok": False,
            "current_pose": "unknown",
            "expected_pose": expected_pose,
            "instruction": "Không ước lượng được hướng đầu; nhìn rõ camera.",
            "yaw": None,
            "pitch": None,
        }

    yaw, pitch = float(pose["yaw"]), float(pose["pitch"])
    current_pose = _classify_head_pose(yaw, pitch)
    pose_ok = current_pose == expected_pose
    if pose_ok:
        instruction = "Đúng hướng, giữ yên."
    elif expected_pose == "frontal":
        instruction = "Nhìn thẳng camera và giữ đầu cân bằng."
    elif current_pose == "frontal":
        instruction = f"{POSE_LABELS[expected_pose]} thêm."
    else:
        instruction = f"Đang hướng {POSE_LABELS.get(current_pose, 'chưa đúng')}; {POSE_LABELS[expected_pose].lower()} thêm."

    return {
        "success": True,
        "pose_ok": pose_ok,
        "current_pose": current_pose,
        "expected_pose": expected_pose,
        "instruction": instruction,
        "yaw": yaw,
        "pitch": pitch,
    }


def _read_enrollment_request():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ValueError("Body JSON không hợp lệ.")
    expected_pose = payload.get("expected_pose")
    if expected_pose not in ENROLLMENT_POSES:
        raise ValueError("Pose enrollment không hợp lệ.")
    frame, jpeg = _decode_enrollment_image(payload.get("image"))
    return frame, jpeg, expected_pose


@app.before_request
def allow_loopback_only():
    if request.remote_addr not in {"127.0.0.1", "::1"}:
        return jsonify({"success": False, "message": "Local requests only."}), 403


@app.get("/health")
def health():
    return jsonify(runtime.health())


@app.post("/api/ai/gallery/refresh")
def refresh_gallery():
    try:
        result = runtime.refresh_gallery()
        return jsonify({"success": True, **result})
    except Exception:
        with runtime._lock:
            runtime._gallery_error = "Could not load gallery from PHP."
        return jsonify({"success": False, "message": "Không thể tải gallery từ PHP."}), 503


@app.get("/api/ai/frame")
def camera_frame():
    try:
        raw, _ = runtime.fetch_camera_frame()
    except Exception:
        return jsonify({"success": False, "message": "Camera không khả dụng."}), 503
    return Response(raw, mimetype="image/jpeg", headers={"Cache-Control": "no-store"})


@app.post("/api/ai/recognize")
def recognize():
    try:
        _, frame = runtime.fetch_camera_frame()
        result = runtime.recognize_frame(frame)
        return jsonify(result)
    except Exception:
        return jsonify({
            "success": False,
            "match": False,
            "ma_nv": None,
            "score": None,
            "message": "AI service hoặc camera chưa sẵn sàng.",
        }), 503


@app.post("/api/ai/enrollment/inspect")
def inspect_enrollment():
    try:
        frame, _, expected_pose = _read_enrollment_request()
        return jsonify(runtime.inspect_enrollment_frame(frame, expected_pose))
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except Exception:
        return jsonify({"success": False, "message": "AI service hoặc model chưa sẵn sàng."}), 503


@app.post("/api/ai/enrollment/capture")
def capture_enrollment():
    try:
        frame, jpeg, expected_pose = _read_enrollment_request()
        result = runtime.capture_enrollment_sample(frame, jpeg, expected_pose)
        return jsonify(result), 200 if result["success"] else 409
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except Exception:
        return jsonify({"success": False, "message": "AI service hoặc model chưa sẵn sàng."}), 503


def main():
    runtime.initialize()
    app.run(host="127.0.0.1", port=5001, debug=False, use_reloader=False, threaded=True)


if __name__ == "__main__":
    main()
