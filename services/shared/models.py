"""
Shared data models for warehouse scheduling system.
Defines Pydantic models used across all microservices.
"""
from enum import Enum
from typing import Optional, Dict, List
from datetime import datetime
from pydantic import BaseModel, Field


class TaskType(str, Enum):
    """Task types in warehouse operations."""
    RETRIEVAL = "retrieval"
    STORAGE = "storage"
    TRANSPORT = "transport"
    CHARGING = "charging"


class TaskPriority(str, Enum):
    """Task priority levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TaskStatus(str, Enum):
    """Task execution status."""
    PENDING = "pending"
    SCHEDULED = "scheduled"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AGVStatus(str, Enum):
    """AGV operational status."""
    IDLE = "idle"
    MOVING = "moving"
    LOADING = "loading"
    UNLOADING = "unloading"
    CHARGING = "charging"
    ERROR = "error"
    MAINTENANCE = "maintenance"


class WarehouseTask(BaseModel):
    """
    Warehouse task model.
    Represents a single task to be executed in the warehouse.
    """
    task_id: str = Field(..., description="Unique task identifier")
    task_type: TaskType = Field(..., description="Type of task")
    priority: TaskPriority = Field(default=TaskPriority.MEDIUM, description="Task priority")
    item_id: Optional[str] = Field(None, description="Item/part identifier")
    quantity: int = Field(default=1, ge=1, description="Quantity of items")
    source: tuple[float, float] = Field(..., description="Source location (x, y)")
    destination: tuple[float, float] = Field(..., description="Destination location (x, y)")
    required_capacity: float = Field(default=1.0, ge=0, description="Required load capacity")
    deadline: Optional[datetime] = Field(None, description="Task deadline")
    status: TaskStatus = Field(default=TaskStatus.PENDING, description="Current task status")
    assigned_agv_id: Optional[str] = Field(None, description="Assigned AGV ID")
    created_at: datetime = Field(default_factory=datetime.now, description="Task creation timestamp")
    estimated_duration: Optional[float] = Field(None, description="Estimated duration in seconds")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class AGVState(BaseModel):
    """
    AGV state model.
    Represents the current state of an AGV in the warehouse.
    """
    agv_id: str = Field(..., description="Unique AGV identifier")
    position: tuple[float, float] = Field(..., description="Current position (x, y)")
    battery_level: float = Field(default=100.0, ge=0, le=100, description="Battery level percentage")
    load_capacity: float = Field(default=100.0, ge=0, description="Maximum load capacity")
    current_load: float = Field(default=0.0, ge=0, description="Current load weight")
    status: AGVStatus = Field(default=AGVStatus.IDLE, description="Current operational status")
    current_task_id: Optional[str] = Field(None, description="Currently assigned task ID")
    last_update: datetime = Field(default_factory=datetime.now, description="Last state update timestamp")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ConflictType(str, Enum):
    """Types of conflicts between AGVs or tasks."""
    PATH_CROSSING = "path_crossing"
    RESOURCE_CONTENTION = "resource_contention"
    DEADLOCK = "deadlock"
    BATTERY_DEPLETION = "battery_depletion"
    CAPACITY_EXCEEDED = "capacity_exceeded"


class ConflictInfo(BaseModel):
    """
    Conflict information model.
    Describes a detected conflict in the schedule.
    """
    conflict_id: str = Field(..., description="Unique conflict identifier")
    conflict_type: ConflictType = Field(..., description="Type of conflict")
    involved_agvs: List[str] = Field(..., description="AGV IDs involved in conflict")
    involved_tasks: List[str] = Field(..., description="Task IDs involved in conflict")
    description: str = Field(..., description="Human-readable conflict description")
    severity: float = Field(default=0.5, ge=0, le=1, description="Conflict severity (0-1)")
    timestamp: datetime = Field(default_factory=datetime.now, description="Conflict detection timestamp")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ArbitrationResult(BaseModel):
    """
    VLM arbitration result model.
    Contains the resolution proposed by the VLM arbitrator.
    """
    conflict_id: str = Field(..., description="ID of the conflict being resolved")
    resolution: str = Field(..., description="Proposed resolution strategy")
    new_assignments: Dict[str, str] = Field(default_factory=dict, description="New task-AGV assignments")
    reasoning: str = Field(..., description="VLM reasoning for the resolution")
    confidence: float = Field(default=0.5, ge=0, le=1, description="Confidence in the resolution")
    alternative_solutions: List[str] = Field(default_factory=list, description="Alternative solutions considered")
    timestamp: datetime = Field(default_factory=datetime.now, description="Arbitration timestamp")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ScheduleResult(BaseModel):
    """
    Schedule result model.
    Contains the output of the scheduling service.
    """
    schedule_id: str = Field(..., description="Unique schedule identifier")
    assignments: Dict[str, str] = Field(..., description="Task ID to AGV ID assignments")
    estimated_completion_time: float = Field(..., description="Estimated completion time in seconds")
    conflicts_detected: List[ConflictInfo] = Field(default_factory=list, description="Conflicts detected")
    conflicts_resolved: List[ArbitrationResult] = Field(default_factory=list, description="Conflicts resolved via VLM")
    makespan: float = Field(..., description="Total schedule makespan")
    total_distance: float = Field(default=0.0, description="Total distance traveled by all AGVs")
    timestamp: datetime = Field(default_factory=datetime.now, description="Schedule generation timestamp")
    success: bool = Field(default=True, description="Whether scheduling was successful")
    error_message: Optional[str] = Field(None, description="Error message if scheduling failed")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ExecutionResult(BaseModel):
    """
    Execution result model.
    Contains the output of the simulation service.
    """
    execution_id: str = Field(..., description="Unique execution identifier")
    schedule_id: str = Field(..., description="Associated schedule ID")
    tasks_completed: List[str] = Field(default_factory=list, description="IDs of completed tasks")
    tasks_failed: List[str] = Field(default_factory=list, description="IDs of failed tasks")
    final_agv_states: List[AGVState] = Field(default_factory=list, description="Final AGV states")
    actual_completion_time: float = Field(..., description="Actual completion time in seconds")
    total_energy_consumed: float = Field(default=0.0, description="Total energy consumed")
    collisions: int = Field(default=0, description="Number of collisions detected")
    timestamp: datetime = Field(default_factory=datetime.now, description="Execution completion timestamp")
    success: bool = Field(default=True, description="Whether execution was successful")
    error_message: Optional[str] = Field(None, description="Error message if execution failed")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ParseResult(BaseModel):
    """
    Parse result model.
    Contains the output of the parser service.
    """
    task: WarehouseTask = Field(..., description="Parsed warehouse task")
    raw_input: Optional[str] = Field(None, description="Original raw input text")
    confidence: float = Field(default=1.0, ge=0, le=1, description="Parser confidence")
    timestamp: datetime = Field(default_factory=datetime.now, description="Parse timestamp")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class HealthResponse(BaseModel):
    """
    Health check response model.
    """
    status: str = Field(..., description="Service status: 'ok' or 'error'")
    service: str = Field(..., description="Service name")
    version: str = Field(default="1.0.0", description="Service version")
    uptime_seconds: float = Field(..., description="Service uptime in seconds")
    dependencies: Dict[str, str] = Field(default_factory=dict, description="Dependency health status")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
