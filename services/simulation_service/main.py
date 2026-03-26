"""
Simulation Service - FastAPI Application.
Provides HTTP endpoints for warehouse task execution simulation.
"""
import sys
import os
import time
import asyncio
from contextlib import asynccontextmanager
from typing import List, Dict

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from services.shared.config import get_simulation_config, get_service_config
from services.shared.models import (
    WarehouseTask,
    AGVState,
    ExecutionResult,
    HealthResponse,
    TaskStatus,
)
from services.shared.utils import (
    generate_execution_id,
    ServiceLogger,
    format_error_response,
)
from services.simulation_service.gym_env import create_warehouse_env, HAS_GYMNASIUM
from services.simulation_service.agv_agent import MultiAGVAgent


# Execute request model
class ExecuteRequest(BaseModel):
    """Request model for execute endpoint."""
    schedule_id: str = Field(..., description="Schedule ID to execute")
    assignments: Dict[str, str] = Field(..., description="Task ID to AGV ID assignments")
    tasks: List[WarehouseTask] = Field(..., description="List of tasks to execute")
    initial_agv_states: List[AGVState] = Field(..., description="Initial AGV states")
    time_limit: float = Field(default=300.0, description="Maximum simulation time in seconds")


# Global state
config = get_simulation_config()
service_config = get_service_config()
logger = ServiceLogger.get_logger(config.service_name, config.log_level)

# Service uptime tracking
start_time = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    logger.info(f"Starting {config.service_name} on {config.host}:{config.port}")
    yield
    logger.info(f"Shutting down {config.service_name}")


# Create FastAPI app
app = FastAPI(
    title="Simulation Service",
    description="Simulation service for warehouse operations",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    uptime = time.time() - start_time

    dependencies = {
        "gymnasium": "ok" if HAS_GYMNASIUM else "not_installed",
    }

    return HealthResponse(
        status="ok",
        service=config.service_name,
        uptime_seconds=uptime,
        dependencies=dependencies,
    )


@app.post("/api/v1/execute", response_model=ExecutionResult)
async def execute_tasks(request: ExecuteRequest, background_tasks: BackgroundTasks):
    """
    Execute scheduled tasks in simulation.

    Simulates AGV movement and task completion using Gymnasium environment.
    Returns execution results with completion status.
    """
    try:
        logger.info(f"Execute request: schedule_id={request.schedule_id}, "
                   f"{len(request.tasks)} tasks, {len(request.initial_agv_states)} AGVs")

        execution_id = generate_execution_id()
        start_time_exec = time.time()

        # Method 1: Use Gymnasium environment if available
        if HAS_GYMNASIUM:
            logger.info("Using Gymnasium environment for simulation")
            result = await _execute_with_gymnasium(request, execution_id, start_time_exec)
        else:
            # Method 2: Fallback to simple agent-based simulation
            logger.info("Using simple agent-based simulation")
            result = await _execute_with_agents(request, execution_id, start_time_exec)

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error executing tasks: {e}", exc_info=True)
        error_response = format_error_response(e, config.service_name)

        return JSONResponse(
            status_code=500,
            content=error_response
        )


async def _execute_with_gymnasium(
    request: ExecuteRequest,
    execution_id: str,
    start_time_exec: float
) -> ExecutionResult:
    """Execute simulation using Gymnasium environment."""
    # Create environment
    env = create_warehouse_env(
        warehouse_size=(config.warehouse_width, config.warehouse_height),
        num_agvs=len(request.initial_agv_states),
        agv_speed=config.agv_speed,
        time_step=config.time_step,
        max_episode_steps=config.max_episode_steps,
    )

    if env is None:
        raise HTTPException(
            status_code=503,
            detail="Gymnasium environment not available"
        )

    # Reset environment
    obs, info = env.reset()

    # Set tasks and assignments
    # Update AGV states in environment
    for i, agv_state in enumerate(request.initial_agv_states):
        if i < len(env.agvs):
            env.agvs[i] = agv_state

    env.set_tasks_and_assignments(request.tasks, request.assignments)

    # Run simulation
    completed_tasks = []
    failed_tasks = []
    total_steps = 0
    collision_count = 0

    for step in range(config.max_episode_steps):
        # Simple action: move towards assigned targets
        action = env._get_observation()  # Placeholder - would need proper action logic

        obs, reward, terminated, truncated, info = env.step(action)
        total_steps += 1

        # Check completion
        completed_tasks = env.completed_tasks.copy()
        collision_count = env.collisions

        if terminated or truncated:
            break

    # Calculate results
    actual_time = time.time() - start_time_exec
    total_energy = env.total_energy

    # Determine failed tasks
    failed_tasks = [task.task_id for task in request.tasks if task.task_id not in completed_tasks]

    return ExecutionResult(
        execution_id=execution_id,
        schedule_id=request.schedule_id,
        tasks_completed=completed_tasks,
        tasks_failed=failed_tasks,
        final_agv_states=env.agvs,
        actual_completion_time=actual_time,
        total_energy_consumed=total_energy,
        collisions=collision_count,
        success=len(failed_tasks) == 0,
    )


async def _execute_with_agents(
    request: ExecuteRequest,
    execution_id: str,
    start_time_exec: float
) -> ExecutionResult:
    """Execute simulation using simple agent-based approach."""
    # Create multi-AGV agent
    agent_system = MultiAGVAgent(request.initial_agv_states, speed=config.agv_speed)

    # Assign tasks
    agent_system.assign_tasks(request.tasks, request.assignments)

    # Simulate execution
    completed_tasks = []
    max_time = request.time_limit
    current_time = 0.0
    dt = config.time_step

    while current_time < max_time:
        # Step simulation
        newly_completed = agent_system.step(dt)
        completed_tasks.extend(newly_completed)

        # Check if all tasks complete
        if len(completed_tasks) >= len(request.tasks):
            break

        current_time += dt

    # Get final states
    final_agv_states = agent_system.get_agv_states()

    # Determine failed tasks
    failed_task_ids = [
        task.task_id
        for task in request.tasks
        if task.task_id not in completed_tasks
    ]

    # Calculate energy consumption
    total_energy = sum(
        agv.battery_level
        for agv in request.initial_agv_states
    ) - sum(
        agv.battery_level
        for agv in final_agv_states
    )

    actual_time = time.time() - start_time_exec

    return ExecutionResult(
        execution_id=execution_id,
        schedule_id=request.schedule_id,
        tasks_completed=completed_tasks,
        tasks_failed=failed_task_ids,
        final_agv_states=final_agv_states,
        actual_completion_time=actual_time,
        total_energy_consumed=total_energy,
        collisions=0,  # Not tracked in simple simulation
        success=len(failed_task_ids) == 0,
    )


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": config.service_name,
        "version": "1.0.0",
        "status": "running",
        "gymnasium_available": HAS_GYMNASIUM,
        "endpoints": {
            "health": "/health",
            "execute": "/api/v1/execute",
            "docs": "/docs"
        }
    }


def main():
    """Run the simulation service."""
    import uvicorn

    uvicorn.run(
        "main:app",
        host=config.host,
        port=config.port,
        log_level=config.log_level.lower(),
        reload=service_config.debug,
    )


if __name__ == "__main__":
    main()
