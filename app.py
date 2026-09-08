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
        return jsonify({
            "status": "error",
            "message": "No JSON body"
        }), 400

    success = services.save_sensor_data(data)

    if success:
        return jsonify({
            "status": "success"
        }), 200

    return jsonify({
        "status": "error",
        "message": "Missing fields"
    }), 400


@app.route('/api/get_health')
def get_health():
    return jsonify(
        services.fetch_health_data()
    )


@app.route('/api/chart/health')
def chart_health():
    """Time-series nhịp tim cho Chart.js."""
    return jsonify(
        services.fetch_health_chart_data()
    )


# ============================================================
# Routes — Environment
# ============================================================

@app.route('/api/environment', methods=['POST'])
def receive_env_data():
    data = request.get_json()

    if not data:
        return jsonify({
            "status": "error",
            "message": "No JSON body"
        }), 400

    success = services.save_environment_data(data)

    if success:
        return jsonify({
            "status": "success"
        }), 200

    return jsonify({
        "status": "error",
        "message": "Missing fields"
    }), 400


@app.route('/api/get_environment')
def get_environment():
    return jsonify(
        services.fetch_latest_environment()
    )


@app.route('/api/chart/environment')
def chart_environment():
    """Time-series nhiệt độ/độ ẩm cho Chart.js."""
    return jsonify(
        services.fetch_environment_chart_data()
    )


# ============================================================
# Routes — Chấm công
# ============================================================

@app.route('/api/chamcong', methods=['POST'])
def receive_cham_cong():
    """
    Nhận dữ liệu chấm công.

    Khi chấm công thành công:
    - Lưu dữ liệu bằng services.mark_attendance()
    - Gán MaNV vừa chấm công làm nhân viên đang được AI giám sát
    """

    data = request.get_json()

    if not data:
        return jsonify({
            "status": "error",
            "message": "No JSON body"
        }), 400

    success = services.mark_attendance(data)

    if success:
        ma_nv = data.get('MaNV')

        # Chỉ gán cho AI sau khi chấm công thành công
        if ma_nv is not None:
            ai_engine.detector.set_active_employee(ma_nv)

        return jsonify({
            "status": "success"
        }), 200

    return jsonify({
        "status": "error",
        "message": "Missing MaNV"
    }), 400


@app.route('/api/get_chamcong')
def get_chamcong():
    return jsonify(
        services.fetch_attendance_history()
    )


# ============================================================
# Routes — AI Alerts & Status
# ============================================================

@app.route('/api/get_alerts')
def get_alerts():
    """Trả về danh sách cảnh báo AI gần nhất."""
    limit = request.args.get(
        'limit',
        10,
        type=int
    )

    return jsonify(
        services.fetch_alert_history(
            limit=limit
        )
    )


@app.route('/api/ai_status')
def ai_status():
    """
    Trả về trạng thái AI hiện tại:
    - EAR
    - Tilt
    - State
    - MaNV đang được giám sát
    """
    return jsonify(
        ai_engine.detector.get_current_status()
    )


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