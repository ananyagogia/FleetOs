"""
Unit tests for Drone Manager and UAV Assignment Engine.
"""

import unittest
import sys
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for path in [BASE_DIR, os.path.join(BASE_DIR, "backend"), os.path.join(BASE_DIR, "database")]:
    if path not in sys.path:
        sys.path.append(path)

from db_connection import init_database, execute_query
import drone_manager
import mission_manager


class TestDroneManager(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        init_database(seed_demo_data=True)

    def test_distance_calculation(self):
        # Distance between Connaught Place and India Gate (~2.3 km)
        dist = drone_manager.calculate_distance(28.6304, 77.2177, 28.6129, 77.2295)
        self.assertGreater(dist, 1.5)
        self.assertLess(dist, 3.5)

    def test_filter_eligible_uavs(self):
        # Create a mission requiring THERMAL capability
        mission = {
            "title": "Night Vision Recon",
            "mission_type": "SURVEILLANCE",
            "priority": 1,
            "latitude": 28.6139,
            "longitude": 77.2090,
            "required_capabilities": "THERMAL",
            "burst_time": 4
        }
        eligible = drone_manager.filter_eligible_uavs(mission)
        self.assertTrue(len(eligible) > 0)
        for u in eligible:
            self.assertEqual(u["status"], "IDLE")
            self.assertEqual(u["availability"], 1)
            self.assertIn("THERMAL", u["capabilities"])

    def test_find_best_uav(self):
        mission = {
            "title": "Medical Drop",
            "mission_type": "MEDICAL_DELIVERY",
            "priority": 1,
            "latitude": 28.6100,
            "longitude": 77.2000,
            "required_capabilities": "CARGO",
            "burst_time": 3
        }
        best = drone_manager.find_best_uav_for_mission(mission)
        self.assertIsNotNone(best)
        self.assertIn("CARGO", best["capabilities"])


if __name__ == "__main__":
    unittest.main()
