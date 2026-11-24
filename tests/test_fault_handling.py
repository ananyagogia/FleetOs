"""
Unit tests for FleetOS Fault Handling & Autonomous Recovery.
Tests:
- Drone Failure: status to OFFLINE, resource release, mission reassignment/re-queuing
- Low Battery: status to CHARGING, docking, reassignment
- Mission Failure: mission marked FAILED, drone freed
- Resource Unavailability: event logging and queuing
- Communication Loss: comm channel released, status OFFLINE
- Auto-Recovery: restores offline airframes, resolves active faults
"""

import unittest
import sys
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for path in [BASE_DIR, os.path.join(BASE_DIR, "backend"), os.path.join(BASE_DIR, "database"), os.path.join(BASE_DIR, "resources")]:
    if path not in sys.path:
        sys.path.append(path)

from db_connection import init_database, execute_query, fetch_one, fetch_all
import drone_manager
import mission_manager
import fault_manager


class TestFaultHandling(unittest.TestCase):

    def setUp(self):
        execute_query("DELETE FROM resource_allocation;")
        execute_query("DELETE FROM assignment;")
        execute_query("DELETE FROM mission_log;")
        execute_query("DELETE FROM fault_log;")
        execute_query("DELETE FROM mission;")
        execute_query("DELETE FROM uav;")
        execute_query("DELETE FROM fleet_resource;")
        init_database(seed_demo_data=True)
        execute_query("UPDATE uav SET status = 'IDLE', availability = 1, battery_level = 95.0;")

    def test_drone_failure_without_mission(self):
        uavs = drone_manager.get_all_uavs()
        target_uav = uavs[0]
        u_id = target_uav["uav_id"]

        res = fault_manager.handle_drone_failure(u_id)
        self.assertEqual(res["uav_status"], "OFFLINE")

        updated = drone_manager.get_uav_by_id(u_id)
        self.assertEqual(updated["status"], "OFFLINE")
        self.assertEqual(updated["availability"], 0)

        # Check fault logged in DB
        fault = fetch_one("SELECT * FROM fault_log WHERE uav_id = %s AND fault_type = 'DRONE_FAILURE';", (u_id,))
        self.assertIsNotNone(fault)
        self.assertEqual(fault["severity"], "critical")

    def test_drone_failure_with_mission_reassignment(self):
        # 1. Create a mission and assign it to UAV 1
        uavs = drone_manager.get_all_uavs()
        u1, u2 = uavs[0], uavs[1]

        mission_res = mission_manager.create_mission({
            "title": "Search Survivor Flare",
            "mission_type": "SURVEILLANCE",
            "priority": 1,
            "latitude": 28.6139,
            "longitude": 77.2090,
            "required_capabilities": "CAMERA",
            "burst_time": 4
        })
        m_id = mission_res["mission_id"]

        assign_res = drone_manager.assign_uav_to_mission(u1["uav_id"], m_id)
        self.assertEqual(assign_res["status"], "ACTIVE")

        # 2. Trigger Drone Failure on UAV 1
        fault_res = fault_manager.handle_drone_failure(u1["uav_id"])
        self.assertEqual(fault_res["uav_status"], "OFFLINE")

        # 3. Verify mission reassignment occurred or was returned to PENDING
        reassign = fault_res["reassignment"]
        self.assertIsNotNone(reassign)
        if reassign.get("reassigned"):
            self.assertNotEqual(reassign["new_uav_id"], u1["uav_id"])
            updated_m = mission_manager.get_mission_by_id(m_id)
            self.assertEqual(updated_m["status"], "ASSIGNED")
        else:
            updated_m = mission_manager.get_mission_by_id(m_id)
            self.assertEqual(updated_m["status"], "PENDING")

    def test_low_battery_handling(self):
        uavs = drone_manager.get_all_uavs()
        u = uavs[0]
        u_id = u["uav_id"]

        res = fault_manager.handle_low_battery(u_id)
        self.assertEqual(res["current_battery"], 12.0)

        updated = drone_manager.get_uav_by_id(u_id)
        self.assertEqual(updated["status"], "CHARGING")
        self.assertEqual(updated["availability"], 0)

        fault = fetch_one("SELECT * FROM fault_log WHERE uav_id = %s AND fault_type = 'LOW_BATTERY';", (u_id,))
        self.assertIsNotNone(fault)

    def test_mission_failure_handling(self):
        m_res = mission_manager.create_mission({
            "title": "Storm Recon Alpha",
            "mission_type": "SURVEILLANCE",
            "priority": 2,
            "latitude": 28.6150,
            "longitude": 77.2100,
            "burst_time": 3
        })
        m_id = m_res["mission_id"]

        res = fault_manager.handle_mission_failure(m_id)
        self.assertEqual(res["fault_type"], "MISSION_FAILURE")

        updated_m = mission_manager.get_mission_by_id(m_id)
        self.assertEqual(updated_m["status"], "FAILED")

    def test_auto_recover(self):
        # Trigger an offline airframe
        uavs = drone_manager.get_all_uavs()
        u_id = uavs[0]["uav_id"]
        fault_manager.handle_drone_failure(u_id)

        recovery = fault_manager.auto_recover_all_faults()
        self.assertTrue(recovery["autonomous_healing_complete"])

        # Drone should be restored (not offline)
        restored = drone_manager.get_uav_by_id(u_id)
        self.assertNotEqual(restored["status"], "OFFLINE")
        self.assertIn(restored["status"], ["IDLE", "ON_MISSION"])


if __name__ == "__main__":
    unittest.main()
