"""Small menu for the standalone AI1 camera test workflows."""

import csv
import subprocess
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from test_ai1_full.gallery_io import DEFAULT_GALLERY_PATH, gallery_info
from test_ai1_full.result_logger import RESULTS_CSV
from test_ai1_full.utils import (PROJECT_ROOT, TEST_ROOT, configure_console, ensure_test_directories,
                                 validate_identity)


def _run(script, *args):
    return subprocess.call([sys.executable, str(TEST_ROOT / script), *map(str, args)], cwd=PROJECT_ROOT)


def _ask_expected():
    value = input("Expected ID (UNKNOWN hoặc Enter để bỏ qua): ").strip()
    if not value:
        return None
    if value.upper() == "UNKNOWN":
        return "UNKNOWN"
    return validate_identity(value)


def _show_gallery():
    try:
        info = gallery_info(DEFAULT_GALLERY_PATH)
    except Exception as exc:
        print(f"Chưa có gallery hợp lệ: {exc}")
        return
    print(f"Model: {info.get('model', 'unknown')}")
    print(f"Embedding dimension: {info.get('embedding_dimension', 'unknown')}")
    print(f"Samples: {info.get('number_of_samples', 'unknown')}")
    print(f"Identities: {', '.join(info.get('identities', info.get('identity', [])))}")
    print(f"File: {DEFAULT_GALLERY_PATH}")


def _show_latest_results():
    if not RESULTS_CSV.is_file():
        print("Chưa có kết quả recognition nào.")
        return
    with RESULTS_CSV.open("r", newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    for row in rows[-10:]:
        print(" | ".join(f"{key}={row.get(key, '')}" for key in
                         ("timestamp", "mode", "expected_id", "predicted_id", "score", "correct", "status")))


def main():
    configure_console()
    ensure_test_directories()
    actions = {
        "1": "1. Capture enrollment",
        "2": "2. Build gallery",
        "3": "3. Single-frame recognition",
        "4": "4. Multi-frame recognition",
        "5": "5. Compare Single vs Multi",
        "6": "6. Show gallery info",
        "7": "7. Show latest results",
    }
    while True:
        print("\n================================")
        print("AI1 FULL TEST")
        print("================================")
        for item in actions.values():
            print(item)
        print("0. Exit")
        choice = input("Chọn: ").strip()
        try:
            if choice == "0":
                return 0
            if choice == "1":
                identity = validate_identity(input("ID nhân viên: ").strip())
                overwrite = input("Cho phép ghi đè ảnh đã tồn tại? (y/N): ").strip().lower() == "y"
                _run("capture_enrollment.py", "--id", identity, *( ["--overwrite"] if overwrite else [] ))
            elif choice == "2":
                _run("build_gallery.py")
            elif choice in {"3", "4", "5"}:
                expected = _ask_expected()
                script = {"3": "test_single_frame.py", "4": "test_multi_frame.py",
                          "5": "compare_single_multi.py"}[choice]
                args = ["--expected", expected] if expected is not None else []
                _run(script, *args)
            elif choice == "6":
                _show_gallery()
            elif choice == "7":
                _show_latest_results()
            else:
                print("Lựa chọn không hợp lệ.")
        except (ValueError, OSError) as exc:
            print(f"Không thể thực hiện lựa chọn: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
