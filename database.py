"""
database.py — Tầng truy cập dữ liệu (Data Access Layer)
=========================================================
Kết nối SQL Server, thực thi truy vấn, trả raw rows.
KHÔNG chứa business logic — chỉ CRUD thuần.

Schema bổ sung (đã tạo ngoài code):
    CaLamViec(MaCa, TenCa, GioBatDau, GioKetThuc)
    PhanCaNhanVien(MaPhanCa, MaNV, MaCa, NgayLamViec)
    ChamCong.MaCa — FK tới CaLamViec
"""

import pyodbc


# ============================================================
# Kết nối
# ============================================================

def get_connection():
    conn_str = (
        "Driver={ODBC Driver 17 for SQL Server};"
        "Server=localhost;"
        "Database=DoAn_ChamCong_AI;"
        "Trusted_Connection=yes;"
    )
    return pyodbc.connect(conn_str, timeout=5)


def _safe_limit(limit, default=10, max_value=100):
    try:
        value = int(limit)
    except (TypeError, ValueError):
        value = default
    return max(1, min(value, max_value))


# ============================================================
# NhanVien
# ============================================================

def get_all_users():
    """Trả về (MaNV, HoTen) tất cả nhân viên."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT MaNV, HoTen
            FROM NhanVien
            ORDER BY MaNV
        """)
        return cursor.fetchall()
    finally:
        conn.close()


def get_total_employees():
    """Tổng số nhân viên trong hệ thống."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM NhanVien")
        row = cursor.fetchone()
        return int(row[0]) if row else 0
    finally:
        conn.close()


# ============================================================
# CaLamViec
# ============================================================

def get_all_shifts():
    """
    Tất cả ca làm việc.
    Trả về: (MaCa, TenCa, GioBatDau, GioKetThuc)
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT MaCa, TenCa, GioBatDau, GioKetThuc
            FROM CaLamViec
            ORDER BY GioBatDau
        """)
        return cursor.fetchall()
    finally:
        conn.close()


# ============================================================
# PhanCaNhanVien
# ============================================================

def get_employee_shift(ma_nv, ngay_lam_viec):
    """
    Lấy ca làm việc của nhân viên trong ngày chỉ định.

    Trả về row hoặc None nếu chưa phân ca.
    Row: (MaCa, TenCa, GioBatDau, GioKetThuc)
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                CLV.MaCa,
                CLV.TenCa,
                CLV.GioBatDau,
                CLV.GioKetThuc

            FROM PhanCaNhanVien PCN

            JOIN CaLamViec CLV
                ON PCN.MaCa = CLV.MaCa

            WHERE
                PCN.MaNV = ?
                AND PCN.NgayLamViec = ?
        """, (ma_nv, ngay_lam_viec))
        return cursor.fetchone()
    finally:
        conn.close()


def assign_shift(ma_nv, ma_ca, ngay_lam_viec):
    """
    Phân ca cho nhân viên trong ngày.
    Mỗi nhân viên chỉ có tối đa 1 ca / ngày.
    Nếu đã có thì UPDATE, chưa có thì INSERT.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()

        # Kiểm tra đã có chưa
        cursor.execute("""
            SELECT MaPhanCa
            FROM PhanCaNhanVien
            WHERE MaNV = ? AND NgayLamViec = ?
        """, (ma_nv, ngay_lam_viec))
        row = cursor.fetchone()

        if row:
            cursor.execute("""
                UPDATE PhanCaNhanVien
                SET MaCa = ?
                WHERE MaNV = ? AND NgayLamViec = ?
            """, (ma_ca, ma_nv, ngay_lam_viec))
        else:
            cursor.execute("""
                INSERT INTO PhanCaNhanVien
                    (MaNV, MaCa, NgayLamViec)
                VALUES (?, ?, ?)
            """, (ma_nv, ma_ca, ngay_lam_viec))

        conn.commit()
    finally:
        conn.close()


# ============================================================
# ChamCong — Check-in / Check-out
# ============================================================

def get_today_record(ma_nv):
    """
    Lấy bản ghi chấm công hôm nay của nhân viên.

    Trả về row hoặc None.
    Row: (MaCC, GioVao, GioRa, MaCa)
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT MaCC, GioVao, GioRa, MaCa
            FROM ChamCong
            WHERE
                MaNV = ?
                AND CAST(GioVao AS DATE) = CAST(GETDATE() AS DATE)
        """, (ma_nv,))
        return cursor.fetchone()
    finally:
        conn.close()


def insert_checkin(ma_nv, ma_ca, ma_tb=1):
    """
    Tạo bản ghi CHECK-IN.
    GioVao = GETDATE(), GioRa = NULL.
    Trả về MaCC vừa tạo.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO ChamCong (MaNV, GioVao, GioRa, MaTB, MaCa)
            OUTPUT INSERTED.MaCC
            VALUES (?, GETDATE(), NULL, ?, ?)
        """, (ma_nv, ma_tb, ma_ca))
        row = cursor.fetchone()
        conn.commit()
        return int(row[0]) if row else None
    finally:
        conn.close()


def update_checkout(ma_cc):
    """
    Cập nhật GioRa = GETDATE() cho bản ghi MaCC.
    Trả về số row bị ảnh hưởng.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE ChamCong
            SET GioRa = GETDATE()
            WHERE MaCC = ?
        """, (ma_cc,))
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


# ============================================================
# ChamCong — Read
# ============================================================

def get_recent_cham_cong(limit=20):
    """
    Lịch sử chấm công gần nhất (dùng cho /api/get_chamcong).
    Trả về: (HoTen, GioVao, GioRa)
    """
    limit = _safe_limit(limit, default=20)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT TOP {limit}
                NV.HoTen,
                CC.GioVao,
                CC.GioRa

            FROM ChamCong CC

            JOIN NhanVien NV
                ON CC.MaNV = NV.MaNV

            ORDER BY CC.GioVao DESC
        """)
        return cursor.fetchall()
    finally:
        conn.close()


def get_today_attendance():
    """
    Toàn bộ nhân viên kèm tình trạng chấm công hôm nay.

    Dùng OUTER APPLY + SELECT TOP 1 để đảm bảo mỗi nhân viên
    CHỈ xuất hiện đúng 1 dòng, kể cả khi ChamCong có nhiều
    bản ghi trong ngày (tránh duplicate nhân vật gây sai KPI).

    Ưu tiên bản ghi có GioVao sớm nhất trong ngày.

    Trả về:
        MaNV, HoTen,
        MaCa, TenCa, GioBatDau, GioKetThuc,
        GioVao, GioRa
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                NV.MaNV,
                NV.HoTen,

                CLV.MaCa,
                CLV.TenCa,
                CLV.GioBatDau,
                CLV.GioKetThuc,

                CC_TODAY.GioVao,
                CC_TODAY.GioRa

            FROM NhanVien NV

            -- Ca làm việc hôm nay (nếu được phân ca)
            LEFT JOIN PhanCaNhanVien PCN
                ON  NV.MaNV = PCN.MaNV
                AND PCN.NgayLamViec = CAST(GETDATE() AS DATE)

            LEFT JOIN CaLamViec CLV
                ON PCN.MaCa = CLV.MaCa

            -- Lấy đúng 1 bản ghi ChamCong hôm nay (GioVao sớm nhất)
            OUTER APPLY (
                SELECT TOP 1
                    CC.GioVao,
                    CC.GioRa
                FROM ChamCong CC
                WHERE
                    CC.MaNV = NV.MaNV
                    AND CAST(CC.GioVao AS DATE) = CAST(GETDATE() AS DATE)
                ORDER BY CC.GioVao ASC
            ) AS CC_TODAY

            ORDER BY NV.MaNV
        """)
        return cursor.fetchall()
    finally:
        conn.close()


def get_today_cham_cong():
    """
    Bản ghi ChamCong hôm nay (đã chấm công).
    Trả về: (HoTen, GioVao, GioRa, MaNV)
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                NV.HoTen,
                CC.GioVao,
                CC.GioRa,
                NV.MaNV

            FROM ChamCong CC

            JOIN NhanVien NV
                ON CC.MaNV = NV.MaNV

            WHERE
                CAST(CC.GioVao AS DATE)
                    = CAST(GETDATE() AS DATE)

            ORDER BY CC.GioVao ASC
        """)
        return cursor.fetchall()
    finally:
        conn.close()


def get_weekly_cham_cong():
    """
    Thống kê chấm công 7 ngày gần nhất.
    Trả về: (NgayChamCong, SoNguoiVao, SoNguoiRa)
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                CAST(CC.GioVao AS DATE)  AS NgayChamCong,
                COUNT(CC.MaCC)             AS SoNguoiVao,
                SUM(
                    CASE
                        WHEN CC.GioRa IS NOT NULL THEN 1
                        ELSE 0
                    END
                )                        AS SoNguoiRa

            FROM ChamCong CC

            WHERE
                CC.GioVao >= CAST(
                    DATEADD(DAY, -6, GETDATE())
                AS DATE)

            GROUP BY
                CAST(CC.GioVao AS DATE)

            ORDER BY
                NgayChamCong ASC
        """)
        return cursor.fetchall()
    finally:
        conn.close()


# ============================================================
# LichSuSucKhoe
# ============================================================

def insert_health_data(ma_nv, nhip_tim, spo2):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO LichSuSucKhoe (MaNV, NhipTim, SpO2, ThoiGian)
            VALUES (?, ?, ?, GETDATE())
        """, (ma_nv, nhip_tim, spo2))
        conn.commit()
    finally:
        conn.close()


def get_recent_health_data(limit=10):
    """
    Trả về: (HoTen, NhipTim, SpO2, ThoiGian)
    """
    limit = _safe_limit(limit, default=10)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT TOP {limit}
                NV.HoTen,
                SK.NhipTim,
                SK.SpO2,
                SK.ThoiGian

            FROM LichSuSucKhoe SK

            JOIN NhanVien NV
                ON SK.MaNV = NV.MaNV

            ORDER BY SK.ThoiGian DESC
        """)
        return cursor.fetchall()
    finally:
        conn.close()


def get_health_chart_data(limit=20):
    """
    Trả về: (HoTen, NhipTim, ThoiGian) — thứ tự ASC để vẽ chart
    """
    limit = _safe_limit(limit, default=20)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT TOP {limit}
                NV.HoTen,
                SK.NhipTim,
                SK.ThoiGian

            FROM LichSuSucKhoe SK

            JOIN NhanVien NV
                ON SK.MaNV = NV.MaNV

            ORDER BY SK.ThoiGian DESC
        """)
        rows = cursor.fetchall()
        return list(reversed(rows))
    finally:
        conn.close()


# ============================================================
# ThongSoMoiTruong
# ============================================================

def insert_environment_data(nhiet_do, do_am, ma_tb=1):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO ThongSoMoiTruong (NhietDo, DoAm, ThoiGian, MaTB)
            VALUES (?, ?, GETDATE(), ?)
        """, (nhiet_do, do_am, ma_tb))
        conn.commit()
    finally:
        conn.close()


def get_recent_environment_data():
    """Trả về (NhietDo, DoAm, ThoiGian) bản ghi mới nhất."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT TOP 1 NhietDo, DoAm, ThoiGian
            FROM ThongSoMoiTruong
            ORDER BY ThoiGian DESC
        """)
        return cursor.fetchone()
    finally:
        conn.close()


def get_environment_chart_data(limit=20):
    """Trả về: (NhietDo, DoAm, ThoiGian) — thứ tự ASC để vẽ chart."""
    limit = _safe_limit(limit, default=20)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT TOP {limit}
                NhietDo, DoAm, ThoiGian
            FROM ThongSoMoiTruong
            ORDER BY ThoiGian DESC
        """)
        rows = cursor.fetchall()
        return list(reversed(rows))
    finally:
        conn.close()


# ============================================================
# LichSuTrangThai (AI)
#
# Schema thật:
#   MaTT, MaNV, MaBieuHien, ThoiGian
# ============================================================

_STATE_TO_BIEU_HIEN = {
    "binh_thuong": 1,
    "buon_ngu":    2,
    "guc_dau":     3,
    "meo_mieng":   4,
}

_STATE_ALIASES = {
    "bình thường":  "binh_thuong",
    "binh thuong":  "binh_thuong",
    "buồn ngủ":     "buon_ngu",
    "buon ngu":     "buon_ngu",
    "gục đầu":      "guc_dau",
    "guc dau":      "guc_dau",
    "méo miệng":    "meo_mieng",
    "meo mieng":    "meo_mieng",
}


def get_ma_bieu_hien(trang_thai):
    if trang_thai is None:
        return 1
    key = str(trang_thai).strip().lower()
    key = _STATE_ALIASES.get(key, key)
    return _STATE_TO_BIEU_HIEN.get(key, 1)


def insert_trang_thai(ma_nv, trang_thai, gia_tri=None):
    """
    Lưu trạng thái AI.
    gia_tri nhận để tương thích với ai_engine nhưng
    DB không có cột GiaTri — bỏ qua.
    Trả về MaTT vừa INSERT.
    """
    ma_bieu_hien = get_ma_bieu_hien(trang_thai)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO LichSuTrangThai (MaNV, MaBieuHien, ThoiGian)
            OUTPUT INSERTED.MaTT
            VALUES (?, ?, GETDATE())
        """, (ma_nv, ma_bieu_hien))
        row = cursor.fetchone()
        conn.commit()
        return int(row[0]) if row else None
    finally:
        conn.close()


# ============================================================
# CanhBao (AI)
#
# Schema thật:
#   MaCB, MaNV, MaLoaiCB, NoiDung, ThoiGian, MaTT, MaTB
# ============================================================

def insert_canh_bao(
    ma_nv,
    loai_canh_bao,
    mo_ta,
    gia_tri=None,
    ma_tt=None,
    ma_tb=1,
    ma_loai_cb=1
):
    """
    Lưu cảnh báo AI.
    EAR / Tilt được gộp vào NoiDung vì DB không có cột GiaTri riêng.
    """
    noi_dung = str(loai_canh_bao)
    if mo_ta:
        noi_dung += f": {mo_ta}"
    if gia_tri is not None:
        noi_dung += f" | GiaTri={gia_tri}"

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO CanhBao
                (MaNV, MaLoaiCB, NoiDung, ThoiGian, MaTT, MaTB)
            VALUES (?, ?, ?, GETDATE(), ?, ?)
        """, (ma_nv, ma_loai_cb, noi_dung, ma_tt, ma_tb))
        conn.commit()
    finally:
        conn.close()


def get_recent_canh_bao(limit=10):
    """
    Trả về: (HoTen, LoaiCanhBao, NoiDung, ThoiGian)
    """
    limit = _safe_limit(limit, default=10)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT TOP {limit}

                NV.HoTen,

                COALESCE(
                    BH.TenBieuHien,
                    LCB.TenLoaiCB
                ) AS LoaiCanhBao,

                CB.NoiDung,

                CB.ThoiGian

            FROM CanhBao CB

            JOIN NhanVien NV
                ON CB.MaNV = NV.MaNV

            LEFT JOIN LoaiCanhBao LCB
                ON CB.MaLoaiCB = LCB.MaLoaiCB

            LEFT JOIN LichSuTrangThai TT
                ON CB.MaTT = TT.MaTT

            LEFT JOIN DanhMucBieuHien BH
                ON TT.MaBieuHien = BH.MaBieuHien

            ORDER BY CB.ThoiGian DESC
        """)
        return cursor.fetchall()
    finally:
        conn.close()


def get_today_alert_count():
    """Số cảnh báo AI hôm nay."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*)
            FROM CanhBao
            WHERE CAST(ThoiGian AS DATE) = CAST(GETDATE() AS DATE)
        """)
        row = cursor.fetchone()
        return int(row[0]) if row else 0
    finally:
        conn.close()