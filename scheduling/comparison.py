"""
FleetOS Scheduling Comparison Engine.
Runs FCFS, SJF, Priority, Round Robin, and Adaptive algorithms
against identical workloads and calculates comparative metrics.
"""

from typing import Any, Dict, List
import sys
import os

# Ensure local imports work cleanly
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from fcfs import fcfs
from sjf import sjf
from priority import priority_scheduling
from round_robin import round_robin
from adaptive import adaptive_scheduling
from metrics import get_detailed_metrics


def compare_scheduling_algorithms(
    missions: List[Dict[str, Any]],
    quantum: int = 2,
    adaptive_mode: str = "NORMAL"
) -> Dict[str, Any]:
    """
    Executes all scheduling algorithms and produces a side-by-side comparison.
    """
    if not missions:
        return {
            "algorithms": {},
            "comparison_table": [],
            "best_algorithm_wt": None,
            "best_algorithm_tat": None
        }

    # 1. Run FCFS
    fcfs_res = fcfs(missions)
    fcfs_metrics = get_detailed_metrics(fcfs_res)

    # 2. Run SJF
    sjf_res = sjf(missions)
    sjf_metrics = get_detailed_metrics(sjf_res)

    # 3. Run Priority
    prio_res = priority_scheduling(missions)
    prio_metrics = get_detailed_metrics(prio_res)

    # 4. Run Round Robin
    rr_res, rr_slices = round_robin(missions, quantum=quantum)
    rr_metrics = get_detailed_metrics(rr_res)

    # 5. Run Adaptive
    adapt_res = adaptive_scheduling(missions, mode=adaptive_mode)
    adapt_metrics = get_detailed_metrics(adapt_res)

    algorithms_data = {
        "FCFS": {
            "schedule": fcfs_res,
            "metrics": fcfs_metrics,
            "type": "Non-preemptive First-Come First-Served"
        },
        "SJF": {
            "schedule": sjf_res,
            "metrics": sjf_metrics,
            "type": "Non-preemptive Shortest Job First"
        },
        "Priority": {
            "schedule": prio_res,
            "metrics": prio_metrics,
            "type": "Non-preemptive Priority"
        },
        "Round Robin": {
            "schedule": rr_res,
            "gantt_slices": rr_slices,
            "metrics": rr_metrics,
            "type": f"Preemptive Round Robin (q={quantum})"
        },
        "Adaptive": {
            "schedule": adapt_res,
            "metrics": adapt_metrics,
            "type": f"FleetOS Multi-factor Adaptive ({adaptive_mode})"
        }
    }

    comparison_table = [
        {
            "algorithm": name,
            "avg_waiting_time": data["metrics"]["average_waiting_time"],
            "avg_turnaround_time": data["metrics"]["average_turnaround_time"],
            "max_waiting_time": data["metrics"]["max_waiting_time"],
            "throughput": data["metrics"]["throughput"],
            "total_time": data["metrics"]["total_execution_time"]
        }
        for name, data in algorithms_data.items()
    ]

    best_wt = min(comparison_table, key=lambda row: row["avg_waiting_time"])["algorithm"]
    best_tat = min(comparison_table, key=lambda row: row["avg_turnaround_time"])["algorithm"]

    return {
        "algorithms": algorithms_data,
        "comparison_table": comparison_table,
        "best_algorithm_wt": best_wt,
        "best_algorithm_tat": best_tat
    }
