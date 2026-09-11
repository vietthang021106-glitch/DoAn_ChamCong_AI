"""
app.py — Flask Controller (Tầng Presentation)
==============================================
- Singleton camera VideoCapture (tránh xung đột tài nguyên)
- Dùng ai_engine.detector để phân tích frame
- RESTful API endpoints cho Dashboard
- Login / Logout + phân quyền theo VaiTro
"""

import threading
import functools
import cv2
from flask import (
    Flask, render_template, request, jsonify,
    Response, session, redirect, url_for
)
import services
import ai_engine

app = Flask(__name__)
app.secret_key = 'doan_chamcong_ai_secret_2024'


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
    return render_template('index.html')


@app.route('/employees')
@admin_required
def employees_page():
    """GET /employees — Trang quản lý nhân viên."""
    return render_template('employees.html')


@app.route('/me')
@login_required
def me_page():
    """GET /me — Trang cá nhân nhân viên."""
    return render_template('me.html')


# ============================================================
# Routes — Video (public cho MJPEG stream)
# ============================================================

@app.route('/video_feed')
def video_feed():
    return Response(
        generate_frames(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
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


@app.route('/api/environment', methods=['POST'])
def receive_env_data():
    data = request.get_json()

    if not data:
        return jsonify({"status": "error", "message": "No JSON body"}), 400

    success = services.save_environment_data(data)

    if success:
        return jsonify({"status": "success"}), 200

    return jsonify({"status": "error", "message": "Missing fields"}), 400


@app.route('/api/chamcong', methods=['POST'])
def receive_cham_cong():
    """
    POST /api/chamcong
    Body: {"MaNV": int, "MaTB": int (optional)}
    PUBLIC — ESP32 gọi trực tiếp.
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
        if ai_engine.detector.active_ma_nv == ma_nv:
            ai_engine.detector.clear_active_employee()

    http_code = 200 if result.get("status") == "success" else 400
    return jsonify(result), http_code


# ============================================================
# Routes — Dashboard API (admin required)
# ============================================================

@app.route('/api/get_health')
@login_required
def get_health():
    return jsonify(services.fetch_health_data())


@app.route('/api/chart/health')
@login_required
def chart_health():
    return jsonify(services.fetch_health_chart_data())


@app.route('/api/get_environment')
@login_required
def get_environment():
    return jsonify(services.fetch_latest_environment())


@app.route('/api/chart/environment')
@login_required
def chart_environment():
    return jsonify(services.fetch_environment_chart_data())


@app.route('/api/get_chamcong')
@login_required
def get_chamcong():
    return jsonify(services.fetch_attendance_history())


@app.route('/api/get_chamcong_today')
@login_required
def get_chamcong_today():
    return jsonify(services.fetch_today_attendance_summary())


@app.route('/api/get_chamcong_weekly')
@login_required
def get_chamcong_weekly():
    return jsonify(services.fetch_attendance_weekly())


@app.route('/api/dashboard/attendance')
@login_required
def dashboard_attendance():
    return jsonify(services.fetch_attendance_dashboard())


@app.route('/api/attendance/today')
@login_required
def attendance_today():
    data = services.fetch_attendance_dashboard()
    return jsonify(data.get("Records", []))


# ============================================================
# Routes — Ca làm việc (admin)
# ============================================================

@app.route('/api/shifts')
@login_required
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
# Routes — AI Alerts & Status
# ============================================================

@app.route('/api/get_alerts')
@login_required
def get_alerts():
    limit = request.args.get('limit', 10, type=int)
    return jsonify(services.fetch_alert_history(limit=limit))


@app.route('/api/ai_status')
@login_required
def ai_status():
    return jsonify(ai_engine.detector.get_current_status())


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
# Routes — Trang cá nhân API
# ============================================================

@app.route('/api/me/attendance')
@login_required
def api_me_attendance():
    """GET /api/me/attendance — Chấm công cá nhân."""
    ma_nv = session.get('MaNV')
    return jsonify(services.fetch_my_attendance(ma_nv))


@app.route('/api/me/info')
@login_required
def api_me_info():
    """GET /api/me/info — Thông tin user đang login."""
    return jsonify({
        "MaNV":      session.get('MaNV'),
        "HoTen":     session.get('HoTen'),
        "MaVaiTro":  session.get('MaVaiTro'),
        "TenVaiTro": session.get('TenVaiTro'),
    })


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