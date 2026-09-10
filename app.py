"""
app.py — Flask Controller (Tầng Presentation)
==============================================
- Singleton camera VideoCapture (tránh xung đột tài nguyên)
- Dùng ai_engine.detector để phân tích frame
- RESTful API endpoints cho Dashboard
"""

import threading
import cv2
from flask import Flask, render_template, request, jsonify, Response
import services
import ai_engine

app = Flask(__name__)
app.secret_key = 'doan_chamcong_ai_secret_2024'


# ============================================================
# Camera Singleton — tránh xung đột tài nguyên giữa các request
# ============================================================

_camera = None
_camera_lock = threading.Lock()


def get_camera():
    """Trả về instance camera toàn cục, khởi tạo nếu chưa có."""
    global _camera

    with _camera_lock:
        if _camera is None or not _camera.isOpened():
            _camera = cv2.VideoCapture(0)
            _camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            _camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            _camera.set(cv2.CAP_PROP_FPS, 30)

        return _camera


# ============================================================
# Video Stream Generator
# ============================================================

def generate_frames():
    """
    Generator cho MJPEG stream.
    Dùng singleton camera + ai_engine.detector để phân tích frame.
    """
    camera = get_camera()

    while True:
        with _camera_lock:
            success, frame = camera.read()

        if not success:
            break

        # Phân tích frame với AI engine
        annotated_frame, alert = ai_engine.detector.analyze_frame(frame)

        # Encode sang JPEG
        ret, buffer = cv2.imencode(
            '.jpg',
            annotated_frame,
            [cv2.IMWRITE_JPEG_QUALITY, 85]
        )

        if not ret:
            continue

        frame_bytes = buffer.tobytes()

        yield (
            b'--frame\r\n'
            b'Content-Type: image/jpeg\r\n\r\n'
            + frame_bytes
            + b'\r\n'
        )


# ============================================================
# Routes — Pages
# ============================================================

@app.route('/')
def index():
    return render_template('index.html')


# ============================================================
# Routes — Video
# ============================================================

@app.route('/video_feed')
def video_feed():
    return Response(
        generate_frames(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )


# ============================================================
# Routes — Sensor / Health
# ============================================================

@app.route('/api/sensor', methods=['POST'])
def receive_sensor_data():
    data = request.get_json()

    if not data:
        return jsonify({"status": "error", "message": "No JSON body"}), 400

    success = services.save_sensor_data(data)

    if success:
        return jsonify({"status": "success"}), 200

    return jsonify({"status": "error", "message": "Missing fields"}), 400


@app.route('/api/get_health')
def get_health():
    return jsonify(services.fetch_health_data())


@app.route('/api/chart/health')
def chart_health():
    """Time-series nhịp tim cho Chart.js."""
    return jsonify(services.fetch_health_chart_data())


# ============================================================
# Routes — Environment
# ============================================================

@app.route('/api/environment', methods=['POST'])
def receive_env_data():
    data = request.get_json()

    if not data:
        return jsonify({"status": "error", "message": "No JSON body"}), 400

    success = services.save_environment_data(data)

    if success:
        return jsonify({"status": "success"}), 200

    return jsonify({"status": "error", "message": "Missing fields"}), 400


@app.route('/api/get_environment')
def get_environment():
    return jsonify(services.fetch_latest_environment())


@app.route('/api/chart/environment')
def chart_environment():
    """Time-series nhiệt độ/độ ẩm cho Chart.js."""
    return jsonify(services.fetch_environment_chart_data())


# ============================================================
# Routes — Chấm công (CORE)
# ============================================================

@app.route('/api/chamcong', methods=['POST'])
def receive_cham_cong():
    """
    POST /api/chamcong
    Body: {"MaNV": int, "MaTB": int (optional)}

    Lần đầu  → checkin
    Lần hai  → checkout
    Lần ba   → completed (không tạo record mới)

    Khi check-in thành công → set_active_employee
    Khi check-out thành công, nếu đúng người → clear_active_employee
    """
    data = request.get_json()

    if not data:
        return jsonify({"status": "error", "message": "No JSON body"}), 400

    ma_nv = data.get('MaNV')
    ma_tb = data.get('MaTB', 1)

    if ma_nv is None:
        return jsonify({"status": "error", "message": "Thiếu MaNV"}), 400

    result = services.process_attendance(ma_nv, ma_tb)

    # Đồng bộ AI Engine
    if result.get("action") == "checkin" and result.get("status") == "success":
        ai_engine.detector.set_active_employee(ma_nv)

    elif result.get("action") == "checkout" and result.get("status") == "success":
        # Chỉ clear nếu đúng là người đang được giám sát
        if ai_engine.detector.active_ma_nv == ma_nv:
            ai_engine.detector.clear_active_employee()

    http_code = 200 if result.get("status") == "success" else 400
    return jsonify(result), http_code


@app.route('/api/get_chamcong')
def get_chamcong():
    """Lịch sử chấm công gần nhất (backward compat)."""
    return jsonify(services.fetch_attendance_history())


@app.route('/api/get_chamcong_today')
def get_chamcong_today():
    """Chấm công hôm nay kèm tổng nhân viên (backward compat)."""
    return jsonify(services.fetch_today_attendance_summary())


@app.route('/api/get_chamcong_weekly')
def get_chamcong_weekly():
    """Thống kê chấm công 7 ngày gần nhất."""
    return jsonify(services.fetch_attendance_weekly())


# ============================================================
# Routes — Dashboard Attendance (NEW)
# ============================================================

@app.route('/api/dashboard/attendance')
def dashboard_attendance():
    """
    GET /api/dashboard/attendance

    Trả về:
    {
        "Summary": {
            "TongNhanVien": int,
            "DaChamCong":   int,
            "DangLamViec":  int,
            "DiTre":        int,
            "VeSom":        int,
            "ChuaChamCong": int,
            "DaRaVe":       int,
            "CanhBaoHomNay":int
        },
        "Records": [
            {
                "MaNV":           int,
                "HoTen":          str,
                "MaCa":           int|null,
                "TenCa":          str,
                "GioBatDau":      "HH:MM"|"--",
                "GioKetThuc":     "HH:MM"|"--",
                "GioVao":         "HH:MM:SS"|null,
                "GioRa":          "HH:MM:SS"|null,
                "TrangThaiVao":   str,
                "TrangThaiRa":    str,
                "TrangThaiTongHop": str
            },
            ...
        ]
    }
    """
    return jsonify(services.fetch_attendance_dashboard())


@app.route('/api/attendance/today')
def attendance_today():
    """
    GET /api/attendance/today
    Alias của dashboard/attendance — trả records list trực tiếp.
    """
    data = services.fetch_attendance_dashboard()
    return jsonify(data.get("Records", []))


# ============================================================
# Routes — Ca làm việc
# ============================================================

@app.route('/api/shifts')
def get_shifts():
    """GET /api/shifts — Danh sách ca làm việc."""
    return jsonify(services.fetch_all_shifts())


@app.route('/api/assign_shift', methods=['POST'])
def post_assign_shift():
    """
    POST /api/assign_shift
    Body: {"MaNV": int, "MaCa": int, "NgayLamViec": "YYYY-MM-DD"}
    NgayLamViec không bắt buộc, mặc định là hôm nay.
    """
    data = request.get_json()

    if not data:
        return jsonify({"status": "error", "message": "No JSON body"}), 400

    ok, msg = services.assign_shift(data)

    if ok:
        return jsonify({"status": "success", "message": msg}), 200

    return jsonify({"status": "error", "message": msg}), 400


# ============================================================
# Routes — AI Alerts & Status
# ============================================================

@app.route('/api/get_alerts')
def get_alerts():
    """Trả về danh sách cảnh báo AI gần nhất."""
    limit = request.args.get('limit', 10, type=int)
    return jsonify(services.fetch_alert_history(limit=limit))


@app.route('/api/ai_status')
def ai_status():
    """
    Trả về trạng thái AI hiện tại:
    - EAR, Tilt, State, MaNV đang được giám sát
    """
    return jsonify(ai_engine.detector.get_current_status())


# ============================================================
# Entry point
# ============================================================

if __name__ == '__main__':
    # use_reloader=False để tránh khởi tạo camera 2 lần khi debug
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True,
        use_reloader=False
    )