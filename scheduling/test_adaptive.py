import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from adaptive import adaptive_scheduling
from metrics import calculate_metrics

missions = [
    {"id": "M1", "arrival_time": 0, "burst_time": 5, "priority": 2, "deadline": 20},
    {"id": "M2", "arrival_time": 1, "burst_time": 3, "priority": 1, "deadline": 10},
    {"id": "M3", "arrival_time": 2, "burst_time": 8, "priority": 4, "deadline": 45},
    {"id": "M4", "arrival_time": 3, "burst_time": 2, "priority": 3, "deadline": 15}
]

print("--- Adaptive Scheduling (NORMAL Mode) ---")
results = adaptive_scheduling(missions, mode="NORMAL")
for result in results:
    print(result)

average_wt, average_tat = calculate_metrics(results)
print("Average Waiting Time:", average_wt)
print("Average Turnaround Time:", average_tat)

print("\n--- Adaptive Scheduling (EMERGENCY Mode) ---")
emerg_results = adaptive_scheduling(missions, mode="EMERGENCY")
for result in emerg_results:
    print(result)
