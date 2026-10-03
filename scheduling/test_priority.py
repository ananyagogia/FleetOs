from priority import priority_scheduling
from metrics import calculate_metrics

missions = [
    {"id": "M1", "arrival_time": 0, "burst_time": 5, "priority": 2},
    {"id": "M2", "arrival_time": 1, "burst_time": 3, "priority": 1},
    {"id": "M3", "arrival_time": 2, "burst_time": 8, "priority": 4},
    {"id": "M4", "arrival_time": 3, "burst_time": 2, "priority": 3}
]

results = priority_scheduling(missions)

for result in results:
    print(result)

average_wt, average_tat = calculate_metrics(results)

print("Average Waiting Time:", average_wt)
print("Average Turnaround Time:", average_tat)