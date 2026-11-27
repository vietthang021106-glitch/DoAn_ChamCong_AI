"""Pluggable frame sources. Recognition consumes BGR ndarrays only."""

import cv2

from .config import CAMERA_HEIGHT, CAMERA_WIDTH


class CameraSource:
    def get_frame(self):
        raise NotImplementedError

    def release(self):
        raise NotImplementedError


class WebcamSource(CameraSource):
    """Open the first Windows camera/backend pair that returns a real frame."""

    def __init__(self, width=CAMERA_WIDTH, height=CAMERA_HEIGHT):
        self.width = int(width)
        self.height = int(height)
        self._capture = None
        self._first_frame = None
        self.camera_index = None
        self.backend_name = None
        self._open_first_working_camera()

    @staticmethod
    def _backend_candidates():
        candidates = []
        for name in ("CAP_MSMF", "CAP_DSHOW"):
            backend = getattr(cv2, name, None)
            if backend is not None:
                candidates.append((name, backend))
        candidates.append(("default", None))
        return candidates

    def _open_first_working_camera(self):
        errors = []
        for backend_name, backend in self._backend_candidates():
            for index in range(6):
                capture = None
                try:
                    capture = (cv2.VideoCapture(index) if backend is None
                               else cv2.VideoCapture(index, backend))
                    if not capture.isOpened():
                        errors.append(f"{backend_name} index {index}: isOpened=False")
                        capture.release()
                        continue
                    capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                    buffer_prop = getattr(cv2, "CAP_PROP_BUFFERSIZE", None)
                    if buffer_prop is not None:
                        capture.set(buffer_prop, 1)
                    ok, frame = capture.read()
                    if not ok or frame is None or getattr(frame, "size", 0) == 0:
                        errors.append(f"{backend_name} index {index}: không đọc được frame")
                        capture.release()
                        continue
                    self._capture = capture
                    self._first_frame = frame
                    self.camera_index = index
                    self.backend_name = backend_name
                    return
                except Exception as exc:
                    errors.append(f"{backend_name} index {index}: {exc}")
                    if capture is not None:
                        capture.release()
        detail = "; ".join(errors[-8:]) or "không tìm thấy camera"
        raise RuntimeError(f"Không mở được webcam Windows (backend/index đã thử: {detail}).")

    def get_frame(self):
        if self._capture is None:
            return None
        if self._first_frame is not None:
            frame, self._first_frame = self._first_frame, None
            return frame
        ok, frame = self._capture.read()
        if not ok or frame is None or getattr(frame, "size", 0) == 0:
            return None
        return frame

    def release(self):
        if self._capture is not None:
            self._capture.release()
            self._capture = None


class Esp32HttpSource(CameraSource):
    """Future extension point for HTTP JPEG frame sources; no network dependency."""

    def __init__(self, *args, **kwargs):
        raise NotImplementedError("Esp32HttpSource chưa được triển khai; hiện chỉ hỗ trợ webcam.")

    def get_frame(self):
        raise NotImplementedError

    def release(self):
        return None
