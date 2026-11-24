"""
FleetOS Resource Manager.
Tracks and manages shared limited infrastructure:
- Fast Charging Pads
- Communication RF Telemetry Bands
- Sensor Payloads
"""

import logging
from typing import Any, Dict, List, Optional
import sys
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_DIR = os.path.join(BASE_DIR, "database")
RES_DIR = os.path.join(BASE_DIR, "resources")
for p in [DB_DIR, RES_DIR]:
    if p not in sys.path:
        sys.path.append(p)

from db_connection import execute_query, fetch_all, fetch_one
from deadlock_detector import deadlock_mgr

logger = logging.getLogger("fleetos.resource_manager")


def get_all_resources() -> List[Dict[str, Any]]:
    """Retrieve all tracked fleet resources with occupancy details."""
    query = "SELECT * FROM fleet_resource ORDER BY resource_id ASC;"
    resources = fetch_all(query)
    for r in resources:
        cap = int(r.get("total_capacity", 1))
        avail = int(r.get("available_count", 0))
        occupied = max(0, cap - avail)
        r["capacity"] = cap
        r["occupied"] = occupied
        r["status"] = f"Nominal ({avail} Available)" if avail > 0 else "Fully Occupied (Queue Active)"
        if r.get("resource_type") == "CHARGING_PAD":
            r["voltage"] = "48.2V / 30A Fast Charge"
        elif r.get("resource_type") == "COMM_CHANNEL":
            r["voltage"] = "5.8 GHz Telemetry Link"
        else:
            r["voltage"] = "Modular Gimbal Bus"
    return resources


def allocate_resource_to_uav(uav_id: int, resource_id: int) -> Dict[str, Any]:
    """Allocates a specific resource to a UAV using deadlock-aware logic."""
    return deadlock_mgr.request_resource(uav_id, resource_id)


def release_resource_from_uav(uav_id: int, resource_id: int) -> bool:
    """Releases a resource held by a UAV."""
    return deadlock_mgr.release_resource(uav_id, resource_id)


def get_active_allocations() -> List[Dict[str, Any]]:
    """Retrieve active allocations with UAV and resource names."""
    query = """
        SELECT ra.allocation_id, ra.resource_id, ra.uav_id, ra.status, ra.requested_at, ra.allocated_at,
               r.name AS resource_name, r.resource_type,
               u.name AS uav_name, u.model AS uav_model
        FROM resource_allocation ra
        JOIN fleet_resource r ON ra.resource_id = r.resource_id
        JOIN uav u ON ra.uav_id = u.uav_id
        WHERE ra.status IN ('HELD', 'WAITING')
        ORDER BY ra.allocation_id DESC;
    """
    return fetch_all(query)


def get_resource_summary() -> Dict[str, Any]:
    """Summary of total vs allocated resources, including active allocations."""
    resources = get_all_resources()
    total_cap = sum(r.get("total_capacity", 0) for r in resources)
    total_avail = sum(r.get("available_count", 0) for r in resources)
    active_allocs = get_active_allocations()

    return {
        "total_capacity": total_cap,
        "total_available": total_avail,
        "total_utilized": total_cap - total_avail,
        "resources": resources,
        "active_allocations": active_allocs,
        "active_allocations_count": len([a for a in active_allocs if a["status"] == "HELD"]),
        "waiting_count": len([a for a in active_allocs if a["status"] == "WAITING"])
    }
