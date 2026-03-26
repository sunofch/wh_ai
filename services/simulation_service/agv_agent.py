"""
AGV Agent for Warehouse Simulation.
Implements simple rule-based agent for executing tasks.
"""
from typing import List, Dict, Optional
import numpy as np

from services.shared.models import (
    WarehouseTask,
    AGVState,
    AGVStatus,
)
from services.shared.utils import (
    calculate_distance,
    ServiceLogger,
)


class AGVAgent:
    """
    Simple rule-based AGV agent.
    Executes assigned tasks by moving through waypoints.
    """

    def __init__(self, agv_state: AGVState, speed: float = 1.0):
        self.agv = agv_state
        self.speed = speed
        self.logger = ServiceLogger.get_logger(f"AGVAgent-{agv_state.agv_id}")

        # Task execution state
        self.current_task: Optional[WarehouseTask] = None
        self.waypoints: List[tuple[float, float]] = []
        self.current_waypoint_index: int = 0
        self.at_source: bool = False
        self.pickup_complete: bool = False

    def assign_task(self, task: WarehouseTask):
        """Assign a task to this AGV."""
        self.current_task = task
        self.waypoints = [task.source, task.destination]
        self.current_waypoint_index = 0
        self.at_source = False
        self.pickup_complete = False

        self.agv.current_task_id = task.task_id
        self.agv.status = AGVStatus.MOVING

        self.logger.info(f"Assigned task {task.task_id}: {task.source} -> {task.destination}")

    def update(self, dt: float) -> bool:
        """
        Update AGV state for one time step.

        Args:
            dt: Time delta in seconds

        Returns:
            True if task is complete, False otherwise
        """
        if self.agv.status in [AGVStatus.ERROR, AGVStatus.MAINTENANCE]:
            return False

        if self.current_task is None:
            self.agv.status = AGVStatus.IDLE
            return False

        # Get current target waypoint
        if self.current_waypoint_index >= len(self.waypoints):
            # Task complete
            self.logger.info(f"Task {self.current_task.task_id} completed")
            self.current_task = None
            self.agv.current_task_id = None
            self.agv.status = AGVStatus.IDLE
            return True

        target = self.waypoints[self.current_waypoint_index]

        # Move towards target
        self._move_towards(target, dt)

        # Check if reached waypoint
        if self._at_position(target):
            self.current_waypoint_index += 1

            # Special handling for source (pickup)
            if not self.at_source and target == self.current_task.source:
                self.at_source = True
                self.agv.status = AGVStatus.LOADING
                self._simulate_loading()

            if self.at_source and target == self.current_task.destination:
                self.agv.status = AGVStatus.UNLOADING
                self._simulate_unloading()

        return False

    def _move_towards(self, target: tuple[float, float], dt: float):
        """Move AGV towards target position."""
        dx = target[0] - self.agv.position[0]
        dy = target[1] - self.agv.position[1]

        distance = (dx**2 + dy**2)**0.5

        if distance > 0:
            # Calculate move distance
            move_distance = min(self.speed * dt, distance)

            # Update position
            new_x = self.agv.position[0] + (dx / distance) * move_distance
            new_y = self.agv.position[1] + (dy / distance) * move_distance

            self.agv.position = (new_x, new_y)
            self.agv.status = AGVStatus.MOVING

    def _at_position(self, target: tuple[float, float], threshold: float = 1.0) -> bool:
        """Check if AGV is at target position."""
        distance = calculate_distance(self.agv.position, target)
        return distance < threshold

    def _simulate_loading(self):
        """Simulate loading operation."""
        # Update load
        if self.current_task:
            self.agv.current_load += self.current_task.required_capacity

        self.logger.debug(f"Loading complete. Current load: {self.agv.current_load}")

    def _simulate_unloading(self):
        """Simulate unloading operation."""
        # Update load
        if self.current_task:
            self.agv.current_load -= self.current_task.required_capacity

        self.logger.debug(f"Unloading complete. Current load: {self.agv.current_load}")


class MultiAGVAgent:
    """
    Manages multiple AGV agents.
    Coordinates execution of scheduled tasks.
    """

    def __init__(self, agv_states: List[AGVState], speed: float = 1.0):
        self.agents: Dict[str, AGVAgent] = {}
        self.speed = speed
        self.logger = ServiceLogger.get_logger("MultiAGVAgent")

        for agv_state in agv_states:
            self.agents[agv_state.agv_id] = AGVAgent(agv_state, speed)

        self.logger.info(f"Initialized {len(self.agents)} AGV agents")

    def assign_tasks(self, tasks: List[WarehouseTask], assignments: Dict[str, str]):
        """Assign tasks to AGVs."""
        for task in tasks:
            agv_id = assignments.get(task.task_id)
            if agv_id and agv_id in self.agents:
                self.agents[agv_id].assign_task(task)

    def step(self, dt: float) -> List[str]:
        """
        Execute one simulation step.

        Args:
            dt: Time delta in seconds

        Returns:
            List of completed task IDs
        """
        completed_tasks = []

        for agent in self.agents.values():
            if agent.update(dt):
                if agent.current_task is None and agent.agv.current_task_id:
                    # Task just completed
                    completed_tasks.append(agent.agv.current_task_id)

        return completed_tasks

    def get_agv_states(self) -> List[AGVState]:
        """Get current states of all AGVs."""
        return [agent.agv for agent in self.agents.values()]

    def get_completed_tasks(self) -> List[str]:
        """Get list of completed task IDs."""
        return [
            agent.agv.current_task_id
            for agent in self.agents.values()
            if agent.current_task is None and agent.agv.current_task_id
        ]
