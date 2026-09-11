import pyodbc
from werkzeug.security import generate_password_hash

def get_connection():
    conn_str = (
        "Driver={ODBC Driver 17 for SQL Server};"
        "Server=localhost;"
        "Database=DoAn_ChamCong_AI;"
        "Trusted_Connection=yes;"
    )
    return pyodbc.connect(conn_str, timeout=5)

def seed_accounts():
    """
    Tạo hoặc cập nhật tài khoản mẫu với mật khẩu được hash.
    Mật khẩu mặc định: '123456'
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()

        # Lấy danh sách nhân viên
        cursor.execute("SELECT MaNV, HoTen, MaVaiTro FROM NhanVien")
        employees = cursor.fetchall()

        for emp in employees:
            ma_nv = emp[0]
            # username mặc định: nv + MaNV, hoặc admin nếu MaVaiTro = 1
            if emp[2] == 1:
                username = f"admin{ma_nv}" if ma_nv > 1 else "admin"
            else:
                username = f"nv{ma_nv}"

            # Mật khẩu mặc định
            password = "123" if username == "admin" else "123456"
            hashed_pw = generate_password_hash(password)

            # Kiểm tra tài khoản đã tồn tại chưa
            cursor.execute("SELECT MaTK FROM TaiKhoan WHERE MaNV = ?", (ma_nv,))
            row = cursor.fetchone()

            if row:
                print(f"Updating password for {username} (MaNV: {ma_nv})")
                cursor.execute(
                    "UPDATE TaiKhoan SET MatKhau = ?, TenDangNhap = ? WHERE MaNV = ?",
                    (hashed_pw, username, ma_nv)
                )
            else:
                print(f"Creating account {username} (MaNV: {ma_nv})")
                cursor.execute(
                    "INSERT INTO TaiKhoan (MaNV, TenDangNhap, MatKhau) VALUES (?, ?, ?)",
                    (ma_nv, username, hashed_pw)
                )
        
        conn.commit()
        print("Done seeding accounts.")
        
    except Exception as e:
        print("Error while seeding accounts:", e)
    finally:
        conn.close()

if __name__ == "__main__":
    seed_accounts()
