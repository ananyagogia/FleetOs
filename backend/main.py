"""
FleetOS Backend API.
Autonomous Multi-UAV Fleet Operating System.
Provides RESTful endpoints connecting database persistence, scheduling engines,
UAV assignment, simulation ticks, and the operational dashboard.
"""

import os
import sys
import logging
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

# Add root directory, database, and scheduling folders to sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_DIR = os.path.join(BASE_DIR, "database")
SCHED_DIR = os.path.join(BASE_DIR, "scheduling")

for path in [BASE_DIR, DB_DIR, SCHED_DIR]:
    if path not in sys.path:
        sys.path.append(path)

from db_connection import init_database, fetch_all, fetch_one
import drone_manager
import mission_manager
import resource_manager
import simulator

from fcfs import fcfs
from sjf import sjf
from priority import priority_scheduling
from round_robin import round_robin
from adaptive import adaptive_scheduling
from comparison import compare_scheduling_algorithms
from metrics import get_detailed_metrics

logger = logging.getLogger("fleetos.api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

# Initialize Flask app with frontend static folder
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")
CORS(app)

# Ensure database is initialized on startup
init_database(seed_demo_data=True)


# ----------------------------------------------------------------------------
# 1. ROOT & STATIC DASHBOARD ROUTES
# ----------------------------------------------------------------------------

@app.route("/")
def serve_dashboard():
    """Serves the FleetOS command center dashboard."""
    if os.path.exists(os.path.join(FRONTEND_DIR, "index.html")):
        return send_from_directory(FRONTEND_DIR, "index.html")
    return jsonify({
        "system": "FleetOS",
        "title": "Autonomous Multi-UAV Fleet Operating System",
        "phase": "Phase 2 Core Working Prototype",
        "status": "Operational"
    })


@app.route("/api/health", methods=["GET"])
def health_check():
    """API health and version check."""
    return jsonify({
        "status": "Online",
        "system": "FleetOS",
        "version": "2.0.0-phase2",
        "architecture": "Mission Input -> DB -> Scheduling -> UAV Assignment -> DB Update -> Dashboard"
    })


# ----------------------------------------------------------------------------
# 2. OVERVIEW & ANALYTICS STATS
# ----------------------------------------------------------------------------

@app.route("/api/stats", methods=["GET"])
def get_dashboard_stats():
    """Returns aggregated fleet and mission statistics."""
    try:
        uavs = drone_manager.get_all_uavs()
        missions = mission_manager.get_all_missions()
        active_assignments = drone_manager.get_active_assignments()

        total_uavs = len(uavs)
        idle_uavs = sum(1 for u in uavs if u.get("status") == "IDLE")
        on_mission_uavs = sum(1 for u in uavs if u.get("status") == "ON_MISSION")
        charging_uavs = sum(1 for u in uavs if u.get("status") == "CHARGING")
        avg_battery = round(sum(float(u.get("battery_level", 0)) for u in uavs) / total_uavs, 1) if total_uavs else 0.0

        total_missions = len(missions)
        pending_missions = sum(1 for m in missions if m.get("status") == "PENDING")
        assigned_missions = sum(1 for m in missions if m.get("status") == "ASSIGNED")
        completed_missions = sum(1 for m in missions if m.get("status") == "COMPLETED")

        res_summary = resource_manager.get_resource_summary()

        return jsonify({
            "fleet": {
                "total": total_uavs,
                "idle": idle_uavs,
                "on_mission": on_mission_uavs,
                "charging": charging_uavs,
                "average_battery": avg_battery
            },
            "missions": {
                "total": total_missions,
                "pending": pending_missions,
                "assigned": assigned_missions,
                "completed": completed_missions
            },
            "active_assignments_count": len(active_assignments),
            "simulation_tick": simulator.get_current_tick(),
            "resources": res_summary
        }), 200
    except Exception as exc:
        logger.exception("Error calculating stats: %s", exc)
        return jsonify({"error": str(exc)}), 500


# ----------------------------------------------------------------------------
# 3. UAV FLEET ENDPOINTS (Vasant's Module)
# ----------------------------------------------------------------------------

@app.route("/api/uavs", methods=["GET"])
def list_uavs():
    """Retrieve all UAVs in the fleet."""
    try:
        uavs = drone_manager.get_all_uavs()
        return jsonify(uavs), 200
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/uavs", methods=["POST"])
def register_uav():
    """Register a new drone in the fleet."""
    data = request.get_json(silent=True) or {}
    if not data.get("name"):
        return jsonify({"error": "UAV name is required"}), 400
    try:
        res = drone_manager.create_uav(data)
        return jsonify(res), 201
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/uavs/<int:uav_id>", methods=["GET"])
def get_uav(uav_id):
    """Retrieve details of a single UAV."""
    uav = drone_manager.get_uav_by_id(uav_id)
    if not uav:
        return jsonify({"error": "UAV not found"}), 404
    return jsonify(uav), 200


@app.route("/api/uavs/<int:uav_id>", methods=["PATCH"])
def update_uav(uav_id):
    """Update status, battery, or location of a UAV."""
    data = request.get_json(silent=True) or {}
    if "status" in data:
        drone_manager.update_uav_status(uav_id, data["status"], data.get("availability"))
    if "battery_level" in data:
        drone_manager.update_uav_battery(uav_id, data["battery_level"])
    if "latitude" in data and "longitude" in data:
        drone_manager.update_uav_location(uav_id, data["latitude"], data["longitude"])
    return jsonify({"message": "UAV updated successfully"}), 200


# ----------------------------------------------------------------------------
# 4. MISSION ENDPOINTS (Mission Input & Management)
# ----------------------------------------------------------------------------

@app.route("/api/missions", methods=["GET"])
def list_missions():
    """Retrieve missions, optionally filtered by status query param."""
    status_filter = request.args.get("status")
    try:
        missions = mission_manager.get_all_missions(status_filter=status_filter)
        return jsonify(missions), 200
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/missions", methods=["POST"])
def add_mission():
    """
    Step 1: Mission Input.
    Validates payload and inserts mission into Database with status 'PENDING'.
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "JSON request body is required"}), 400

    required_fields = ["mission_type", "priority", "latitude", "longitude"]
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Field '{field}' is required"}), 400

    try:
        result = mission_manager.create_mission(data)
        return jsonify(result), 201
    except Exception as exc:
        logger.exception("Failed to create mission: %s", exc)
        return jsonify({"error": "Could not create mission"}), 500


@app.route("/api/missions/<int:mission_id>", methods=["GET"])
def get_mission(mission_id):
    """Retrieve single mission details."""
    mission = mission_manager.get_mission_by_id(mission_id)
    if not mission:
        return jsonify({"error": "Mission not found"}), 404
    return jsonify(mission), 200


@app.route("/api/missions/<int:mission_id>/status", methods=["PATCH"])
def change_mission_status(mission_id):
    """Update status of a mission."""
    data = request.get_json(silent=True) or {}
    new_status = data.get("status")
    if not new_status:
        return jsonify({"error": "status is required"}), 400

    success = mission_manager.update_mission_status(mission_id, new_status)
    if not success:
        return jsonify({"error": "Mission not found"}), 404
    return jsonify({"message": f"Mission status updated to {new_status}"}), 200


# ----------------------------------------------------------------------------
# 5. SCHEDULING ENDPOINTS (Ananya's Module)
# ----------------------------------------------------------------------------

@app.route("/api/schedule", methods=["POST"])
def schedule_missions():
    """
    Step 3: Scheduling.
    Runs selected scheduling algorithm on pending missions.
    Algorithms supported: FCFS, SJF, Priority, Round Robin, Adaptive.
    """
    data = request.get_json(silent=True) or {}
    algo = data.get("algorithm", "FCFS").upper()
    quantum = int(data.get("quantum", 2))
    adaptive_mode = data.get("adaptive_mode", "NORMAL").upper()

    # Get pending missions from DB
    missions = mission_manager.get_pending_missions()
    if not missions:
        return jsonify({
            "message": "No pending missions in queue to schedule",
            "schedule": [],
            "metrics": get_detailed_metrics([])
        }), 200

    gantt_slices = []
    if algo == "FCFS":
        results = fcfs(missions)
    elif algo == "SJF":
        results = sjf(missions)
    elif algo == "PRIORITY":
        results = priority_scheduling(missions)
    elif algo in ("ROUND_ROBIN", "RR"):
        results, gantt_slices = round_robin(missions, quantum=quantum)
    elif algo == "ADAPTIVE":
        results = adaptive_scheduling(missions, mode=adaptive_mode)
    else:
        return jsonify({"error": f"Unknown algorithm: {algo}"}), 400

    metrics = get_detailed_metrics(results)

    # Standard Gantt slices if not already computed by Round Robin
    if not gantt_slices:
        gantt_slices = [
            {
                "id": r["id"],
                "title": r.get("title", f"Mission-{r['id']}"),
                "start_time": r["start_time"],
                "end_time": r["completion_time"]
            }
            for r in results
        ]

    return jsonify({
        "algorithm": algo,
        "schedule": results,
        "gantt_slices": gantt_slices,
        "metrics": metrics
    }), 200


@app.route("/api/schedule/compare", methods=["POST"])
def compare_algorithms():
    """
    Compares all scheduling algorithms side-by-side with WT/TAT metrics.
    """
    data = request.get_json(silent=True) or {}
    quantum = int(data.get("quantum", 2))
    adaptive_mode = data.get("adaptive_mode", "NORMAL")

    missions = mission_manager.get_pending_missions()
    if not missions:
        # If no pending missions, use a standard benchmark set so user can view comparison
        missions = [
            {"id": "M1", "title": "Search Sector Alpha", "priority": 2, "burst_time": 5, "arrival_time": 0, "deadline": 25},
            {"id": "M2", "title": "Blood Delivery", "priority": 1, "burst_time": 3, "arrival_time": 1, "deadline": 15},
            {"id": "M3", "title": "Perimeter Patrol", "priority": 4, "burst_time": 8, "arrival_time": 2, "deadline": 45},
            {"id": "M4", "title": "Hotspot Flare Scan", "priority": 3, "burst_time": 2, "arrival_time": 3, "deadline": 20},
            {"id": "M5", "title": "Sensor Mapping", "priority": 5, "burst_time": 6, "arrival_time": 4, "deadline": 60}
        ]

    comparison_results = compare_scheduling_algorithms(
        missions,
        quantum=quantum,
        adaptive_mode=adaptive_mode
    )

    return jsonify(comparison_results), 200


# ----------------------------------------------------------------------------
# 6. UAV ASSIGNMENT ENDPOINTS (Vasant's Module)
# ----------------------------------------------------------------------------

@app.route("/api/missions/<int:mission_id>/eligible-uavs", methods=["GET"])
def get_eligible_uavs(mission_id):
    """Filters UAVs meeting requirements for the mission."""
    mission = mission_manager.get_mission_by_id(mission_id)
    if not mission:
        return jsonify({"error": "Mission not found"}), 404

    eligible = drone_manager.filter_eligible_uavs(mission)
    return jsonify({"mission_id": mission_id, "eligible_uavs": eligible}), 200


@app.route("/api/missions/<int:mission_id>/assign", methods=["POST"])
def assign_mission(mission_id):
    """
    Step 4 & 5: UAV Assignment & Database Update.
    Evaluates eligible UAVs, picks best candidate (or uses provided uav_id),
    locks the drone, binds assignment, updates mission status to 'ASSIGNED'.
    """
    mission = mission_manager.get_mission_by_id(mission_id)
    if not mission:
        return jsonify({"error": "Mission not found"}), 404

    if mission["status"] != "PENDING":
        return jsonify({"error": f"Mission is already in '{mission['status']}' state"}), 400

    data = request.get_json(silent=True) or {}
    uav_id = data.get("uav_id")

    # If no uav_id is explicitly specified, automatically evaluate best eligible UAV
    if not uav_id:
        best_uav = drone_manager.find_best_uav_for_mission(mission)
        if not best_uav:
            return jsonify({
                "error": "No eligible UAV available. Drones may be busy, lack required capabilities, or have low battery."
            }), 409
        uav_id = best_uav["uav_id"]

    try:
        assignment = drone_manager.assign_uav_to_mission(uav_id, mission_id)
        return jsonify(assignment), 200
    except Exception as exc:
        logger.exception("Assignment error: %s", exc)
        return jsonify({"error": str(exc)}), 400


@app.route("/api/missions/auto-assign-all", methods=["POST"])
def auto_assign_all():
    """
    End-to-End Orchestrator:
    1. Fetches all pending missions.
    2. Schedules them using the chosen algorithm.
    3. Iteratively assigns the best available UAV to each scheduled mission.
    4. Updates database state.
    """
    data = request.get_json(silent=True) or {}
    algo = data.get("algorithm", "PRIORITY").upper()

    pending_missions = mission_manager.get_pending_missions()
    if not pending_missions:
        return jsonify({"message": "No pending missions to assign", "assignments": []}), 200

    # 1. Schedule missions
    if algo == "FCFS":
        scheduled = fcfs(pending_missions)
    elif algo == "SJF":
        scheduled = sjf(pending_missions)
    elif algo == "ROUND_ROBIN":
        scheduled, _ = round_robin(pending_missions)
    elif algo == "ADAPTIVE":
        scheduled = adaptive_scheduling(pending_missions)
    else:
        scheduled = priority_scheduling(pending_missions)

    assignments_made = []
    unassigned = []

    for item in scheduled:
        m_id = item["id"]
        mission = mission_manager.get_mission_by_id(m_id)
        if not mission or mission["status"] != "PENDING":
            continue

        best_uav = drone_manager.find_best_uav_for_mission(mission)
        if best_uav:
            try:
                res = drone_manager.assign_uav_to_mission(best_uav["uav_id"], m_id)
                assignments_made.append(res)
            except Exception as e:
                unassigned.append({"mission_id": m_id, "reason": str(e)})
        else:
            unassigned.append({
                "mission_id": m_id,
                "title": mission["title"],
                "reason": "No eligible UAV with sufficient battery and matching capabilities"
            })

    return jsonify({
        "message": f"Assigned {len(assignments_made)} missions successfully",
        "assignments": assignments_made,
        "unassigned": unassigned
    }), 200


@app.route("/api/assignments", methods=["GET"])
def list_assignments():
    """Retrieve active and ongoing assignments."""
    try:
        assignments = drone_manager.get_active_assignments()
        return jsonify(assignments), 200
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ----------------------------------------------------------------------------
# 7. SIMULATION RUNNER ENDPOINTS (Telemetry & Mission Progress)
# ----------------------------------------------------------------------------

@app.route("/api/simulation/step", methods=["POST"])
def step_simulation_tick():
    """Advances simulated flight clock by 1 tick."""
    try:
        result = simulator.step_simulation()
        return jsonify(result), 200
    except Exception as exc:
        logger.exception("Simulation step error: %s", exc)
        return jsonify({"error": str(exc)}), 500


@app.route("/api/reset-demo", methods=["POST"])
def reset_demo_environment():
    """Resets tables and re-seeds initial UAV fleet & missions."""
    try:
        from db_connection import execute_query
        execute_query("DELETE FROM assignment;")
        execute_query("DELETE FROM mission_log;")
        execute_query("DELETE FROM mission;")
        execute_query("DELETE FROM uav;")
        execute_query("DELETE FROM fleet_resource;")
        init_database(seed_demo_data=True)
        return jsonify({"message": "FleetOS demonstration environment reset successfully"}), 200
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ----------------------------------------------------------------------------
# 8. RESOURCE MANAGEMENT ENDPOINTS
# ----------------------------------------------------------------------------

@app.route("/api/resources", methods=["GET"])
def get_resources():
    """Get status of shared resources."""
    try:
        summary = resource_manager.get_resource_summary()
        return jsonify(summary), 200
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"================================================================")
    print(f" FLEETOS: Autonomous Multi-UAV Fleet Operating System (Phase 2)")
    print(f" Server running at: http://localhost:{port}")
    print(f" Dashboard UI:      http://localhost:{port}/")
    print(f" API Health:        http://localhost:{port}/api/health")
    print(f"================================================================")
    app.run(host="0.0.0.0", port=port, debug=False)
