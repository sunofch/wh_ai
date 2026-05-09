# src/warehouse/simulation/agv.py
"""AGV状态机 + 轨迹记录"""

from __future__ import annotations
from src.warehouse.models import AGVStatus, TransportTask


class AGV:
    def __init__(self, agv_id: int, init_pos: tuple[int, int], max_steps: int = 15000):
        self.agv_id = agv_id
        self.init_pos = init_pos
        self.current_pos = init_pos
        self.battery = 100
        self.status = AGVStatus.IDLE
        self.assigned_tasks: list[TransportTask] = []
        self.completed_count = 0
        self.total_time: int = 0
        self.trajectory: list[tuple[int, int, str, int]] = [
            (init_pos[0], init_pos[1], "idle", -1) for _ in range(max_steps)
        ]

    def record_path(self, path: list[tuple[int, int]], start_t: int,
                    state: str, task_id: int) -> int:
        for i, pos in enumerate(path):
            t = start_t + i
            if t < len(self.trajectory):
                self.trajectory[t] = (pos[0], pos[1], state, task_id)
        return start_t + len(path) - 1

    def record_path_timed(self, path: list[tuple[int, int]], path_times: list[int],
                          state: str, task_id: int) -> int:
        """记录带非均匀时间步的路径，转弯/加速期间AGV停留在原位"""
        for i, pos in enumerate(path):
            t = path_times[i]
            if t < len(self.trajectory):
                self.trajectory[t] = (pos[0], pos[1], state, task_id)
            # 填充当前位置到下一位置之间的停留时间
            if i + 1 < len(path_times):
                for t_fill in range(path_times[i] + 1, path_times[i + 1]):
                    if t_fill < len(self.trajectory):
                        self.trajectory[t_fill] = (pos[0], pos[1], state, task_id)
        return path_times[-1]

    def record_wait(self, pos: tuple[int, int], start_t: int,
                    duration: int, state: str, task_id: int) -> int:
        for t in range(start_t, start_t + duration):
            if t < len(self.trajectory):
                self.trajectory[t] = (pos[0], pos[1], state, task_id)
        return start_t + duration

    def update_position(self, path: list[tuple[int, int]]):
        if path:
            self.current_pos = path[-1]

    def consume_battery(self, steps: int):
        self.battery = max(0, self.battery - steps)

    def charge_full(self):
        self.battery = 100
