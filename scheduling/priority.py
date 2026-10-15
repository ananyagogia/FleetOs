"""
Priority Scheduling Algorithm for FleetOS (Non-preemptive).
Selects the arrived mission with highest priority (lower numerical value = higher priority, e.g., 1 is Emergency).
"""

from typing import Any, Dict, List


def priority_scheduling(missions: List[Dict[str, Any]], lower_is_higher: bool = True) -> List[Dict[str, Any]]:
    """
    Executes Priority scheduling on a list of missions.
    Each mission is expected to have:
      - 'id' (or 'mission_id')
      - 'burst_time' (duration)
      - 'priority' (integer, 1=Emergency/Highest)
      - 'arrival_time' (optional, defaults to 0)
    """
    if not missions:
        return []

    current_time = 0
    remaining_missions = [dict(m) for m in missions]
    results = []

    while remaining_missions:
        available_missions = [
            m for m in remaining_missions
            if m.get("arrival_time", 0) <= current_time
        ]

        if not available_missions:
            current_time = min(m.get("arrival_time", 0) for m in remaining_missions)
            continue

        # Select mission with highest priority
        if lower_is_higher:
            selected = min(
                available_missions,
                key=lambda m: (
                    m.get("priority", 3),
                    m.get("arrival_time", 0),
                    str(m.get("id", m.get("mission_id", 0)))
                )
            )
        else:
            selected = max(
                available_missions,
                key=lambda m: (
                    m.get("priority", 3),
                    -m.get("arrival_time", 0)
                )
            )

        m_id = selected.get("id", selected.get("mission_id"))
        arrival_time = selected.get("arrival_time", 0)
        burst_time = selected.get("burst_time", 1)

        start_time = current_time
        completion_time = start_time + burst_time
        waiting_time = start_time - arrival_time
        turnaround_time = completion_time - arrival_time

        results.append({
            "id": m_id,
            "title": selected.get("title", f"Mission-{m_id}"),
            "arrival_time": arrival_time,
            "burst_time": burst_time,
            "priority": selected.get("priority", 3),
            "start_time": start_time,
            "completion_time": completion_time,
            "waiting_time": waiting_time,
            "turnaround_time": turnaround_time
        })

        current_time = completion_time
        remaining_missions.remove(selected)

    return results