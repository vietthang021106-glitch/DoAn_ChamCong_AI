"""Loopback AI API; PHP remains the only owner of MariaDB access."""

import base64
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
        try:
            self.engine.initialize()
        except Exception as exc:
            self._model_error = str(exc)
        try:
            self.refresh_gallery()
        except Exception:
            self._gallery_error = "Could not load gallery from PHP."

    def refresh_gallery(self):
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


runtime = AIRuntime()
app = Flask(__name__)


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


def main():
    runtime.initialize()
    app.run(host="127.0.0.1", port=5001, debug=False, use_reloader=False, threaded=True)


if __name__ == "__main__":
    main()
