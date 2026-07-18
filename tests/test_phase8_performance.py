"""TEST-007 deterministic latency/load and local-equivalence smoke tests."""
import time
import unittest
from concurrent.futures import ThreadPoolExecutor

from app.core.simulation import Vector2D, calculate_resultant_vector


class TestPhase8Performance(unittest.TestCase):
    def test_vector_turn_latency_slo_and_concurrent_equivalence(self):
        intent = Vector2D(10, 0)
        started = time.perf_counter()
        baseline = calculate_resultant_vector(intent, [])
        elapsed = time.perf_counter() - started
        self.assertLess(elapsed, 0.2, "single deterministic turn exceeds 200ms SLO")
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: calculate_resultant_vector(intent, []), range(64)))
        self.assertTrue(all(result == baseline for result in results), "local/A2A-equivalent deterministic telemetry diverged")
