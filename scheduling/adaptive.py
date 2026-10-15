"""
FleetOS Adaptive Scheduler (Proposed Novel Contribution).
Dynamically adjusts weights based on mission urgency, priority, burst duration,
and system condition (e.g., NORMAL, EMERGENCY, CONSERVATION).
"""

from typing import Any, Dict, List


def adaptive_scheduling(
    missions: List[Dict[str, Any]],
    mode: str = "NORMAL"
) -> List[Dict[str, Any]]:
    """
    Executes Adaptive Scheduling on missions.
    Modes:
      - 'NORMAL': Balanced weighting between priority, burst efficiency, and urgency.
      - 'EMERGENCY': High urgency and priority weighting (rapid response to critical threats).
      - 'CONSERVATION': High penalty on long burst durations to preserve drone fleet battery.
    """
    if not missions:
        return []

    # Define weight vectors according to operating condition
    if mode.upper() == "EMERGENCY":
        w_priority = 0.50
        w_urgency = 0.35
        w_burst = 0.15
    elif mode.upper() == "CONSERVATION":
        w_priority = 0.30
        w_urgency = 0.20
        w_burst = 0.50
    else:  # NORMAL
        w_priority = 0.40
        w_urgency = 0.30
        w_burst = 0.30

    current_time = 0
    remaining_missions = [dict(m) for m in missions]
    results = []

    while remaining_missions:
        available = [
            m for m in remaining_missions
            if m.get("arrival_time", 0) <= current_time
        ]

        if not available:
            current_time = min(m.get("arrival_time", 0) for m in remaining_missions)
            continue

        # Score all available missions
        def compute_score(m: Dict[str, Any]) -> float:
            priority = m.get("priority", 3)
            # Higher score for higher priority (priority 1 -> 5, priority 5 -> 1)
            p_score = (6 - max(1, min(5, priority))) / 5.0

            # Urgency based on deadline proximity
            deadline = m.get("deadline", 60)
            time_left = max(1, deadline - current_time)
            u_score = 1.0 / (1.0 + (time_left / 20.0))

            # Burst efficiency (shorter burst -> higher efficiency)
            burst = max(1, m.get("burst_time", 1))
            b_score = 1.0 / (1.0 + (burst / 10.0))

            return (w_priority * p_score) + (w_urgency * u_score) + (w_burst * b_score)

        # Select highest composite score
        selected = max(
            available,
            key=lambda m: (compute_score(m), -m.get("arrival_time", 0))
        )

        m_id = selected.get("id", selected.get("mission_id"))
        arrival_time = selected.get("arrival_time", 0)
        burst_time = selected.get("burst_time", 1)

        start_time = current_time
        completion_time = start_time + burst_time
        waiting_time = start_time - arrival_time
        turnaround_time = completion_time - arrival_time
        calculated_score = round(compute_score(selected), 3)

        results.append({
            "id": m_id,
            "title": selected.get("title", f"Mission-{m_id}"),
            "arrival_time": arrival_time,
            "burst_time": burst_time,
            "priority": selected.get("priority", 3),
            "adaptive_score": calculated_score,
            "mode": mode,
            "start_time": start_time,
            "completion_time": completion_time,
            "waiting_time": waiting_time,
            "turnaround_time": turnaround_time
        })

        current_time = completion_time
        remaining_missions.remove(selected)

    return results
