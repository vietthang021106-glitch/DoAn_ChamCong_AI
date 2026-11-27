"""Build the file-only multi-sample gallery from five captured production poses."""

import argparse
from pathlib import Path
import sys

import cv2

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from test_ai1_full.ai1_adapter import initialize_model, production_pose_label
from test_ai1_full.config import ENROLLMENT_POSES
from test_ai1_full.gallery_io import DEFAULT_GALLERY_PATH, save_gallery
from test_ai1_full.utils import (ENROLLMENT_ROOT, configure_console, ensure_test_directories,
                                 list_images, safe_identity_path, validate_identity)
import face_engine
import face_matching


def build_gallery(enrollment_root=ENROLLMENT_ROOT, output_path=DEFAULT_GALLERY_PATH, engine=None):
    root = Path(enrollment_root)
    identity_dirs = sorted((path for path in root.iterdir() if path.is_dir()), key=lambda p: p.name.casefold()) if root.is_dir() else []
    if not identity_dirs:
        raise ValueError(f"Chưa có ảnh enrollment trong {root}.")
    engine = engine or initialize_model()
    gallery = {}
    for identity_dir in identity_dirs:
        identity = validate_identity(identity_dir.name)
        if identity.upper() == "UNKNOWN":
            raise ValueError("Thư mục UNKNOWN không được dùng làm enrollment.")
        if identity_dir.resolve() != safe_identity_path(root, identity):
            raise ValueError(f"{identity}: thư mục enrollment không nằm an toàn bên trong {root}.")
        files = list_images(identity_dir)
        image_map = {path.stem: path for path in files}
        if len(files) != len(ENROLLMENT_POSES) or len(image_map) != len(files):
            raise ValueError(f"{identity}: cần đúng 5 file ảnh, mỗi pose đúng một file.")
        unexpected = sorted(set(image_map) - set(ENROLLMENT_POSES))
        if unexpected:
            raise ValueError(f"{identity}: tên pose không hợp lệ: {', '.join(unexpected)}.")
        missing = [pose for pose in ENROLLMENT_POSES if pose not in image_map]
        if missing:
            raise ValueError(f"{identity}: thiếu pose {', '.join(missing)}.")
        embeddings, poses = [], []
        for expected_pose in ENROLLMENT_POSES:
            path = image_map[expected_pose]
            frame = cv2.imread(str(path), cv2.IMREAD_COLOR)
            if frame is None or frame.size == 0:
                raise ValueError(f"{identity}/{path.name}: không giải mã được ảnh.")
            faces = engine.detect_embeddings(frame)
            if not faces:
                raise ValueError(f"{identity}/{path.name}: không phát hiện khuôn mặt hợp lệ.")
            if len(faces) != 1:
                raise ValueError(f"{identity}/{path.name}: cần đúng một khuôn mặt, có {len(faces)}.")
            face = faces[0]
            quality = face_engine.assess_capture_quality(frame, face)
            if not quality.get("ready"):
                raise ValueError(f"{identity}/{path.name}: {quality.get('instruction', 'ảnh không đạt chất lượng')}.")
            pose = production_pose_label(face)
            if pose != expected_pose:
                raise ValueError(f"{identity}/{path.name}: pose phát hiện là {pose}, cần {expected_pose}.")
            vector = face_matching.normalize_embedding(face.get("embedding"), 512)
            if vector.shape != (512,) or not face.get("vector_bytes"):
                raise ValueError(f"{identity}/{path.name}: embedding 512D không hợp lệ.")
            embeddings.append(vector)
            poses.append(expected_pose)
        gallery[identity] = {"embeddings": embeddings, "poses": poses}
    return save_gallery(gallery, output_path)


def main(argv=None):
    configure_console()
    parser = argparse.ArgumentParser(description="Build a file-based AI1 gallery from data/enrollment.")
    parser.add_argument("--output", default=str(DEFAULT_GALLERY_PATH), help="Đường dẫn output .npz")
    args = parser.parse_args(argv)
    ensure_test_directories()
    try:
        gallery_path, metadata_path = build_gallery(output_path=args.output)
        print(f"Gallery đã lưu: {gallery_path}")
        print(f"Metadata đã lưu: {metadata_path}")
        return 0
    except Exception as exc:
        print(f"Không build được gallery: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
