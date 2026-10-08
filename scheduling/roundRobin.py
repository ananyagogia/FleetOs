def round_robin(missions, time_quantum):
    current_time = 0
    remaining_missions = missions.copy()
    remaining_burst = {
        mission["id"]: mission["burst_time"]
        for mission in missions
    }

    results = []

    while remaining_missions:
        executed = False

        for mission in remaining_missions.copy():
            if mission["arrival_time"] <= current_time:
                executed = True

                mission_id = mission["id"]
                burst_left = remaining_burst[mission_id]

                execution_time = min(time_quantum, burst_left)

                current_time += execution_time
                remaining_burst[mission_id] -= execution_time

                if remaining_burst[mission_id] == 0:
                    completion_time = current_time
                    turnaround_time = (
                        completion_time - mission["arrival_time"]
                    )

                    waiting_time = (
                        turnaround_time - mission["burst_time"]
                    )

                    results.append({
                        "id": mission_id,
                        "completion_time": completion_time,
                        "waiting_time": waiting_time,
                        "turnaround_time": turnaround_time
                    })

                    remaining_missions.remove(mission)

        if not executed:
            current_time = min(
                mission["arrival_time"]
                for mission in remaining_missions
            )

    return results