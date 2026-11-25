import time
import unittest
from pathlib import Path
import sys
from unittest.mock import patch

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ai_service
from camera_source import (
    CameraSource, Esp32MjpegSource, FramePacket, FramePump, WebcamSource,
    validate_stream_url,
)


def vector(index):
    result = np.zeros(512, dtype=np.float32)
    result[index] = 1.0
    return result


def frame_with_noise(seed, scale=35):
    rng = np.random.default_rng(seed)
    return rng.integers(70, 70 + scale, size=(160, 160, 3), dtype=np.uint8)


class SnapshotEngine:
    _initialized = True

    def __init__(self, identities, delay=None):
        self.identities = list(identities)
        self.calls = 0
        self.delay = delay

    def detect_embeddings(self, frame):
        identity = self.identities[min(self.calls, len(self.identities) - 1)]
        self.calls += 1
        if self.delay is not None:
            self.delay.wait(1)
        return [{"embedding": vector(identity), "bbox": [10, 10, 150, 150]}]


class SequenceCameraSource(CameraSource):
    def __init__(self):
        self.sequence = 0
        self.running = True

    def is_opened(self):
        return self.running

    def get_frame(self):
        if not self.running:
            return None
        self.sequence += 1
        return FramePacket(np.zeros((8, 8, 3), dtype=np.uint8), self.sequence, time.monotonic())

    def release(self):
        self.running = False


class RecognitionSessionTests(unittest.TestCase):
    def runtime(self, identities, delay=None):
        runtime = ai_service.AIRuntime()
        runtime.engine = SnapshotEngine(identities, delay)
        runtime._gallery_loaded = True
        runtime._gallery = {7: {"HoTen": "Nhan vien test", "embeddings": (vector(0),), "n_samples": 1}}
        runtime.refresh_gallery = lambda: {"embedding_count": 1, "employee_count": 1, "invalid_count": 0}
        return runtime

    def wait_for_terminal(self, runtime, session_id):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            record = runtime.get_recognition_session(session_id)
            if record["state"] in {"COMPLETED", "ABORTED"}:
                return record
            time.sleep(.02)
        self.fail("Recognition session did not finish within the test timeout.")

    def test_three_fresh_snapshots_match_with_best_frame_without_averaging(self):
        runtime = self.runtime([0, 0, 0])
        frames = [frame_with_noise(4, 30), frame_with_noise(5, 100), frame_with_noise(6, 55)]
        packets = []
        for index, frame in enumerate(frames, start=1):
            ok, encoded = cv2.imencode(".jpg", frame)
            self.assertTrue(ok)
            packets.append((encoded.tobytes(), frame, index, time.monotonic()))
        runtime.fetch_camera_snapshot = lambda: packets.pop(0)
        started = runtime.start_recognition_session()
        record = self.wait_for_terminal(runtime, started["session_id"])
        self.assertEqual(record["state"], "COMPLETED")
        self.assertEqual(record["captured_frames"], 3)
        self.assertTrue(record["result"]["recognized"])
        self.assertEqual(record["result"]["ma_nv"], 7)
        expected_best = max(
            range(3), key=lambda index: ai_service._face_sharpness(frames[index], [10, 10, 150, 150])
        ) + 1
        self.assertEqual(record["result"]["best_frame_index"], expected_best)
        self.assertEqual(record["result"]["frame_width"], 160)
        self.assertEqual(record["result"]["temporal_consistency_min"], 1.0)

    def test_inconsistent_identity_aborts_without_a_match(self):
        runtime = self.runtime([0, 1, 0])
        frame = frame_with_noise(8)
        ok, encoded = cv2.imencode(".jpg", frame)
        self.assertTrue(ok)
        packets = [(encoded.tobytes(), frame, index, time.monotonic()) for index in (1, 2, 3)]
        runtime.fetch_camera_snapshot = lambda: packets.pop(0)
        started = runtime.start_recognition_session()
        record = self.wait_for_terminal(runtime, started["session_id"])
        self.assertEqual(record["state"], "ABORTED")
        self.assertEqual(record["result"]["reason"], "RETRY")
        self.assertEqual(record["result"]["retry_reason"], "INCONSISTENT_FACES")
        self.assertNotIn("ma_nv", record["result"])

    def test_double_start_is_rejected_while_worker_is_running(self):
        release = __import__("threading").Event()
        runtime = self.runtime([0, 0, 0], release)
        frame = frame_with_noise(9)
        ok, encoded = cv2.imencode(".jpg", frame)
        self.assertTrue(ok)
        packets = [(encoded.tobytes(), frame, index, time.monotonic()) for index in (1, 2, 3)]
        runtime.fetch_camera_snapshot = lambda: packets.pop(0)
        started = runtime.start_recognition_session()
        self.assertIsNotNone(started)
        self.assertIsNone(runtime.start_recognition_session())
        release.set()
        self.wait_for_terminal(runtime, started["session_id"])

    def test_three_snapshots_reject_missing_face(self):
        runtime = self.runtime([0, 0, 0])
        runtime.engine.detect_embeddings = lambda _frame: []
        frame = frame_with_noise(10)
        ok, encoded = cv2.imencode(".jpg", frame)
        self.assertTrue(ok)
        runtime.fetch_camera_snapshot = lambda: (encoded.tobytes(), frame, 1, time.monotonic())
        started = runtime.start_recognition_session()
        record = self.wait_for_terminal(runtime, started["session_id"])
        self.assertEqual(record["state"], "ABORTED")
        self.assertEqual(record["result"]["retry_reason"], "NO_FACE")

    def test_timeout_aborts_session_and_late_worker_cannot_replace_result(self):
        release_inference = __import__("threading").Event()
        runtime = self.runtime([0, 0, 0], release_inference)
        frame = frame_with_noise(11)
        ok, encoded = cv2.imencode(".jpg", frame)
        self.assertTrue(ok)
        runtime.fetch_camera_snapshot = lambda: (encoded.tobytes(), frame, 1, time.monotonic())
        started = runtime.start_recognition_session()
        deadline = time.monotonic() + 1
        while runtime.engine.calls == 0 and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertEqual(runtime.engine.calls, 1)

        runtime._expire_recognition_session(started["session_id"])
        timed_out = runtime.get_recognition_session(started["session_id"])
        self.assertEqual(timed_out["state"], "ABORTED")
        self.assertEqual(timed_out["result"]["retry_reason"], "TIMEOUT")
        release_inference.set()
        runtime._recognition_sessions[started["session_id"]]["future"].result(timeout=2)
        record = runtime.get_recognition_session(started["session_id"])
        self.assertEqual(record["result"]["retry_reason"], "TIMEOUT")


class CameraSourceTests(unittest.TestCase):
    def test_webcam_source_uses_backend_fallback_and_requires_a_real_frame(self):
        calls = []
        frame = np.full((12, 16, 3), 80, dtype=np.uint8)

        class FakeCapture:
            def __init__(self, index, backend):
                calls.append((index, backend))
                self.backend = backend
                self.released = False

            def isOpened(self):
                return True

            def set(self, *_args):
                return True

            def read(self):
                return (self.backend == cv2.CAP_DSHOW, frame.copy())

            def release(self):
                self.released = True

        with patch("camera_source.sys.platform", "win32"), \
             patch("camera_source.cv2.VideoCapture", side_effect=FakeCapture):
            source = WebcamSource(indexes=[0])
        try:
            packet = source.get_frame()
            self.assertIsNotNone(packet)
            self.assertEqual(packet.frame.shape, frame.shape)
            self.assertEqual(calls, [(0, cv2.CAP_MSMF), (0, cv2.CAP_DSHOW)])
        finally:
            source.release()

    def test_frame_pump_delivers_new_cloned_snapshot_and_rejects_stale(self):
        source = SequenceCameraSource()
        pump = FramePump(source, stale_seconds=.75)
        try:
            deadline = time.monotonic() + 1
            packet = None
            while time.monotonic() < deadline and packet is None:
                packet = pump.get_frame()
                time.sleep(.01)
            self.assertIsNotNone(packet)
            packet.frame[0, 0] = 255
            self.assertFalse(np.all(pump.get_frame().frame[0, 0] == 255))
            source.release()
            with pump._lock:
                pump._latest = FramePacket(packet.frame, packet.sequence, time.monotonic() - 1.0)
            self.assertIsNone(pump.get_frame())
        finally:
            pump.release()

    def test_esp32_jpeg_parser_decodes_complete_soi_eoi_image(self):
        ok, encoded = cv2.imencode(".jpg", np.full((16, 16, 3), 100, dtype=np.uint8))
        self.assertTrue(ok)
        source = object.__new__(Esp32MjpegSource)
        source._running = True
        source._lock = __import__("threading").Lock()
        source._sequence = 0
        source._latest = None
        source.stale_seconds = .75
        source._decode_jpegs(bytearray(b"multipart-header" + encoded.tobytes() + b"tail"))
        self.assertEqual(source._sequence, 1)
        self.assertIsNotNone(source.get_frame())

    def test_esp32_stream_reconnects_after_a_failed_connection(self):
        ok, encoded = cv2.imencode(".jpg", np.full((16, 16, 3), 90, dtype=np.uint8))
        self.assertTrue(ok)
        source = object.__new__(Esp32MjpegSource)
        source.url = "http://esp32cam.local:81/stream"
        source.stale_seconds = .75
        source._lock = __import__("threading").Lock()
        source._running = True
        source._sequence = 0
        source._latest = None
        source._connection_url = lambda: source.url
        calls = []

        class Response:
            def __init__(self): self.read_count = 0
            def __enter__(self): return self
            def __exit__(self, *_args): return None
            def read(self, _size):
                self.read_count += 1
                if self.read_count == 1:
                    return encoded.tobytes()
                source._running = False
                return b""

        def connect(*_args, **_kwargs):
            calls.append(1)
            if len(calls) == 1:
                raise OSError("camera reconnect test")
            return Response()

        with patch("camera_source.urllib.request.urlopen", side_effect=connect), \
             patch("camera_source.time.sleep"):
            source._read_stream()
        self.assertEqual(len(calls), 2)
        self.assertEqual(source._sequence, 1)
        self.assertIsNotNone(source.get_frame())

    def test_stream_url_rejects_credentials_and_unsupported_schemes(self):
        with self.assertRaises(ValueError):
            validate_stream_url("file:///tmp/stream")
        with self.assertRaises(ValueError):
            validate_stream_url("http://user:password@camera.local/stream")
        self.assertEqual(validate_stream_url("http://esp32cam.local:81/stream"),
                         "http://esp32cam.local:81/stream")


if __name__ == "__main__":
    unittest.main()
