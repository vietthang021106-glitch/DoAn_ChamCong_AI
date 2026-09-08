import pyodbc

# ============================================================
# Kết nối cơ sở dữ liệu SQL Server
# ============================================================

def get_connection():
    conn_str = (
        "Driver={ODBC Driver 17 for SQL Server};"
        "Server=HEHE\\admin;"
        "Database=DoAn_ChamCong_AI;"
        "Trusted_Connection=yes;"
    )
    return pyodbc.connect(conn_str)


# ============================================================
# NhanVien
# ============================================================

def get_all_users():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT MaNV, HoTen FROM NhanVien")
    rows = cursor.fetchall()
    conn.close()
    return rows


# ============================================================
# LichSuSucKhoe (Health)
# ============================================================

def insert_health_data(ma_nv, nhip_tim, spo2):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO LichSuSucKhoe (MaNV, NhipTim, SpO2) VALUES (?, ?, ?)",
        (ma_nv, nhip_tim, spo2)
    )
    conn.commit()
    conn.close()

def get_recent_health_data(limit=5):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT TOP {limit} NhanVien.HoTen, LichSuSucKhoe.NhipTim,
               LichSuSucKhoe.SpO2, LichSuSucKhoe.ThoiGian
        FROM LichSuSucKhoe
        JOIN NhanVien ON LichSuSucKhoe.MaNV = NhanVien.MaNV
        ORDER BY LichSuSucKhoe.ThoiGian DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_health_chart_data(limit=20):
    """Trả về dữ liệu nhịp tim gần nhất để vẽ biểu đồ (sắp xếp tăng dần)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT TOP {limit} NhanVien.HoTen, LichSuSucKhoe.NhipTim, LichSuSucKhoe.ThoiGian
        FROM LichSuSucKhoe
        JOIN NhanVien ON LichSuSucKhoe.MaNV = NhanVien.MaNV
        ORDER BY LichSuSucKhoe.ThoiGian DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return list(reversed(rows))


# ============================================================
# ThongSoMoiTruong (Environment)
# ============================================================

def insert_environment_data(nhiet_do, do_am, ma_tb=1):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO ThongSoMoiTruong (NhietDo, DoAm, MaTB) VALUES (?, ?, ?)",
        (nhiet_do, do_am, ma_tb)
    )
    conn.commit()
    conn.close()

def get_recent_environment_data():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT TOP 1 NhietDo, DoAm, ThoiGian FROM ThongSoMoiTruong ORDER BY ThoiGian DESC"
    )
    row = cursor.fetchone()
    conn.close()
    return row

def get_environment_chart_data(limit=20):
    """Trả về lịch sử nhiệt độ/độ ẩm để vẽ biểu đồ (sắp xếp tăng dần)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT TOP {limit} NhietDo, DoAm, ThoiGian
        FROM ThongSoMoiTruong
        ORDER BY ThoiGian DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return list(reversed(rows))


# ============================================================
# ChamCong (Attendance)
# ============================================================

def insert_cham_cong(ma_nv, ma_tb=1):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO ChamCong (MaNV, GioVao, MaTB) VALUES (?, GETDATE(), ?)",
        (ma_nv, ma_tb)
    )
    conn.commit()
    conn.close()

def get_recent_cham_cong(limit=5):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT TOP {limit} NhanVien.HoTen, ChamCong.GioVao, ChamCong.GioRa
        FROM ChamCong
        JOIN NhanVien ON ChamCong.MaNV = NhanVien.MaNV
        ORDER BY ChamCong.GioVao DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows


# ============================================================
# CanhBao (Alerts — lưu khi phát hiện vi phạm trạng thái)
# ============================================================

def insert_canh_bao(ma_nv, loai_canh_bao, mo_ta, gia_tri=None):
    """Lưu một cảnh báo mới vào bảng CanhBao."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO CanhBao (MaNV, LoaiCanhBao, MoTa, GiaTri)
           VALUES (?, ?, ?, ?)""",
        (ma_nv, loai_canh_bao, mo_ta, gia_tri)
    )
    conn.commit()
    conn.close()

def get_recent_canh_bao(limit=10):
    """Lấy danh sách cảnh báo gần nhất kèm tên nhân viên."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT TOP {limit}
               NhanVien.HoTen,
               CanhBao.LoaiCanhBao,
               CanhBao.MoTa,
               CanhBao.GiaTri,
               CanhBao.ThoiGian,
               CanhBao.DaXuLy
        FROM CanhBao
        JOIN NhanVien ON CanhBao.MaNV = NhanVien.MaNV
        ORDER BY CanhBao.ThoiGian DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows


# ============================================================
# LichSuTrangThai (State Log — log từng frame AI phân tích)
# ============================================================

def insert_trang_thai(ma_nv, trang_thai, gia_tri=None):
    """Lưu log trạng thái AI (gọi thưa hơn để không flood DB)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO LichSuTrangThai (MaNV, TrangThai, GiaTri)
           VALUES (?, ?, ?)""",
        (ma_nv, trang_thai, gia_tri)
    )
    conn.commit()
    conn.close()