def priority_scheduling(missions):
    current_time = 0
    remaining_missions = missions.copy()
    results = []

    while remaining_missions:
        available_missions = [
            mission for mission in remaining_missions
            if mission["arrival_time"] <= current_time
        ]

        if not available_missions:
            current_time = min(
                mission["arrival_time"] for mission in remaining_missions
            )
            continue

        selected_mission = min(
            available_missions,
            key=lambda mission: mission["priority"]
        )

        start_time = current_time
        completion_time = start_time + selected_mission["burst_time"]

        waiting_time = start_time - selected_mission["arrival_time"]
        turnaround_time = completion_time - selected_mission["arrival_time"]

        results.append({
            "id": selected_mission["id"],
            "start_time": start_time,
            "completion_time": completion_time,
            "waiting_time": waiting_time,
            "turnaround_time": turnaround_time
        })

        current_time = completion_time
        remaining_missions.remove(selected_mission)

    return results