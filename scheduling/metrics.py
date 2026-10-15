"""
Performance Metrics Calculator for FleetOS Schedulers.
Computes Average Waiting Time (AWT), Average Turnaround Time (ATAT), and throughput.
"""

from typing import Any, Dict, List, Tuple


def calculate_metrics(results: List[Dict[str, Any]]) -> Tuple[float, float]:
    """
    Returns (average_waiting_time, average_turnaround_time) for backward compatibility.
    """
    if not results:
        return 0.0, 0.0

    total_waiting_time = sum(r.get("waiting_time", 0) for r in results)
    total_turnaround_time = sum(r.get("turnaround_time", 0) for r in results)
    n = len(results)

    return round(total_waiting_time / n, 2), round(total_turnaround_time / n, 2)


def get_detailed_metrics(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Returns full detailed performance metrics dictionary.
    """
    if not results:
        return {
            "total_missions": 0,
            "average_waiting_time": 0.0,
            "average_turnaround_time": 0.0,
            "max_waiting_time": 0,
            "max_turnaround_time": 0,
            "total_execution_time": 0,
            "throughput": 0.0
        }

    n = len(results)
    avg_wt, avg_tat = calculate_metrics(results)
    max_wt = max(r.get("waiting_time", 0) for r in results)
    max_tat = max(r.get("turnaround_time", 0) for r in results)
    total_time = max(r.get("completion_time", 0) for r in results)
    throughput = round(n / total_time, 4) if total_time > 0 else float(n)

    return {
        "total_missions": n,
        "average_waiting_time": avg_wt,
        "average_turnaround_time": avg_tat,
        "max_waiting_time": max_wt,
        "max_turnaround_time": max_tat,
        "total_execution_time": total_time,
        "throughput": throughput
    }