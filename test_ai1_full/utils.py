"""Shared path and image helpers for the isolated AI1 test package."""

from pathlib import Path
import re
import sys


TEST_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = TEST_ROOT.parent
DATA_ROOT = TEST_ROOT / "data"
ENROLLMENT_ROOT = DATA_ROOT / "enrollment"
CAPTURES_ROOT = DATA_ROOT / "captures"
GALLERY_ROOT = TEST_ROOT / "gallery"
RESULTS_ROOT = TEST_ROOT / "results"
IDENTITY_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def validate_identity(identity):
    """Return a safe identity component or raise ValueError."""
    if not isinstance(identity, str) or not identity or not IDENTITY_PATTERN.fullmatch(identity):
        raise ValueError("ID chỉ được chứa chữ cái ASCII, số, dấu gạch dưới và dấu gạch ngang.")
    if identity in {".", ".."}:
        raise ValueError("ID không hợp lệ.")
    return identity


def safe_identity_path(root, identity):
    """Build an identity directory while explicitly enforcing containment."""
    identity = validate_identity(identity)
    root = Path(root).resolve()
    target = (root / identity).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError("ID tạo đường dẫn nằm ngoài thư mục dữ liệu.") from exc
    return target


def list_images(folder):
    folder = Path(folder)
    if not folder.is_dir():
        return []
    return sorted(
        (path for path in folder.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES),
        key=lambda path: path.name.casefold(),
    )


def ensure_test_directories():
    for path in (ENROLLMENT_ROOT, CAPTURES_ROOT, GALLERY_ROOT, RESULTS_ROOT):
        path.mkdir(parents=True, exist_ok=True)


def configure_console():
    """Avoid Windows legacy code pages crashing on Vietnamese CLI text."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(errors="replace")
            except (OSError, ValueError):
                pass
