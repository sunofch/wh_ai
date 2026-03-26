"""
Gymnasium Environment for Warehouse Simulation.
Implements a standard RL environment for multi-AGV warehouse operations.
"""
import numpy as np
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime

try:
    import gymnasium as gym
    from gymnasium import spaces
    HAS_GYMNASIUM = True
except ImportError:
    HAS_GYMNASIUM = False

from services.shared.models import (
    WarehouseTask,
    AGVState,
    AGVStatus,
    TaskStatus,
)
from services.shared.utils import (
    calculate_distance,
    generate_agv_id,
    ServiceLogger,
)


class WarehouseEnv(gym.Env):
    """
    Warehouse simulation environment for multi-AGV operations.

    Observation Space:
        - AGV positions and states
        - Task information
        - Battery levels

    Action Space:
        - AGV movement directions
        - Task assignments

    Reward:
        - Task completion bonuses
        - Collision penalties
        - Energy efficiency bonuses
    """

    metadata = {"render_modes": ["human", "rgb_array"], "render_fps": 4}

    def __init__(
        self,
        warehouse_size: Tuple[float, float] = (100.0, 100.0),
        num_agvs: int = 3,
        agv_speed: float = 1.0,
        time_step: float = 0.1,
        max_episode_steps: int = 1000,
    ):
        if not HAS_GYMNASIUM:
            raise ImportError("Gymnasium is not installed. Install with: pip install gymnasium")

        super().__init__()

        self.warehouse_size = warehouse_size
        self.num_agvs = num_agvs
        self.agv_speed = agv_speed
        self.time_step = time_step
        self.max_episode_steps = max_episode_steps

        self.logger = ServiceLogger.get_logger("WarehouseEnv")

        # Define action space: for each AGV, choose [dx, dy] direction
        # Actions: 0=stay, 1=up, 2=down, 3=left, 4=right
        self.action_space = spaces.MultiDiscrete([5] * num_agvs)

        # Define observation space
        # [agv1_x, agv1_y, agv1_battery, agv1_load, ..., task1_x, task1_y, ...]
        obs_size = num_agvs * 4 + 20 * 4  # AGV states + up to 20 tasks
        self.observation_space = spaces.Box(
            low=-np.inf,
            high=np.inf,
            shape=(obs_size,),
            dtype=np.float32
        )

        # State
        self.agvs: List[AGVState] = []
        self.tasks: List[WarehouseTask] = []
        self.assignments: Dict[str, str] = {}  # task_id -> agv_id
        self.completed_tasks: List[str] = []
        self.failed_tasks: List[str] = []
        self.collisions: int = 0
        self.current_step: int = 0
        self.total_energy: float = 0.0

    def reset(
        self,
        seed: Optional[int] = None,
        options: Optional[dict] = None,
    ) -> Tuple[np.ndarray, dict]:
        """Reset the environment."""
        super().reset(seed=seed)

        # Initialize AGVs at random positions
        self.agvs = []
        for i in range(self.num_agvs):
            self.agvs.append(AGVState(
                agv_id=generate_agv_id(i + 1),
                position=(
                    np.random.uniform(0, self.warehouse_size[0]),
                    np.random.uniform(0, self.warehouse_size[1])
                ),
                battery_level=100.0,
                load_capacity=100.0,
                current_load=0.0,
                status=AGVStatus.IDLE,
            ))

        # Clear tasks
        self.tasks = []
        self.assignments = {}
        self.completed_tasks = []
        self.failed_tasks = []
        self.collisions = 0
        self.current_step = 0
        self.total_energy = 0.0

        observation = self._get_observation()
        info = {}

        return observation, info

    def step(self, action: np.ndarray) -> Tuple[np.ndarray, float, bool, bool, dict]:
        """
        Execute one environment step.

        Args:
            action: Array of actions for each AGV

        Returns:
            observation, reward, terminated, truncated, info
        """
        self.current_step += 1

        # Execute actions
        reward = 0.0
        for i, agv_action in enumerate(action):
            if i >= len(self.agvs):
                break

            agv = self.agvs[i]
            movement_reward = self._execute_agv_action(agv, agv_action)
            reward += movement_reward

        # Update task progress
        task_reward = self._update_tasks()
        reward += task_reward

        # Check collisions
        collision_penalty = self._check_collisions()
        reward -= collision_penalty * 10  # Penalty for collisions

        # Update battery
        self._update_battery()

        # Check termination
        terminated = len(self.completed_tasks) == len(self.tasks) and len(self.tasks) > 0
        truncated = self.current_step >= self.max_episode_steps

        observation = self._get_observation()
        info = {
            "completed_tasks": len(self.completed_tasks),
            "failed_tasks": len(self.failed_tasks),
            "collisions": self.collisions,
            "total_energy": self.total_energy,
        }

        return observation, reward, terminated, truncated, info

    def set_tasks_and_assignments(
        self,
        tasks: List[WarehouseTask],
        assignments: Dict[str, str]
    ):
        """Set tasks and assignments for the episode."""
        self.tasks = tasks
        self.assignments = assignments

        # Update AGV states with assigned tasks
        for task_id, agv_id in assignments.items():
            for agv in self.agvs:
                if agv.agv_id == agv_id:
                    agv.current_task_id = task_id
                    agv.status = AGVStatus.MOVING
                    break

    def _execute_agv_action(self, agv: AGVState, action: int) -> float:
        """Execute action for a single AGV."""
        if agv.status in [AGVStatus.CHARGING, AGVStatus.ERROR]:
            return 0.0

        # Get current task if any
        task = None
        if agv.current_task_id:
            task = next((t for t in self.tasks if t.task_id == agv.current_task_id), None)

        # Determine target position
        target = None
        if task:
            # First go to source, then to destination
            dist_to_source = calculate_distance(agv.position, task.source)
            dist_to_dest = calculate_distance(agv.position, task.destination)

            if dist_to_source < 2.0:  # At source
                target = task.destination
            else:
                target = task.source
        else:
            # No task, stay still
            return 0.0

        # Move towards target
        if target is not None:
            dx = target[0] - agv.position[0]
            dy = target[1] - agv.position[1]

            # Normalize and apply speed
            distance = (dx**2 + dy**2)**0.5
            if distance > 0:
                move_distance = min(self.agv_speed * self.time_step, distance)
                new_x = agv.position[0] + (dx / distance) * move_distance
                new_y = agv.position[1] + (dy / distance) * move_distance

                # Clamp to warehouse bounds
                new_x = max(0, min(self.warehouse_size[0], new_x))
                new_y = max(0, min(self.warehouse_size[1], new_y))

                agv.position = (new_x, new_y)

                # Reward for moving towards target
                reward = -0.1  # Small penalty for each step (encourage efficiency)
                if distance < 2.0:
                    reward += 1.0  # Bonus for reaching target
                return reward

        return 0.0

    def _update_tasks(self) -> float:
        """Update task progress and return reward."""
        reward = 0.0

        for task in self.tasks:
            if task.task_id in self.completed_tasks or task.task_id in self.failed_tasks:
                continue

            # Get assigned AGV
            agv_id = self.assignments.get(task.task_id)
            if not agv_id:
                continue

            agv = next((a for a in self.agvs if a.agv_id == agv_id), None)
            if not agv:
                continue

            # Check if at destination
            dist_to_dest = calculate_distance(agv.position, task.destination)

            if dist_to_dest < 2.0:  # At destination
                self.completed_tasks.append(task.task_id)
                reward += 10.0  # Big reward for completing task
                self.logger.info(f"Task {task.task_id} completed")

                # Update AGV state
                agv.current_task_id = None
                agv.status = AGVStatus.IDLE
                task.status = TaskStatus.COMPLETED

        return reward

    def _check_collisions(self) -> int:
        """Check for AGV collisions and return count."""
        collisions = 0
        min_distance = 2.0

        for i, agv1 in enumerate(self.agvs):
            for agv2 in self.agvs[i + 1:]:
                dist = calculate_distance(agv1.position, agv2.position)
                if dist < min_distance:
                    collisions += 1
                    self.collisions += 1
                    self.logger.warning(f"Collision between {agv1.agv_id} and {agv2.agv_id}")

        return collisions

    def _update_battery(self):
        """Update AGV battery levels."""
        battery_drain = 0.01  # 1% per 100 steps

        for agv in self.agvs:
            if agv.status != AGVStatus.CHARGING:
                agv.battery_level = max(0, agv.battery_level - battery_drain)
                self.total_energy += battery_drain

    def _get_observation(self) -> np.ndarray:
        """Get current observation."""
        obs = []

        # AGV states
        for agv in self.agvs:
            obs.extend([
                agv.position[0] / self.warehouse_size[0],  # Normalize
                agv.position[1] / self.warehouse_size[1],
                agv.battery_level / 100.0,
                agv.current_load / agv.load_capacity,
            ])

        # Task states (pad to 20 tasks)
        for i in range(20):
            if i < len(self.tasks):
                task = self.tasks[i]
                obs.extend([
                    task.source[0] / self.warehouse_size[0],
                    task.source[1] / self.warehouse_size[1],
                    task.destination[0] / self.warehouse_size[0],
                    task.destination[1] / self.warehouse_size[1],
                ])
            else:
                obs.extend([0.0, 0.0, 0.0, 0.0])

        return np.array(obs, dtype=np.float32)


def create_warehouse_env(
    warehouse_size: Tuple[float, float] = (100.0, 100.0),
    num_agvs: int = 3,
    agv_speed: float = 1.0,
    time_step: float = 0.1,
    max_episode_steps: int = 1000,
):
    """Create a warehouse environment if Gymnasium is available."""
    if HAS_GYMNASIUM:
        return WarehouseEnv(
            warehouse_size=warehouse_size,
            num_agvs=num_agvs,
            agv_speed=agv_speed,
            time_step=time_step,
            max_episode_steps=max_episode_steps,
        )
    else:
        return None
