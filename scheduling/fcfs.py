"""
First-Come, First-Served (FCFS) Scheduling Algorithm for FleetOS.
Missions are scheduled in the order they arrive.
"""

from typing import Any, Dict, List


def fcfs(missions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Executes FCFS scheduling on a list of missions.
    Each mission is expected to have:
      - 'id' (or 'mission_id')
      - 'burst_time' (duration)
      - 'arrival_time' (optional, defaults to 0)
    """
    if not missions:
        return []

    # Sort missions by arrival time to ensure FCFS invariant
    sorted_missions = sorted(
        missions,
        key=lambda m: (m.get("arrival_time", 0), m.get("id", m.get("mission_id", 0)))
    )

    current_time = 0
    results = []

    for mission in sorted_missions:
        m_id = mission.get("id", mission.get("mission_id"))
        arrival_time = mission.get("arrival_time", 0)
        burst_time = mission.get("burst_time", 1)

        # Handle CPU/Scheduler idle time
        if current_time < arrival_time:
            current_time = arrival_time

        start_time = current_time
        completion_time = start_time + burst_time
        waiting_time = start_time - arrival_time
        turnaround_time = completion_time - arrival_time

        record = {
            "id": m_id,
            "title": mission.get("title", f"Mission-{m_id}"),
            "arrival_time": arrival_time,
            "burst_time": burst_time,
            "priority": mission.get("priority", 3),
            "start_time": start_time,
            "completion_time": completion_time,
            "waiting_time": waiting_time,
            "turnaround_time": turnaround_time
        }
        results.append(record)
        current_time = completion_time

    return results