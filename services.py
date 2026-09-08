import database

# ============================================================
# NhanVien
# ============================================================

def fetch_dashboard_data():
    users = database.get_all_users()
    return [{"MaNV": row[0], "HoTen": row[1]} for row in users]


# ============================================================
# Health (Sức khỏe)
# ============================================================

def save_sensor_data(data):
    ma_nv   = data.get('MaNV')
    nhip_tim = data.get('NhipTim')
    spo2    = data.get('SpO2')
    if ma_nv and nhip_tim and spo2:
        database.insert_health_data(ma_nv, nhip_tim, spo2)
        return True
    return False

def fetch_health_data():
    records = database.get_recent_health_data()
    return [
        {
            "HoTen":    row[0],
            "NhipTim":  row[1],
            "SpO2":     row[2],
            "ThoiGian": row[3].strftime("%Y-%m-%d %H:%M:%S")
        }
        for row in records
    ]

def fetch_health_chart_data():
    """Trả về time-series nhịp tim cho Chart.js."""
    records = database.get_health_chart_data(limit=20)
    return [
        {
            "HoTen":    row[0],
            "NhipTim":  row[1],
            "ThoiGian": row[2].strftime("%H:%M:%S")
        }
        for row in records
    ]


# ============================================================
# Environment (Môi trường)
# ============================================================

def save_environment_data(data):
    nhiet_do = data.get('NhietDo')
    do_am    = data.get('DoAm')
    if nhiet_do is not None and do_am is not None:
        database.insert_environment_data(nhiet_do, do_am)
        return True
    return False

def fetch_latest_environment():
    row = database.get_recent_environment_data()
    if row:
        return {
            "NhietDo":  row[0],
            "DoAm":     row[1],
            "ThoiGian": row[2].strftime("%Y-%m-%d %H:%M:%S")
        }
    return {"NhietDo": "--", "DoAm": "--", "ThoiGian": "--"}

def fetch_environment_chart_data():
    """Trả về time-series nhiệt độ/độ ẩm cho Chart.js."""
    records = database.get_environment_chart_data(limit=20)
    return [
        {
            "NhietDo":  row[0],
            "DoAm":     row[1],
            "ThoiGian": row[2].strftime("%H:%M:%S")
        }
        for row in records
    ]


# ============================================================
# ChamCong (Attendance)
# ============================================================

def mark_attendance(data):
    ma_nv = data.get('MaNV')
    if ma_nv:
        database.insert_cham_cong(ma_nv)
        return True
    return False

def fetch_attendance_history():
    records = database.get_recent_cham_cong()
    return [
        {
            "HoTen":  row[0],
            "GioVao": row[1].strftime("%Y-%m-%d %H:%M:%S") if row[1] else "--",
            "GioRa":  row[2].strftime("%Y-%m-%d %H:%M:%S") if row[2] else "--"
        }
        for row in records
    ]


# ============================================================
# CanhBao / LichSuTrangThai (AI Alerts)
# ============================================================

def save_alert(ma_nv, loai_canh_bao, mo_ta, gia_tri=None):
    """
    Lưu một cảnh báo AI vào bảng CanhBao.
    Được gọi từ ai_engine khi phát hiện buồn ngủ hoặc gục đầu.
    """
    try:
        database.insert_canh_bao(ma_nv, loai_canh_bao, mo_ta, gia_tri)
        return True
    except Exception as e:
        print(f"[services] Loi luu canh bao: {e}")
        return False

def save_state_log(ma_nv, trang_thai, gia_tri=None):
    """
    Lưu log trạng thái AI vào LichSuTrangThai (gọi định kỳ, không phải mỗi frame).
    """
    try:
        database.insert_trang_thai(ma_nv, trang_thai, gia_tri)
        return True
    except Exception as e:
        print(f"[services] Loi luu trang thai: {e}")
        return False

def fetch_alert_history(limit=10):
    """Trả về danh sách cảnh báo gần nhất cho Dashboard."""
    records = database.get_recent_canh_bao(limit=limit)
    result = []
    for row in records:
        result.append({
            "HoTen":      row[0],
            "LoaiCanhBao": row[1],
            "MoTa":       row[2] if row[2] else "",
            "GiaTri":     round(float(row[3]), 3) if row[3] is not None else None,
            "ThoiGian":   row[4].strftime("%Y-%m-%d %H:%M:%S"),
            "DaXuLy":     bool(row[5])
        })
    return result