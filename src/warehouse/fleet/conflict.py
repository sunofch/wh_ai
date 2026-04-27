# src/warehouse/fleet/conflict.py
"""冲突路段管理 + 避让"""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.warehouse.fleet.map_builder import WarehouseMap
    from src.warehouse.fleet.pathfinding import SpaceTimeTable


class RoadSegment:
    def __init__(self, seg_id: str, start: tuple, end: tuple,
                 length: int, yield_points: list[str], direction: str):
        self.seg_id = seg_id
        self.start = start
        self.end = end
        self.length = length
        self.yield_points = yield_points
        self.direction = direction
        self.occupied_by: int | None = None
        self.occupied_dir: str | None = None

    @property
    def is_occupied(self) -> bool:
        return self.occupied_by is not None

    def occupy(self, agv_id: int, direction: str):
        self.occupied_by = agv_id
        self.occupied_dir = direction

    def release(self):
        self.occupied_by = None
        self.occupied_dir = None


class ConflictManager:
    def __init__(self, warehouse_map, st_table: SpaceTimeTable):
        self.wmap = warehouse_map
        self.st_table = st_table
        self.segments: dict[str, RoadSegment] = {}
        for seg_id, seg_info in warehouse_map.config.conflict_segments.items():
            self.segments[seg_id] = RoadSegment(
                seg_id=seg_id,
                start=seg_info["start"],
                end=seg_info["end"],
                length=seg_info["length"],
                yield_points=seg_info["yield_points"],
                direction=seg_info["direction"],
            )

    def request_segment(self, agv_id: int, seg_id: str, direction: str,
                        time_step: int) -> bool:
        seg = self.segments[seg_id]
        if seg.is_occupied and seg.occupied_dir != direction:
            return False  # 对向占用，拒绝
        seg.occupy(agv_id, direction)
        return True

    def request_yield(self, agv_id: int, seg_id: str, time_step: int):
        """让AGV避让：锁定避让点"""
        seg = self.segments[seg_id]
        if seg.yield_points:
            yp_id = seg.yield_points[0]
            self.st_table.lock_yield_point(yp_id, time_step, time_step + 12, agv_id)

    def release_segment(self, agv_id: int, seg_id: str):
        seg = self.segments[seg_id]
        if seg.occupied_by == agv_id:
            seg.release()
