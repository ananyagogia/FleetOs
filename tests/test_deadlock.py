"""
Unit tests for FleetOS Deadlock Detection & Recovery Engine.
Tests:
- Wait-For Graph (WFG) & Resource Allocation Graph (RAG) construction
- DFS Cycle Detection
- Deadlock Simulation
- Deadlock Recovery & Preemption
"""

import unittest
import sys
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for path in [BASE_DIR, os.path.join(BASE_DIR, "backend"), os.path.join(BASE_DIR, "database"), os.path.join(BASE_DIR, "resources")]:
    if path not in sys.path:
        sys.path.append(path)

from db_connection import init_database, execute_query, fetch_all
from deadlock_detector import ResourceAllocationGraph, DeadlockManager, deadlock_mgr


class TestDeadlockDetectionAndRecovery(unittest.TestCase):

    def setUp(self):
        init_database(seed_demo_data=True)
        # Reset allocations
        execute_query("DELETE FROM resource_allocation;")
        deadlock_mgr.load_from_database()

    def test_rag_cycle_detection(self):
        rag = ResourceAllocationGraph()
        # U1 holds R1, requests R2
        rag.allocate("U1", "R1")
        rag.request("U1", "R2")

        # U2 holds R2, requests R1 (Circular Wait!)
        rag.allocate("U2", "R2")
        rag.request("U2", "R1")

        cycles = rag.detect_cycles()
        self.assertGreater(len(cycles), 0)
        cycle_path = cycles[0]["cycle_path"]
        self.assertIn("U1", cycle_path)
        self.assertIn("U2", cycle_path)

    def test_rag_no_false_positives(self):
        rag = ResourceAllocationGraph()
        # Linear dependency: U1 -> R2 held by U2. No cycle.
        rag.allocate("U2", "R2")
        rag.request("U1", "R2")

        cycles = rag.detect_cycles()
        self.assertEqual(len(cycles), 0)

    def test_deadlock_simulation_and_recovery(self):
        # 1. Simulate deadlock condition
        sim_res = deadlock_mgr.simulate_deadlock_scenario()
        self.assertTrue(sim_res["deadlock_present"])
        self.assertGreater(len(sim_res["cycles"]), 0)

        # 2. Check detection report
        detection = deadlock_mgr.detect_deadlock()
        self.assertTrue(detection["deadlock_detected"])

        # 3. Trigger autonomous recovery
        rec_res = deadlock_mgr.resolve_deadlock()
        self.assertTrue(rec_res["resolved"])
        self.assertIsNotNone(rec_res["victim_preempted"])

        # 4. Verify graph after recovery has no cycles
        after = deadlock_mgr.detect_deadlock()
        self.assertFalse(after["deadlock_detected"])


if __name__ == "__main__":
    unittest.main()
