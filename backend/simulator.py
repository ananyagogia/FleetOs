"""
FleetOS Simulation Engine.
Drives dynamic time progression, UAV flight movement, battery drain,
charging cycles, and mission completion events.
"""

import logging
from typing import Any, Dict, List
import sys
import os

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "database")
if DB_DIR not in sys.path:
    sys.path.append(DB_DIR)

from db_connection import execute_query, fetch_all, fetch_one

logger = logging.getLogger("fleetos.simulator")

_SIMULATION_TICK = 0


def get_current_tick() -> int:
    """Returns current simulated clock tick."""
    global _SIMULATION_TICK
    return _SIMULATION_TICK


def step_simulation() -> Dict[str, Any]:
    """
    Advances the FleetOS simulation by one discrete time tick.
    1. Updates active assignments: drains battery, interpolates position.
    2. Completes finished missions, frees UAVs.
    3. Recharges UAVs that are currently in CHARGING status.
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

        # Move drone incrementally closer to target (25% lerp per tick)
        uav_lat = float(assign["uav_lat"])
        uav_lon = float(assign["uav_lon"])
        target_lat = float(assign["m_lat"])
        target_lon = float(assign["m_lon"])

        next_lat = round(uav_lat + (target_lat - uav_lat) * 0.35, 6)
        next_lon = round(uav_lon + (target_lon - uav_lon) * 0.35, 6)

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
            
            # If battery is low, put UAV in charging, otherwise return to IDLE
            if new_battery <= 25.0:
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
