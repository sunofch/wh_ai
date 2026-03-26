"""
Conflict Detection Module.
Detects conflicts between AGVs and tasks in the warehouse.
"""
import math
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass

from services.shared.models import (
    WarehouseTask,
    AGVState,
    ConflictInfo,
    ConflictType,
)
from services.shared.utils import (
    calculate_distance,
    generate_conflict_id,
    ServiceLogger,
)


@dataclass
class PathSegment:
    """Represents a segment of an AGV's path."""
    start: Tuple[float, float]
    end: Tuple[float, float]
    agv_id: str
    task_id: str


class ConflictDetector:
    """Detects conflicts in warehouse scheduling."""

    def __init__(self, min_distance_threshold: float = 2.0):
        self.min_distance_threshold = min_distance_threshold
        self.logger = ServiceLogger.get_logger("ConflictDetector")

    def detect_conflicts(
        self,
        tasks: List[WarehouseTask],
        agv_states: List[AGVState],
        assignments: Dict[str, str]  # task_id -> agv_id
    ) -> List[ConflictInfo]:
        """
        Detect conflicts in the schedule.

        Args:
            tasks: List of scheduled tasks
            agv_states: List of AGV states
            assignments: Task to AGV assignments

        Returns:
            List of detected conflicts
        """
        conflicts = []

        # Build paths for each assignment
        paths = self._build_paths(tasks, agv_states, assignments)

        # Detect path crossing conflicts
        path_conflicts = self._detect_path_crossings(paths)
        conflicts.extend(path_conflicts)

        # Detect resource contention
        resource_conflicts = self._detect_resource_contention(tasks, agv_states, assignments)
        conflicts.extend(resource_conflicts)

        # Detect battery issues
        battery_conflicts = self._detect_battery_issues(tasks, agv_states, assignments)
        conflicts.extend(battery_conflicts)

        # Detect capacity issues
        capacity_conflicts = self._detect_capacity_issues(tasks, agv_states, assignments)
        conflicts.extend(capacity_conflicts)

        self.logger.info(f"Detected {len(conflicts)} conflicts")
        return conflicts

    def _build_paths(
        self,
        tasks: List[WarehouseTask],
        agv_states: List[AGVState],
        assignments: Dict[str, str]
    ) -> List[PathSegment]:
        """Build path segments for all assignments."""
        paths = []
        agv_dict = {agv.agv_id: agv for agv in agv_states}
        task_dict = {task.task_id: task for task in tasks}

        for task_id, agv_id in assignments.items():
            if agv_id not in agv_dict or task_id not in task_dict:
                continue

            agv = agv_dict[agv_id]
            task = task_dict[task_id]

            # Create path from AGV position to task source
            paths.append(PathSegment(
                start=agv.position,
                end=task.source,
                agv_id=agv_id,
                task_id=task_id
            ))

            # Create path from task source to destination
            paths.append(PathSegment(
                start=task.source,
                end=task.destination,
                agv_id=agv_id,
                task_id=task_id
            ))

        return paths

    def _detect_path_crossings(self, paths: List[PathSegment]) -> List[ConflictInfo]:
        """Detect path crossing conflicts between AGVs."""
        conflicts = []

        for i, path1 in enumerate(paths):
            for path2 in paths[i + 1:]:
                if path1.agv_id == path2.agv_id:
                    continue

                # Check if paths intersect
                if self._paths_intersect(path1, path2):
                    severity = self._calculate_crossing_severity(path1, path2)
                    conflicts.append(ConflictInfo(
                        conflict_id=generate_conflict_id(),
                        conflict_type=ConflictType.PATH_CROSSING,
                        involved_agvs=[path1.agv_id, path2.agv_id],
                        involved_tasks=[path1.task_id, path2.task_id],
                        description=f"Path crossing between AGV {path1.agv_id} and {path2.agv_id}",
                        severity=severity
                    ))

        return conflicts

    def _paths_intersect(self, path1: PathSegment, path2: PathSegment) -> bool:
        """Check if two path segments intersect."""
        # Simple distance-based check
        # In a real system, you'd use more sophisticated geometry

        # Check minimum distance between segments
        min_dist = self._segment_distance(path1, path2)
        return min_dist < self.min_distance_threshold

    def _segment_distance(self, path1: PathSegment, path2: PathSegment) -> float:
        """Calculate minimum distance between two line segments."""
        # Simplified: check distances between all four point combinations
        points = [
            (path1.start, path2.start),
            (path1.start, path2.end),
            (path1.end, path2.start),
            (path1.end, path2.end),
        ]

        distances = [calculate_distance(p1, p2) for p1, p2 in points]
        return min(distances)

    def _calculate_crossing_severity(self, path1: PathSegment, path2: PathSegment) -> float:
        """Calculate severity of path crossing based on angle and distance."""
        # Simplified severity calculation
        min_dist = self._segment_distance(path1, path2)

        # Closer paths are more severe
        severity = max(0, 1 - (min_dist / (2 * self.min_distance_threshold)))
        return min(1.0, severity)

    def _detect_resource_contention(
        self,
        tasks: List[WarehouseTask],
        agv_states: List[AGVState],
        assignments: Dict[str, str]
    ) -> List[ConflictInfo]:
        """Detect resource contention (multiple AGVs needing same resource)."""
        conflicts = []

        # Group tasks by destination
        destination_tasks: Dict[Tuple[float, float], List[str]] = {}
        for task in tasks:
            if task.destination not in destination_tasks:
                destination_tasks[task.destination] = []
            destination_tasks[task.destination].append(task.task_id)

        # Check for multiple tasks going to same destination
        for dest, task_ids in destination_tasks.items():
            if len(task_ids) > 1:
                agvs = [assignments.get(tid) for tid in task_ids if tid in assignments]
                agvs = [agv for agv in agvs if agv is not None]

                if len(agvs) > 1:
                    conflicts.append(ConflictInfo(
                        conflict_id=generate_conflict_id(),
                        conflict_type=ConflictType.RESOURCE_CONTENTION,
                        involved_agvs=agvs,
                        involved_tasks=task_ids,
                        description=f"Multiple AGVs ({', '.join(agvs)}) accessing same location {dest}",
                        severity=0.7
                    ))

        return conflicts

    def _detect_battery_issues(
        self,
        tasks: List[WarehouseTask],
        agv_states: List[AGVState],
        assignments: Dict[str, str]
    ) -> List[ConflictInfo]:
        """Detect potential battery depletion issues."""
        conflicts = []
        agv_dict = {agv.agv_id: agv for agv in agv_states}
        task_dict = {task.task_id: task for task in tasks}

        for task_id, agv_id in assignments.items():
            if agv_id not in agv_dict or task_id not in task_dict:
                continue

            agv = agv_dict[agv_id]
            task = task_dict[task_id]

            # Estimate battery consumption
            total_distance = (
                calculate_distance(agv.position, task.source) +
                calculate_distance(task.source, task.destination)
            )

            # Assume 1% battery per 10 units of distance (simplified)
            estimated_consumption = total_distance / 10.0

            if agv.battery_level - estimated_consumption < 20:  # 20% threshold
                conflicts.append(ConflictInfo(
                    conflict_id=generate_conflict_id(),
                    conflict_type=ConflictType.BATTERY_DEPLETION,
                    involved_agvs=[agv_id],
                    involved_tasks=[task_id],
                    description=f"AGV {agv_id} battery ({agv.battery_level}%) may be insufficient "
                               f"for task {task_id} (estimated consumption: {estimated_consumption:.1f}%)",
                    severity=0.8
                ))

        return conflicts

    def _detect_capacity_issues(
        self,
        tasks: List[WarehouseTask],
        agv_states: List[AGVState],
        assignments: Dict[str, str]
    ) -> List[ConflictInfo]:
        """Detect capacity exceeded issues."""
        conflicts = []
        agv_dict = {agv.agv_id: agv for agv in agv_states}
        task_dict = {task.task_id: task for task in tasks}

        for task_id, agv_id in assignments.items():
            if agv_id not in agv_dict or task_id not in task_dict:
                continue

            agv = agv_dict[agv_id]
            task = task_dict[task_id]

            available_capacity = agv.load_capacity - agv.current_load

            if task.required_capacity > available_capacity:
                conflicts.append(ConflictInfo(
                    conflict_id=generate_conflict_id(),
                    conflict_type=ConflictType.CAPACITY_EXCEEDED,
                    involved_agvs=[agv_id],
                    involved_tasks=[task_id],
                    description=f"AGV {agv_id} capacity exceeded: "
                               f"required {task.required_capacity}, available {available_capacity}",
                    severity=0.9
                ))

        return conflicts
