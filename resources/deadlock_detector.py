"""
FleetOS Deadlock Detection & Recovery Engine.
Implements:
1. Resource Allocation Graph (RAG) and Wait-For Graph (WFG) representation.
2. Depth-First Search (DFS) cycle detection for circular wait conditions.
3. Autonomous Deadlock Recovery via victim selection, preemption, resource reclaim, and mission re-queuing.
4. Database persistence and event logging.
"""

import sys
import os
import logging
from typing import Dict, List, Set, Tuple, Optional, Any

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_DIR = os.path.join(BASE_DIR, "database")
if DB_DIR not in sys.path:
    sys.path.append(DB_DIR)

from db_connection import execute_query, fetch_all, fetch_one

logger = logging.getLogger("fleetos.deadlock")


class ResourceAllocationGraph:
    """
    Bipartite Resource Allocation Graph (RAG) and projected Wait-For Graph (WFG).
    
    Nodes:
    - UAV Tasks: U1, U2, ...
    - Fleet Resources: R1, R2, ...
    
    Edges:
    - Assignment edge: R -> U (Resource is held by UAV)
    - Request edge: U -> R (UAV is waiting for Resource)
    - WFG Edge: U_wait -> U_hold (Derived from U_wait -> R -> U_hold)
    """

    def __init__(self):
        # resource_id -> list of holding uav_ids
        self.allocations: Dict[str, List[str]] = {}
        # uav_id -> list of requested resource_ids
        self.requests: Dict[str, List[str]] = {}

    def clear(self):
        """Reset in-memory graph."""
        self.allocations.clear()
        self.requests.clear()

    def allocate(self, uav_id: str, resource_id: str):
        """Record resource allocation (R -> U)."""
        u_str = str(uav_id)
        r_str = str(resource_id)
        if r_str not in self.allocations:
            self.allocations[r_str] = []
        if u_str not in self.allocations[r_str]:
            self.allocations[r_str].append(u_str)

        # Remove from pending requests if it was waiting
        if u_str in self.requests and r_str in self.requests[u_str]:
            self.requests[u_str].remove(r_str)

    def request(self, uav_id: str, resource_id: str):
        """Record resource request edge (U -> R)."""
        u_str = str(uav_id)
        r_str = str(resource_id)
        if u_str not in self.requests:
            self.requests[u_str] = []
        if r_str not in self.requests[u_str]:
            self.requests[u_str].append(r_str)

    def release(self, uav_id: str, resource_id: str):
        """Release allocation edge."""
        u_str = str(uav_id)
        r_str = str(resource_id)
        if r_str in self.allocations and u_str in self.allocations[r_str]:
            self.allocations[r_str].remove(u_str)
            if not self.allocations[r_str]:
                del self.allocations[r_str]

    def build_wait_for_graph(self) -> Dict[str, Set[str]]:
        """
        Derives Wait-For Graph (WFG) from RAG:
        If UAV U_a requests resource R, and resource R is held by UAV U_b,
        then directed edge U_a -> U_b exists in WFG.
        """
        wfg: Dict[str, Set[str]] = {}

        # Ensure all known UAVs have an entry
        all_uavs = set()
        for r_holders in self.allocations.values():
            all_uavs.update(r_holders)
        all_uavs.update(self.requests.keys())

        for u in all_uavs:
            wfg[u] = set()

        for uav_waiting, req_resources in self.requests.items():
            for res in req_resources:
                holders = self.allocations.get(res, [])
                for uav_holding in holders:
                    if uav_waiting != uav_holding:
                        wfg[uav_waiting].add(uav_holding)

        return wfg

    def detect_cycles(self) -> List[Dict[str, Any]]:
        """
        Performs DFS on the Wait-For Graph to detect all directed cycles.
        Returns list of cycle details including cycle path and contested resources.
        """
        wfg = self.build_wait_for_graph()
        visited = set()
        rec_stack = set()
        cycles_found = []

        def dfs(node: str, path: List[str]):
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbor in sorted(list(wfg.get(node, set()))):
                if neighbor not in visited:
                    dfs(neighbor, path)
                elif neighbor in rec_stack:
                    # Circular wait cycle detected
                    idx = path.index(neighbor)
                    cycle_nodes = path[idx:] + [neighbor]

                    # Identify resources contested in this cycle
                    contested = []
                    for i in range(len(cycle_nodes) - 1):
                        u_wait = cycle_nodes[i]
                        u_hold = cycle_nodes[i + 1]
                        # Find which resource u_wait requested that u_hold has
                        for req_r in self.requests.get(u_wait, []):
                            if u_hold in self.allocations.get(req_r, []):
                                contested.append({
                                    "waiting_uav": u_wait,
                                    "holding_uav": u_hold,
                                    "resource": req_r
                                })

                    cycles_found.append({
                        "cycle": cycle_nodes,
                        "cycle_path": " -> ".join(cycle_nodes),
                        "contested_resources": contested
                    })

            path.pop()
            rec_stack.remove(node)

        for n in sorted(list(wfg.keys())):
            if n not in visited:
                dfs(n, [])

        return cycles_found


class DeadlockManager:
    """
    High-level manager orchestrating resource allocation,
    deadlock detection, cycle resolution, and database persistence.
    """

    def __init__(self):
        self.rag = ResourceAllocationGraph()
        self.load_from_database()

    def load_from_database(self):
        """Loads active allocations and pending requests from DB."""
        self.rag.clear()
        try:
            allocs = fetch_all(
                """
                SELECT ra.resource_id, ra.uav_id, ra.status, r.name AS resource_name, u.name AS uav_name
                FROM resource_allocation ra
                JOIN fleet_resource r ON ra.resource_id = r.resource_id
                JOIN uav u ON ra.uav_id = u.uav_id
                WHERE ra.status IN ('HELD', 'WAITING');
                """
            )
            for row in allocs:
                u_id = f"UAV-{row['uav_id']}"
                r_id = f"RES-{row['resource_id']}"
                if row["status"] == "HELD":
                    self.rag.allocate(u_id, r_id)
                elif row["status"] == "WAITING":
                    self.rag.request(u_id, r_id)
        except Exception as exc:
            logger.warning("Could not sync RAG from database: %s", exc)

    def request_resource(self, uav_id: int, resource_id: int) -> Dict[str, Any]:
        """
        UAV requests a shared resource.
        If resource is available, allocates it immediately.
        If unavailable, queues request and checks for deadlock.
        """
        u_str = f"UAV-{uav_id}"
        r_str = f"RES-{resource_id}"

        res = fetch_one("SELECT * FROM fleet_resource WHERE resource_id = %s;", (resource_id,))
        if not res:
            raise ValueError(f"Resource #{resource_id} not found")

        avail = int(res["available_count"])
        if avail > 0:
            # Grant resource
            execute_query(
                "UPDATE fleet_resource SET available_count = available_count - 1 WHERE resource_id = %s;",
                (resource_id,)
            )
            execute_query(
                """
                INSERT INTO resource_allocation (resource_id, uav_id, status, allocated_at)
                VALUES (%s, %s, 'HELD', CURRENT_TIMESTAMP);
                """,
                (resource_id, uav_id)
            )
            self.rag.allocate(u_str, r_str)
            logger.info("Granted %s to UAV #%s", res["name"], uav_id)
            return {
                "status": "ALLOCATED",
                "uav_id": uav_id,
                "resource_id": resource_id,
                "resource_name": res["name"],
                "message": f"Resource '{res['name']}' granted to UAV #{uav_id}"
            }
        else:
            # Resource exhausted: queue wait request
            execute_query(
                """
                INSERT INTO resource_allocation (resource_id, uav_id, status, requested_at)
                VALUES (%s, %s, 'WAITING', CURRENT_TIMESTAMP);
                """,
                (resource_id, uav_id)
            )
            self.rag.request(u_str, r_str)
            logger.warning("UAV #%s waiting for %s (currently occupied)", uav_id, res["name"])

            # Check if this request caused a circular wait
            cycles = self.rag.detect_cycles()
            if cycles:
                logger.error("DEADLOCK DETECTED! Cycle: %s", cycles[0]["cycle_path"])

            return {
                "status": "WAITING",
                "uav_id": uav_id,
                "resource_id": resource_id,
                "resource_name": res["name"],
                "deadlock_risk": len(cycles) > 0,
                "cycles": cycles,
                "message": f"Resource '{res['name']}' occupied. UAV #{uav_id} added to wait queue."
            }

    def release_resource(self, uav_id: int, resource_id: int) -> bool:
        """
        Releases an allocated resource held by a UAV.
        Transfers it to any waiting UAV if present.
        """
        u_str = f"UAV-{uav_id}"
        r_str = f"RES-{resource_id}"

        # Update allocation table
        execute_query(
            """
            UPDATE resource_allocation
            SET status = 'RELEASED', released_at = CURRENT_TIMESTAMP
            WHERE uav_id = %s AND resource_id = %s AND status = 'HELD';
            """,
            (uav_id, resource_id)
        )
        self.rag.release(u_str, r_str)

        # Check if another UAV is waiting for this resource
        waiter = fetch_one(
            """
            SELECT allocation_id, uav_id FROM resource_allocation
            WHERE resource_id = %s AND status = 'WAITING'
            ORDER BY requested_at ASC
            LIMIT 1;
            """,
            (resource_id,)
        )

        if waiter:
            # Transfer directly to waiter without changing available_count
            w_uav_id = waiter["uav_id"]
            execute_query(
                """
                UPDATE resource_allocation
                SET status = 'HELD', allocated_at = CURRENT_TIMESTAMP
                WHERE allocation_id = %s;
                """,
                (waiter["allocation_id"],)
            )
            self.rag.allocate(f"UAV-{w_uav_id}", r_str)
            logger.info("Transferred released resource #%s to waiting UAV #%s", resource_id, w_uav_id)
        else:
            # Return to available capacity
            res = fetch_one("SELECT total_capacity, available_count FROM fleet_resource WHERE resource_id = %s;", (resource_id,))
            if res:
                new_avail = min(res["total_capacity"], res["available_count"] + 1)
                execute_query("UPDATE fleet_resource SET available_count = %s WHERE resource_id = %s;", (new_avail, resource_id))

        return True

    def detect_deadlock(self) -> Dict[str, Any]:
        """Runs cycle detection on current state."""
        self.load_from_database()
        cycles = self.rag.detect_cycles()
        wfg = self.rag.build_wait_for_graph()

        # Format WFG for API presentation
        wfg_formatted = {k: list(v) for k, v in wfg.items()}

        return {
            "deadlock_detected": len(cycles) > 0,
            "cycle_count": len(cycles),
            "cycles": cycles,
            "wait_for_graph": wfg_formatted,
            "allocations": self.rag.allocations,
            "requests": self.rag.requests
        }

    def resolve_deadlock(self) -> Dict[str, Any]:
        """
        Autonomous Deadlock Recovery Mechanism:
        1. Identifies cycle.
        2. Evaluates tasks involved and selects lowest priority victim task.
        3. Preempts victim: releases its resources, reclaims them, rolls back mission to PENDING.
        4. Fulfills blocked waiter.
        5. Logs detection and resolution in fault_log.
        """
        detection = self.detect_deadlock()
        if not detection["deadlock_detected"]:
            return {
                "message": "No deadlock cycle currently detected. Fleet state is nominal.",
                "resolved": False
            }

        primary_cycle = detection["cycles"][0]
        cycle_uav_ids = [n.replace("UAV-", "") for n in primary_cycle["cycle"][:-1] if n.startswith("UAV-")]

        # Victim selection: Find UAV running lowest priority mission (highest priority number)
        victim_uav_id = None
        victim_mission = None
        max_priority_num = -1

        for u_id in cycle_uav_ids:
            try:
                numeric_id = int(u_id)
                # Find active assignment for this UAV
                assign = fetch_one(
                    """
                    SELECT a.assignment_id, a.mission_id, m.title, m.priority
                    FROM assignment a
                    JOIN mission m ON a.mission_id = m.mission_id
                    WHERE a.uav_id = %s AND a.status = 'ACTIVE'
                    LIMIT 1;
                    """,
                    (numeric_id,)
                )
                if assign and assign["priority"] > max_priority_num:
                    max_priority_num = assign["priority"]
                    victim_uav_id = numeric_id
                    victim_mission = assign
            except Exception:
                pass

        # Fallback to last node in cycle if no mission found
        if not victim_uav_id and cycle_uav_ids:
            victim_uav_id = int(cycle_uav_ids[-1])

        # Execute preemption on victim
        victim_callsign = f"UAV-{victim_uav_id}"
        uav_record = fetch_one("SELECT name FROM uav WHERE uav_id = %s;", (victim_uav_id,))
        if uav_record:
            victim_callsign = uav_record["name"]

        # 1. Release all resources held by victim
        held_resources = fetch_all(
            "SELECT resource_id FROM resource_allocation WHERE uav_id = %s AND status = 'HELD';",
            (victim_uav_id,)
        )
        released_resource_ids = []
        for r_row in held_resources:
            r_id = r_row["resource_id"]
            self.release_resource(victim_uav_id, r_id)
            released_resource_ids.append(r_id)

        # 2. Cancel/clean any WAITING requests of victim
        execute_query(
            "UPDATE resource_allocation SET status = 'RELEASED' WHERE uav_id = %s AND status = 'WAITING';",
            (victim_uav_id,)
        )

        # 3. If victim had an active mission, roll it back to PENDING queue
        if victim_mission:
            execute_query("UPDATE assignment SET status = 'REASSIGNED' WHERE assignment_id = %s;", (victim_mission["assignment_id"],))
            execute_query("UPDATE mission SET status = 'PENDING' WHERE mission_id = %s;", (victim_mission["mission_id"],))
            execute_query(
                """
                INSERT INTO mission_log (mission_id, uav_id, event, status)
                VALUES (%s, %s, 'Preempted due to deadlock resolution; re-queued to PENDING', 'PENDING');
                """,
                (victim_mission["mission_id"], victim_uav_id)
            )

        # 4. Set victim UAV status back to IDLE
        execute_query("UPDATE uav SET status = 'IDLE', availability = 1 WHERE uav_id = %s;", (victim_uav_id,))

        # 5. Log incident and resolution in fault_log
        desc = (
            f"Autonomous deadlock resolution triggered. Circular wait detected: {primary_cycle['cycle_path']}. "
            f"Victim airframe '{victim_callsign}' (UAV #{victim_uav_id}) preempted. "
            f"{len(released_resource_ids)} resources reclaimed. Contested task re-queued for dispatch."
        )
        execute_query(
            """
            INSERT INTO fault_log (uav_id, fault_type, severity, status, description, resolved_at)
            VALUES (%s, 'DEADLOCK_DETECTED', 'critical', 'RESOLVED', %s, CURRENT_TIMESTAMP);
            """,
            (victim_uav_id, desc)
        )

        # Reload graph state
        self.load_from_database()

        return {
            "resolved": True,
            "cycle_broken": primary_cycle["cycle_path"],
            "victim_preempted": {
                "uav_id": victim_uav_id,
                "callsign": victim_callsign,
                "requeued_mission": victim_mission["title"] if victim_mission else None
            },
            "reclaimed_resources": released_resource_ids,
            "resolution_summary": desc
        }

    def simulate_deadlock_scenario(self) -> Dict[str, Any]:
        """
        Creates a classic circular wait scenario for testing and UI demonstration:
        1. Ensures 2 resources (Pad Alpha and Comm Band High) exist.
        2. Sets their capacity to occupied/1.
        3. Assigns Resource 1 to UAV A; UAV A requests Resource 2.
        4. Assigns Resource 2 to UAV B; UAV B requests Resource 1.
        5. Verifies deadlock cycle is detected.
        """
        uavs = fetch_all("SELECT uav_id, name FROM uav ORDER BY uav_id ASC LIMIT 2;")
        if len(uavs) < 2:
            return {"error": "Need at least 2 UAVs to simulate deadlock"}

        resources = fetch_all("SELECT resource_id, name FROM fleet_resource ORDER BY resource_id ASC LIMIT 2;")
        if len(resources) < 2:
            return {"error": "Need at least 2 resources to simulate deadlock"}

        uav_a, uav_b = uavs[0], uavs[1]
        res_1, res_2 = resources[0], resources[1]

        # Reset any prior allocations for these two UAVs
        execute_query("DELETE FROM resource_allocation WHERE uav_id IN (%s, %s);", (uav_a["uav_id"], uav_b["uav_id"]))

        # Force available_count = 0 to simulate full utilization
        execute_query("UPDATE fleet_resource SET available_count = 0 WHERE resource_id IN (%s, %s);", (res_1["resource_id"], res_2["resource_id"]))

        # UAV A holds Res 1
        execute_query(
            "INSERT INTO resource_allocation (resource_id, uav_id, status, allocated_at) VALUES (%s, %s, 'HELD', CURRENT_TIMESTAMP);",
            (res_1["resource_id"], uav_a["uav_id"])
        )
        # UAV B holds Res 2
        execute_query(
            "INSERT INTO resource_allocation (resource_id, uav_id, status, allocated_at) VALUES (%s, %s, 'HELD', CURRENT_TIMESTAMP);",
            (res_2["resource_id"], uav_b["uav_id"])
        )

        # UAV A requests Res 2 (held by B)
        execute_query(
            "INSERT INTO resource_allocation (resource_id, uav_id, status, requested_at) VALUES (%s, %s, 'WAITING', CURRENT_TIMESTAMP);",
            (res_2["resource_id"], uav_a["uav_id"])
        )
        # UAV B requests Res 1 (held by A) -> Circular Wait!
        execute_query(
            "INSERT INTO resource_allocation (resource_id, uav_id, status, requested_at) VALUES (%s, %s, 'WAITING', CURRENT_TIMESTAMP);",
            (res_1["resource_id"], uav_b["uav_id"])
        )

        # Sync RAG and detect
        self.load_from_database()
        detection = self.detect_deadlock()

        # Log warning in fault_log
        desc = (
            f"Simulated circular wait condition active: UAV #{uav_a['uav_id']} ({uav_a['name']}) "
            f"holding '{res_1['name']}' requests '{res_2['name']}'. "
            f"UAV #{uav_b['uav_id']} ({uav_b['name']}) holding '{res_2['name']}' requests '{res_1['name']}."
        )
        execute_query(
            """
            INSERT INTO fault_log (uav_id, fault_type, severity, status, description)
            VALUES (%s, 'DEADLOCK_DETECTED', 'critical', 'ACTIVE', %s);
            """,
            (uav_a["uav_id"], desc)
        )

        return {
            "simulation_success": True,
            "uav_a": uav_a,
            "uav_b": uav_b,
            "resource_1": res_1,
            "resource_2": res_2,
            "deadlock_present": detection["deadlock_detected"],
            "cycles": detection["cycles"],
            "message": "Deadlock condition successfully simulated between UAV-A and UAV-B."
        }


# Singleton instance for system-wide deadlock management
deadlock_mgr = DeadlockManager()
