"""
FleetOS Simulation Engine.
Drives dynamic time progression, UAV flight movement, battery drain,
charging cycles, mission completion events, and telemetry updates.
"""

import logging
from typing import Any, Dict, List
import sys
import os

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "database")
RES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "resources")
for p in [DB_DIR, RES_DIR]:
    if p not in sys.path:
        sys.path.append(p)

from db_connection import execute_query, fetch_all, fetch_one
from deadlock_detector import deadlock_mgr
import fault_manager

logger = logging.getLogger("fleetos.simulator")

_SIMULATION_TICK = 0


def get_current_tick() -> int:
    """Returns current simulated clock tick."""
    global _SIMULATION_TICK
    return _SIMULATION_TICK


def reset_simulation():
    """Resets simulated clock tick to zero."""
    global _SIMULATION_TICK
    _SIMULATION_TICK = 0


def step_simulation() -> Dict[str, Any]:
    """
    Advances the FleetOS simulation by one discrete time tick.
    1. Updates active assignments: drains battery, interpolates position, logs flight hours.
    2. Detects low battery (< 20%) and triggers autonomous docking/reassignment.
    3. Completes finished missions, frees UAVs, and releases resources.
    4. Recharges UAVs that are currently in CHARGING status.
    Returns list of logged simulation events.
    """
    global _SIMULATION_TICK
    _SIMULATION_TICK += 1
    events = []

    # 1. Process Active Missions
    active_assignments = fetch_all(
        """
        SELECT a.assignment_id, a.uav_id, a.mission_id,
               u.name AS uav_name, u.battery_level, u.latitude AS uav_lat, u.longitude AS uav_lon,
               m.title AS mission_title, m.latitude AS m_lat, m.longitude AS m_lon, m.burst_time
        FROM assignment a
        JOIN uav u ON a.uav_id = u.uav_id
        JOIN mission m ON a.mission_id = m.mission_id
        WHERE a.status = 'ACTIVE';
        """
    )

    for assign in active_assignments:
        uav_id = assign["uav_id"]
        mission_id = assign["mission_id"]
        current_battery = float(assign["battery_level"])

        # Drain battery by ~4% per tick during active flight
        new_battery = max(0.0, current_battery - 4.0)

        # Increment flight hours in maintenance log
        execute_query(
            "UPDATE uav_maintenance SET flight_hours = flight_hours + 0.1 WHERE uav_id = %s;",
            (uav_id,)
        )

        # Move drone incrementally closer to target (35% lerp per tick)
        uav_lat = float(assign["uav_lat"])
        uav_lon = float(assign["uav_lon"])
        target_lat = float(assign["m_lat"])
        target_lon = float(assign["m_lon"])

        next_lat = round(uav_lat + (target_lat - uav_lat) * 0.35, 6)
        next_lon = round(uav_lon + (target_lon - uav_lon) * 0.35, 6)

        # Check for critical battery during flight
        if new_battery <= 20.0:
            fault_res = fault_manager.handle_low_battery(
                uav_id,
                description=f"Airframe {assign['uav_name']} reached critical battery reserve ({new_battery}%) during '{assign['mission_title']}'. RTB engaged."
            )
            events.append({
                "type": "LOW_BATTERY_FAULT",
                "uav_id": uav_id,
                "uav_name": assign["uav_name"],
                "battery": new_battery,
                "message": fault_res["message"]
            })
            continue

        # Count ticks spent on this mission
        log_count = fetch_one(
            "SELECT COUNT(*) AS cnt FROM mission_log WHERE mission_id = %s AND event = 'Simulation Tick';",
            (mission_id,)
        )
        ticks_elapsed = (log_count["cnt"] if log_count else 0) + 1

        # Check if mission reached completion
        burst_time = int(assign.get("burst_time", 4))
        if ticks_elapsed >= burst_time:
            # Complete Mission & Free UAV
            execute_query(
                "UPDATE assignment SET status = 'COMPLETED', completed_at = CURRENT_TIMESTAMP WHERE assignment_id = %s;",
                (assign["assignment_id"],)
            )
            execute_query("UPDATE mission SET status = 'COMPLETED' WHERE mission_id = %s;", (mission_id,))

            # Release any resources allocated to this UAV
            held = fetch_all("SELECT resource_id FROM resource_allocation WHERE uav_id = %s AND status = 'HELD';", (uav_id,))
            for r in held:
                deadlock_mgr.release_resource(uav_id, r["resource_id"])

            # Increment cycles in maintenance table
            execute_query("UPDATE uav_maintenance SET cycles = cycles + 1 WHERE uav_id = %s;", (uav_id,))

            # If battery is low, put UAV in charging, otherwise return to IDLE
            if new_battery <= 30.0:
                execute_query(
                    "UPDATE uav SET battery_level = %s, status = 'CHARGING', availability = 0, latitude = %s, longitude = %s WHERE uav_id = %s;",
                    (new_battery, next_lat, next_lon, uav_id)
                )
                status_msg = "Mission completed, UAV auto-docked for recharging"
            else:
                execute_query(
                    "UPDATE uav SET battery_level = %s, status = 'IDLE', availability = 1, latitude = %s, longitude = %s WHERE uav_id = %s;",
                    (new_battery, next_lat, next_lon, uav_id)
                )
                status_msg = "Mission completed, UAV returned to IDLE"

            execute_query(
                "INSERT INTO mission_log (mission_id, uav_id, event, status) VALUES (%s, %s, %s, 'COMPLETED');",
                (mission_id, uav_id, status_msg)
            )

            events.append({
                "type": "MISSION_COMPLETED",
                "mission_id": mission_id,
                "mission_title": assign["mission_title"],
                "uav_id": uav_id,
                "uav_name": assign["uav_name"],
                "final_battery": new_battery,
                "message": f"Mission '{assign['mission_title']}' completed by {assign['uav_name']}"
            })
        else:
            # Progress tick
            execute_query(
                "UPDATE uav SET battery_level = %s, latitude = %s, longitude = %s WHERE uav_id = %s;",
                (new_battery, next_lat, next_lon, uav_id)
            )
            execute_query(
                "INSERT INTO mission_log (mission_id, uav_id, event, status) VALUES (%s, %s, 'Simulation Tick', 'IN_PROGRESS');",
                (mission_id, uav_id)
            )
            events.append({
                "type": "MISSION_IN_PROGRESS",
                "mission_id": mission_id,
                "uav_id": uav_id,
                "uav_name": assign["uav_name"],
                "progress": f"{ticks_elapsed}/{burst_time} ticks",
                "battery": new_battery,
                "message": f"{assign['uav_name']} executing '{assign['mission_title']}' (Battery: {new_battery}%)"
            })

    # 2. Process Charging Drones
    charging_drones = fetch_all("SELECT * FROM uav WHERE status = 'CHARGING';")
    for drone in charging_drones:
        d_id = drone["uav_id"]
        cur_bat = float(drone["battery_level"])
        recharged_bat = min(100.0, cur_bat + 15.0)

        if recharged_bat >= 100.0:
            execute_query(
                "UPDATE uav SET battery_level = 100.0, status = 'IDLE', availability = 1 WHERE uav_id = %s;",
                (d_id,)
            )
            # Release charging pad if allocated
            pad_alloc = fetch_one(
                """
                SELECT ra.resource_id
                FROM resource_allocation ra
                JOIN fleet_resource r ON ra.resource_id = r.resource_id
                WHERE ra.uav_id = %s AND r.resource_type = 'CHARGING_PAD' AND ra.status = 'HELD';
                """,
                (d_id,)
            )
            if pad_alloc:
                deadlock_mgr.release_resource(d_id, pad_alloc["resource_id"])

            events.append({
                "type": "UAV_CHARGED",
                "uav_id": d_id,
                "uav_name": drone["name"],
                "message": f"UAV {drone['name']} fully recharged to 100% and ready for operations"
            })
        else:
            execute_query(
                "UPDATE uav SET battery_level = %s WHERE uav_id = %s;",
                (recharged_bat, d_id)
            )
            events.append({
                "type": "UAV_CHARGING",
                "uav_id": d_id,
                "uav_name": drone["name"],
                "battery": recharged_bat,
                "message": f"UAV {drone['name']} charging (Current: {recharged_bat}%)"
            })

    logger.info("Simulation tick %s executed with %s events", _SIMULATION_TICK, len(events))
    return {
        "simulation_tick": _SIMULATION_TICK,
        "events": events,
        "active_missions_count": len(active_assignments),
        "charging_count": len(charging_drones)
    }
