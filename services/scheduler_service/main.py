"""
Scheduler Service - FastAPI Application.
Provides HTTP endpoints for task scheduling with OR-Tools and VLM arbitration.
"""
import sys
import os
import time
from contextlib import asynccontextmanager
from typing import List, Dict, Optional

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from services.shared.config import get_scheduler_config, get_service_config
from services.shared.models import (
    WarehouseTask,
    AGVState,
    ScheduleResult,
    HealthResponse,
)
from services.shared.utils import ServiceLogger, format_error_response
from services.scheduler_service.scheduler import create_scheduler, HAS_ORTOOLS
from services.scheduler_service.conflict_detector import ConflictDetector
from services.scheduler_service.arbitrator import VLMArbitrator


# Schedule request model
class ScheduleRequest(BaseModel):
    """Request model for schedule endpoint."""
    tasks: List[WarehouseTask] = Field(..., description="List of tasks to schedule")
    agv_states: List[AGVState] = Field(..., description="Current AGV states")
    enable_arbitration: Optional[bool] = Field(None, description="Override VLM arbitration setting")


# Global state
config = get_scheduler_config()
service_config = get_service_config()
logger = ServiceLogger.get_logger(config.service_name, config.log_level)

# Service components
scheduler = None
conflict_detector = None
arbitrator = None

# Service uptime tracking
start_time = time.time()


def initialize_components():
    """Initialize scheduler components."""
    global scheduler, conflict_detector, arbitrator

    # Initialize OR-Tools scheduler
    if HAS_ORTOOLS:
        scheduler = create_scheduler(
            solver_timeout_seconds=config.solver_timeout_seconds,
        )
        if scheduler:
            logger.info("OR-Tools scheduler initialized")
    else:
        logger.warning("OR-Tools not available, scheduling will be limited")

    # Initialize conflict detector
    conflict_detector = ConflictDetector(
        min_distance_threshold=config.min_distance_threshold
    )
    logger.info("Conflict detector initialized")

    # Initialize VLM arbitrator
    if config.enable_vlm_arbitration:
        arbitrator = VLMArbitrator(timeout=config.vlm_timeout)
        logger.info("VLM arbitrator initialized")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    logger.info(f"Starting {config.service_name} on {config.host}:{config.port}")
    initialize_components()
    yield
    logger.info(f"Shutting down {config.service_name}")


# Create FastAPI app
app = FastAPI(
    title="Scheduler Service",
    description="Task scheduling service for warehouse operations",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    uptime = time.time() - start_time

    dependencies = {
        "ortools": "ok" if HAS_ORTOOLS else "not_installed",
        "scheduler": "ok" if scheduler else "not_initialized",
        "conflict_detector": "ok",
        "vlm_arbitrator": "ok" if arbitrator else "disabled",
    }

    status = "ok"
    if not HAS_ORTOOLS and not scheduler:
        status = "degraded"

    return HealthResponse(
        status=status,
        service=config.service_name,
        uptime_seconds=uptime,
        dependencies=dependencies,
    )


@app.post("/api/v1/schedule", response_model=ScheduleResult)
async def schedule_tasks(request: ScheduleRequest):
    """
    Schedule tasks to AGVs.

    1. Uses OR-Tools CP-SAT for initial assignment
    2. Detects conflicts in the schedule
    3. If conflicts found and arbitration enabled, uses VLM to resolve
    4. Returns final schedule with assignments
    """
    try:
        logger.info(f"Schedule request: {len(request.tasks)} tasks, {len(request.agv_states)} AGVs")

        if not scheduler:
            raise HTTPException(
                status_code=503,
                detail="Scheduler not available. OR-Tools may not be installed."
            )

        # Step 1: Initial scheduling with OR-Tools
        logger.info("Running OR-Tools scheduler...")
        schedule_result = scheduler.schedule(request.tasks, request.agv_states)

        if not schedule_result.success:
            logger.warning(f"OR-Tools scheduling failed: {schedule_result.error_message}")

            # Try VLM arbitration even if OR-Tools failed
            if request.enable_arbitration or (request.enable_arbitration is None and config.enable_vlm_arbitration):
                logger.info("Attempting VLM arbitration for failed schedule...")
                # Create a dummy conflict for the whole schedule
                from services.shared.models import ConflictInfo, ConflictType
                dummy_conflict = ConflictInfo(
                    conflict_id="schedule-failure",
                    conflict_type=ConflictType.RESOURCE_CONTENTION,
                    involved_agvs=[agv.agv_id for agv in request.agv_states],
                    involved_tasks=[task.task_id for task in request.tasks],
                    description="OR-Tools could not find feasible schedule",
                    severity=1.0,
                )

                if arbitrator:
                    arbitration_results = arbitrator.arbitrate(
                        [dummy_conflict],
                        request.tasks,
                        request.agv_states,
                        {}
                    )

                    if arbitration_results:
                        # Use VLM suggestions
                        schedule_result.error_message = "Schedule created via VLM arbitration"
                        # Build assignments from arbitration results
                        for result in arbitration_results:
                            if result.new_assignments:
                                schedule_result.assignments = result.new_assignments
                                schedule_result.success = True
                                schedule_result.conflicts_resolved = arbitration_results

        if not schedule_result.success:
            return schedule_result

        # Step 2: Detect conflicts
        if config.enable_conflict_detection:
            logger.info("Detecting conflicts...")
            conflicts = conflict_detector.detect_conflicts(
                request.tasks,
                request.agv_states,
                schedule_result.assignments
            )

            schedule_result.conflicts_detected = conflicts

            # Step 3: Arbitrate conflicts if needed
            should_arbitrate = (
                (request.enable_arbitration or (request.enable_arbitration is None and config.enable_vlm_arbitration))
                and conflicts
                and arbitrator
            )

            if should_arbitrate:
                logger.info(f"Arbitrating {len(conflicts)} conflicts with VLM...")
                arbitration_results = arbitrator.arbitrate(
                    conflicts,
                    request.tasks,
                    request.agv_states,
                    schedule_result.assignments
                )

                schedule_result.conflicts_resolved = arbitration_results

                # Apply arbitration results
                for result in arbitration_results:
                    if result.new_assignments:
                        # Update assignments with VLM suggestions
                        schedule_result.assignments.update(result.new_assignments)
                        logger.info(f"Applied arbitration for conflict {result.conflict_id}: "
                                   f"{result.resolution}")

        logger.info(f"Schedule completed: {len(schedule_result.assignments)} tasks assigned, "
                   f"{len(schedule_result.conflicts_detected)} conflicts, "
                   f"{len(schedule_result.conflicts_resolved)} resolved")

        return schedule_result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error scheduling tasks: {e}", exc_info=True)
        error_response = format_error_response(e, config.service_name)
        return JSONResponse(
            status_code=500,
            content=error_response
        )


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": config.service_name,
        "version": "1.0.0",
        "status": "running",
        "ortools_available": HAS_ORTOOLS,
        "endpoints": {
            "health": "/health",
            "schedule": "/api/v1/schedule",
            "docs": "/docs"
        }
    }


def main():
    """Run the scheduler service."""
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
