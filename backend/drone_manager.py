"""
FleetOS Drone Manager (UAV Management & Assignment Engine).
Responsible for UAV fleet inventory, availability, battery health,
capability filtering, distance evaluation, and atomic UAV assignment.
"""

import math
import logging
from typing import Any, Dict, List, Optional, Tuple
import sys
import os

# Ensure database package is importable
DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "database")
if DB_DIR not in sys.path:
    sys.path.append(DB_DIR)

from db_connection import execute_query, fetch_all, fetch_one

logger = logging.getLogger("fleetos.drone_manager")


def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Computes approximate distance (in kilometers) between two coordinates
    using the Haversine formula.
    """
    R = 6371.0  # Earth radius in kilometers

    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (math.sin(d_lat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(d_lon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(R * c, 3)


def get_all_uavs() -> List[Dict[str, Any]]:
    """Retrieve all UAVs in the fleet."""
    query = """
        SELECT uav_id, name, model, battery_level, latitude, longitude,
               status, availability, max_payload_kg, capabilities, created_at
        FROM uav
        ORDER BY uav_id ASC;
    """
    return fetch_all(query)


def get_uav_by_id(uav_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve a single UAV by its ID."""
    query = "SELECT * FROM uav WHERE uav_id = %s;"
    return fetch_one(query, (uav_id,))


def create_uav(data: Dict[str, Any]) -> Dict[str, Any]:
    """Register a new UAV in the fleet."""
    query = """
        INSERT INTO uav (name, model, battery_level, latitude, longitude,
                         status, availability, max_payload_kg, capabilities)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
    """
    params = (
        data["name"],
        data.get("model", "Standard-Quadcopter"),
        float(data.get("battery_level", 100.0)),
        float(data.get("latitude", 28.6139)),
        float(data.get("longitude", 77.2090)),
        data.get("status", "IDLE"),
        1 if data.get("availability", True) else 0,
        float(data.get("max_payload_kg", 5.0)),
        data.get("capabilities", "CAMERA")
    )
    uav_id = execute_query(query, params)
    return {
        "uav_id": uav_id,
        "name": data["name"],
        "message": "UAV registered successfully"
    }


def update_uav_status(uav_id: int, status: str, availability: Optional[bool] = None) -> bool:
    """Update operational status and availability of a UAV."""
    if availability is None:
        avail_val = 1 if status == "IDLE" else 0
    else:
        avail_val = 1 if availability else 0

    query = "UPDATE uav SET status = %s, availability = %s WHERE uav_id = %s;"
    rows = execute_query(query, (status, avail_val, uav_id))
    return rows > 0


def update_uav_battery(uav_id: int, battery_level: float) -> bool:
    """Update UAV battery level."""
    clamped_battery = max(0.0, min(100.0, float(battery_level)))
    # Automatically switch to CHARGING if low battery, or IDLE if full
    status_clause = ""
    if clamped_battery <= 20.0:
        query = "UPDATE uav SET battery_level = %s, status = 'CHARGING', availability = 0 WHERE uav_id = %s;"
        rows = execute_query(query, (clamped_battery, uav_id))
    else:
        query = "UPDATE uav SET battery_level = %s WHERE uav_id = %s;"
        rows = execute_query(query, (clamped_battery, uav_id))
    return rows > 0


def update_uav_location(uav_id: int, latitude: float, longitude: float) -> bool:
    """Update UAV GPS coordinates."""
    query = "UPDATE uav SET latitude = %s, longitude = %s WHERE uav_id = %s;"
    rows = execute_query(query, (latitude, longitude, uav_id))
    return rows > 0


def filter_eligible_uavs(mission: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Filters UAVs that meet operational prerequisites for the given mission:
    1. Must be IDLE and available.
    2. Battery level must exceed safety threshold + estimated mission consumption.
    3. Must possess all required mission capabilities.
    """
    all_drones = get_all_uavs()
    eligible = []

    m_lat = float(mission.get("latitude", 28.6139))
    m_lon = float(mission.get("longitude", 77.2090))
    burst_time = int(mission.get("burst_time", 5))

    required_caps = [
        c.strip().upper()
        for c in mission.get("required_capabilities", "").split(",")
        if c.strip()
    ]

    for drone in all_drones:
        # 1. Availability check
        if not drone["availability"] or drone["status"] != "IDLE":
            continue

        # 2. Distance and Energy Estimation
        dist_km = calculate_distance(
            float(drone["latitude"]),
            float(drone["longitude"]),
            m_lat,
            m_lon
        )
        # Energy model: 20% safety margin + 1% per km flight + 2% per burst time tick
        estimated_drain = 20.0 + (dist_km * 1.5) + (burst_time * 2.0)
        battery = float(drone["battery_level"])
        if battery < estimated_drain or battery < 25.0:
            continue

        # 3. Capability Matching
        drone_caps = [
            c.strip().upper()
            for c in (drone.get("capabilities") or "").split(",")
            if c.strip()
        ]
        if required_caps and not all(req in drone_caps for req in required_caps):
            continue

        # Passed all filters
        drone_copy = dict(drone)
        drone_copy["distance_to_target_km"] = dist_km
        drone_copy["estimated_drain_pct"] = round(estimated_drain, 1)
        eligible.append(drone_copy)

    return eligible


def find_best_uav_for_mission(mission: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Evaluates eligible UAVs and ranks them using a weighted score:
      Score = (Battery / 100) * 0.40 - (Normalized Distance) * 0.60
    Returns the top-ranked UAV.
    """
    eligible = filter_eligible_uavs(mission)
    if not eligible:
        return None

    # Find maximum distance for normalization
    max_dist = max([d["distance_to_target_km"] for d in eligible] + [1.0])

    def rank_score(d: Dict[str, Any]) -> float:
        norm_battery = float(d["battery_level"]) / 100.0
        norm_dist = d["distance_to_target_km"] / max_dist
        # Prefer closest drone with healthy battery
        return (norm_battery * 0.40) - (norm_dist * 0.60)

    ranked = sorted(eligible, key=rank_score, reverse=True)
    best = ranked[0]
    best["suitability_score"] = round(rank_score(best), 3)
    return best


def assign_uav_to_mission(uav_id: int, mission_id: int) -> Dict[str, Any]:
    """
    Executes atomic assignment:
    1. Validates UAV is IDLE.
    2. Updates UAV to 'ON_MISSION' and availability = 0.
    3. Updates Mission to 'ASSIGNED'.
    4. Creates record in assignment table.
    5. Appends to mission_log.
    """
    uav = get_uav_by_id(uav_id)
    if not uav:
        raise ValueError(f"UAV with ID {uav_id} does not exist")

    if uav["status"] != "IDLE" or not uav["availability"]:
        raise ValueError(f"UAV {uav['name']} is not currently available (Status: {uav['status']})")

    # 1. Update UAV
    update_uav_status(uav_id, "ON_MISSION", availability=False)

    # 2. Update Mission
    execute_query(
        "UPDATE mission SET status = 'ASSIGNED' WHERE mission_id = %s;",
        (mission_id,)
    )

    # 3. Create Assignment record
    assignment_id = execute_query(
        """
        INSERT INTO assignment (uav_id, mission_id, status)
        VALUES (%s, %s, 'ACTIVE');
        """,
        (uav_id, mission_id)
    )

    # 4. Log event
    execute_query(
        """
        INSERT INTO mission_log (mission_id, uav_id, event, status)
        VALUES (%s, %s, 'UAV Assigned', 'ASSIGNED');
        """,
        (mission_id, uav_id)
    )

    logger.info("FleetOS: UAV %s successfully assigned to Mission %s (Assignment ID: %s)",
                uav_id, mission_id, assignment_id)

    return {
        "assignment_id": assignment_id,
        "uav_id": uav_id,
        "uav_name": uav["name"],
        "mission_id": mission_id,
        "status": "ACTIVE",
        "message": f"UAV {uav['name']} successfully assigned to Mission {mission_id}"
    }


def get_active_assignments() -> List[Dict[str, Any]]:
    """Fetch all active assignments joined with UAV and Mission details."""
    query = """
        SELECT a.assignment_id, a.status AS assignment_status, a.assigned_at,
               u.uav_id, u.name AS uav_name, u.battery_level, u.status AS uav_status,
               m.mission_id, m.title AS mission_title, m.mission_type, m.priority,
               m.burst_time, m.latitude AS target_lat, m.longitude AS target_lon
        FROM assignment a
        JOIN uav u ON a.uav_id = u.uav_id
        JOIN mission m ON a.mission_id = m.mission_id
        WHERE a.status = 'ACTIVE'
        ORDER BY a.assignment_id DESC;
    """
    return fetch_all(query)
