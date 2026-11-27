"""
app.py — Flask Controller (Tầng Presentation)
==============================================
- Singleton camera source + FramePump (tránh xung đột tài nguyên)
- Video feed chỉ phân phối frame từ camera singleton
- RESTful API endpoints cho Dashboard
- Login / Logout + phân quyền theo VaiTro
"""

import functools
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request

import cv2
from flask import (
    Flask, render_template, request, jsonify,
    Response, session, redirect, url_for
)
import services
import database as _db
from camera_source import FramePacket, open_camera as _open_camera_source

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-change-me")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

AI1_SERVICE_URL = os.getenv("AI1_SERVICE_URL", "http://127.0.0.1:5001").rstrip("/")
PHP_EMPLOYEE_URL = os.getenv(
    "PHP_EMPLOYEE_URL",
    "http://127.0.0.1/DoAn_ChamCong_AI/?action=index",
)


# ============================================================
# Auth Middleware
# ============================================================

def login_required(f):
    """Decorator: yêu cầu đăng nhập."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if 'MaNV' not in session:
            # API request → trả JSON 401
            if request.path.startswith('/api/'):
                return jsonify({"status": "error", "message": "Chưa đăng nhập"}), 401
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    """Decorator: yêu cầu đăng nhập + Quản trị viên (MaVaiTro=1)."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if 'MaNV' not in session:
            if request.path.startswith('/api/'):
                return jsonify({"status": "error", "message": "Chưa đăng nhập"}), 401
            return redirect(url_for('login_page'))
        if session.get('MaVaiTro') != 1:
            if request.path.startswith('/api/'):
                return jsonify({"status": "error", "message": "Không có quyền truy cập"}), 403
            return redirect(url_for('me_page'))
        return f(*args, **kwargs)
    return decorated


# ============================================================
# Camera Source Singleton — tránh xung đột tài nguyên giữa các request
# ============================================================

_camera = None
_camera_lock = threading.Lock()
_camera_retry_after = 0.0
_camera_generation = 0


def get_camera():
    """Return the sole background-pumped camera source shared by all routes."""
    global _camera, _camera_retry_after, _camera_generation

    with _camera_lock:
        should_retry = _camera is not None and not _camera.is_opened() and time.monotonic() >= _camera_retry_after
        if _camera is None or should_retry:
            if _camera is not None:
                _camera.release()
            _camera = _open_camera_source()
            _camera_generation += 1
            _camera_retry_after = time.monotonic() + 5.0

        return _camera


# ============================================================
# Video Stream Generator
# ============================================================

def generate_frames():
    """
    Generator cho MJPEG stream.
    Dùng singleton camera và giữ nguyên frame nguồn cho các client video.
    """
    while True:
        packet = _read_camera_packet()
        if packet is None:
            time.sleep(0.03)
            continue
        frame = packet.frame

        # Encode sang JPEG
        ret, buffer = cv2.imencode(
            '.jpg',
            frame,
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
# Routes — Login / Logout
# ============================================================

@app.route('/login')
def login_page():
    """GET /login — Trang đăng nhập."""
    # Đã login rồi thì redirect
    if 'MaNV' in session:
        if session.get('MaVaiTro') == 1:
            return redirect(url_for('index'))
        return redirect(url_for('me_page'))
    return render_template('login.html')


@app.route('/api/login', methods=['POST'])
def api_login():
    """
    POST /api/login
    Body: {"TenDangNhap": "admin", "MatKhau": "admin123"}
    """
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "No JSON body"}), 400

    username = data.get('TenDangNhap', '')
    password = data.get('MatKhau', '')

    result = services.authenticate(username, password)

    if result.get("status") != "success":
        return jsonify(result), 401

    user = result["user"]

    # Lưu session
    session['MaTK']      = user['MaTK']
    session['MaNV']      = user['MaNV']
    session['HoTen']     = user['HoTen']
    session['MaVaiTro']  = user['MaVaiTro']
    session['TenVaiTro'] = user['TenVaiTro']

    # Xác định URL redirect theo role
    if user['MaVaiTro'] == 1:
        redirect_url = '/'
    else:
        redirect_url = '/me'

    return jsonify({
        "status":      "success",
        "message":     "Đăng nhập thành công",
        "redirect":    redirect_url,
        "user": {
            "MaNV":      user['MaNV'],
            "HoTen":     user['HoTen'],
            "MaVaiTro":  user['MaVaiTro'],
            "TenVaiTro": user['TenVaiTro'],
        },
    }), 200


@app.route('/api/logout', methods=['POST'])
def api_logout():
    """POST /api/logout — Đăng xuất."""
    session.clear()
    return jsonify({"status": "success", "message": "Đã đăng xuất"}), 200


@app.route('/logout')
def logout_page():
    """GET /logout — Đăng xuất và redirect về login."""
    session.clear()
    return redirect(url_for('login_page'))


# ============================================================
# Routes — Pages (có phân quyền)
# ============================================================

@app.route('/')
@admin_required
def index():
    return render_template('index.html', php_employee_url=PHP_EMPLOYEE_URL)


@app.route('/employees')
@admin_required
def employees_page():
    """GET /employees — Trang quản lý nhân viên."""
    return render_template('employees.html')


@app.route('/me')
@login_required
def me_page():
    """GET /me — Trang cá nhân nhân viên."""
    if session.get('MaVaiTro') == 1:
        return redirect(url_for('index'))
    return render_template('me.html')


# ============================================================
# Routes — Video (public cho MJPEG stream)
# ============================================================

@app.route('/video_feed')
@login_required
def video_feed():
    return Response(
        generate_frames(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )


@app.route('/internal/camera/frame')
def internal_camera_frame():
    """Expose one frame to the loopback AI service through the camera owner."""
    if request.remote_addr not in {'127.0.0.1', '::1'}:
        return jsonify({"success": False, "message": "Local requests only."}), 403

    packet = _read_camera_packet()
    if packet is None:
        return jsonify({"success": False, "message": "Camera không khả dụng."}), 503
    frame = packet.frame

    encoded, image = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not encoded:
        return jsonify({"success": False, "message": "Không mã hóa được frame."}), 503

    return Response(
        image.tobytes(),
        mimetype='image/jpeg',
        headers={
            "Cache-Control": "no-store",
            "X-Frame-Sequence": str(packet.sequence),
            "X-Frame-Monotonic": format(packet.captured_at, ".9f"),
        },
    )


# ============================================================
# Routes — ESP32 Sensor (PUBLIC — không yêu cầu login)
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


@app.route('/api/chamcong', methods=['POST'])
def receive_cham_cong():
    """
    POST /api/chamcong
    Body: {"MaNV": int, "MaTB": int (optional)}
    PUBLIC — ESP32 gọi trực tiếp.

    Nếu camera singleton đang mở, capture 1 frame và encode JPG
    để lưu làm bằng chứng. Không tạo camera mới.
    Nếu camera chưa mở hoặc có lỗi, image_bytes = None —
    chấm công vẫn hoạt động bình thường.
    """
    data = request.get_json()

    if not data:
        return jsonify({"status": "error", "message": "No JSON body"}), 400

    ma_nv = data.get('MaNV')
    ma_tb = data.get('MaTB', 1)

    if ma_nv is None:
        return jsonify({"status": "error", "message": "Thiếu MaNV"}), 400

    # --- Capture frame từ singleton camera ---
    # Dùng get_camera() thay vì check _camera is not None trực tiếp,
    # để camera được khởi tạo ngay cả khi /video_feed chưa được gọi trước.
    image_bytes = None
    try:
        ok, frame = _read_camera_frame()
        if ok and frame is not None:
            image_bytes = services.encode_frame_to_jpg(frame)
    except Exception as _cap_err:
        # Không được để lỗi camera block chấm công
        print(f"[app] Canh bao: khong the capture frame: {_cap_err}")

    result = services.process_attendance(ma_nv, ma_tb, image_bytes)

    http_code = 200 if result.get("status") == "success" else 400
    return jsonify(result), http_code



# ============================================================
# Routes — Ảnh bằng chứng chấm công (admin only)
# ============================================================


@app.route('/api/attendance/<int:ma_cc>/image/in')
@admin_required
def attendance_image_in(ma_cc):
    """
    GET /api/attendance/<ma_cc>/image/in
    Trả AnhVao của bản ghi MaCC dưới dạng image/jpeg.
    """
    img = _db.get_attendance_image(ma_cc, "in")
    if img is None:
        return jsonify({
            "status":  "error",
            "message": "Không có ảnh bằng chứng",
        }), 404
    return Response(img, mimetype="image/jpeg")


@app.route('/api/attendance/<int:ma_cc>/image/out')
@admin_required
def attendance_image_out(ma_cc):
    """
    GET /api/attendance/<ma_cc>/image/out
    Trả AnhRa của bản ghi MaCC dưới dạng image/jpeg.
    """
    img = _db.get_attendance_image(ma_cc, "out")
    if img is None:
        return jsonify({
            "status":  "error",
            "message": "Không có ảnh bằng chứng",
        }), 404
    return Response(img, mimetype="image/jpeg")


# ============================================================
# Routes — Dashboard API (admin required)
# ============================================================

@app.route('/api/get_health')
@admin_required
def get_health():
    return jsonify(services.fetch_health_data())


@app.route('/api/chart/health')
@admin_required
def chart_health():
    return jsonify(services.fetch_health_chart_data())


@app.route('/api/get_chamcong')
@admin_required
def get_chamcong():
    return jsonify(services.fetch_attendance_history())


@app.route('/api/get_chamcong_today')
@admin_required
def get_chamcong_today():
    return jsonify(services.fetch_today_attendance_summary())


@app.route('/api/get_chamcong_weekly')
@admin_required
def get_chamcong_weekly():
    return jsonify(services.fetch_attendance_weekly())


@app.route('/api/dashboard/attendance')
@admin_required
def dashboard_attendance():
    from datetime import datetime as _dt
    date_str = request.args.get('date')
    if date_str:
        try:
            _dt.strptime(date_str.strip(), '%Y-%m-%d')
        except ValueError:
            return jsonify({
                'status': 'error',
                'message': 'Ngày không hợp lệ. Định dạng yêu cầu: YYYY-MM-DD'
            }), 400
    return jsonify(services.fetch_attendance_dashboard(date_str))


@app.route('/api/attendance/today')
@admin_required
def attendance_today():
    data = services.fetch_attendance_dashboard()
    return jsonify(data.get("Records", []))


@app.route('/api/attendance/history')
@admin_required
def attendance_history_filtered():
    tu_ngay = request.args.get('tu_ngay')
    den_ngay = request.args.get('den_ngay')
    keyword = request.args.get('keyword')
    
    # validate date format if provided
    from datetime import datetime as _dt
    for date_str in [tu_ngay, den_ngay]:
        if date_str:
            try:
                _dt.strptime(date_str.strip(), '%Y-%m-%d')
            except ValueError:
                return jsonify({
                    'status': 'error',
                    'message': 'Ngày không hợp lệ. Định dạng yêu cầu: YYYY-MM-DD'
                }), 400
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
                
    data = services.fetch_attendance_history_filtered(tu_ngay, den_ngay, keyword, page, limit)
    return jsonify(data)


# ============================================================
# Routes — Ca làm việc (admin)
# ============================================================

@app.route('/api/shifts')
@admin_required
def get_shifts():
    return jsonify(services.fetch_all_shifts())


@app.route('/api/assign_shift', methods=['POST'])
@admin_required
def post_assign_shift():
    data = request.get_json()

    if not data:
        return jsonify({"status": "error", "message": "No JSON body"}), 400

    ok, msg = services.assign_shift(data)

    if ok:
        return jsonify({"status": "success", "message": msg}), 200

    return jsonify({"status": "error", "message": msg}), 400


# ============================================================
# ============================================================
# Routes — Vai trò (admin)
# ============================================================

@app.route('/api/roles')
@admin_required
def get_roles():
    return jsonify(services.fetch_all_roles())


# ============================================================
# Routes — Nhân viên CRUD (admin)
# ============================================================

@app.route('/api/employees')
@admin_required
def list_employees():
    return jsonify(services.fetch_employees())


@app.route('/api/employees/<int:ma_nv>')
@admin_required
def get_employee(ma_nv):
    emp = services.fetch_employee(ma_nv)
    if emp is None:
        return jsonify({"status": "error", "message": "Không tìm thấy nhân viên"}), 404
    return jsonify(emp)


@app.route('/api/employees', methods=['POST'])
@admin_required
def create_employee():
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "No JSON body"}), 400

    data.pop("AnhKhuonMat", None)

    result = services.create_employee(data)

    if result.get("status") == "success":
        return jsonify(result), 201

    return jsonify(result), 400


@app.route('/api/employees/<int:ma_nv>', methods=['PUT'])
@admin_required
def update_employee(ma_nv):
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "No JSON body"}), 400

    data.pop("AnhKhuonMat", None)

    try:
        result = services.edit_employee(ma_nv, data)
    except Exception as e:
        return jsonify({"status": "error", "message": f"Lỗi server: {e}"}), 500

    if result.get("status") == "success":
        return jsonify(result), 200

    if result.get("status") == "not_found":
        return jsonify({"status": "error", "message": "Không tìm thấy nhân viên"}), 404

    return jsonify(result), 400


# ============================================================
# AI1 routes — PHP/MariaDB owns enrollment; the loopback AI service owns recognition.


def _read_camera_packet():
    try:
        packet = get_camera().get_frame()
        if packet is None:
            return None
        return FramePacket(
            packet.frame,
            (_camera_generation << 32) | int(packet.sequence),
            packet.captured_at,
        )
    except Exception as exc:
        app.logger.warning("Camera source unavailable: %s", exc)
        return None


def _read_camera_frame():
    packet = _read_camera_packet()
    return (True, packet.frame) if packet is not None else (False, None)


def _request_ai1_json(method, path, payload=None):
    """Proxy a fixed loopback AI-service route without exposing arbitrary URLs."""
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        AI1_SERVICE_URL + path,
        data=body,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method=method,
    )
    try:
        response = urllib.request.urlopen(req, timeout=2.0)
    except urllib.error.HTTPError as exc:
        response = exc
    except Exception as exc:
        raise RuntimeError("AI service không khả dụng.") from exc
    with response:
        raw = response.read(1024 * 1024 + 1)
        status_code = getattr(response, "status", 200)
    if len(raw) > 1024 * 1024:
        raise RuntimeError("Phản hồi AI service vượt giới hạn.")
    try:
        result = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("AI service trả phản hồi không hợp lệ.") from exc
    if not isinstance(result, dict):
        raise RuntimeError("AI service trả phản hồi không hợp lệ.")
    return status_code, result


@app.route('/api/employees/<int:ma_nv>/face/register', methods=['POST'])
@admin_required
def register_face(ma_nv):
    return jsonify({
        "status": "error",
        "message": "Đăng ký khuôn mặt dùng luồng quản lý nhân viên PHP/MariaDB.",
        "enrollment_url": PHP_EMPLOYEE_URL,
    }), 410


@app.route('/api/face/identify', methods=['POST'])
@admin_required
def face_identify():
    return jsonify({"status": "RETRY", "match": False,
                    "message": "Nhận diện một ảnh đơn đã tắt; dùng session ba snapshot."}), 409


@app.route('/api/face/verify', methods=['POST'])
@admin_required
def face_verify():
    return jsonify({"status": "RETRY", "match": False,
                    "message": "Xác minh một ảnh đơn đã tắt; dùng session ba snapshot."}), 409


@app.route('/api/face/identify/camera', methods=['POST'])
@admin_required
def face_identify_camera():
    """Compatibility endpoint: start the central three-fresh-snapshot session."""
    return start_face_recognition_session()


@app.route('/api/face/recognition-sessions', methods=['POST'])
@admin_required
def start_face_recognition_session():
    try:
        status_code, result = _request_ai1_json(
            "POST", "/api/ai/recognition-sessions", {}
        )
    except Exception as exc:
        return jsonify({"success": False, "message": str(exc)}), 503
    return jsonify(result), status_code


@app.route('/api/face/recognition-sessions/<session_id>', methods=['GET'])
@admin_required
def face_recognition_session_status(session_id):
    if not re.fullmatch(r"[a-f0-9]{32}", session_id):
        return jsonify({"success": False, "message": "Session ID không hợp lệ."}), 400
    try:
        status_code, result = _request_ai1_json(
            "GET", f"/api/ai/recognition-sessions/{session_id}"
        )
    except Exception as exc:
        return jsonify({"success": False, "message": str(exc)}), 503
    return jsonify(result), status_code


# Routes — Trang cá nhân API
# ============================================================

@app.route('/api/me/attendance')
@login_required
def api_me_attendance():
    """GET /api/me/attendance — Chấm công cá nhân."""
    ma_nv = session.get('MaNV')
    return jsonify(services.fetch_my_attendance(ma_nv))


@app.route('/api/me/profile')
@login_required
def api_me_profile():
    ma_nv = session.get('MaNV')
    return jsonify(services.fetch_employee_profile(ma_nv))


@app.route('/api/me/today')
@login_required
def api_me_today():
    ma_nv = session.get('MaNV')
    return jsonify(services.fetch_my_today_status(ma_nv))


@app.route('/api/me/health')
@login_required
def api_me_health():
    ma_nv = session.get('MaNV')
    return jsonify(services.fetch_my_health(ma_nv))


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
