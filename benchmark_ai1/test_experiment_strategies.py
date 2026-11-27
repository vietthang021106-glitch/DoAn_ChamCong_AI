"""Small unit tests for benchmark-only matching and fusion functions."""

import unittest

import numpy as np

from benchmark_ai1.fusion import mean_l2_normalize
from benchmark_ai1.matching_strategies import MAX, TOP2_MEAN, aggregate_similarity_scores


class MatchingStrategyTests(unittest.TestCase):
    def test_max_returns_top_similarity(self):
        self.assertAlmostEqual(aggregate_similarity_scores([0.2, 0.95, 0.8], MAX), 0.95)

    def test_top2_mean_uses_two_best_and_falls_back_for_one_sample(self):
        self.assertAlmostEqual(aggregate_similarity_scores([0.2, 0.95, 0.8], TOP2_MEAN), 0.875)
        self.assertAlmostEqual(aggregate_similarity_scores([0.73], TOP2_MEAN), 0.73)

    def test_three_frame_mean_is_l2_normalized(self):
        fused = mean_l2_normalize([
            np.array([1.0, 0.0], dtype=np.float32),
            np.array([0.0, 1.0], dtype=np.float32),
            np.array([1.0, 1.0], dtype=np.float32),
        ])
        self.assertTrue(np.allclose(fused, [2**-0.5, 2**-0.5], atol=1e-6))
        self.assertAlmostEqual(float(np.linalg.norm(fused)), 1.0, places=6)


if __name__ == "__main__":
    unittest.main()
