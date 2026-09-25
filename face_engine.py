"""
face_engine.py — Face Recognition Engine (Enrollment Phase)
============================================================
Nhiệm vụ duy nhất của file này:
  - Khởi tạo InsightFace FaceAnalysis model (CPU, buffalo_l)
  - extract_embedding(frame) -> (embedding_bytes, embedding_np) hoặc raise

PHASE 1: ENROLLMENT ONLY.
Chưa có recognition / matching.

Yêu cầu:
    pip install insightface onnxruntime
"""

import numpy as np


class FaceRecognitionEngine:
    """
    Wrapper InsightFace FaceAnalysis cho enrollment.

    Usage:
        engine = FaceRecognitionEngine()
        engine.initialize()
        vector_bytes, emb_np = engine.extract_embedding(frame)
    """

    def __init__(self):
        self._app = None
        self._initialized = False

    # ------------------------------------------------------------------
    # initialize
    # ------------------------------------------------------------------

    def initialize(self):
        """
        Khởi tạo InsightFace FaceAnalysis với model buffalo_l, CPU only.
        Gọi một lần khi server khởi động.

        Raises:
            RuntimeError nếu InsightFace không cài hoặc model lỗi.
        """
        if self._initialized:
            return

        try:
            from insightface.app import FaceAnalysis
        except ImportError as e:
            raise RuntimeError(
                f"insightface chua duoc cai dat. Chay: pip install insightface onnxruntime\n"
                f"Chi tiet: {e}"
            )

        try:
            self._app = FaceAnalysis(
                name="buffalo_l",
                providers=["CPUExecutionProvider"],
            )
            # ctx_id=-1 = CPU
            self._app.prepare(ctx_id=-1, det_size=(640, 640))
            self._initialized = True
            print("[face_engine] FaceAnalysis (buffalo_l, CPU) san sang.")
        except Exception as e:
            raise RuntimeError(f"[face_engine] Khoi tao FaceAnalysis that bai: {e}")

    # ------------------------------------------------------------------
    # extract_embedding
    # ------------------------------------------------------------------

    def extract_embedding(self, frame):
        """
        Phan tich frame va trich xuat normed face embedding 512 chieu.

        Tham so:
            frame : numpy ndarray, BGR, kich thuoc bat ky (tu OpenCV).

        Tra ve:
            (vector_bytes, embedding_np)
              vector_bytes  : bytes float32, do dai 2048 byte (512 * 4)
              embedding_np  : np.ndarray shape (512,), dtype float32

        Raises:
            RuntimeError("Chua khoi tao engine")
            RuntimeError("Khong phat hien khuon mat")
            RuntimeError("Chi duoc co mot khuon mat")
            RuntimeError("Embedding khong hop le: ...")
        """
        if not self._initialized or self._app is None:
            raise RuntimeError("Engine chua duoc khoi tao. Goi initialize() truoc.")

        if frame is None:
            raise RuntimeError("Frame dau vao la None.")

        # InsightFace nhan BGR frame (OpenCV default) — khong can chuyen RGB
        faces = self._app.get(frame)

        if len(faces) == 0:
            raise RuntimeError("Khong phat hien khuon mat")

        if len(faces) > 1:
            raise RuntimeError("Chi duoc co mot khuon mat")

        face = faces[0]

        # Lay normed_embedding (da chuan hoa L2)
        raw_emb = face.normed_embedding
        if raw_emb is None:
            raise RuntimeError("Model khong tra ve embedding (thieu recognition module?)")

        embedding = np.asarray(raw_emb, dtype=np.float32)

        if embedding.size != 512:
            raise RuntimeError(
                f"Embedding khong hop le: kich thuoc {embedding.size}, can 512."
            )

        # Luu binary bytes (float32 little-endian)
        vector_bytes = embedding.tobytes()

        return vector_bytes, embedding


# ============================================================
# Singleton — khoi tao lazy khi can
# ============================================================

face_engine = FaceRecognitionEngine()
