import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import database
conn = database.get_connection()
cursor = conn.cursor()
cursor.execute("UPDATE TaiKhoan SET MatKhau='123456' WHERE TenDangNhap='admin'")
cursor.execute("UPDATE TaiKhoan SET TenDangNhap='user01', MatKhau='123456' WHERE TenDangNhap='nv2'")
conn.commit()
print("Updated TaiKhoan for admin and user01")
