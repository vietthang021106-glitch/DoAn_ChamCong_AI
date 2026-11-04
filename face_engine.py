"""InsightFace buffalo_l detection, embedding extraction, and head-pose estimation."""

import numpy as np
import threading
import cv2


MODEL_NAME = "buffalo_l"
EMBEDDING_DIMENSIONS = 512
DETECTION_MIN_SCORE = 0.5
ENROLLMENT_MIN_SCORE = 0.65

# Generic 3D face reference ordered like InsightFace's five-point landmarks:
# image-left eye, image-right eye, nose, image-left mouth, image-right mouth.
_POSE_MODEL_POINTS = np.asarray([
    [-32.0, 32.0, 28.0],
    [32.0, 32.0, 28.0],
    [0.0, 0.0, 0.0],
    [-23.0, -30.0, 20.0],
    [23.0, -30.0, 20.0],
], dtype=np.float64)


def estimate_head_pose(keypoints, frame_shape):
    """Estimate a raw solvePnP orientation from InsightFace's ordered five points.

    Camera coordinates use image X right, image Y down and Z away from the lens;
    the generic face model uses a different frontal-axis convention.  Therefore
    the returned legacy yaw/pitch are diagnostic raw Euler values, not a
    camera-calibrated pose.  Standalone guided enrollment calibrates the returned
    rotation matrix against the user's stable frontal reference.
    """
    points = np.asarray(keypoints, dtype=np.float64)
    if points.shape != (5, 2) or not np.all(np.isfinite(points)):
        raise ValueError("Expected five finite 2D face keypoints.")

    height, width = frame_shape[:2]
    focal = float(width)
    camera = np.asarray([
        [focal, 0.0, width / 2.0],
        [0.0, focal, height / 2.0],
        [0.0, 0.0, 1.0],
    ], dtype=np.float64)
    distortion = np.zeros((4, 1), dtype=np.float64)
    ok, rotation_vector, translation_vector = cv2.solvePnP(
        _POSE_MODEL_POINTS,
        points,
        camera,
        distortion,
        flags=cv2.SOLVEPNP_SQPNP,
    )
    if not ok:
        raise ValueError("Could not estimate head pose from face keypoints.")

    rotation, _ = cv2.Rodrigues(rotation_vector)
    yaw = np.degrees(np.arctan2(-rotation[2, 0], np.hypot(rotation[0, 0], rotation[1, 0])))
    pitch = np.degrees(np.arctan2(rotation[2, 1], rotation[2, 2]))
    reprojected, _ = cv2.projectPoints(
        _POSE_MODEL_POINTS, rotation_vector, translation_vector, camera, distortion
    )
    residuals = reprojected.reshape(-1, 2) - points
    reprojection_error = float(np.sqrt(np.mean(np.sum(residuals * residuals, axis=1))))
    camera_points = _POSE_MODEL_POINTS @ rotation.T + translation_vector.reshape(1, 3)
    if (not np.all(np.isfinite(rotation)) or not np.all(np.isfinite(translation_vector))
            or not np.isfinite(reprojection_error)):
        raise ValueError("Head pose solution is not finite.")
    return {
        "yaw": float(yaw),
        "pitch": float(pitch),
        "raw_yaw": float(yaw),
        "raw_pitch": float(pitch),
        "rotation_matrix": rotation.astype(np.float64).tolist(),
        "reprojection_error_px": reprojection_error,
        "positive_depth": bool(np.all(camera_points[:, 2] > 0.0)),
    }


def classify_head_pose(yaw, pitch):
    """Map landmark-derived yaw/pitch angles to the five enrollment poses."""
    yaw, pitch = float(yaw), float(pitch)
    if not np.isfinite(yaw) or not np.isfinite(pitch):
        return "unknown"
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


def assess_capture_quality(frame, face, center_tolerance=(0.18, 0.16),
                           max_size_ratio=(1.15, 1.08), edge_margin_ratio=0.0):
    """Check the source AI1 enrollment gates on the exact frame being captured."""
    def rejected(instruction):
        return {"ready": False, "instruction": instruction}
    if not isinstance(frame, np.ndarray) or frame.ndim != 3 or frame.shape[2] != 3:
        return rejected("Ảnh camera không hợp lệ.")

    height, width = frame.shape[:2]
    try:
        box = np.asarray(face.get("bbox"), dtype=np.float64).reshape(-1)
        score = float(face.get("detection_score"))
    except (TypeError, ValueError):
        return rejected("Chưa trích xuất được khuôn mặt rõ nét.")
    if box.size != 4 or not np.all(np.isfinite(box)) or not np.isfinite(score):
        return rejected("Chưa trích xuất được khuôn mặt rõ nét.")
    x1, y1, x2, y2 = box
    if x2 <= x1 or y2 <= y1 or x1 < 0 or y1 < 0 or x2 > width or y2 > height:
        return rejected("Đặt toàn bộ khuôn mặt trong khung hình.")
    if score < ENROLLMENT_MIN_SCORE:
        return rejected("Khuôn mặt chưa rõ. Nhìn vào camera và tăng ánh sáng.")

    try:
        tolerance_x, tolerance_y = [float(value) for value in center_tolerance]
    except (TypeError, ValueError):
        return rejected("Cấu hình vùng trung tâm không hợp lệ.")
    if (not np.isfinite(tolerance_x) or not np.isfinite(tolerance_y)
            or tolerance_x < 0 or tolerance_y < 0):
        return rejected("Cấu hình vùng trung tâm không hợp lệ.")
    try:
        max_width_ratio, max_height_ratio = [float(value) for value in max_size_ratio]
    except (TypeError, ValueError):
        return rejected("Cấu hình kích thước khuôn mặt không hợp lệ.")
    if (not np.isfinite(max_width_ratio) or not np.isfinite(max_height_ratio)
            or max_width_ratio <= 0 or max_height_ratio <= 0):
        return rejected("Cấu hình kích thước khuôn mặt không hợp lệ.")
    try:
        edge_margin_ratio = float(edge_margin_ratio)
    except (TypeError, ValueError):
        return rejected("Cấu hình khoảng cách mép khung không hợp lệ.")
    if not np.isfinite(edge_margin_ratio) or edge_margin_ratio < 0 or edge_margin_ratio >= 0.5:
        return rejected("Cấu hình khoảng cách mép khung không hợp lệ.")

    guide_height = min(height * 0.72, width * 0.86)
    guide_width = guide_height * 0.78
    guide_x, guide_y = width * 0.5, height * 0.51
    face_width, face_height = x2 - x1, y2 - y1
    if face_width < guide_width * 0.48 or face_height < guide_height * 0.5:
        return rejected("Mặt quá xa. Tiến gần camera hơn.")
    if (face_width > guide_width * max_width_ratio
            or face_height > guide_height * max_height_ratio):
        return rejected("Mặt quá gần. Lùi nhẹ để thấy toàn bộ khuôn mặt.")
    edge_x = face_width * edge_margin_ratio
    edge_y = face_height * edge_margin_ratio
    if (x1 < edge_x or y1 < edge_y
            or width - x2 < edge_x or height - y2 < edge_y):
        return rejected("Đưa khuôn mặt xa mép khung hình hơn.")
    if (abs((x1 + x2) / 2 - guide_x) / guide_width > tolerance_x
            or abs((y1 + y2) / 2 - guide_y) / guide_height > tolerance_y):
        return rejected("Đưa khuôn mặt về gần vùng trung tâm, giữ khoảng cách phù hợp.")

    crop = frame[int(y1):int(y2), int(x1):int(x2)]
    if not crop.size:
        return rejected("Chưa trích xuất được khuôn mặt rõ nét.")
    try:
        gray = cv2.cvtColor(cv2.resize(crop, (128, 160)), cv2.COLOR_BGR2GRAY)
        sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        brightness = float(gray.mean())
    except cv2.error:
        return rejected("Ảnh camera không hợp lệ.")
    if not np.isfinite(brightness) or brightness < 40 or brightness > 225:
        return rejected("Ánh sáng chưa phù hợp. Chiếu sáng đều khuôn mặt.")
    if not np.isfinite(sharpness) or sharpness < 20:
        return rejected("Ảnh chưa rõ. Giữ yên và kiểm tra nét camera.")
    return {"ready": True, "instruction": "Đúng hướng, giữ yên.",
            "sharpness": sharpness, "brightness": brightness}


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
        self._lock = threading.RLock()

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
        with self._lock:
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
                    name=MODEL_NAME,
                    allowed_modules=["detection", "recognition"],
                    providers=["CPUExecutionProvider"],
                )
                self._app.prepare(ctx_id=-1, det_size=(640, 640))
                self._initialized = True
                print(f"[face_engine] FaceAnalysis ({MODEL_NAME}, CPU) san sang.")
            except Exception as e:
                self._app = None
                raise RuntimeError(f"[face_engine] Khoi tao FaceAnalysis that bai: {e}")

    # ------------------------------------------------------------------
    # extract_embedding
    # ------------------------------------------------------------------

    def detect_embeddings(self, frame):
        """
        Detect faces and extract one normalized 512D embedding per detected face.

        Args:
            frame: OpenCV BGR image.

        Returns:
            list[dict]: Embedding bytes/array, bounding box, detector score, and pose.
        """
        if not self._initialized or self._app is None:
            raise RuntimeError("Engine chua duoc khoi tao. Goi initialize() truoc.")
        if not isinstance(frame, np.ndarray) or frame.ndim != 3 or frame.shape[2] != 3 or frame.size == 0:
            raise RuntimeError("Frame BGR dau vao khong hop le.")

        with self._lock:
            faces = self._app.get(frame)

        results = []
        for face in faces:
            try:
                score = float(getattr(face, "det_score", 0.0))
            except (TypeError, ValueError):
                continue
            bbox = getattr(face, "bbox", None)
            if not np.isfinite(score) or score < DETECTION_MIN_SCORE or score > 1.0:
                continue
            if bbox is None:
                continue
            try:
                bbox = np.asarray(bbox, dtype=np.float64).reshape(-1)
            except (TypeError, ValueError):
                continue
            if bbox.size != 4 or not np.all(np.isfinite(bbox)) or bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
                continue
            raw_emb = getattr(face, "normed_embedding", None)
            if raw_emb is None:
                raw_emb = getattr(face, "embedding", None)
            if raw_emb is None:
                raise RuntimeError("Model khong tra ve embedding (thieu recognition module?)")

            embedding = np.asarray(raw_emb, dtype=np.float32).reshape(-1)
            if embedding.size != EMBEDDING_DIMENSIONS:
                raise RuntimeError(
                    f"Embedding khong hop le: kich thuoc {embedding.size}, can {EMBEDDING_DIMENSIONS}."
                )
            norm = float(np.linalg.norm(embedding))
            if not np.isfinite(norm) or norm <= 1e-12:
                raise RuntimeError("Embedding khong hop le: norm bang 0 hoac khong huu han.")
            embedding = np.asarray(embedding / norm, dtype=np.float32)

            keypoints = getattr(face, "kps", None)
            pose = None
            if keypoints is not None:
                try:
                    pose = estimate_head_pose(keypoints, frame.shape)
                except (ValueError, cv2.error):
                    pose = None
            results.append({
                "embedding": embedding,
                "vector_bytes": embedding.astype("<f4", copy=False).tobytes(),
                "bbox": [float(value) for value in bbox],
                "detection_score": score,
                "head_pose": pose,
            })
        return results

    def inspect_pose(self, frame):
        """
        Inspect face count and head pose without writing an embedding to storage.

        Args:
            frame: OpenCV BGR image.

        Returns:
            dict: Face count, coarse pose label, and yaw/pitch when available.
        """
        faces = self.detect_embeddings(frame)
        if not faces:
            return {"face_count": 0, "current_pose": "no_face", "yaw": None, "pitch": None}
        if len(faces) != 1:
            return {"face_count": len(faces), "current_pose": "multiple_faces", "yaw": None, "pitch": None}
        pose = faces[0]["head_pose"]
        quality = assess_capture_quality(frame, faces[0])
        if pose is None:
            return {"face_count": 1, "current_pose": "unknown", "yaw": None, "pitch": None,
                    "quality_ok": quality["ready"], "quality_instruction": quality["instruction"]}
        return {"face_count": 1, "current_pose": classify_head_pose(pose["yaw"], pose["pitch"]), **pose,
                "quality_ok": quality["ready"], "quality_instruction": quality["instruction"]}

    def extract_embedding(self, frame):
        """
        Phân tích frame và trích xuất embedding khuôn mặt đã chuẩn hóa 512 chiều.

        Tham so:
            frame: numpy ndarray BGR do OpenCV cung cấp.

        Tra ve:
            tuple: (vector_bytes, embedding_np), lần lượt là 2048 byte float32
                little-endian và mảng numpy shape (512,), dtype float32.

        Raises:
            RuntimeError("Chua khoi tao engine")
            RuntimeError("Khong phat hien khuon mat")
            RuntimeError("Chi duoc co mot khuon mat")
            RuntimeError("Embedding khong hop le: ...")
        """
        faces = self.detect_embeddings(frame)

        if len(faces) == 0:
            raise RuntimeError("Khong phat hien khuon mat")

        if len(faces) > 1:
            raise RuntimeError("Chi duoc co mot khuon mat")

        return faces[0]["vector_bytes"], faces[0]["embedding"]


# ============================================================
# Singleton — khoi tao lazy khi can
# ============================================================

face_engine = FaceRecognitionEngine()
