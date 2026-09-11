"""
test_api.py -- Script kiem thu gia lap phan cung ESP32
=======================================================
Gui du lieu cam bien (suc khoe, moi truong, cham cong) dinh ky
len server Flask, va kiem tra cac API endpoint.
"""

import requests
import random
import time
from datetime import date

BASE_URL = 'http://127.0.0.1:5000'


def check_server():
    try:
        r = requests.get(f'{BASE_URL}/', timeout=3)
        print(f"[OK] Server hoat dong -- HTTP {r.status_code}")
        return True
    except requests.exceptions.ConnectionError:
        print("[LOI] Khong ket noi duoc server. Hay chay 'python app.py' truoc.")
        return False


# ============================================================
# GET endpoints cu
# ============================================================

def check_get_endpoints():
    print("\n=== Kiem tra GET endpoints ===\n")
    endpoints = [
        ('/api/get_health',        'Lich su suc khoe'),
        ('/api/get_environment',   'Moi truong moi nhat'),
        ('/api/get_chamcong',      'Lich su cham cong'),
        ('/api/get_alerts',        'Canh bao AI'),
        ('/api/ai_status',         'Trang thai AI hien tai'),
        ('/api/chart/health',      'Chart nhip tim'),
        ('/api/chart/environment', 'Chart nhiet do'),
    ]
    for path, label in endpoints:
        try:
            r = requests.get(f'{BASE_URL}{path}', timeout=5)
            data = r.json()
            count = len(data) if isinstance(data, list) else 'object'
            print(f"  [{r.status_code}] {label:30s} -> {count} records")
        except Exception as e:
            print(f"  [LOI] {label:30s} -> {e}")


# ============================================================
# GET /api/dashboard/attendance
# ============================================================

def test_dashboard_attendance():
    print("\n=== TEST: GET /api/dashboard/attendance ===\n")
    try:
        r = requests.get(f'{BASE_URL}/api/dashboard/attendance', timeout=5)
        print(f"  HTTP {r.status_code}")
        data = r.json()
        if 'Summary' in data and 'Records' in data:
            s = data['Summary']
            print(f"  [OK] TongNhanVien={s.get('TongNhanVien')} "
                  f"DaChamCong={s.get('DaChamCong')} "
                  f"DangLamViec={s.get('DangLamViec')}")
            print(f"  [OK] Records: {len(data['Records'])} nhan vien")
        else:
            print(f"  [WARN] cau truc khong mong doi")
    except Exception as e:
        print(f"  [LOI] {e}")


# ============================================================
# GET /api/attendance/today
# ============================================================

def test_attendance_today():
    print("\n=== TEST: GET /api/attendance/today ===\n")
    try:
        r = requests.get(f'{BASE_URL}/api/attendance/today', timeout=5)
        print(f"  HTTP {r.status_code}")
        data = r.json()
        if isinstance(data, list):
            print(f"  [OK] {len(data)} records tra ve")
        else:
            print(f"  [WARN] khong phai list")
    except Exception as e:
        print(f"  [LOI] {e}")


# ============================================================
# GET /api/shifts
# ============================================================

def test_get_shifts():
    print("\n=== TEST: GET /api/shifts ===\n")
    try:
        r = requests.get(f'{BASE_URL}/api/shifts', timeout=5)
        print(f"  HTTP {r.status_code}")
        data = r.json()
        if isinstance(data, list):
            print(f"  [OK] {len(data)} ca lam viec")
            for ca in data:
                print(f"       MaCa={ca.get('MaCa')} GioBatDau={ca.get('GioBatDau')} GioKetThuc={ca.get('GioKetThuc')}")
        else:
            print(f"  [WARN] {data}")
    except Exception as e:
        print(f"  [LOI] {e}")


# ============================================================
# POST /api/assign_shift
# ============================================================

def test_assign_shift(ma_nv=1, ma_ca=1):
    print("\n=== TEST: POST /api/assign_shift ===\n")
    today = date.today().isoformat()
    payload = {"MaNV": ma_nv, "MaCa": ma_ca, "NgayLamViec": today}
    print(f"  Payload: {payload}")
    try:
        r = requests.post(f'{BASE_URL}/api/assign_shift', json=payload, timeout=5)
        resp = r.json()
        icon = "[OK]" if r.status_code == 200 else "[WARN]"
        print(f"  {icon} HTTP {r.status_code} -> status={resp.get('status')}")
    except Exception as e:
        print(f"  [LOI] {e}")
    try:
        r2 = requests.post(f'{BASE_URL}/api/assign_shift', json={}, timeout=5)
        print(f"  [OK] body rong -> HTTP {r2.status_code}")
    except Exception as e:
        print(f"  [LOI] body rong: {e}")


# ============================================================
# POST /api/chamcong
# ============================================================

def test_chamcong(ma_nv=1):
    print("\n=== TEST: POST /api/chamcong ===\n")
    payload = {"MaNV": ma_nv, "MaTB": 1}
    try:
        r = requests.post(f'{BASE_URL}/api/chamcong', json=payload, timeout=5)
        resp = r.json()
        print(f"  [checkin]  HTTP {r.status_code} action={resp.get('action')} status={resp.get('status')}")
    except Exception as e:
        print(f"  [LOI] checkin: {e}")
    time.sleep(1)
    try:
        r = requests.post(f'{BASE_URL}/api/chamcong', json=payload, timeout=5)
        resp = r.json()
        print(f"  [checkout] HTTP {r.status_code} action={resp.get('action')} status={resp.get('status')}")
    except Exception as e:
        print(f"  [LOI] checkout: {e}")
    try:
        r2 = requests.post(f'{BASE_URL}/api/chamcong', json={}, timeout=5)
        print(f"  [OK] thieu MaNV -> HTTP {r2.status_code}")
    except Exception as e:
        print(f"  [LOI] thieu MaNV: {e}")


# ============================================================
# GET /api/roles
# ============================================================

def test_get_roles():
    print("\n=== TEST: GET /api/roles ===\n")
    try:
        r = requests.get(f'{BASE_URL}/api/roles', timeout=5)
        print(f"  HTTP {r.status_code}")
        data = r.json()
        if isinstance(data, list):
            print(f"  [OK] {len(data)} vai tro")
            for vt in data:
                print(f"       MaVaiTro={vt.get('MaVaiTro')} TenVaiTro={vt.get('TenVaiTro')}")
        else:
            print(f"  [WARN] {data}")
        return data
    except Exception as e:
        print(f"  [LOI] {e}")
        return []


# ============================================================
# GET /api/employees
# ============================================================

def test_list_employees():
    print("\n=== TEST: GET /api/employees ===\n")
    try:
        r = requests.get(f'{BASE_URL}/api/employees', timeout=5)
        print(f"  HTTP {r.status_code}")
        data = r.json()
        if isinstance(data, list):
            print(f"  [OK] {len(data)} nhan vien")
            for emp in data:
                flag = "da-dk" if emp.get('DaDangKyKhuonMat') else "chua-dk"
                print(f"       MaNV={emp.get('MaNV')} TenVaiTro={emp.get('TenVaiTro')} KhuonMat={flag}")
            # Kiem tra AnhKhuonMat khong bi lo ra ngoai
            if data and 'AnhKhuonMat' in data[0]:
                print("  [WARN] AnhKhuonMat bi lo ra client -- kiem tra lai!")
            else:
                print("  [OK] AnhKhuonMat khong bi lo ra client")
        else:
            print(f"  [WARN] {data}")
        return data
    except Exception as e:
        print(f"  [LOI] {e}")
        return []


# ============================================================
# POST /api/employees + GET by ID + PUT
# NOTE: record test van con trong DB sau khi chay (khong DELETE)
# ============================================================

def test_employee_crud():
    print("\n=== TEST: POST /api/employees ===\n")
    ma_nv_moi = None

    # POST hop le
    payload = {"HoTen": "Nhan Vien Test", "MaVaiTro": 2}
    print(f"  Payload: {payload}")
    try:
        r = requests.post(f'{BASE_URL}/api/employees', json=payload, timeout=5)
        resp = r.json()
        print(f"  HTTP {r.status_code} -> status={resp.get('status')} MaNV={resp.get('MaNV')}")
        if r.status_code == 201:
            ma_nv_moi = resp.get('MaNV')
            print(f"  [OK] Tao thanh cong MaNV={ma_nv_moi}")
        else:
            print(f"  [WARN] Khong tao duoc")
    except Exception as e:
        print(f"  [LOI] POST hop le: {e}")

    # POST thieu HoTen
    try:
        r = requests.post(f'{BASE_URL}/api/employees', json={"MaVaiTro": 2}, timeout=5)
        print(f"  [OK] thieu HoTen -> HTTP {r.status_code}")
    except Exception as e:
        print(f"  [LOI] thieu HoTen: {e}")

    # POST HoTen rong
    try:
        r = requests.post(f'{BASE_URL}/api/employees', json={"HoTen": "   ", "MaVaiTro": 2}, timeout=5)
        print(f"  [OK] HoTen rong -> HTTP {r.status_code}")
    except Exception as e:
        print(f"  [LOI] HoTen rong: {e}")

    # POST role khong ton tai
    try:
        r = requests.post(f'{BASE_URL}/api/employees',
                          json={"HoTen": "Test Role 999", "MaVaiTro": 999}, timeout=5)
        print(f"  [OK] role 999 -> HTTP {r.status_code}")
    except Exception as e:
        print(f"  [LOI] role 999: {e}")

    # POST co AnhKhuonMat trong body (phai bi bo qua)
    try:
        r = requests.post(f'{BASE_URL}/api/employees',
                          json={"HoTen": "Test AnhKM", "MaVaiTro": 2, "AnhKhuonMat": "fake_data"}, timeout=5)
        print(f"  [OK] AnhKhuonMat bi bo qua -> HTTP {r.status_code} MaNV={r.json().get('MaNV')}")
        if r.status_code == 201:
            # don dep record nay khoi danh sach can test
            pass
    except Exception as e:
        print(f"  [LOI] AnhKhuonMat test: {e}")

    if ma_nv_moi is None:
        print("\n  [WARN] Khong lay duoc MaNV -- bo qua GET/PUT test.")
        return

    # GET by ID
    print(f"\n=== TEST: GET /api/employees/{ma_nv_moi} ===\n")
    try:
        r = requests.get(f'{BASE_URL}/api/employees/{ma_nv_moi}', timeout=5)
        resp = r.json()
        print(f"  HTTP {r.status_code}")
        if r.status_code == 200:
            print(f"  [OK] MaNV={resp.get('MaNV')} TenVaiTro={resp.get('TenVaiTro')}"
                  f" DaDangKyKhuonMat={resp.get('DaDangKyKhuonMat')}")
            if 'AnhKhuonMat' in resp:
                print("  [WARN] AnhKhuonMat lo ra client!")
            else:
                print("  [OK] AnhKhuonMat khong lo ra client")
        else:
            print(f"  [WARN] {resp}")
    except Exception as e:
        print(f"  [LOI] GET by ID: {e}")

    # GET 404
    try:
        r = requests.get(f'{BASE_URL}/api/employees/999999', timeout=5)
        print(f"  [OK] ID 999999 -> HTTP {r.status_code}")
    except Exception as e:
        print(f"  [LOI] 404 test: {e}")

    # PUT
    print(f"\n=== TEST: PUT /api/employees/{ma_nv_moi} ===\n")
    put_payload = {"HoTen": "Nhan Vien Test Updated", "MaVaiTro": 2}
    print(f"  Payload: {put_payload}")
    try:
        r = requests.put(f'{BASE_URL}/api/employees/{ma_nv_moi}',
                         json=put_payload, timeout=5)
        resp = r.json()
        print(f"  HTTP {r.status_code} -> status={resp.get('status')}")
        if r.status_code == 200:
            print(f"  [OK] Cap nhat thanh cong")
    except Exception as e:
        print(f"  [LOI] PUT: {e}")

    # Verify sau PUT
    try:
        r = requests.get(f'{BASE_URL}/api/employees/{ma_nv_moi}', timeout=5)
        resp = r.json()
        if r.status_code == 200:
            print(f"  [VERIFY] HoTen sau PUT = '{resp.get('HoTen')}'")
        else:
            print(f"  [WARN] Verify that bai")
    except Exception as e:
        print(f"  [LOI] Verify: {e}")

    print(f"\n  [NOTE] Record test MaNV={ma_nv_moi} van con trong DB (khong DELETE).")


# ============================================================
# Gia lap cam bien
# ============================================================

def run_simulation(cycles=3, interval_sec=2):
    print(f"\n=== Bat dau gia lap {cycles} chu ky, moi {interval_sec}s ===\n")
    for i in range(cycles):
        ma_nv_rnd = random.choice([1, 2])
        nhip_tim  = random.randint(68, 98)
        spo2      = round(random.uniform(95.0, 100.0), 1)
        nhiet_do  = round(random.uniform(24.0, 30.5), 1)
        do_am     = round(random.uniform(50.0, 80.0), 1)
        print(f"--- Chu ky {i+1}/{cycles} | MaNV={ma_nv_rnd} ---")
        try:
            r = requests.post(f'{BASE_URL}/api/sensor',
                              json={"MaNV": ma_nv_rnd, "NhipTim": nhip_tim, "SpO2": spo2},
                              timeout=5)
            print(f"  [sensor] NhipTim={nhip_tim} SpO2={spo2} -> {r.status_code}")
        except Exception as e:
            print(f"  [sensor] LOI: {e}")
        try:
            r = requests.post(f'{BASE_URL}/api/environment',
                              json={"NhietDo": nhiet_do, "DoAm": do_am},
                              timeout=5)
            print(f"  [env]    NhietDo={nhiet_do} DoAm={do_am} -> {r.status_code}")
        except Exception as e:
            print(f"  [env]    LOI: {e}")
        time.sleep(interval_sec)


# ============================================================
# Entrypoint
# ============================================================

if __name__ == '__main__':
    if not check_server():
        exit(1)

    check_get_endpoints()
    test_dashboard_attendance()
    test_attendance_today()
    test_get_shifts()
    test_assign_shift(ma_nv=1, ma_ca=1)
    test_chamcong(ma_nv=1)

    # ----- Nhan vien (moi) -----
    test_get_roles()
    test_list_employees()
    test_employee_crud()   # POST + GET/{id} + PUT -- khong DELETE

    run_simulation(cycles=3, interval_sec=2)
    check_get_endpoints()
    test_dashboard_attendance()

    print("\n=== Hoan tat kiem thu ===")