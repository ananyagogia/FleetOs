"""
Unit tests for FleetOS Scheduling Algorithms.
Tests FCFS, SJF, Priority, Round Robin, and Adaptive.
"""

import unittest
import sys
import os

# Add scheduling directory to path
SCHED_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scheduling")
if SCHED_DIR not in sys.path:
    sys.path.append(SCHED_DIR)

from fcfs import fcfs
from sjf import sjf
from priority import priority_scheduling
from round_robin import round_robin
from adaptive import adaptive_scheduling
from metrics import calculate_metrics, get_detailed_metrics
from comparison import compare_scheduling_algorithms


class TestSchedulingAlgorithms(unittest.TestCase):

    def setUp(self):
        self.sample_missions = [
            {"id": "M1", "arrival_time": 0, "burst_time": 5, "priority": 2, "deadline": 25},
            {"id": "M2", "arrival_time": 1, "burst_time": 3, "priority": 1, "deadline": 15},
            {"id": "M3", "arrival_time": 2, "burst_time": 8, "priority": 4, "deadline": 40},
            {"id": "M4", "arrival_time": 3, "burst_time": 2, "priority": 3, "deadline": 20}
        ]

    def test_fcfs(self):
        results = fcfs(self.sample_missions)
        self.assertEqual(len(results), 4)
        # Order should be M1 -> M2 -> M3 -> M4
        order = [r["id"] for r in results]
        self.assertEqual(order, ["M1", "M2", "M3", "M4"])
        awt, atat = calculate_metrics(results)
        self.assertGreaterEqual(awt, 0)
        self.assertGreater(atat, awt)

    def test_sjf(self):
        results = sjf(self.sample_missions)
        self.assertEqual(len(results), 4)
        # At time 0, M1 runs (0-5). By t=5, M2, M3, M4 are arrived.
        # Shortest among remaining: M4 (burst 2) -> M2 (burst 3) -> M3 (burst 8)
        order = [r["id"] for r in results]
        self.assertEqual(order, ["M1", "M4", "M2", "M3"])

    def test_priority(self):
        results = priority_scheduling(self.sample_missions)
        self.assertEqual(len(results), 4)
        # At time 0, M1 runs (0-5). By t=5, highest priority is M2 (p1) -> M4 (p3) -> M3 (p4)
        order = [r["id"] for r in results]
        self.assertEqual(order, ["M1", "M2", "M4", "M3"])

    def test_round_robin(self):
        results, slices = round_robin(self.sample_missions, quantum=2)
        self.assertEqual(len(results), 4)
        self.assertGreater(len(slices), 4)  # Must have preemptions
        awt, atat = calculate_metrics(results)
        self.assertGreaterEqual(awt, 0)

    def test_adaptive(self):
        results = adaptive_scheduling(self.sample_missions, mode="EMERGENCY")
        self.assertEqual(len(results), 4)
        self.assertTrue(all("adaptive_score" in r for r in results))

    def test_comparison(self):
        comparison = compare_scheduling_algorithms(self.sample_missions, quantum=2)
        self.assertIn("FCFS", comparison["algorithms"])
        self.assertIn("SJF", comparison["algorithms"])
        self.assertIn("Priority", comparison["algorithms"])
        self.assertIn("Round Robin", comparison["algorithms"])
        self.assertIn("Adaptive", comparison["algorithms"])
        self.assertIsNotNone(comparison["best_algorithm_wt"])


if __name__ == "__main__":
    unittest.main()
