"""
test_api.py — Script kiểm thử giả lập phần cứng ESP32
=======================================================
Gửi dữ liệu cảm biến (sức khỏe, môi trường, chấm công) định kỳ
lên server Flask, và kiểm tra các API endpoint.
"""

import requests
import random
import time
import json
from datetime import date

BASE_URL = 'http://127.0.0.1:5000'

# ============================================================
# Kiểm tra server có đang chạy không
# ============================================================
def check_server():
    try:
        r = requests.get(f'{BASE_URL}/', timeout=3)
        print(f"[OK] Server hoat dong — HTTP {r.status_code}")
        return True
    except requests.exceptions.ConnectionError:
        print("[LOI] Khong ket noi duoc server. Hay chay 'python app.py' truoc.")
        return False


# ============================================================
# Kiểm tra GET endpoints (cũ)
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
# TEST: GET /api/dashboard/attendance
# ============================================================
def test_dashboard_attendance():
    print("\n=== TEST: GET /api/dashboard/attendance ===\n")
    try:
        r = requests.get(f'{BASE_URL}/api/dashboard/attendance', timeout=5)
        print(f"  HTTP {r.status_code}")
        data = r.json()

        # Kiểm tra cấu trúc
        if 'Summary' in data and 'Records' in data:
            s = data['Summary']
            print(f"  [OK] Summary keys: {list(s.keys())}")
            print(f"       TongNhanVien={s.get('TongNhanVien')}  "
                  f"DaChamCong={s.get('DaChamCong')}  "
                  f"DangLamViec={s.get('DangLamViec')}")
            print(f"  [OK] Records: {len(data['Records'])} nhan vien")
            if data['Records']:
                rec = data['Records'][0]
                print(f"       Sample: MaNV={rec.get('MaNV')} HoTen={rec.get('HoTen')} "
                      f"TrangThaiTongHop={rec.get('TrangThaiTongHop')}")
        else:
            print(f"  [WARN] Cau truc khong mong doi: {list(data.keys())}")
    except Exception as e:
        print(f"  [LOI] {e}")


# ============================================================
# TEST: GET /api/attendance/today
# ============================================================
def test_attendance_today():
    print("\n=== TEST: GET /api/attendance/today ===\n")
    try:
        r = requests.get(f'{BASE_URL}/api/attendance/today', timeout=5)
        print(f"  HTTP {r.status_code}")
        data = r.json()

        if isinstance(data, list):
            print(f"  [OK] {len(data)} records tra ve")
            if data:
                rec = data[0]
                print(f"       Sample keys: {list(rec.keys())}")
        else:
            print(f"  [WARN] Ket qua khong phai list: {type(data)}")
    except Exception as e:
        print(f"  [LOI] {e}")


# ============================================================
# TEST: GET /api/shifts
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
                print(f"       MaCa={ca.get('MaCa')}  TenCa={ca.get('TenCa')}  "
                      f"{ca.get('GioBatDau')} - {ca.get('GioKetThuc')}")
        else:
            print(f"  [WARN] Ket qua: {data}")
    except Exception as e:
        print(f"  [LOI] {e}")
    return []


# ============================================================
# TEST: POST /api/assign_shift
# ============================================================
def test_assign_shift(ma_nv=1, ma_ca=1):
    print("\n=== TEST: POST /api/assign_shift ===\n")
    today = date.today().isoformat()

    payload = {
        "MaNV":        ma_nv,
        "MaCa":        ma_ca,
        "NgayLamViec": today
    }
    print(f"  Payload: {payload}")

    try:
        r = requests.post(
            f'{BASE_URL}/api/assign_shift',
            json=payload,
            timeout=5
        )
        resp = r.json()
        status_icon = "[OK]" if r.status_code == 200 else "[WARN]"
        print(f"  {status_icon} HTTP {r.status_code} -> {resp}")
    except Exception as e:
        print(f"  [LOI] {e}")

    # Test thiếu body
    try:
        r2 = requests.post(f'{BASE_URL}/api/assign_shift', json={}, timeout=5)
        print(f"  [OK] Body rong -> HTTP {r2.status_code} {r2.json()}")
    except Exception as e:
        print(f"  [LOI] Body rong test: {e}")


# ============================================================
# TEST: POST /api/chamcong  (checkin + checkout)
# ============================================================
def test_chamcong(ma_nv=1):
    print("\n=== TEST: POST /api/chamcong ===\n")

    # --- Check-in ---
    payload_in = {"MaNV": ma_nv, "MaTB": 1}
    print(f"  [Check-in] Payload: {payload_in}")
    try:
        r = requests.post(f'{BASE_URL}/api/chamcong', json=payload_in, timeout=5)
        resp = r.json()
        print(f"  HTTP {r.status_code} -> action={resp.get('action')} "
              f"status={resp.get('status')} msg={resp.get('message', '')}")
    except Exception as e:
        print(f"  [LOI] Check-in: {e}")

    time.sleep(1)

    # --- Check-out ---
    print(f"  [Check-out] Payload: {payload_in}")
    try:
        r = requests.post(f'{BASE_URL}/api/chamcong', json=payload_in, timeout=5)
        resp = r.json()
        print(f"  HTTP {r.status_code} -> action={resp.get('action')} "
              f"status={resp.get('status')} msg={resp.get('message', '')}")
    except Exception as e:
        print(f"  [LOI] Check-out: {e}")

    # --- Thiếu MaNV ---
    try:
        r2 = requests.post(f'{BASE_URL}/api/chamcong', json={}, timeout=5)
        print(f"  [OK] Thieu MaNV -> HTTP {r2.status_code} {r2.json()}")
    except Exception as e:
        print(f"  [LOI] Thieu MaNV test: {e}")


# ============================================================
# Gửi dữ liệu giả lập (vòng lặp chính)
# ============================================================
def run_simulation(cycles=3, interval_sec=2):
    print(f"\n=== Bat dau gia lap {cycles} chu ky, moi {interval_sec}s ===\n")

    for i in range(cycles):
        ma_nv_random = random.choice([1, 2])
        nhip_tim     = random.randint(68, 98)
        spo2         = round(random.uniform(95.0, 100.0), 1)
        nhiet_do     = round(random.uniform(24.0, 30.5), 1)
        do_am        = round(random.uniform(50.0, 80.0), 1)

        print(f"--- Chu ky {i+1}/{cycles} | MaNV={ma_nv_random} ---")

        # --- Sức khỏe ---
        try:
            r = requests.post(
                f'{BASE_URL}/api/sensor',
                json={"MaNV": ma_nv_random, "NhipTim": nhip_tim, "SpO2": spo2},
                timeout=5
            )
            print(f"  [sensor]   NhipTim={nhip_tim} SpO2={spo2} -> {r.status_code} {r.json()}")
        except Exception as e:
            print(f"  [sensor]   LOI: {e}")

        # --- Môi trường ---
        try:
            r = requests.post(
                f'{BASE_URL}/api/environment',
                json={"NhietDo": nhiet_do, "DoAm": do_am},
                timeout=5
            )
            print(f"  [env]      NhietDo={nhiet_do} DoAm={do_am} -> {r.status_code} {r.json()}")
        except Exception as e:
            print(f"  [env]      LOI: {e}")

        time.sleep(interval_sec)


# ============================================================
# Entrypoint
# ============================================================
if __name__ == '__main__':
    if not check_server():
        exit(1)

    # --- GET endpoints cũ ---
    check_get_endpoints()

    # --- GET endpoints mới ---
    test_dashboard_attendance()
    test_attendance_today()
    test_get_shifts()

    # --- POST endpoints mới ---
    test_assign_shift(ma_nv=1, ma_ca=1)
    test_chamcong(ma_nv=1)

    # --- Giả lập cảm biến ---
    run_simulation(cycles=3, interval_sec=2)

    # --- Kiểm tra lại sau khi có dữ liệu ---
    check_get_endpoints()
    test_dashboard_attendance()
    test_attendance_today()

    print("\n=== Hoan tat kiem thu ===")