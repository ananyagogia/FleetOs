"""
Round Robin (RR) Scheduling Algorithm for FleetOS (Preemptive).
Allocates fixed time slices (time quantum) cyclically among ready missions.
"""

from collections import deque
from typing import Any, Dict, List, Tuple


def round_robin(missions: List[Dict[str, Any]], quantum: int = 2) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Executes Round Robin scheduling with time quantum.
    Returns:
      (results, gantt_slices)
      - results: list of mission completion and metrics records
      - gantt_slices: list of executed time chunks [{"id": ..., "start_time": ..., "end_time": ...}]
    """
    if not missions:
        return [], []

    if quantum <= 0:
        quantum = 2

    # Clone missions with remaining burst tracking
    pending = []
    original_info = {}
    for m in missions:
        m_id = m.get("id", m.get("mission_id"))
        arrival = m.get("arrival_time", 0)
        burst = m.get("burst_time", 1)
        item = {
            "id": m_id,
            "title": m.get("title", f"Mission-{m_id}"),
            "arrival_time": arrival,
            "burst_time": burst,
            "remaining_time": burst,
            "priority": m.get("priority", 3),
            "first_start_time": None,
            "completion_time": 0
        }
        pending.append(item)
        original_info[m_id] = item

    # Sort initially by arrival time
    pending.sort(key=lambda m: (m["arrival_time"], str(m["id"])))

    ready_queue = deque()
    gantt_slices = []
    current_time = 0
    completed_missions = []
    total_missions = len(pending)

    # Helper to push newly arrived missions into ready queue
    pending_idx = 0

    def enqueue_arrived(up_to_time: int):
        nonlocal pending_idx
        while pending_idx < len(pending) and pending[pending_idx]["arrival_time"] <= up_to_time:
            ready_queue.append(pending[pending_idx])
            pending_idx += 1

    # Start with initial arrivals
    enqueue_arrived(current_time)

    while len(completed_missions) < total_missions:
        if not ready_queue:
            # CPU is idle, advance to next mission arrival
            if pending_idx < len(pending):
                current_time = pending[pending_idx]["arrival_time"]
                enqueue_arrived(current_time)
            else:
                break

        current_mission = ready_queue.popleft()

        # Record first start time
        if current_mission["first_start_time"] is None:
            current_mission["first_start_time"] = current_time

        exec_time = min(quantum, current_mission["remaining_time"])
        start_slice = current_time
        end_slice = current_time + exec_time

        gantt_slices.append({
            "id": current_mission["id"],
            "title": current_mission["title"],
            "start_time": start_slice,
            "end_time": end_slice
        })

        current_time = end_slice
        current_mission["remaining_time"] -= exec_time

        # Check for any new missions that arrived while this slice was running
        enqueue_arrived(current_time)

        if current_mission["remaining_time"] > 0:
            # Requeue if not finished
            ready_queue.append(current_mission)
        else:
            # Mission completed
            current_mission["completion_time"] = current_time
            completed_missions.append(current_mission)

    # Compute final metrics for each mission
    results = []
    # Preserve original mission order in results
    for m in missions:
        m_id = m.get("id", m.get("mission_id"))
        item = original_info[m_id]
        arrival = item["arrival_time"]
        burst = item["burst_time"]
        comp = item["completion_time"]
        tat = comp - arrival
        wt = tat - burst

        results.append({
            "id": m_id,
            "title": item["title"],
            "arrival_time": arrival,
            "burst_time": burst,
            "priority": item["priority"],
            "start_time": item["first_start_time"] if item["first_start_time"] is not None else arrival,
            "completion_time": comp,
            "waiting_time": max(0, wt),
            "turnaround_time": tat
        })

    return results, gantt_slices
