"""Unit tests that do not open a webcam or claim recognition accuracy."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

import face_matching
from test_ai1_full.gallery_io import load_gallery, save_gallery
from test_ai1_full.recognition import check_frame_consistency, fuse_three_embeddings
from test_ai1_full.config import ENROLLMENT_POSES
from test_ai1_full.utils import TEST_ROOT, safe_identity_path, validate_identity
from test_ai1_full.ai1_adapter import production_pose_label
from test_ai1_full import build_gallery as gallery_builder


def basis(index):
    vector = np.zeros(512, dtype=np.float32)
    vector[index] = 1.0
    return vector


class AI1LogicTests(unittest.TestCase):
    def test_l2_normalize_produces_unit_norm(self):
        normalized = face_matching.normalize_embedding(np.full(512, 3.0, dtype=np.float32))
        self.assertAlmostEqual(float(np.linalg.norm(normalized)), 1.0, places=6)

    def test_cosine_similarity(self):
        self.assertAlmostEqual(face_matching.cosine_similarity(basis(0), basis(0)), 1.0, places=6)
        self.assertAlmostEqual(face_matching.cosine_similarity(basis(0), basis(1)), 0.0, places=6)

    def test_gallery_save_load_keeps_samples_and_poses(self):
        gallery = {"MaNV_1": {"embeddings": [basis(0), basis(1)], "poses": ["frontal", "left"]}}
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as temp:
            path = Path(temp) / "gallery.npz"
            save_gallery(gallery, path)
            loaded = load_gallery(path)
        self.assertEqual(len(loaded["MaNV_1"]["embeddings"]), 2)
        self.assertEqual(loaded["MaNV_1"]["poses"], ["frontal", "left"])

    def test_multi_sample_max_matching(self):
        score = face_matching.max_sample_similarity(basis(7), [basis(0), basis(7), basis(8)])
        self.assertAlmostEqual(score, 1.0, places=6)

    def test_three_embedding_mean_is_normalized_mean(self):
        result = fuse_three_embeddings([basis(0), basis(1), basis(2)])
        expected = np.zeros(512, dtype=np.float32)
        expected[:3] = 1.0 / np.sqrt(3.0)
        np.testing.assert_allclose(result, expected, atol=1e-6)

    def test_multi_frame_output_has_unit_l2_norm(self):
        result = fuse_three_embeddings([basis(0), basis(1), basis(2)])
        self.assertAlmostEqual(float(np.linalg.norm(result)), 1.0, places=6)

    def test_wrong_embedding_dimension_rejected(self):
        with self.assertRaises(ValueError):
            face_matching.normalize_embedding(np.zeros(511, dtype=np.float32))

    def test_nan_embedding_rejected(self):
        invalid = basis(0)
        invalid[5] = np.nan
        with self.assertRaises(ValueError):
            face_matching.normalize_embedding(invalid)

    def test_path_traversal_ids_rejected(self):
        for identity in ("../escape", "..\\escape", "C:\\outside", "/tmp/outside"):
            with self.subTest(identity=identity), self.assertRaises(ValueError):
                safe_identity_path(Path("data"), identity)
        self.assertEqual(validate_identity("MaNV_1-2"), "MaNV_1-2")

    def test_one_or_two_frames_are_not_valid_multi_frame(self):
        for sequence in ([basis(0)], [basis(0), basis(0)]):
            with self.subTest(count=len(sequence)):
                self.assertFalse(check_frame_consistency(sequence)["valid"])
                with self.assertRaises(ValueError):
                    fuse_three_embeddings(sequence)

    def test_consistency_accepts_matching_embeddings(self):
        result = check_frame_consistency([basis(0), basis(0), basis(0)], threshold=0.35)
        self.assertTrue(result["valid"])
        self.assertAlmostEqual(result["min_similarity"], 1.0, places=6)

    def test_consistency_rejects_different_embeddings(self):
        result = check_frame_consistency([basis(0), basis(0), basis(1)], threshold=0.35)
        self.assertFalse(result["valid"])
        self.assertEqual(len(result["pairwise"]), 3)

    def test_production_pose_labels_are_reused(self):
        self.assertEqual(production_pose_label({"head_pose": {"yaw": 0, "pitch": 0}}), "frontal")
        self.assertEqual(production_pose_label({"head_pose": {"yaw": 20, "pitch": 0}}), "left")

    def test_gallery_builder_in_memory_fixture_writes_five_distinct_samples(self):
        class FakeEngine:
            def __init__(self):
                self.index = 0

            def detect_embeddings(self, frame):
                vector = basis(self.index)
                self.index += 1
                return [{"embedding": vector, "vector_bytes": vector.astype("<f4").tobytes()}]

        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as temp:
            root = Path(temp) / "enrollment"
            employee = root / "MaNV_1"
            employee.mkdir(parents=True)
            for pose in ENROLLMENT_POSES:
                (employee / f"{pose}.jpg").write_bytes(b"in-memory test fixture")
            output = Path(temp) / "gallery.npz"
            with patch.object(gallery_builder.cv2, "imread",
                              return_value=np.zeros((480, 640, 3), dtype=np.uint8)), \
                 patch.object(gallery_builder.face_engine, "assess_capture_quality",
                              return_value={"ready": True}), \
                 patch.object(gallery_builder, "production_pose_label", side_effect=ENROLLMENT_POSES):
                gallery_builder.build_gallery(root, output, engine=FakeEngine())
            built = load_gallery(output)
        self.assertEqual(len(built["MaNV_1"]["embeddings"]), 5)
        self.assertEqual(built["MaNV_1"]["poses"], list(ENROLLMENT_POSES))


if __name__ == "__main__":
    unittest.main()
