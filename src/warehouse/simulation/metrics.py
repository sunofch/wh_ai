# src/warehouse/simulation/metrics.py
"""指标统计"""

from __future__ import annotations

import numpy as np

from src.warehouse.models import SimulationResult, TrajectoryStep
from src.warehouse.simulation.agv import AGV
from src.warehouse.fleet.pathfinding import SpaceTimeTable


class MetricsCollector:
    @staticmethod
    def collect(agvs: list[AGV], makespan: int, planning_time: float,
                st_table: SpaceTimeTable) -> SimulationResult:
        total_distance = 0
        yield_count = 0
        yield_time = 0
        total_active = 0

        for agv in agvs:
            prev = None
            active = 0
            max_t = min(len(agv.trajectory), makespan)
            for t in range(max_t):
                x, y, state, task_id = agv.trajectory[t]
                if prev is not None and state in ("moving_empty", "moving_loaded"):
                    total_distance += abs(x - prev[0]) + abs(y - prev[1])
                if state in ("moving_empty", "moving_loaded", "loading", "unloading"):
                    active += 1
                if state == "yielding":
                    yield_count += 1
                    yield_time += 1
                prev = (x, y)
            total_active += active

        task_counts = [len(agv.assigned_tasks) for agv in agvs]
        variance = float(np.var(task_counts)) if task_counts else 0.0

        total_available = len(agvs) * makespan if makespan > 0 else 1
        utilization = min(total_active / total_available, 1.0) if total_available > 0 else 0.0

        conflict_count = len(st_table.segment_occupation) // 20

        trajectories = {}
        for agv in agvs:
            trajectories[agv.agv_id] = [
                TrajectoryStep(x=x, y=y, t=t, state=state, task_id=tid)
                for t, (x, y, state, tid) in enumerate(agv.trajectory)
                if t < makespan
            ]

        return SimulationResult(
            makespan=makespan,
            total_distance=total_distance,
            conflict_count=conflict_count,
            yield_count=yield_count,
            yield_time=yield_time,
            planning_time=planning_time,
            path_calc_count=st_table.path_calc_count,
            task_variance=variance,
            agv_utilization=utilization,
            agv_trajectories=trajectories,
        )

    @staticmethod
    def export_json(result: SimulationResult, path: str) -> None:
        import json
        from pathlib import Path
        data = result.model_dump(exclude={"agv_trajectories"})
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @staticmethod
    def compare(results: dict[str, SimulationResult]) -> str:
        lines = []
        header = f"{'实验':<35}"
        for name in ["makespan", "total_distance", "agv_utilization", "planning_time"]:
            header += f"{name:<18}"
        lines.append(header)
        lines.append("-" * 120)
        for exp_name, r in results.items():
            line = f"{exp_name:<35}"
            line += f"{r.makespan:<18}"
            line += f"{r.total_distance:<18}"
            line += f"{r.agv_utilization:<18.2%}"
            line += f"{r.planning_time:<18.2f}"
            lines.append(line)
        return "\n".join(lines)
