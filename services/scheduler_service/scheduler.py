"""
OR-Tools CP-SAT Scheduler.
Implements constraint-based task scheduling using Google OR-Tools.
"""
from typing import List, Dict, Optional, Tuple
from datetime import datetime

try:
    from ortools.sat.python import cp_model
    HAS_ORTOOLS = True
except ImportError:
    HAS_ORTOOLS = False

from services.shared.models import (
    WarehouseTask,
    AGVState,
    ScheduleResult,
    TaskPriority,
    TaskStatus,
)
from services.shared.utils import (
    generate_schedule_id,
    calculate_distance,
    estimate_travel_time,
    ServiceLogger,
)


class ORToolsScheduler:
    """
    Task scheduler using OR-Tools CP-SAT solver.
    Assigns tasks to AGVs while respecting constraints.
    """

    def __init__(
        self,
        solver_timeout_seconds: int = 30,
        agv_speed: float = 1.0,
    ):
        if not HAS_ORTOOLS:
            raise ImportError("OR-Tools is not installed. Install with: pip install ortools")

        self.solver_timeout_seconds = solver_timeout_seconds
        self.agv_speed = agv_speed
        self.logger = ServiceLogger.get_logger("ORToolsScheduler")

    def schedule(
        self,
        tasks: List[WarehouseTask],
        agv_states: List[AGVState]
    ) -> ScheduleResult:
        """
        Schedule tasks to AGVs using CP-SAT solver.

        Args:
            tasks: List of tasks to schedule
            agv_states: List of available AGVs

        Returns:
            ScheduleResult with assignments and timing
        """
        start_time = datetime.now()
        schedule_id = generate_schedule_id()

        self.logger.info(f"Scheduling {len(tasks)} tasks to {len(agv_states)} AGVs")

        if not tasks:
            return ScheduleResult(
                schedule_id=schedule_id,
                assignments={},
                estimated_completion_time=0.0,
                makespan=0.0,
                timestamp=start_time,
                success=True
            )

        if not agv_states:
            return ScheduleResult(
                schedule_id=schedule_id,
                assignments={},
                estimated_completion_time=0.0,
                makespan=0.0,
                timestamp=start_time,
                success=False,
                error_message="No AGVs available for scheduling"
            )

        # Build CP-SAT model
        model = cp_model.CpModel()

        # Create variables
        # x[task_idx, agv_idx] = 1 if task assigned to AGV
        num_tasks = len(tasks)
        num_agvs = len(agv_states)

        x = {}
        for task_idx in range(num_tasks):
            for agv_idx in range(num_agvs):
                x[task_idx, agv_idx] = model.NewBoolVar(f"x_{task_idx}_{agv_idx}")

        # Task start time variables
        task_starts = {}
        for task_idx in range(num_tasks):
            task_starts[task_idx] = model.NewIntVar(0, 1000000, f"start_{task_idx}")

        # Calculate priority weights
        priority_weights = [self._get_priority_weight(task.priority) for task in tasks]

        # Constraint 1: Each task assigned to exactly one AGV
        for task_idx in range(num_tasks):
            model.Add(sum(x[task_idx, agv_idx] for agv_idx in range(num_agvs)) == 1)

        # Constraint 2: Capacity constraints
        for agv_idx, agv in enumerate(agv_states):
            tasks_for_agv = []
            capacities = []
            for task_idx, task in enumerate(tasks):
                if task.required_capacity > (agv.load_capacity - agv.current_load):
                    # Task doesn't fit, don't assign
                    model.Add(x[task_idx, agv_idx] == 0)
                else:
                    tasks_for_agv.append(task_idx)
                    capacities.append(task.required_capacity)

        # Constraint 3: No overlap on same AGV
        for agv_idx in range(num_agvs):
            for i in range(num_tasks):
                for j in range(i + 1, num_tasks):
                    # If both tasks assigned to same AGV, they must be sequential
                    both_assigned = model.NewBoolVar(f"both_{i}_{j}_{agv_idx}")
                    model.Add(x[i, agv_idx] + x[j, agv_idx] == 2).OnlyEnforceIf(both_assigned)
                    model.Add(x[i, agv_idx] + x[j, agv_idx] <= 1).OnlyEnforceIf(both_assigned.Not())

                    # Add precedence constraint
                    duration_i = self._estimate_task_duration(tasks[i], agv_states[agv_idx])
                    duration_j = self._estimate_task_duration(tasks[j], agv_states[agv_idx])

                    # Create boolean literals for ordering
                    i_before_j = model.NewBoolVar(f"i_before_j_{i}_{j}_{agv_idx}")

                    # If both assigned to same AGV, either i before j OR j before i
                    model.Add(task_starts[i] + duration_i <= task_starts[j]).OnlyEnforceIf(
                        [both_assigned, i_before_j]
                    )
                    model.Add(task_starts[j] + duration_j <= task_starts[i]).OnlyEnforceIf(
                        [both_assigned, i_before_j.Not()]
                    )

        # Constraint 4: Deadline constraints
        for task_idx, task in enumerate(tasks):
            if task.deadline is not None:
                deadline_seconds = (task.deadline - datetime.now()).total_seconds()
                duration = max(
                    self._estimate_task_duration(task, agv_states[0])
                    for agv in agv_states
                )
                model.Add(task_starts[task_idx] + duration <= deadline_seconds)

        # Objective: Minimize makespan while prioritizing important tasks
        makespan = model.NewIntVar(0, 1000000, "makespan")

        for task_idx in range(num_tasks):
            # Add constraint that makespan >= task start + duration for all AGVs
            for agv_idx in range(num_agvs):
                duration = self._estimate_task_duration(tasks[task_idx], agv_states[agv_idx])
                # If task assigned to this AGV, makespan >= start + duration
                model.Add(task_starts[task_idx] + duration <= makespan).OnlyEnforceIf(
                    x[task_idx, agv_idx]
                )

        # Weighted objective: minimize makespan + prioritize important tasks
        model.Minimize(makespan)

        # Solve
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = self.solver_timeout_seconds
        solver.parameters.log_search_progress = False

        status = solver.Solve(model)

        if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
            # Extract solution
            assignments = {}
            task_positions = {}

            total_distance = 0.0

            for task_idx in range(num_tasks):
                for agv_idx in range(num_agvs):
                    if solver.Value(x[task_idx, agv_idx]) == 1:
                        task_id = tasks[task_idx].task_id
                        agv_id = agv_states[agv_idx].agv_id
                        assignments[task_id] = agv_id

                        # Calculate distance
                        distance = (
                            calculate_distance(agv_states[agv_idx].position, tasks[task_idx].source) +
                            calculate_distance(tasks[task_idx].source, tasks[task_idx].destination)
                        )
                        total_distance += distance

                        break

            makespan_value = solver.Value(makespan)

            self.logger.info(f"Schedule found with makespan {makespan_value}s")

            return ScheduleResult(
                schedule_id=schedule_id,
                assignments=assignments,
                estimated_completion_time=makespan_value,
                makespan=makespan_value,
                total_distance=total_distance,
                timestamp=start_time,
                success=True
            )

        else:
            self.logger.warning(f"No feasible solution found (status: {status})")

            return ScheduleResult(
                schedule_id=schedule_id,
                assignments={},
                estimated_completion_time=0.0,
                makespan=0.0,
                timestamp=start_time,
                success=False,
                error_message=f"No feasible solution found. Solver status: {status}"
            )

    def _get_priority_weight(self, priority: TaskPriority) -> int:
        """Get numeric weight for priority level."""
        weights = {
            TaskPriority.CRITICAL: 1000,
            TaskPriority.HIGH: 100,
            TaskPriority.MEDIUM: 10,
            TaskPriority.LOW: 1,
        }
        return weights.get(priority, 10)

    def _estimate_task_duration(self, task: WarehouseTask, agv: AGVState) -> int:
        """Estimate task duration in seconds."""
        # Calculate travel distances
        to_source = calculate_distance(agv.position, task.source)
        to_dest = calculate_distance(task.source, task.destination)

        # Add 30 seconds for loading/unloading
        handling_time = 30

        # Calculate travel time
        travel_time = estimate_travel_time(to_source + to_dest, self.agv_speed)

        return int(travel_time + handling_time)


def create_scheduler(
    solver_timeout_seconds: int = 30,
    agv_speed: float = 1.0,
) -> Optional[ORToolsScheduler]:
    """
    Create OR-Tools scheduler if available.

    Returns None if OR-Tools is not installed.
    """
    if HAS_ORTOOLS:
        return ORToolsScheduler(solver_timeout_seconds, agv_speed)
    else:
        return None
