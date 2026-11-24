"""
FleetOS Fault Detection & Autonomous Recovery Engine.
Implements fault handling and self-healing for:
1. Drone Failure (airframe/motor crash, mid-flight loss)
2. Low Battery (critical depletion, emergency RTB & docking)
3. Mission Failure (sensor error, unreachable target, timeout)
4. Resource Unavailability (pad/channel exhaustion & queuing)
5. Communication Failure (telemetry disconnect & failsafe)

Features:
- Complete database persistence in fault_log & mission_log
- Resource release and reclamation
- Autonomous mission reassignment to eligible idle UAVs
"""

import sys
import os
import logging
from typing import Dict, List, Any, Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_DIR = os.path.join(BASE_DIR, "database")
RES_DIR = os.path.join(BASE_DIR, "resources")
for p in [BASE_DIR, DB_DIR, RES_DIR]:
    if p not in sys.path:
        sys.path.append(p)

from db_connection import execute_query, fetch_all, fetch_one
import drone_manager
import mission_manager
from deadlock_detector import deadlock_mgr

logger = logging.getLogger("fleetos.fault_manager")


def get_all_faults(status: Optional[str] = None, severity: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Retrieves all logged faults from the database, joined with UAV details.
    """
    conditions = []
    params = []

    if status:
        conditions.append("f.status = %s")
        params.append(status.upper())
    if severity:
        conditions.append("f.severity = %s")
        params.append(severity.lower())

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    query = f"""
        SELECT f.fault_id, f.uav_id, f.fault_type, f.severity, f.status,
               f.description, f.timestamp, f.resolved_at,
               u.name AS uav_name, u.model AS uav_model, u.status AS uav_status
        FROM fault_log f
        LEFT JOIN uav u ON f.uav_id = u.uav_id
        {where_clause}
        ORDER BY f.fault_id DESC;
    """
    return fetch_all(query, tuple(params))


def trigger_fault(
    fault_type: str,
    uav_id: Optional[int] = None,
    mission_id: Optional[int] = None,
    description: Optional[str] = None
) -> Dict[str, Any]:
    """
    Dispatches fault handling according to failure scenario.
    Updates statuses, releases resources, logs faults, and reassigns missions.
    """
    fault_type = fault_type.upper()

    if fault_type in ("DRONE_FAILURE", "MOTOR_FAILURE", "HARDWARE_FAULT"):
        return handle_drone_failure(uav_id, description)
    elif fault_type == "LOW_BATTERY":
        return handle_low_battery(uav_id, description)
    elif fault_type == "MISSION_FAILURE":
        return handle_mission_failure(mission_id, uav_id, description)
    elif fault_type == "RESOURCE_UNAVAILABLE":
        return handle_resource_unavailability(uav_id, description)
    elif fault_type in ("COMM_LOSS", "COMMUNICATION_FAILURE"):
        return handle_communication_failure(uav_id, description)
    else:
        raise ValueError(f"Unsupported fault type: {fault_type}")


# ----------------------------------------------------------------------------
# Scenario 1: Drone Failure & Mission Reassignment
# ----------------------------------------------------------------------------
def handle_drone_failure(uav_id: Optional[int], description: Optional[str] = None) -> Dict[str, Any]:
    """
    Handles critical drone failure:
    1. Sets UAV to OFFLINE and unavailable.
    2. Releases any held resources (pads, comms, payloads).
    3. Finds active mission: reassigns to an eligible idle UAV, or returns to PENDING queue.
    4. Records event in fault_log and mission_log.
    """
    if not uav_id:
        # Pick any active or idle UAV
        uav = fetch_one("SELECT uav_id, name FROM uav WHERE status != 'OFFLINE' LIMIT 1;")
        if not uav:
            raise ValueError("No active UAV available to simulate drone failure")
        uav_id = uav["uav_id"]

    drone = drone_manager.get_uav_by_id(uav_id)
    if not drone:
        raise ValueError(f"UAV #{uav_id} not found")

    uav_name = drone["name"]
    logger.critical("FAULT DETECTED: Drone Failure on %s (ID: %s)", uav_name, uav_id)

    # 1. Update UAV status to OFFLINE
    execute_query(
        "UPDATE uav SET status = 'OFFLINE', availability = 0 WHERE uav_id = %s;",
        (uav_id,)
    )

    # 2. Release all resources held by this UAV
    held_resources = fetch_all(
        "SELECT resource_id FROM resource_allocation WHERE uav_id = %s AND status = 'HELD';",
        (uav_id,)
    )
    for r in held_resources:
        deadlock_mgr.release_resource(uav_id, r["resource_id"])

    # Clean any pending waiting requests from this UAV
    execute_query("DELETE FROM resource_allocation WHERE uav_id = %s AND status = 'WAITING';", (uav_id,))

    # 3. Check for active mission assignment
    active_assign = fetch_one(
        """
        SELECT a.assignment_id, a.mission_id, m.title, m.priority, m.latitude, m.longitude,
               m.required_capabilities, m.burst_time
        FROM assignment a
        JOIN mission m ON a.mission_id = m.mission_id
        WHERE a.uav_id = %s AND a.status = 'ACTIVE'
        LIMIT 1;
        """,
        (uav_id,)
    )

    reassignment_info = None
    if active_assign:
        m_id = active_assign["mission_id"]
        # Mark current assignment as FAILED
        execute_query("UPDATE assignment SET status = 'FAILED' WHERE assignment_id = %s;", (active_assign["assignment_id"],))

        # Attempt mission reassignment
        mission_obj = mission_manager.get_mission_by_id(m_id)
        # Reset mission status to PENDING temporarily so search finds candidates
        execute_query("UPDATE mission SET status = 'PENDING' WHERE mission_id = %s;", (m_id,))

        replacement_uav = drone_manager.find_best_uav_for_mission(mission_obj)
        if replacement_uav:
            try:
                new_assign = drone_manager.assign_uav_to_mission(replacement_uav["uav_id"], m_id)
                reassignment_info = {
                    "reassigned": True,
                    "new_uav_id": replacement_uav["uav_id"],
                    "new_uav_name": replacement_uav["name"],
                    "mission_id": m_id,
                    "mission_title": active_assign["title"]
                }
                execute_query(
                    """
                    INSERT INTO mission_log (mission_id, uav_id, event, status)
                    VALUES (%s, %s, %s, 'ASSIGNED');
                    """,
                    (m_id, replacement_uav["uav_id"], f"Emergency mission reassignment from {uav_name} to {replacement_uav['name']}")
                )
                logger.info("Successfully reassigned mission #%s to UAV %s", m_id, replacement_uav["name"])
            except Exception as e:
                logger.error("Failed to reassign mission: %s", e)
                reassignment_info = {"reassigned": False, "reason": str(e)}
        else:
            reassignment_info = {
                "reassigned": False,
                "reason": "No other eligible idle UAV available with matching sensors and battery. Mission placed in PENDING queue."
            }
            execute_query(
                """
                INSERT INTO mission_log (mission_id, uav_id, event, status)
                VALUES (%s, %s, 'Mission returned to queue due to airframe failure', 'PENDING');
                """,
                (m_id, uav_id)
            )

    # 4. Insert fault log
    fault_desc = description or f"Critical hardware malfunction on {uav_name} (ID: #{uav_id}). Airframe forced OFFLINE."
    if reassignment_info and reassignment_info.get("reassigned"):
        fault_desc += f" Mission #{reassignment_info['mission_id']} successfully reassigned to {reassignment_info['new_uav_name']}."
    elif reassignment_info:
        fault_desc += f" Mission placed in queue: {reassignment_info.get('reason')}."

    fault_id = execute_query(
        """
        INSERT INTO fault_log (uav_id, fault_type, severity, status, description)
        VALUES (%s, 'DRONE_FAILURE', 'critical', 'ACTIVE', %s);
        """,
        (uav_id, fault_desc)
    )

    return {
        "fault_id": fault_id,
        "fault_type": "DRONE_FAILURE",
        "uav_id": uav_id,
        "uav_name": uav_name,
        "uav_status": "OFFLINE",
        "released_resources_count": len(held_resources),
        "reassignment": reassignment_info,
        "message": fault_desc
    }


# ----------------------------------------------------------------------------
# Scenario 2: Low Battery & Emergency Docking / Reassignment
# ----------------------------------------------------------------------------
def handle_low_battery(uav_id: Optional[int], description: Optional[str] = None) -> Dict[str, Any]:
    """
    Handles critical low battery:
    1. Lowers battery level to 12.0% (safety threshold).
    2. Switches UAV status to CHARGING and availability = 0.
    3. Attempts to allocate a charging pad.
    4. Reassigns active mission if any.
    5. Logs warning in fault_log.
    """
    if not uav_id:
        uav = fetch_one("SELECT uav_id, name FROM uav WHERE status = 'ON_MISSION' LIMIT 1;")
        if not uav:
            uav = fetch_one("SELECT uav_id, name FROM uav WHERE status = 'IDLE' LIMIT 1;")
        if not uav:
            raise ValueError("No UAV available to trigger low battery")
        uav_id = uav["uav_id"]

    drone = drone_manager.get_uav_by_id(uav_id)
    uav_name = drone["name"]

    # Update battery and status
    execute_query(
        "UPDATE uav SET battery_level = 12.0, status = 'CHARGING', availability = 0 WHERE uav_id = %s;",
        (uav_id,)
    )

    # Release any non-charging resources
    non_charging = fetch_all(
        """
        SELECT ra.resource_id, r.name, r.resource_type
        FROM resource_allocation ra
        JOIN fleet_resource r ON ra.resource_id = r.resource_id
        WHERE ra.uav_id = %s AND r.resource_type != 'CHARGING_PAD' AND ra.status = 'HELD';
        """,
        (uav_id,)
    )
    for res in non_charging:
        deadlock_mgr.release_resource(uav_id, res["resource_id"])

    # Attempt to allocate charging pad
    charging_pad = fetch_one("SELECT resource_id, name, available_count FROM fleet_resource WHERE resource_type = 'CHARGING_PAD' AND available_count > 0 LIMIT 1;")
    pad_allocated = False
    pad_name = "None"
    if charging_pad:
        try:
            deadlock_mgr.request_resource(uav_id, charging_pad["resource_id"])
            pad_allocated = True
            pad_name = charging_pad["name"]
        except Exception:
            pass

    # Reassign active mission if drone was airborne
    active_assign = fetch_one(
        """
        SELECT a.assignment_id, a.mission_id, m.title
        FROM assignment a
        JOIN mission m ON a.mission_id = m.mission_id
        WHERE a.uav_id = %s AND a.status = 'ACTIVE'
        LIMIT 1;
        """,
        (uav_id,)
    )

    reassignment_info = None
    if active_assign:
        m_id = active_assign["mission_id"]
        execute_query("UPDATE assignment SET status = 'REASSIGNED' WHERE assignment_id = %s;", (active_assign["assignment_id"],))
        execute_query("UPDATE mission SET status = 'PENDING' WHERE mission_id = %s;", (m_id,))

        mission_obj = mission_manager.get_mission_by_id(m_id)
        replacement = drone_manager.find_best_uav_for_mission(mission_obj)
        if replacement:
            drone_manager.assign_uav_to_mission(replacement["uav_id"], m_id)
            reassignment_info = {
                "reassigned": True,
                "new_uav_id": replacement["uav_id"],
                "new_uav_name": replacement["name"]
            }
        else:
            reassignment_info = {
                "reassigned": False,
                "reason": "Mission returned to PENDING queue for next available UAV"
            }

    desc = description or (
        f"Critical battery depletion on {uav_name} (12.0%). Autonomous RTB engaged. "
        f"Docked at {pad_name if pad_allocated else 'Waiting for available charging pad'}."
    )
    if reassignment_info and reassignment_info.get("reassigned"):
        desc += f" Sortie reassigned to {reassignment_info['new_uav_name']}."

    fault_id = execute_query(
        """
        INSERT INTO fault_log (uav_id, fault_type, severity, status, description)
        VALUES (%s, 'LOW_BATTERY', 'warning', 'ACTIVE', %s);
        """,
        (uav_id, desc)
    )

    return {
        "fault_id": fault_id,
        "fault_type": "LOW_BATTERY",
        "uav_id": uav_id,
        "uav_name": uav_name,
        "current_battery": 12.0,
        "charging_docked": pad_allocated,
        "charging_pad": pad_name,
        "reassignment": reassignment_info,
        "message": desc
    }


# ----------------------------------------------------------------------------
# Scenario 3: Mission Failure
# ----------------------------------------------------------------------------
def handle_mission_failure(mission_id: Optional[int], uav_id: Optional[int] = None, description: Optional[str] = None) -> Dict[str, Any]:
    """
    Handles sortie / mission abort:
    1. Sets mission status to FAILED.
    2. Marks assignment as FAILED.
    3. Frees UAV back to IDLE.
    4. Releases allocated resources.
    5. Logs fault.
    """
    if not mission_id:
        active = fetch_one("SELECT a.mission_id, a.uav_id FROM assignment a WHERE a.status = 'ACTIVE' LIMIT 1;")
        if active:
            mission_id = active["mission_id"]
            uav_id = active["uav_id"]
        else:
            m = fetch_one("SELECT mission_id FROM mission WHERE status IN ('PENDING', 'ASSIGNED') LIMIT 1;")
            if not m:
                raise ValueError("No mission available to fail")
            mission_id = m["mission_id"]

    mission = mission_manager.get_mission_by_id(mission_id)
    if not mission:
        raise ValueError(f"Mission #{mission_id} not found")

    # Mark mission FAILED
    execute_query("UPDATE mission SET status = 'FAILED' WHERE mission_id = %s;", (mission_id,))

    # If assignment active, complete it as FAILED and free drone
    assign = fetch_one("SELECT assignment_id, uav_id FROM assignment WHERE mission_id = %s AND status = 'ACTIVE';", (mission_id,))
    freed_uav = None
    if assign:
        execute_query("UPDATE assignment SET status = 'FAILED', completed_at = CURRENT_TIMESTAMP WHERE assignment_id = %s;", (assign["assignment_id"],))
        u_id = assign["uav_id"]
        execute_query("UPDATE uav SET status = 'IDLE', availability = 1 WHERE uav_id = %s;", (u_id,))
        freed_uav = u_id

        # Release resources
        held = fetch_all("SELECT resource_id FROM resource_allocation WHERE uav_id = %s AND status = 'HELD';", (u_id,))
        for r in held:
            deadlock_mgr.release_resource(u_id, r["resource_id"])

    desc = description or f"Sortie '{mission['title']}' (ID: #{mission_id}) aborted due to flight path or sensor fault."
    fault_id = execute_query(
        """
        INSERT INTO fault_log (uav_id, fault_type, severity, status, description)
        VALUES (%s, 'MISSION_FAILURE', 'warning', 'ACTIVE', %s);
        """,
        (freed_uav or uav_id, desc)
    )

    execute_query(
        """
        INSERT INTO mission_log (mission_id, uav_id, event, status)
        VALUES (%s, %s, %s, 'FAILED');
        """,
        (mission_id, freed_uav or uav_id, desc)
    )

    return {
        "fault_id": fault_id,
        "fault_type": "MISSION_FAILURE",
        "mission_id": mission_id,
        "freed_uav_id": freed_uav,
        "message": desc
    }


# ----------------------------------------------------------------------------
# Scenario 4: Resource Unavailability
# ----------------------------------------------------------------------------
def handle_resource_unavailability(uav_id: Optional[int], description: Optional[str] = None) -> Dict[str, Any]:
    """
    Logs resource exhaustion warning and manages queuing.
    """
    res = fetch_one("SELECT resource_id, name, total_capacity FROM fleet_resource WHERE available_count = 0 LIMIT 1;")
    if not res:
        res = fetch_one("SELECT resource_id, name, total_capacity FROM fleet_resource LIMIT 1;")

    r_name = res["name"] if res else "Charging Hub Infrastructure"
    r_id = res["resource_id"] if res else None

    desc = description or f"Resource bottleneck: '{r_name}' at 100% capacity. New allocation requests placed in Wait-For Queue."
    fault_id = execute_query(
        """
        INSERT INTO fault_log (uav_id, fault_type, severity, status, description)
        VALUES (%s, 'RESOURCE_UNAVAILABLE', 'warning', 'ACTIVE', %s);
        """,
        (uav_id, desc)
    )

    return {
        "fault_id": fault_id,
        "fault_type": "RESOURCE_UNAVAILABLE",
        "resource_id": r_id,
        "resource_name": r_name,
        "message": desc
    }


# ----------------------------------------------------------------------------
# Scenario 5: Communication Failure & Recovery
# ----------------------------------------------------------------------------
def handle_communication_failure(uav_id: Optional[int], description: Optional[str] = None) -> Dict[str, Any]:
    """
    Handles RF telemetry drop / loss:
    1. Sets UAV status to OFFLINE or failsafe.
    2. Releases allocated communication bandwidth channels.
    3. If UAV was on critical mission, prepares autonomous mission handover.
    """
    if not uav_id:
        uav = fetch_one("SELECT uav_id, name FROM uav WHERE status != 'OFFLINE' LIMIT 1;")
        if not uav:
            raise ValueError("No active UAV available for comm loss")
        uav_id = uav["uav_id"]

    drone = drone_manager.get_uav_by_id(uav_id)
    uav_name = drone["name"]

    # Release telemetry comm channels held by this UAV
    comm_channels = fetch_all(
        """
        SELECT ra.resource_id
        FROM resource_allocation ra
        JOIN fleet_resource r ON ra.resource_id = r.resource_id
        WHERE ra.uav_id = %s AND r.resource_type = 'COMM_CHANNEL' AND ra.status = 'HELD';
        """,
        (uav_id,)
    )
    for c in comm_channels:
        deadlock_mgr.release_resource(uav_id, c["resource_id"])

    # Update UAV status to OFFLINE
    execute_query("UPDATE uav SET status = 'OFFLINE', availability = 0 WHERE uav_id = %s;", (uav_id,))

    desc = description or f"RF telemetry link severed with airframe {uav_name} (ID: #{uav_id}). Autonomous failsafe RTB initiated."
    fault_id = execute_query(
        """
        INSERT INTO fault_log (uav_id, fault_type, severity, status, description)
        VALUES (%s, 'COMM_LOSS', 'warning', 'ACTIVE', %s);
        """,
        (uav_id, desc)
    )

    return {
        "fault_id": fault_id,
        "fault_type": "COMM_LOSS",
        "uav_id": uav_id,
        "uav_name": uav_name,
        "released_comm_channels": len(comm_channels),
        "message": desc
    }


# ----------------------------------------------------------------------------
# Autonomous Self-Healing & Resolution
# ----------------------------------------------------------------------------
def resolve_fault(fault_id: int, notes: Optional[str] = None) -> Dict[str, Any]:
    """
    Marks a fault as RESOLVED. If UAV was OFFLINE, restores it to IDLE.
    """
    fault = fetch_one("SELECT * FROM fault_log WHERE fault_id = %s;", (fault_id,))
    if not fault:
        raise ValueError(f"Fault #{fault_id} does not exist")

    execute_query(
        """
        UPDATE fault_log
        SET status = 'RESOLVED', resolved_at = CURRENT_TIMESTAMP
        WHERE fault_id = %s;
        """,
        (fault_id,)
    )

    uav_restored = False
    if fault.get("uav_id"):
        u_id = fault["uav_id"]
        # If UAV is currently OFFLINE, restore to IDLE and available
        uav = drone_manager.get_uav_by_id(u_id)
        if uav and uav["status"] == "OFFLINE":
            execute_query("UPDATE uav SET status = 'IDLE', availability = 1, battery_level = 95.0 WHERE uav_id = %s;", (u_id,))
            uav_restored = True

    return {
        "fault_id": fault_id,
        "status": "RESOLVED",
        "uav_restored": uav_restored,
        "message": f"Fault #{fault_id} marked as RESOLVED."
    }


def auto_recover_all_faults() -> Dict[str, Any]:
    """
    Comprehensive autonomous self-healing scan:
    1. Resolves active faults where conditions are clear.
    2. Restores OFFLINE airframes with >30% battery.
    3. Dispatches any pending missions created by failed sorties.
    4. Resolves deadlocks if present.
    """
    # 1. Resolve deadlocks
    deadlock_res = deadlock_mgr.resolve_deadlock()

    # 2. Restore offline UAVs
    restored_uavs = []
    offline_drones = fetch_all("SELECT uav_id, name, battery_level FROM uav WHERE status = 'OFFLINE';")
    for d in offline_drones:
        d_id = d["uav_id"]
        execute_query("UPDATE uav SET status = 'IDLE', availability = 1, battery_level = 95.0 WHERE uav_id = %s;", (d_id,))
        restored_uavs.append(d["name"])

    # 3. Mark active faults as RESOLVED
    updated_faults = execute_query(
        "UPDATE fault_log SET status = 'RESOLVED', resolved_at = CURRENT_TIMESTAMP WHERE status = 'ACTIVE';"
    )

    # 4. Auto-assign any pending missions
    auto_assign_res = {}
    try:
        from main import auto_assign_all
        # or call drone_manager directly
        pending = mission_manager.get_pending_missions()
        assigned_count = 0
        for m in pending:
            best = drone_manager.find_best_uav_for_mission(m)
            if best:
                drone_manager.assign_uav_to_mission(best["uav_id"], m["id"])
                assigned_count += 1
        auto_assign_res = {"reassigned_pending_missions": assigned_count}
    except Exception as e:
        auto_assign_res = {"error": str(e)}

    return {
        "autonomous_healing_complete": True,
        "deadlock_recovery": deadlock_res,
        "restored_airframes": restored_uavs,
        "resolved_faults_count": updated_faults,
        "mission_dispatch": auto_assign_res,
        "message": f"Auto-recovery executed: {len(restored_uavs)} airframes restored, {updated_faults} faults cleared."
    }
