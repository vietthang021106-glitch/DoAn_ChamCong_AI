"""
test_api.py — Script kiểm thử giả lập phần cứng ESP32
=======================================================
Gửi dữ liệu cảm biến (sức khỏe, môi trường, chấm công) định kỳ
lên server Flask, và kiểm tra các API endpoint mới.
"""

import requests
import random
import time

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
# Gửi dữ liệu giả lập (vòng lặp chính)
# ============================================================
def run_simulation(cycles=5, interval_sec=3):
    print(f"\n=== Bat dau gia lap {cycles} chu ky, moi {interval_sec}s ===\n")

    for i in range(cycles):
        ma_nv_random = random.choice([1, 2])
        nhip_tim     = random.randint(68, 98)
        spo2         = random.randint(95, 100)
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

        # --- Chấm công (chỉ lần đầu) ---
        if i == 0:
            try:
                r = requests.post(
                    f'{BASE_URL}/api/chamcong',
                    json={"MaNV": ma_nv_random},
                    timeout=5
                )
                print(f"  [chamcong] MaNV={ma_nv_random} -> {r.status_code} {r.json()}")
            except Exception as e:
                print(f"  [chamcong] LOI: {e}")

        time.sleep(interval_sec)

# ============================================================
# Kiểm tra GET endpoints
# ============================================================
def check_get_endpoints():
    print("\n=== Kiem tra GET endpoints ===\n")

    endpoints = [
        ('/api/get_health',      'Lich su suc khoe'),
        ('/api/get_environment', 'Moi truong moi nhat'),
        ('/api/get_chamcong',    'Lich su cham cong'),
        ('/api/get_alerts',      'Canh bao AI'),
        ('/api/ai_status',       'Trang thai AI hien tai'),
        ('/api/chart/health',    'Chart nhip tim'),
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
# Entrypoint
# ============================================================
if __name__ == '__main__':
    if not check_server():
        exit(1)

    check_get_endpoints()
    run_simulation(cycles=5, interval_sec=3)
    check_get_endpoints()

    print("\n=== Hoan tat kiem thu ===")