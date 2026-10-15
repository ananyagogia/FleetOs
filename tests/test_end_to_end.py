"""
End-to-End Integration Test for FleetOS Phase 2.
Validates the complete operational lifecycle:
Mission Input -> Database -> Scheduling -> UAV Assignment -> Database Update -> Dashboard Verification
"""

import unittest
import sys
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for path in [BASE_DIR, os.path.join(BASE_DIR, "backend"), os.path.join(BASE_DIR, "database"), os.path.join(BASE_DIR, "scheduling")]:
    if path not in sys.path:
        sys.path.append(path)

from db_connection import init_database, execute_query, fetch_one
import drone_manager
import mission_manager
from priority import priority_scheduling
import main


class TestEndToEndPipeline(unittest.TestCase):

    def setUp(self):
        init_database(seed_demo_data=True)
        self.app = main.app.test_client()

    def test_complete_phase_2_flow(self):
        # -------------------------------------------------------------
        # STEP 1: Mission Input via API (POST /api/missions)
        # -------------------------------------------------------------
        mission_payload = {
            "title": "Operation Rapid Rescue Alpha",
            "mission_type": "SEARCH_AND_RESCUE",
            "priority": 1,
            "latitude": 28.6140,
            "longitude": 77.2095,
            "burst_time": 4,
            "arrival_time": 0,
            "deadline": 20,
            "required_capabilities": "THERMAL,CAMERA"
        }
        res1 = self.app.post("/api/missions", json=mission_payload)
        self.assertEqual(res1.status_code, 201)
        mission_data = res1.get_json()
        m_id = mission_data["mission_id"]
        self.assertIsNotNone(m_id)

        # -------------------------------------------------------------
        # STEP 2: Database Persistence Verification
        # -------------------------------------------------------------
        saved_mission = mission_manager.get_mission_by_id(m_id)
        self.assertIsNotNone(saved_mission)
        self.assertEqual(saved_mission["status"], "PENDING")
        self.assertEqual(saved_mission["priority"], 1)

        # -------------------------------------------------------------
        # STEP 3: Scheduling Engine (POST /api/schedule)
        # -------------------------------------------------------------
        res2 = self.app.post("/api/schedule", json={"algorithm": "PRIORITY"})
        self.assertEqual(res2.status_code, 200)
        sched_data = res2.get_json()
        self.assertIn("schedule", sched_data)
        self.assertIn("metrics", sched_data)
        # Verify our newly created mission is in the scheduled queue
        scheduled_ids = [item["id"] for item in sched_data["schedule"]]
        self.assertIn(m_id, scheduled_ids)

        # -------------------------------------------------------------
        # STEP 4: UAV Assignment Engine (POST /api/missions/<id>/assign)
        # -------------------------------------------------------------
        res3 = self.app.post(f"/api/missions/{m_id}/assign")
        self.assertEqual(res3.status_code, 200)
        assignment_data = res3.get_json()
        self.assertEqual(assignment_data["mission_id"], m_id)
        assigned_uav_id = assignment_data["uav_id"]
        self.assertIsNotNone(assigned_uav_id)

        # -------------------------------------------------------------
        # STEP 5: Database State Updates Verification
        # -------------------------------------------------------------
        # 5a. Mission must now be ASSIGNED
        updated_mission = mission_manager.get_mission_by_id(m_id)
        self.assertEqual(updated_mission["status"], "ASSIGNED")

        # 5b. Assigned UAV must be ON_MISSION and not available
        updated_uav = drone_manager.get_uav_by_id(assigned_uav_id)
        self.assertEqual(updated_uav["status"], "ON_MISSION")
        self.assertEqual(updated_uav["availability"], 0)

        # 5c. Active assignment record must exist in DB
        active_assignments = drone_manager.get_active_assignments()
        assigned_ids = [a["mission_id"] for a in active_assignments]
        self.assertIn(m_id, assigned_ids)

        # -------------------------------------------------------------
        # STEP 6: Dashboard Statistics API Reflection
        # -------------------------------------------------------------
        res4 = self.app.get("/api/stats")
        self.assertEqual(res4.status_code, 200)
        stats = res4.get_json()
        self.assertGreaterEqual(stats["missions"]["assigned"], 1)
        self.assertGreaterEqual(stats["fleet"]["on_mission"], 1)

        # -------------------------------------------------------------
        # STEP 7: Simulation Flight Step & Completion
        # -------------------------------------------------------------
        # Step simulation several times until mission finishes
        for _ in range(5):
            sim_res = self.app.post("/api/simulation/step")
            self.assertEqual(sim_res.status_code, 200)

        # After sufficient ticks, mission completes and UAV returns
        completed_mission = mission_manager.get_mission_by_id(m_id)
        self.assertEqual(completed_mission["status"], "COMPLETED")


if __name__ == "__main__":
    unittest.main()
