import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from round_robin import round_robin
from metrics import calculate_metrics

missions = [
    {"id": "M1", "arrival_time": 0, "burst_time": 5},
    {"id": "M2", "arrival_time": 1, "burst_time": 3},
    {"id": "M3", "arrival_time": 2, "burst_time": 8},
    {"id": "M4", "arrival_time": 3, "burst_time": 2}
]

results, slices = round_robin(missions, quantum=2)

print("--- Round Robin (Quantum = 2) Results ---")
for result in results:
    print(result)

print("\n--- Gantt Slices ---")
for s in slices:
    print(f"[{s['start_time']} - {s['end_time']}] Mission {s['id']}")

average_wt, average_tat = calculate_metrics(results)
print("\nAverage Waiting Time:", average_wt)
print("Average Turnaround Time:", average_tat)
