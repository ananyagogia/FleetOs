"""
FleetOS Resource Manager.
Tracks and manages shared limited infrastructure:
- Charging pads
- Communication telemetry bandwidth channels
- Sensor payloads
"""

import logging
from typing import Any, Dict, List, Optional
import sys
import os

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "database")
if DB_DIR not in sys.path:
    sys.path.append(DB_DIR)

from db_connection import execute_query, fetch_all, fetch_one

logger = logging.getLogger("fleetos.resource_manager")


def get_all_resources() -> List[Dict[str, Any]]:
    """Retrieve all tracked fleet resources."""
    query = "SELECT * FROM fleet_resource ORDER BY resource_id ASC;"
    return fetch_all(query)


def allocate_resource(resource_type: str) -> Optional[Dict[str, Any]]:
    """
    Allocates one instance of the requested resource type if available.
    """
    query = """
        SELECT * FROM fleet_resource
        WHERE resource_type = %s AND available_count > 0
        LIMIT 1;
    """
    res = fetch_one(query, (resource_type,))
    if not res:
        logger.warning("Resource exhaustion: No available %s", resource_type)
        return None

    r_id = res["resource_id"]
    execute_query(
        "UPDATE fleet_resource SET available_count = available_count - 1 WHERE resource_id = %s;",
        (r_id,)
    )
    logger.info("Allocated %s from resource #%s (%s)", resource_type, r_id, res["name"])
    return {
        "resource_id": r_id,
        "name": res["name"],
        "resource_type": resource_type,
        "remaining": res["available_count"] - 1
    }


def release_resource(resource_id: int) -> bool:
    """Releases an instance of an allocated resource."""
    query = """
        UPDATE fleet_resource
        SET available_count = LEAST(total_capacity, available_count + 1)
        WHERE resource_id = %s;
    """
    # For SQLite compatibility:
    # We can check and update directly
    res = fetch_one("SELECT * FROM fleet_resource WHERE resource_id = %s;", (resource_id,))
    if not res:
        return False

    new_val = min(res["total_capacity"], res["available_count"] + 1)
    execute_query("UPDATE fleet_resource SET available_count = %s WHERE resource_id = %s;", (new_val, resource_id))
    logger.info("Released resource #%s (%s), available: %s", resource_id, res["name"], new_val)
    return True


def get_resource_summary() -> Dict[str, Any]:
    """Summary of total vs allocated resources."""
    resources = get_all_resources()
    total_cap = sum(r.get("total_capacity", 0) for r in resources)
    total_avail = sum(r.get("available_count", 0) for r in resources)
    return {
        "total_capacity": total_cap,
        "total_available": total_avail,
        "total_utilized": total_cap - total_avail,
        "resources": resources
    }
