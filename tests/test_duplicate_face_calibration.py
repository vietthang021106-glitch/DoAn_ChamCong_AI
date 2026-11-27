import tempfile
import unittest
from pathlib import Path

import numpy as np

from tools.calibrate_face_duplicate_threshold import (
    calibrate,
    choose_threshold,
    max_5x5_cosine,
    rates_at_threshold,
)


def five_basis_vectors(offset=0):
    vectors = np.zeros((5, 512), dtype=np.float32)
    for index in range(5):
        vectors[index, (index + offset) % 512] = 1.0
    return vectors


class DuplicateFaceCalibrationTests(unittest.TestCase):
    def test_max_5x5_scores_the_best_pair_not_centroid(self):
        left = five_basis_vectors()
        right = five_basis_vectors(4)
        self.assertEqual(max_5x5_cosine(left, right), 1.0)

    def test_threshold_reports_pairwise_fmr_and_fnmr(self):
        result = rates_at_threshold([0.92, 0.88], [0.91, 0.30], 0.90)
        self.assertEqual(result['false_match_count'], 1)
        self.assertEqual(result['false_non_match_count'], 1)
        self.assertEqual(result['fmr'], 0.5)
        self.assertEqual(result['fnmr'], 0.5)

    def test_threshold_requires_explicit_targets_and_never_marks_impossible_targets_valid(self):
        result = choose_threshold([0.8, 0.9], [0.95, 0.7], max_fmr=0.0, max_fnmr=0.0)
        self.assertFalse(result['meets_error_targets'])
        with self.assertRaises(ValueError):
            choose_threshold([0.8], [0.2], max_fmr=-0.1, max_fnmr=0.1)

    def test_insufficient_labeled_dataset_returns_unvalidated_report_without_loading_model(self):
        with tempfile.TemporaryDirectory() as temporary:
            dataset = Path(temporary) / 'dataset'
            session = dataset / 'person-a' / 'session-1'
            session.mkdir(parents=True)
            for pose in ('frontal', 'left', 'right', 'up', 'down'):
                (session / f'{pose}.jpg').write_bytes(b'fixture-only')
            report = calibrate(dataset, 0.01, 0.10, min_identities=2)
        self.assertFalse(report['validated'])
        self.assertEqual(report['validation_reason'], 'INSUFFICIENT_LABELED_CALIBRATION_SESSIONS')
        self.assertEqual(report['sample_counts']['identity_count'], 1)
        self.assertEqual(report['sample_counts']['image_count'], 0)


if __name__ == '__main__':
    unittest.main()
