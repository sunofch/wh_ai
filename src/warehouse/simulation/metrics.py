# src/warehouse/simulation/metrics.py
"""指标统计与对比表输出

从AGV轨迹中计算: makespan(最大完成时间)、总移动距离、AGV利用率、任务数方差。
compare()方法生成动态列宽的对比表, 适配不同长度的实验名和数值。
"""

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
        total_active = 0

        for agv in agvs:
            prev = None
            active = 0
            max_t = min(len(agv.trajectory), makespan)
            for t in range(max_t):
                x, y, state, task_id = agv.trajectory[t]
                if prev is not None and (x, y) != prev:
                    total_distance += abs(x - prev[0]) + abs(y - prev[1])
                if state in ("moving_empty", "moving_loaded", "loading", "unloading"):
                    active += 1
                prev = (x, y)
            total_active += active

        task_counts = [len(agv.assigned_tasks) for agv in agvs]
        variance = float(np.var(task_counts)) if task_counts else 0.0

        total_available = len(agvs) * makespan if makespan > 0 else 1
        utilization = min(total_active / total_available, 1.0) if total_available > 0 else 0.0

        trajectories = {}
        for agv in agvs:
            trajectories[agv.agv_id] = [
                TrajectoryStep(x=x, y=y, t=t, state=state, task_id=tid)
                for t, (x, y, state, tid) in enumerate(agv.trajectory)
                if t < makespan
            ]

        conflict_count = 0
        for t in range(makespan):
            positions: dict[tuple[int, int], list[int]] = {}
            for agv in agvs:
                if t < len(agv.trajectory):
                    x, y, _, _ = agv.trajectory[t]
                    positions.setdefault((x, y), []).append(agv.agv_id)
            for ids in positions.values():
                if len(ids) > 1:
                    conflict_count += 1

        return SimulationResult(
            makespan=makespan,
            total_distance=total_distance,
            planning_time=planning_time,
            path_calc_count=st_table.path_calc_count,
            task_variance=variance,
            agv_utilization=utilization,
            conflict_count=conflict_count,
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
        items = list(results.items())
        if not items:
            return ""

        w_name = max(max(len(n) for n in results.keys()), 4)
        w_ms = max(len(str(r.makespan)) for _, r in items)
        w_dist = max(len(str(r.total_distance)) for _, r in items)
        w_util = max(len(f"{r.agv_utilization:.2%}") for _, r in items)
        w_time = max(len(f"{r.planning_time:.2f}s") for _, r in items)

        hdr_ms = max(w_ms, len("makespan"))
        hdr_dist = max(w_dist, len("total_distance"))
        hdr_util = max(w_util, len("agv_utilization"))
        hdr_time = max(w_time, len("planning_time"))

        c_ms = max(hdr_ms, w_ms)
        c_dist = max(hdr_dist, w_dist)
        c_util = max(hdr_util, w_util)
        c_time = max(hdr_time, w_time)

        sep_len = 2 + w_name + 3 + c_ms + 3 + c_dist + 3 + c_util + 3 + c_time
        sep = "═" * sep_len

        lines = [""]
        lines.append(f"  {sep}")
        lines.append(f"  {'实验':<{w_name}}   {'makespan':>{c_ms}}   {'total_distance':>{c_dist}}   {'agv_utilization':>{c_util}}   {'planning_time':>{c_time}}")
        lines.append(f"  {'─' * sep_len}")
        for name, r in items:
            util_s = f"{r.agv_utilization:.2%}"
            time_s = f"{r.planning_time:.2f}s"
            lines.append(
                f"  {name:<{w_name}}   {r.makespan:>{c_ms}}   {r.total_distance:>{c_dist}}   {util_s:>{c_util}}   {time_s:>{c_time}}"
            )
        lines.append(f"  {sep}")
        return "\n".join(lines)
