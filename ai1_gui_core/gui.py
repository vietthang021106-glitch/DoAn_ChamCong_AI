"""Desktop Tkinter shell for the isolated, local-only AI1 standalone system."""

import os
import queue
import shutil
import tempfile
import threading
import time
import uuid
from pathlib import Path
from tkinter import messagebox, ttk

import cv2
import numpy as np
import tkinter as tk
from PIL import Image, ImageOps, ImageTk

import face_matching
from ai1_standalone_core.ai1_adapter import validate_enrollment_frame
from ai1_standalone_core.config import (
    EMBEDDING_DIMENSIONS,
    FRAME_CONSISTENCY_THRESHOLD,
    POSES,
    RECOGNITION_THRESHOLD,
    STALE_FRAME_SECONDS,
)
from ai1_standalone_core.utils import safe_identity_path, validate_employee_id
from .controller import AI1GuiController
from .enrollment_state import EnrollmentCaptureState


BG = "#0d1117"
PANEL = "#161b22"
CARD = "#1c2128"
TEXT = "#e6edf3"
DIM = "#8b949e"
BLUE = "#1f6feb"
GREEN = "#238636"
RED = "#da3633"
YELLOW = "#d29922"
POSE_LABELS = {
    "frontal": "Nhìn thẳng",
    "left": "Xoay trái",
    "right": "Xoay phải",
    "up": "Ngẩng lên",
    "down": "Cúi xuống",
}
MESSAGE_LABELS = {
    "NO FACE": "Không thấy khuôn mặt",
    "MULTIPLE FACES": "Chỉ để một người trong khung",
    "FACE TOO SMALL": "Mặt quá xa — tiến gần camera hơn",
    "FACE TOO LARGE": "Mặt quá gần — lùi nhẹ khỏi camera",
    "FACE POSITION": "Đưa mặt vào giữa khung hướng dẫn",
    "BAD LIGHTING": "Ánh sáng chưa phù hợp",
    "TOO BLURRY": "Ảnh bị mờ — giữ yên và kiểm tra camera",
    "WRONG POSE": "Điều chỉnh theo pose yêu cầu",
    "SAME PERSON": "Khuôn mặt khác mẫu nhìn thẳng",
    "STALE_FRAME": "Đang chờ khung hình mới",
    "CAMERA DISCONNECTED": "Camera chưa có frame mới",
    "INVALID EMBEDDING": "Embedding không hợp lệ — thử lại",
}


def _atomic_write_jpeg(path, frame):
    """Write an uncommitted enrollment image into its private stage atomically."""
    path = Path(path)
    ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
    if not ok or encoded is None or encoded.size == 0:
        raise OSError("Không mã hóa được ảnh pose.")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", prefix=".pose-", suffix=".tmp",
                                         dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(encoded.tobytes())
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


class AI1Gui:
    """Responsive dark GUI; all model/camera work runs outside Tk's main thread."""

    def __init__(self, root=None, controller=None):
        self.root = root or tk.Tk()
        self.controller = controller or AI1GuiController()
        self.events = queue.Queue()
        self.close_event = threading.Event()
        self.active_operation = None
        self.active_token = None
        self.active_stop_event = None
        self.worker_thread = None
        self.closing = False
        self.enrollment = None
        self.current_packet = None
        self.current_photo = None
        self.thumbnail_photos = [None] * len(POSES)
        self.captured_pose_order = []
        self.latest_analysis = {}
        self.best_result_frame = None
        self.best_frame_until = 0.0
        self.last_result_status = None

        self.root.title("AI1 Standalone | Nhận diện khuôn mặt")
        self.root.geometry("1480x900")
        self.root.minsize(1160, 720)
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._configure_style()
        self._build_ui()
        self._set_controls()
        self._start_job("startup", lambda: self.controller.startup(self.close_event))
        self.root.after(60, self._poll_events)
        self.root.after(33, self._update_preview)

    def run(self):
        self.root.mainloop()

    def _configure_style(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 10))
        style.configure("Treeview", background=CARD, foreground=TEXT,
                        fieldbackground=CARD, rowheight=27, borderwidth=0)
        style.configure("Treeview.Heading", background=PANEL, foreground=DIM,
                        font=("Segoe UI", 9, "bold"))
        style.map("Treeview", background=[("selected", BLUE)], foreground=[("selected", "white")])
        style.configure("Horizontal.TProgressbar", troughcolor=PANEL,
                        background=GREEN, thickness=11)
        style.configure("TCombobox", fieldbackground=CARD, background=CARD, foreground=TEXT)

    def _build_ui(self):
        header = tk.Frame(self.root, bg=PANEL, height=64)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)
        tk.Label(header, text="AI1 STANDALONE", bg=PANEL, fg=TEXT,
                 font=("Segoe UI", 15, "bold")).pack(side="left", padx=(20, 12), pady=16)
        tk.Label(header, text="ArcFace buffalo_l  ·  SCRFD  ·  dữ liệu riêng trên máy này",
                 bg=PANEL, fg=DIM, font=("Segoe UI", 10)).pack(side="left", pady=18)
        self.header_status = tk.StringVar(value="Đang tải AI1...")
        self.header_label = tk.Label(header, textvariable=self.header_status, bg=PANEL, fg=YELLOW,
                                      font=("Segoe UI", 9, "bold"))
        self.header_label.pack(side="right", padx=20)

        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=14, pady=12)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)

        left = tk.Frame(body, bg=BG)
        left.grid(row=0, column=0, sticky="nsew")
        left.columnconfigure(0, weight=1)
        left.rowconfigure(0, weight=1)
        self.preview = tk.Label(left, bg="#05070a", fg=DIM,
                                text="Đang khởi tạo AI1 và camera…", font=("Segoe UI", 14))
        self.preview.grid(row=0, column=0, sticky="nsew")
        self.preview_hint = tk.StringVar(value="Camera preview sẽ xuất hiện tại đây.")
        tk.Label(left, textvariable=self.preview_hint, bg=BG, fg=DIM,
                 anchor="w", font=("Segoe UI", 9)).grid(row=1, column=0, sticky="ew", pady=(8, 0))

        side = tk.Frame(body, bg=BG, width=410)
        side.grid(row=0, column=1, sticky="ns", padx=(14, 0))
        side.grid_propagate(False)
        side.rowconfigure(3, weight=1)

        camera_card = self._card(side, "NGUỒN CAMERA")
        camera_card.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        camera_form = tk.Frame(camera_card, bg=CARD)
        camera_form.pack(fill="x", padx=12, pady=(1, 9))
        self.camera_type_var = tk.StringVar(value="WEBCAM")
        self.camera_combo = ttk.Combobox(camera_form, textvariable=self.camera_type_var,
                                         values=("WEBCAM", "ESP32-CAM"), state="readonly", width=13)
        self.camera_combo.grid(row=0, column=0, sticky="w")
        self.stream_url_var = tk.StringVar(
            value=os.getenv("AI1_ESP32_STREAM_URL", "http://esp32cam.local:81/stream")
        )
        self.stream_entry = ttk.Entry(camera_form, textvariable=self.stream_url_var, width=27)
        self.stream_entry.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        camera_form.columnconfigure(1, weight=1)
        self.camera_button = self._button(camera_card, "Chọn nguồn camera", self._change_camera, BLUE)
        self.camera_button.pack(fill="x", padx=12, pady=(0, 11))

        employee_card = self._card(side, "NHÂN VIÊN LOCAL")
        employee_card.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        form = tk.Frame(employee_card, bg=CARD)
        form.pack(fill="x", padx=12, pady=(0, 8))
        tk.Label(form, text="Employee ID", bg=CARD, fg=DIM, font=("Segoe UI", 9)).grid(
            row=0, column=0, sticky="w")
        tk.Label(form, text="Employee Name", bg=CARD, fg=DIM, font=("Segoe UI", 9)).grid(
            row=0, column=1, sticky="w", padx=(8, 0))
        self.id_var = tk.StringVar()
        self.name_var = tk.StringVar()
        self.id_entry = ttk.Entry(form, textvariable=self.id_var, width=14)
        self.name_entry = ttk.Entry(form, textvariable=self.name_var, width=22)
        self.id_entry.grid(row=1, column=0, sticky="ew", pady=(3, 0))
        self.name_entry.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=(3, 0))
        form.columnconfigure(1, weight=1)
        self.register_button = self._button(employee_card, "Đăng ký khuôn mặt", self._begin_registration, GREEN)
        self.register_button.pack(fill="x", padx=12, pady=(0, 6))
        quick = tk.Frame(employee_card, bg=CARD)
        quick.pack(fill="x", padx=12, pady=(0, 10))
        self.refresh_button = self._button(quick, "Làm mới danh sách", self._refresh, "#30363d")
        self.refresh_button.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.delete_button = self._button(quick, "Xóa nhân viên", self._delete_selected, "#30363d")
        self.delete_button.pack(side="left", fill="x", expand=True, padx=(4, 0))

        capture_card = self._card(side, "ENROLLMENT 5 POSE · AUTO CAPTURE")
        capture_card.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        self.pose_var = tk.StringVar(value="Pose yêu cầu: —")
        self.detected_pose_var = tk.StringVar(value="Pose phát hiện: —")
        self.quality_var = tk.StringVar(value="Quality: chờ enrollment")
        self.stability_var = tk.StringVar(value="Stability: 0/8")
        for variable in (self.pose_var, self.detected_pose_var, self.quality_var, self.stability_var):
            tk.Label(capture_card, textvariable=variable, bg=CARD, fg=TEXT,
                     font=("Segoe UI", 9), anchor="w").pack(fill="x", padx=12, pady=1)
        self.progress = ttk.Progressbar(capture_card, maximum=5)
        self.progress.pack(fill="x", padx=12, pady=(6, 8))
        thumbs = tk.Frame(capture_card, bg=CARD)
        thumbs.pack(fill="x", padx=8, pady=(0, 8))
        self.thumb_labels = []
        self.thumb_status_labels = []
        for pose in POSES:
            cell = tk.Frame(thumbs, bg=PANEL, padx=2, pady=3)
            cell.pack(side="left", fill="both", expand=True, padx=2)
            image_label = tk.Label(cell, text="—", width=7, height=3, bg=PANEL, fg=DIM,
                                   font=("Segoe UI", 9, "bold"))
            image_label.pack(fill="both", expand=True)
            status_label = tk.Label(cell, text="•", bg=PANEL, fg=DIM, font=("Segoe UI", 9, "bold"))
            status_label.pack(pady=(2, 0))
            tk.Label(cell, text=POSE_LABELS[pose], bg=PANEL, fg=DIM,
                     font=("Segoe UI", 7)).pack(pady=(0, 2))
            self.thumb_labels.append(image_label)
            self.thumb_status_labels.append(status_label)
        capture_actions = tk.Frame(capture_card, bg=CARD)
        capture_actions.pack(fill="x", padx=12, pady=(0, 10))
        self.retake_button = self._button(capture_actions, "Chụp lại pose", self._retake_pose, "#30363d")
        self.retake_button.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.cancel_button = self._button(capture_actions, "Hủy", self._cancel_enrollment, "#30363d")
        self.cancel_button.pack(side="left", fill="x", expand=True, padx=(4, 0))
        self.save_button = self._button(capture_card, "Lưu lại 5 mẫu local", self._retry_save, BLUE)
        self.save_button.pack(fill="x", padx=12, pady=(0, 10))

        list_card = self._card(side, "DANH SÁCH NHÂN VIÊN STANDALONE")
        list_card.grid(row=3, column=0, sticky="nsew")
        table_wrap = tk.Frame(list_card, bg=CARD)
        table_wrap.pack(fill="both", expand=True, padx=9, pady=(0, 9))
        self.employee_table = ttk.Treeview(table_wrap, columns=("id", "name", "samples"),
                                           show="headings", height=5, selectmode="browse")
        for column, title in (("id", "Employee ID"), ("name", "Họ tên"), ("samples", "Mẫu")):
            self.employee_table.heading(column, text=title)
        self.employee_table.column("id", width=90, stretch=False)
        self.employee_table.column("name", width=205)
        self.employee_table.column("samples", width=48, stretch=False, anchor="center")
        self.employee_table.pack(fill="both", expand=True)
        self.employee_table.bind("<<TreeviewSelect>>", self._select_employee)

        footer = tk.Frame(self.root, bg=PANEL, height=105)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)
        top = tk.Frame(footer, bg=PANEL)
        top.pack(fill="x", padx=15, pady=(11, 2))
        self.state_var = tk.StringVar(value="TRẠNG THÁI: ĐANG TẢI AI1")
        self.prediction_var = tk.StringVar(value="KẾT QUẢ: —")
        tk.Label(top, textvariable=self.state_var, bg=PANEL, fg=YELLOW,
                 font=("Segoe UI", 10, "bold"), anchor="w").pack(side="left")
        tk.Label(top, textvariable=self.prediction_var, bg=PANEL, fg=TEXT,
                 font=("Segoe UI", 10, "bold"), anchor="w").pack(side="left", padx=(24, 0))
        bottom = tk.Frame(footer, bg=PANEL)
        bottom.pack(fill="x", padx=15, pady=(4, 10))
        self.progress_var = tk.StringVar(value="Tiến độ: 0/5")
        self.sharpness_var = tk.StringVar(value="Sharpness: —")
        self.latency_var = tk.StringVar(value="Latency: —")
        self.score_var = tk.StringVar(value="Similarity: —")
        self.threshold_var = tk.StringVar(value=f"Threshold: {RECOGNITION_THRESHOLD:.3f}")
        self.consistency_var = tk.StringVar(value=f"Temporal: {FRAME_CONSISTENCY_THRESHOLD:.2f}")
        for variable in (self.progress_var, self.sharpness_var, self.latency_var,
                         self.score_var, self.threshold_var, self.consistency_var):
            tk.Label(bottom, textvariable=variable, bg=PANEL, fg=DIM,
                     font=("Segoe UI", 9), anchor="w").pack(side="left", padx=(0, 18))
        actions = tk.Frame(bottom, bg=PANEL)
        actions.pack(side="right")
        self.recognize_button = self._button(actions, "Nhận diện khuôn mặt", self._recognize, GREEN)
        self.recognize_button.pack(side="left", padx=(0, 8))
        self.exit_button = self._button(actions, "Thoát", self._on_close, "#30363d")
        self.exit_button.pack(side="left")

    @staticmethod
    def _card(parent, title):
        card = tk.Frame(parent, bg=CARD, highlightthickness=1, highlightbackground="#30363d")
        tk.Label(card, text=title, bg=CARD, fg=BLUE, font=("Segoe UI", 9, "bold"),
                 anchor="w").pack(fill="x", padx=12, pady=(9, 6))
        return card

    @staticmethod
    def _button(parent, text, command, color):
        return tk.Button(parent, text=text, command=command, bg=color, fg="white",
                         activebackground=color, activeforeground="white", relief="flat",
                         bd=0, padx=10, pady=7, cursor="hand2", font=("Segoe UI", 9, "bold"))

    def _set_controls(self):
        idle = self.active_operation is None and not self.closing
        ready = bool(self.controller.ready)
        enabled = tk.NORMAL if idle and ready else tk.DISABLED
        for widget in (self.register_button, self.refresh_button, self.delete_button,
                       self.recognize_button, self.camera_button, self.camera_combo,
                       self.stream_entry, self.id_entry, self.name_entry):
            widget.configure(state=enabled)
        in_enrollment = self.active_operation == "enrollment" and self.enrollment is not None
        self.retake_button.configure(state=tk.NORMAL if in_enrollment else tk.DISABLED)
        save_retry = idle and self.enrollment is not None and self.enrollment.get("ready_to_save")
        self.cancel_button.configure(state=tk.NORMAL if in_enrollment or save_retry else tk.DISABLED)
        self.save_button.configure(state=tk.NORMAL if save_retry else tk.DISABLED)
        if self.closing:
            self.exit_button.configure(state=tk.DISABLED)

    def _start_job(self, kind, callback):
        if self.closing or self.active_operation is not None:
            return False
        token = uuid.uuid4().hex
        stop_event = threading.Event()
        self.active_operation, self.active_token, self.active_stop_event = kind, token, stop_event
        self._set_controls()

        def run():
            try:
                value = callback()
                payload = {"kind": kind, "value": value, "error": None}
            except Exception as exc:
                payload = {"kind": kind, "value": None, "error": exc}
            self.events.put(("job_done", token, payload))

        self.worker_thread = threading.Thread(target=run, name=f"ai1-gui-{kind}", daemon=True)
        self.worker_thread.start()
        return True

    def _start_session(self, kind, worker):
        if self.closing or self.active_operation is not None:
            return None
        token = self.controller.begin_session()
        if token is None:
            self.state_var.set("TRẠNG THÁI: SESSION ĐANG CHẠY")
            return None
        stop_event = threading.Event()
        self.active_operation, self.active_token, self.active_stop_event = kind, token, stop_event
        self._set_controls()

        def run():
            try:
                value = worker(token, stop_event)
                payload = {"kind": kind, "value": value, "error": None}
            except Exception as exc:
                payload = {"kind": kind, "value": None, "error": exc}
            finally:
                self.controller.end_session(token)
            self.events.put(("session_done", token, payload))

        self.worker_thread = threading.Thread(target=run, name=f"ai1-gui-{kind}", daemon=True)
        self.worker_thread.start()
        return token

    def _poll_events(self):
        if self.closing:
            return
        while True:
            try:
                kind, token, payload = self.events.get_nowait()
            except queue.Empty:
                break
            if token != self.active_token:
                continue
            if kind == "enrollment_progress":
                self._show_enrollment_progress(payload)
            elif kind == "enrollment_captured":
                self._show_captured_pose(payload)
            elif kind == "enrollment_retake":
                self._show_retake_pose(payload)
            elif kind == "enrollment_saving":
                self.state_var.set("TRẠNG THÁI: ĐANG KIỂM TRA VÀ LƯU ĐỦ 5 MẪU")
                self.enrollment_hint_set("Đang xác minh 5 embedding rồi lưu vào kho standalone local.")
            elif kind == "recognition_progress":
                count, total = payload
                self.state_var.set("TRẠNG THÁI: ĐANG QUÉT KHUÔN MẶT")
                self.progress_var.set(f"Snapshot: {count}/{total}")
                self.preview_hint.set(f"ĐANG QUÉT KHUÔN MẶT · {count}/{total}")
            elif kind == "job_done":
                self.active_operation = None
                self._handle_job_done(payload)
                self._set_controls()
            elif kind == "session_done":
                self.active_operation = None
                self._handle_session_done(payload)
                self._set_controls()
        self.root.after(60, self._poll_events)

    def _handle_job_done(self, payload):
        kind, value, error = payload["kind"], payload["value"], payload["error"]
        if kind == "startup":
            if error:
                self.header_status.set(f"Lỗi khởi tạo AI1: {error}")
                self.header_label.configure(fg=RED)
                self.state_var.set("TRẠNG THÁI: INIT FAILED")
                messagebox.showerror("AI1 không khởi tạo được", str(error), parent=self.root)
                return
            self._populate_employees(value["employees"])
            self.threshold_var.set(f"Threshold: {value['threshold']:.3f}")
            if value["camera_available"]:
                self.header_status.set("buffalo_l sẵn sàng · camera đã kết nối")
                self.header_label.configure(fg=GREEN)
                self.state_var.set("TRẠNG THÁI: READY")
                self.preview.configure(text="")
                self.preview_hint.set("Webcam sẵn sàng. Có thể chọn ESP32-CAM trong nguồn camera.")
            else:
                self.header_status.set("buffalo_l sẵn sàng · camera chưa có frame")
                self.header_label.configure(fg=YELLOW)
                self.state_var.set("TRẠNG THÁI: CAMERA UNAVAILABLE")
                self.preview.configure(text="Camera chưa sẵn sàng — chọn lại nguồn camera.")
                self.preview_hint.set(value.get("camera_error") or "Kiểm tra webcam hoặc URL ESP32-CAM.")
            return
        if error:
            self.state_var.set(f"TRẠNG THÁI: LỖI · {str(error)[:90]}")
            messagebox.showerror("Thao tác thất bại", str(error), parent=self.root)
            if kind == "change_camera":
                self.header_status.set(f"Camera chưa kết nối · {str(error)[:75]}")
                self.header_label.configure(fg=RED)
            return
        if kind == "refresh":
            self._populate_employees(value["employees"])
            self.state_var.set("TRẠNG THÁI: ĐÃ LÀM MỚI DANH SÁCH LOCAL")
        elif kind == "delete_employee":
            self._populate_employees(value["employees"])
            self.state_var.set("TRẠNG THÁI: ĐÃ XÓA NHÂN VIÊN LOCAL")
            self.prediction_var.set("KẾT QUẢ: —")
        elif kind == "change_camera":
            self.camera_type_var.set("ESP32-CAM" if value["camera_type"] == "esp32" else "WEBCAM")
            self.header_status.set(
                "ESP32-CAM đã chọn · chờ frame mới" if value["camera_type"] == "esp32"
                else "Webcam đã kết nối"
            )
            self.header_label.configure(fg=GREEN if value["camera_available"] else YELLOW)
            self.state_var.set("TRẠNG THÁI: CAMERA ĐÃ ĐỔI")
        elif kind == "retry_save":
            self._enrollment_saved(value)

    def _handle_session_done(self, payload):
        kind, value, error = payload["kind"], payload["value"], payload["error"]
        if kind == "enrollment":
            if error:
                session = self.enrollment
                if session is not None and session.get("state") is not None and session["state"].complete:
                    session["ready_to_save"] = True
                    session["session_id"] = None
                    self.state_var.set("TRẠNG THÁI: LƯU CHƯA THÀNH CÔNG · CÓ THỂ THỬ LẠI")
                    self.enrollment_hint_set(str(error))
                else:
                    self._discard_enrollment()
                    self.state_var.set("TRẠNG THÁI: RETRY · ENROLLMENT ĐÃ HỦY")
                    self.preview_hint.set(str(error))
                return
            if value and value.get("status") == "SAVED":
                self._enrollment_saved(value["snapshot"])
            elif value and value.get("status") == "SAVE_FAILED":
                session = self.enrollment
                if session is not None:
                    session["state"] = value["state"]
                    session["ready_to_save"] = True
                    session["session_id"] = None
                self.state_var.set("TRẠNG THÁI: LƯU THẤT BẠI · CÓ THỂ THỬ LẠI")
                self.enrollment_hint_set(value.get("error", "Không lưu được 5 mẫu."))
            else:
                self._discard_enrollment()
                self.state_var.set("TRẠNG THÁI: ĐĂNG KÝ ĐÃ HỦY · GALLERY KHÔNG THAY ĐỔI")
            return
        if kind == "recognition":
            if error:
                result = {"status": "RETRY", "predicted_id": "UNKNOWN", "score": 0.0,
                          "threshold": self.controller.threshold, "reason": str(error),
                          "latency_ms": 0.0}
            else:
                result = value
            if result is not None:
                self._show_recognition(result)
        elif kind == "save_retry":
            if error:
                if self.enrollment:
                    self.enrollment["ready_to_save"] = True
                self.state_var.set("TRẠNG THÁI: RETRY SAVE")
                self.enrollment_hint_set(str(error))
            else:
                self._enrollment_saved(value)

    def _populate_employees(self, employees):
        for item in self.employee_table.get_children():
            self.employee_table.delete(item)
        for employee in employees:
            identity = employee["MaNV"]
            samples = len(self.controller.gallery.get(identity, {}).get("embeddings", ()))
            self.employee_table.insert("", "end", iid=identity,
                                       values=(identity, employee["HoTen"], samples))
        self.header_status.set(f"buffalo_l sẵn sàng · {len(employees)} nhân viên standalone")
        self.header_label.configure(fg=GREEN)

    def _select_employee(self, _event=None):
        selection = self.employee_table.selection()
        if not selection:
            return
        identity = selection[0]
        employee = next((item for item in self.controller.employees if item["MaNV"] == identity), None)
        if employee:
            self.id_var.set(employee["MaNV"])
            self.name_var.set(employee["HoTen"])

    def _refresh(self):
        self.state_var.set("TRẠNG THÁI: ĐANG LÀM MỚI GALLERY LOCAL…")
        self._start_job("refresh", self.controller.refresh_data)

    def _change_camera(self):
        selected = self.camera_type_var.get().strip().upper()
        source_type = "esp32" if selected == "ESP32-CAM" else "webcam"
        url = self.stream_url_var.get().strip()
        self.state_var.set("TRẠNG THÁI: ĐANG MỞ NGUỒN CAMERA…")
        self._start_job("change_camera", lambda: self.controller.change_camera(source_type, url))

    def _begin_registration(self):
        if self.controller.source is None:
            messagebox.showwarning("Camera chưa sẵn sàng", "Chọn nguồn camera đang có frame trước.",
                                   parent=self.root)
            return
        try:
            identity = validate_employee_id(self.id_var.get().strip())
        except ValueError as exc:
            messagebox.showerror("Employee ID không hợp lệ", str(exc), parent=self.root)
            return
        name = self.name_var.get().strip()
        if not name:
            messagebox.showerror("Thiếu Employee Name", "Nhập họ tên trước khi đăng ký.", parent=self.root)
            return
        existing = identity in {person["MaNV"] for person in self.controller.employees}
        overwrite = False
        if existing:
            overwrite = messagebox.askyesno(
                "Thay dữ liệu standalone?",
                f"{identity} đã tồn tại. Thay dữ liệu local hiện tại bằng đủ 5 mẫu mới?",
                parent=self.root,
            )
            if not overwrite:
                return
        else:
            target = safe_identity_path(self.controller.store.images_root, identity)
            if target.exists():
                messagebox.showerror("Dữ liệu local không đồng bộ",
                                     "Đã có thư mục ảnh cho mã này; không ghi đè im lặng.",
                                     parent=self.root)
                return
        try:
            self.controller.store.ensure()
            stage = Path(tempfile.mkdtemp(prefix=f".pending-gui-{identity}-",
                                          dir=self.controller.store.root))
        except Exception as exc:
            messagebox.showerror("Không tạo được thư mục tạm", str(exc), parent=self.root)
            return
        self.enrollment = {
            "identity": identity, "name": name, "overwrite": overwrite,
            "stage": stage, "frames": {}, "state": EnrollmentCaptureState(ready_frames=8),
            "requests": queue.Queue(), "ready_to_save": False, "saved": False,
            "session_id": None, "captured_order_ui": [],
        }
        self._reset_thumbnails()
        self.progress.configure(value=0)
        self.progress_var.set("Tiến độ: 0/5")
        self.stability_var.set("Stability: 0/8")
        self.quality_var.set("Quality: đang kiểm tra")
        self.pose_var.set("Pose yêu cầu: 1/5 · Nhìn thẳng")
        self.detected_pose_var.set("Pose phát hiện: —")
        self.enrollment_hint_set("Đưa mặt vào guide; giữ đúng pose 8 frame liên tiếp để tự chụp.")
        token = self._start_session("enrollment", self._enrollment_worker)
        if token is None:
            self._discard_enrollment()
            return
        self.enrollment["session_id"] = token
        self.state_var.set(f"TRẠNG THÁI: ĐĂNG KÝ {identity} · POSE 1/5")
        self._set_controls()

    def _enrollment_worker(self, token, stop_event):
        session = self.enrollment
        if session is None:
            return {"status": "CANCELLED"}
        state = session["state"]
        last_sequence = -1
        last_ui_time = 0.0
        last_ui_signature = None
        saved = False
        try:
            while not stop_event.is_set():
                while True:
                    try:
                        request = session["requests"].get_nowait()
                    except queue.Empty:
                        break
                    if request == "reset-stability":
                        state.reset_stability()
                        continue
                    pose = request
                    if pose in state.embeddings:
                        state.clear_pose(pose)
                        session["frames"].pop(pose, None)
                        image_path = session["stage"] / f"{pose}.jpg"
                        if image_path.exists():
                            image_path.unlink()
                        self.events.put(("enrollment_retake", token, {
                            "pose": pose, "captured": len(state.embeddings),
                            "current_pose": state.current_pose,
                        }))

                packet = self.controller.get_packet()
                if packet is None:
                    state.reset_stability()
                    self._post_enrollment_progress(token, {
                        "current_pose": state.current_pose, "detected_pose": "—",
                        "stable_frame_count": 0, "ready_frames": 8, "captured": len(state.embeddings),
                        "code": "CAMERA DISCONNECTED", "reason": "Camera chưa có frame mới.",
                        "bbox": None, "sharpness": None, "color": RED, "sequence": None,
                    }, last_ui_signature, last_ui_time)
                    last_ui_signature = self._analysis_signature("CAMERA DISCONNECTED", state, "—")
                    last_ui_time = time.monotonic()
                    stop_event.wait(0.04)
                    continue

                if packet.sequence <= last_sequence:
                    stop_event.wait(0.005)
                    continue
                last_sequence = packet.sequence
                age = time.monotonic() - packet.captured_at
                pose = state.current_pose
                if age < -0.1 or age > STALE_FRAME_SECONDS:
                    state.reset_stability()
                    analysis = {
                        "current_pose": pose, "detected_pose": "—", "stable_frame_count": 0,
                        "ready_frames": 8, "captured": len(state.embeddings), "code": "STALE_FRAME",
                        "reason": "Khung hình camera đã cũ.", "bbox": None, "sharpness": None,
                        "color": RED, "sequence": packet.sequence,
                    }
                else:
                    frame = packet.frame.copy()
                    outcome = validate_enrollment_frame(self.controller.engine, frame, pose)
                    observation = state.observe(packet.sequence, outcome)
                    face = outcome.get("face") if isinstance(outcome, dict) else None
                    quality = outcome.get("quality", {}) if isinstance(outcome, dict) else {}
                    analysis = {
                        **observation,
                        "detected_pose": outcome.get("detected_pose", "—"),
                        "bbox": list(face["bbox"]) if isinstance(face, dict) and face.get("bbox") else None,
                        "sharpness": quality.get("sharpness"),
                        "brightness": quality.get("brightness"),
                        "color": GREEN if observation["capture_due"] else
                                 (YELLOW if outcome.get("status") == "OK" else RED),
                        "sequence": packet.sequence,
                    }
                    signature = self._analysis_signature(analysis.get("code"), state,
                                                         analysis.get("detected_pose"))
                    now = time.monotonic()
                    if signature != last_ui_signature or now - last_ui_time >= 0.12:
                        self.events.put(("enrollment_progress", token, analysis))
                        last_ui_signature, last_ui_time = signature, now

                    if observation["capture_due"]:
                        _atomic_write_jpeg(session["stage"] / f"{pose}.jpg", frame)
                        capture = state.capture(outcome)
                        session["frames"][pose] = frame.copy()
                        self.events.put(("enrollment_captured", token, {
                            "pose": pose, "frame": frame.copy(), "captured": capture["captured"],
                            "current_pose": capture["complete"] and None or state.current_pose,
                        }))

                        if state.complete:
                            consistency = state.validate_complete()
                            if not consistency["valid"]:
                                bad_poses = consistency.get("bad_poses") or list(POSES)
                                for bad_pose in bad_poses:
                                    state.clear_pose(bad_pose)
                                    session["frames"].pop(bad_pose, None)
                                    staged = session["stage"] / f"{bad_pose}.jpg"
                                    if staged.exists():
                                        staged.unlink()
                                self.events.put(("enrollment_retake", token, {
                                    "poses": bad_poses, "captured": len(state.embeddings),
                                    "current_pose": state.current_pose, "reason": consistency.get("reason"),
                                }))
                                continue
                            self.events.put(("enrollment_saving", token, {}))
                            try:
                                snapshot = self.controller.register_employee(
                                    session["identity"], session["name"], state.embeddings,
                                    session["stage"], overwrite=session["overwrite"],
                                )
                            except Exception as exc:
                                session["ready_to_save"] = True
                                session["state"] = state
                                return {"status": "SAVE_FAILED", "error": str(exc), "state": state}
                            saved = True
                            session["saved"] = True
                            return {"status": "SAVED", "snapshot": snapshot}

            return {"status": "CANCELLED"}
        finally:
            if not saved and stop_event.is_set() and session["stage"].exists():
                shutil.rmtree(session["stage"], ignore_errors=True)

    @staticmethod
    def _analysis_signature(code, state, detected_pose):
        return (code, state.current_pose, state.stable_frame_count, len(state.embeddings), detected_pose)

    def _post_enrollment_progress(self, token, analysis, _last_signature, _last_time):
        self.events.put(("enrollment_progress", token, analysis))

    def _show_enrollment_progress(self, analysis):
        if self.enrollment is None:
            return
        pose = analysis.get("current_pose")
        pose_number = POSES.index(pose) + 1 if pose in POSES else min(int(analysis.get("captured", 0)) + 1, 5)
        requested = POSE_LABELS.get(pose, "Đã đủ 5 pose")
        self.pose_var.set(f"Pose yêu cầu: {pose_number}/5 · {requested}")
        detected = analysis.get("detected_pose") or "—"
        self.detected_pose_var.set(f"Pose phát hiện: {POSE_LABELS.get(detected, detected)}")
        stable = int(analysis.get("stable_frame_count", 0))
        ready_frames = int(analysis.get("ready_frames", 8))
        self.stability_var.set(f"Stability: {stable}/{ready_frames}")
        code = str(analysis.get("code", ""))
        reason = str(analysis.get("reason", ""))
        message = MESSAGE_LABELS.get(code, reason or "Giữ yên…")
        if analysis.get("capture_due"):
            message = "Đang tự chụp…"
        self.quality_var.set(f"Quality: {'GOOD' if analysis.get('color') == GREEN else message}")
        self.state_var.set("TRẠNG THÁI: SẴN SÀNG" if analysis.get("capture_due") else
                           f"TRẠNG THÁI: {message}")
        self.preview_hint.set(message)
        self.latest_analysis = analysis
        if analysis.get("sharpness") is not None:
            self.sharpness_var.set(f"Sharpness: {float(analysis['sharpness']):.1f}")

    def _show_captured_pose(self, payload):
        pose = payload["pose"]
        frame = payload["frame"]
        index = POSES.index(pose)
        thumb = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        thumb = ImageOps.fit(thumb, (74, 50), method=Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(thumb)
        self.thumbnail_photos[index] = photo
        self.thumb_labels[index].configure(image=photo, text="")
        self.thumb_status_labels[index].configure(text="✓", fg=GREEN)
        if pose not in self.captured_pose_order:
            self.captured_pose_order.append(pose)
        self.progress.configure(value=payload["captured"])
        self.progress_var.set(f"Tiến độ: {payload['captured']}/5")
        self.stability_var.set("Stability: 0/8")
        if payload["current_pose"]:
            number = POSES.index(payload["current_pose"]) + 1
            self.pose_var.set(f"Pose yêu cầu: {number}/5 · {POSE_LABELS[payload['current_pose']]}")
            self.state_var.set(f"TRẠNG THÁI: ĐÃ TỰ CHỤP {payload['captured']}/5")
            self.preview_hint.set(f"✓ {POSE_LABELS[pose]} · chuyển pose tiếp theo")
        else:
            self.pose_var.set("ĐÃ ĐỦ 5 MẪU · ĐANG KIỂM TRA")
            self.state_var.set("TRẠNG THÁI: ĐÃ ĐỦ 5 MẪU · ĐANG KIỂM TRA")
            self.preview_hint.set("Đang xác minh đủ 5 embedding trước khi lưu local.")

    def _show_retake_pose(self, payload):
        poses = payload.get("poses", [payload.get("pose")])
        for pose in poses:
            if pose not in POSES:
                continue
            index = POSES.index(pose)
            self.thumb_labels[index].configure(image="", text="—")
            self.thumb_status_labels[index].configure(text="•", fg=DIM)
            self.thumbnail_photos[index] = None
            if pose in self.captured_pose_order:
                self.captured_pose_order.remove(pose)
        self.progress.configure(value=payload.get("captured", 0))
        self.progress_var.set(f"Tiến độ: {payload.get('captured', 0)}/5")
        pose = payload.get("current_pose")
        if pose in POSES:
            self.pose_var.set(f"Pose yêu cầu: {POSES.index(pose) + 1}/5 · {POSE_LABELS[pose]}")
        self.stability_var.set("Stability: 0/8")
        self.state_var.set("TRẠNG THÁI: CẦN CHỤP LẠI POSE")
        self.preview_hint.set(payload.get("reason") or "Mẫu chưa cùng người; chụp lại pose được đánh dấu.")

    def _retake_pose(self):
        if self.enrollment is None:
            return
        if self.active_operation == "enrollment":
            if self.captured_pose_order:
                self.enrollment["requests"].put(self.captured_pose_order[-1])
            else:
                self.enrollment["requests"].put("reset-stability")
            self.state_var.set("TRẠNG THÁI: ĐANG CHỤP LẠI POSE…")
            return
        if self.enrollment.get("ready_to_save"):
            messagebox.showinfo("Đã đủ 5 mẫu", "Đang có đủ 5 mẫu; hãy lưu hoặc hủy phiên này.",
                                parent=self.root)

    def _cancel_enrollment(self):
        if self.enrollment is None:
            return
        if self.active_operation == "enrollment" and self.active_stop_event is not None:
            self.active_stop_event.set()
            self.state_var.set("TRẠNG THÁI: ĐANG HỦY ENROLLMENT…")
            return
        if self.enrollment.get("ready_to_save"):
            shutil.rmtree(self.enrollment["stage"], ignore_errors=True)
        self._discard_enrollment()
        self.state_var.set("TRẠNG THÁI: ĐĂNG KÝ ĐÃ HỦY · GALLERY KHÔNG THAY ĐỔI")
        self._set_controls()

    def _discard_enrollment(self):
        session = self.enrollment
        self.enrollment = None
        if session is not None and not session.get("saved"):
            shutil.rmtree(session["stage"], ignore_errors=True)
        self._reset_thumbnails()
        self.progress.configure(value=0)
        self.progress_var.set("Tiến độ: 0/5")
        self.pose_var.set("Pose yêu cầu: —")
        self.detected_pose_var.set("Pose phát hiện: —")
        self.quality_var.set("Quality: chờ enrollment")
        self.stability_var.set("Stability: 0/8")

    def _reset_thumbnails(self):
        self.thumbnail_photos = [None] * len(POSES)
        self.captured_pose_order = []
        if not hasattr(self, "thumb_labels"):
            return
        for image_label, status_label in zip(self.thumb_labels, self.thumb_status_labels):
            image_label.configure(image="", text="—")
            status_label.configure(text="•", fg=DIM)

    def _retry_save(self):
        session = self.enrollment
        if session is None or not session.get("ready_to_save"):
            return
        validation = session["state"].validate_complete()
        if not validation["valid"]:
            messagebox.showerror("5 pose chưa nhất quán", validation.get("reason", "Kiểm tra thất bại."),
                                 parent=self.root)
            return
        self.state_var.set("TRẠNG THÁI: ĐANG LƯU 5 MẪU LOCAL…")
        token = self._start_session("save_retry", lambda _token, _stop: self.controller.register_employee(
            session["identity"], session["name"], session["state"].embeddings,
            session["stage"], overwrite=session["overwrite"],
        ))
        if token:
            session["session_id"] = token
            session["ready_to_save"] = False
            self._set_controls()

    def _enrollment_saved(self, snapshot):
        self._populate_employees(snapshot["employees"])
        self.enrollment = None
        self.progress.configure(value=5)
        self.progress_var.set("Tiến độ: 5/5 · ĐÃ LƯU LOCAL")
        self.pose_var.set("ĐÃ ĐỦ 5 MẪU")
        self.stability_var.set("Stability: 8/8 · hoàn tất")
        self.state_var.set("TRẠNG THÁI: ĐĂNG KÝ THÀNH CÔNG")
        self.prediction_var.set("KẾT QUẢ: ĐÃ LƯU 5 EMBEDDING")
        self.preview_hint.set("Đã lưu đủ 5 pose và 5 embedding trong ai1_standalone_data.")
        self._set_controls()

    def enrollment_hint_set(self, text):
        self.quality_var.set(f"Quality: {text}")

    def _delete_selected(self):
        selected = self.employee_table.selection()
        if not selected:
            messagebox.showinfo("Chọn nhân viên", "Chọn nhân viên trong danh sách local.",
                                parent=self.root)
            return
        identity = selected[0]
        if not messagebox.askyesno("Xóa dữ liệu standalone",
                                   f"Xóa vĩnh viễn {identity} khỏi ai1_standalone_data trên máy này?",
                                   parent=self.root):
            return
        self.state_var.set(f"TRẠNG THÁI: ĐANG XÓA {identity} KHỎI KHO LOCAL…")
        self._start_job("delete_employee",
                        lambda: self.controller.delete_employee(identity, confirmed=True))

    def _recognize(self):
        if self.enrollment is not None:
            messagebox.showinfo("Đang enrollment", "Hoàn tất hoặc hủy enrollment trước.", parent=self.root)
            return
        self.best_result_frame = None
        self.best_frame_until = 0.0
        self.last_result_status = None
        self.state_var.set("TRẠNG THÁI: ĐANG QUÉT KHUÔN MẶT")
        self.prediction_var.set("KẾT QUẢ: ĐANG LẤY 3 SNAPSHOT MỚI")
        self.score_var.set("Similarity: —")
        self.sharpness_var.set("Sharpness: —")
        self.latency_var.set("Latency: —")
        self.progress_var.set("Snapshot: 0/3")
        self.preview_hint.set("ĐANG QUÉT KHUÔN MẶT · 0/3")

        def run(token, stop_event):
            return self.controller.recognize(
                stop_event,
                progress_callback=lambda count, total: self.events.put(
                    ("recognition_progress", token, (count, total))
                ),
                session_id=token,
            )
        self._start_session("recognition", run)

    def _show_recognition(self, result):
        self.last_result_status = result["status"]
        status = result["status"]
        score = float(result.get("score", 0.0))
        threshold = float(result.get("threshold", self.controller.threshold))
        latency = float(result.get("latency_ms", 0.0))
        self.threshold_var.set(f"Threshold: {threshold:.3f}")
        self.score_var.set(f"Similarity: {score:.3f}")
        self.latency_var.set(f"Latency: {latency:.1f} ms")
        self.sharpness_var.set(f"Sharpness: {float(result.get('sharpness', 0.0)):.1f}")
        self.progress_var.set(f"Snapshot: {result.get('captured_frames', 3)}/3")
        if status == "MATCH":
            identity = result["predicted_id"]
            employee = next((person for person in self.controller.employees
                             if person["MaNV"] == identity), None)
            name = employee["HoTen"] if employee else identity
            self.state_var.set("TRẠNG THÁI: ✓ MATCH")
            self.prediction_var.set(f"Mã NV: {identity} · Tên: {name}")
            self.preview_hint.set(f"NHẬN DIỆN THÀNH CÔNG · Similarity {score:.3f} · Threshold {threshold:.3f}")
        elif status == "UNKNOWN":
            self.state_var.set("TRẠNG THÁI: UNKNOWN")
            self.prediction_var.set("KẾT QUẢ: KHÔNG XÁC ĐỊNH KHUÔN MẶT")
            self.preview_hint.set(f"UNKNOWN · Similarity {score:.3f} · Threshold {threshold:.3f}")
        else:
            reason = str(result.get("reason", "Không đủ snapshot hợp lệ."))
            self.state_var.set("TRẠNG THÁI: RETRY · THỬ LẠI")
            self.prediction_var.set("KẾT QUẢ: RETRY")
            self.preview_hint.set(reason)
        best_frame = result.get("best_frame")
        if isinstance(best_frame, np.ndarray) and best_frame.size:
            overlay = best_frame.copy()
            bbox = result.get("bbox")
            color = (60, 220, 90) if status == "MATCH" else (40, 50, 240)
            if bbox and len(bbox) == 4:
                x1, y1, x2, y2 = [int(round(float(value))) for value in bbox]
                cv2.rectangle(overlay, (x1, y1), (x2, y2), color, 3)
            label = result["predicted_id"] if status == "MATCH" else status
            cv2.putText(overlay, str(label), (14, 34), cv2.FONT_HERSHEY_SIMPLEX,
                        0.85, color, 2, cv2.LINE_AA)
            self.best_result_frame = overlay
            self.best_frame_until = time.monotonic() + 4.0
        else:
            self.best_result_frame = None
            self.best_frame_until = 0.0

    def _draw_preview(self, frame, packet):
        image = frame.copy()
        height, width = image.shape[:2]
        center = (width // 2, int(height * 0.51))
        axes = (int(min(height * 0.72, width * 0.86) * 0.78 / 2),
                int(min(height * 0.72, width * 0.86) / 2))
        mask = np.zeros((height, width), dtype=np.uint8)
        cv2.ellipse(mask, center, axes, 0, 0, 360, 255, -1)
        dark = (image.astype(np.float32) * 0.48).astype(np.uint8)
        image = np.where(mask[:, :, None] > 0, image, dark)

        analysis = self.latest_analysis
        same_frame = analysis.get("sequence") == getattr(packet, "sequence", None)
        if same_frame and analysis.get("bbox"):
            bbox = analysis["bbox"]
            x1, y1, x2, y2 = [int(round(float(value))) for value in bbox]
            color_hex = analysis.get("color", RED)
            color = {GREEN: (50, 200, 90), YELLOW: (0, 210, 255), RED: (45, 55, 245)}.get(
                color_hex, (45, 55, 245)
            )
            cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)
        guide_color = (50, 200, 90) if same_frame and analysis.get("capture_due") else \
                      ((0, 210, 255) if same_frame and analysis.get("code") == "STABILIZING"
                       else (45, 55, 245))
        cv2.ellipse(image, center, axes, 0, 0, 360, guide_color, 2, cv2.LINE_AA)
        if self.active_operation == "recognition":
            cv2.putText(image, self.progress_var.get(), (14, 30), cv2.FONT_HERSHEY_SIMPLEX,
                        0.65, (0, 220, 255), 2, cv2.LINE_AA)
        elif self.enrollment is not None:
            cv2.putText(image, f"{self.stability_var.get()}  |  {self.progress_var.get()}",
                        (14, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.58, guide_color, 2, cv2.LINE_AA)
        return image

    def _update_preview(self):
        if self.closing:
            return
        packet = self.controller.get_packet()
        frame = packet.frame if packet is not None else None
        if frame is not None:
            self.current_packet = packet
            if self.best_result_frame is not None and time.monotonic() < self.best_frame_until:
                display = self.best_result_frame.copy()
            else:
                if self.best_result_frame is not None:
                    self.best_result_frame = None
                    if self.last_result_status in {"MATCH", "UNKNOWN"}:
                        self.state_var.set("TRẠNG THÁI: READY")
                        self.prediction_var.set("KẾT QUẢ: —")
                        self.preview_hint.set("Camera sẵn sàng cho phiên tiếp theo.")
                        self.last_result_status = None
                display = self._draw_preview(frame, packet)
            rgb = cv2.cvtColor(display, cv2.COLOR_BGR2RGB)
            image = Image.fromarray(rgb)
            width = max(500, self.preview.winfo_width())
            height = max(340, self.preview.winfo_height())
            image = ImageOps.contain(image, (width, height), method=Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(image)
            self.current_photo = photo
            self.preview.configure(image=photo, text="")
        elif self.controller.ready and self.active_operation is None:
            self.preview.configure(text="Chưa có frame mới từ camera.")
        self.root.after(33, self._update_preview)

    def _on_close(self):
        if self.closing:
            return
        self.closing = True
        self.close_event.set()
        if self.active_stop_event is not None:
            self.active_stop_event.set()
        session = self.enrollment
        worker = self.worker_thread

        def cleanup():
            if worker is not None and worker.is_alive():
                worker.join()
            if session is not None and not session.get("saved"):
                shutil.rmtree(session["stage"], ignore_errors=True)
            try:
                self.controller.release()
            except Exception:
                pass

        threading.Thread(target=cleanup, name="ai1-gui-close-cleanup", daemon=True).start()
        self.root.destroy()
