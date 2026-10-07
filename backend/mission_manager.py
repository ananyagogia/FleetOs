"""
FleetOS Mission Manager.
Manages mission creation, state transitions, validation, and database operations.
"""

import logging
from typing import Any, Dict, List, Optional
import sys
import os

# Ensure database package is importable
DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "database")
if DB_DIR not in sys.path:
    sys.path.append(DB_DIR)

from db_connection import execute_query, fetch_all, fetch_one

logger = logging.getLogger("fleetos.mission_manager")


def create_mission(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Creates and records a new mission in the database.
    """
    title = data.get("title") or f"{data.get('mission_type', 'Operational')} Mission"
    mission_type = data.get("mission_type")
    priority = int(data.get("priority", 3))
    latitude = float(data.get("latitude", 28.6139))
    longitude = float(data.get("longitude", 77.2090))
    required_caps = data.get("required_capabilities", "CAMERA")
    burst_time = int(data.get("burst_time", 5))
    arrival_time = int(data.get("arrival_time", 0))
    deadline = int(data.get("deadline", 60))

    query = """
        INSERT INTO mission (
            title, mission_type, priority, latitude, longitude,
            required_capabilities, burst_time, arrival_time, deadline, status
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'PENDING');
    """
    params = (
        title, mission_type, priority, latitude, longitude,
        required_caps, burst_time, arrival_time, deadline
    )

    mission_id = execute_query(query, params)

    # Log initial creation event
    execute_query(
        """
        INSERT INTO mission_log (mission_id, uav_id, event, status)
        VALUES (%s, NULL, 'Mission Created', 'PENDING');
        """,
        (mission_id,)
    )

    logger.info("FleetOS: Created mission #%s (%s)", mission_id, title)
    return {
        "mission_id": mission_id,
        "title": title,
        "mission_type": mission_type,
        "priority": priority,
        "burst_time": burst_time,
        "arrival_time": arrival_time,
        "status": "PENDING",
        "message": "Mission registered successfully in queue"
    }


def get_all_missions(status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieve all missions, optionally filtered by status."""
    if status_filter:
        query = "SELECT * FROM mission WHERE status = %s ORDER BY mission_id DESC;"
        return fetch_all(query, (status_filter,))
    else:
        query = "SELECT * FROM mission ORDER BY mission_id DESC;"
        return fetch_all(query)


def get_pending_missions() -> List[Dict[str, Any]]:
    """Retrieve missions awaiting scheduling and assignment."""
    query = """
        SELECT mission_id AS id, mission_id, title, mission_type, priority,
               latitude, longitude, required_capabilities, burst_time, arrival_time,
               deadline, status, created_at
        FROM mission
        WHERE status = 'PENDING'
        ORDER BY priority ASC, arrival_time ASC, mission_id ASC;
    """
    return fetch_all(query)


def get_mission_by_id(mission_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve a single mission by ID."""
    query = "SELECT * FROM mission WHERE mission_id = %s;"
    return fetch_one(query, (mission_id,))


def update_mission_status(mission_id: int, new_status: str) -> bool:
    """Updates the status of a mission and creates an audit entry."""
    query = "UPDATE mission SET status = %s WHERE mission_id = %s;"
    rows = execute_query(query, (new_status, mission_id))

    if rows > 0:
        execute_query(
            """
            INSERT INTO mission_log (mission_id, uav_id, event, status)
            VALUES (%s, NULL, %s, %s);
            """,
            (mission_id, f"Status updated to {new_status}", new_status)
        )
        return True
    return False


def delete_mission(mission_id: int) -> bool:
    """Deletes a mission by ID."""
    query = "DELETE FROM mission WHERE mission_id = %s;"
    rows = execute_query(query, (mission_id,))
    return rows > 0
