"""
Shared utilities for warehouse scheduling system.
"""
import time
import uuid
import logging
from typing import Any, Dict
from datetime import datetime


def generate_task_id() -> str:
    """Generate a unique task ID."""
    return f"task-{uuid.uuid4().hex[:8]}"


def generate_agv_id(agv_number: int) -> str:
    """Generate an AGV ID from its number."""
    return f"agv-{agv_number:03d}"


def generate_schedule_id() -> str:
    """Generate a unique schedule ID."""
    return f"schedule-{uuid.uuid4().hex[:8]}"


def generate_execution_id() -> str:
    """Generate a unique execution ID."""
    return f"execution-{uuid.uuid4().hex[:8]}"


def generate_conflict_id() -> str:
    """Generate a unique conflict ID."""
    return f"conflict-{uuid.uuid4().hex[:8]}"


def calculate_distance(
    pos1: tuple[float, float],
    pos2: tuple[float, float]
) -> float:
    """Calculate Euclidean distance between two positions."""
    return ((pos1[0] - pos2[0])**2 + (pos1[1] - pos2[1])**2)**0.5


def estimate_travel_time(
    distance: float,
    speed: float = 1.0
) -> float:
    """Estimate travel time given distance and speed."""
    return distance / speed if speed > 0 else float('inf')


class ServiceLogger:
    """Standardized logger for services."""

    @staticmethod
    def get_logger(name: str, level: str = "INFO") -> logging.Logger:
        """Get a configured logger instance."""
        logger = logging.getLogger(name)
        logger.setLevel(getattr(logging, level.upper(), logging.INFO))

        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)

        return logger


def format_error_response(
    error: Exception,
    service_name: str
) -> Dict[str, Any]:
    """Format an error response consistently."""
    return {
        "success": False,
        "error": str(error),
        "error_type": type(error).__name__,
        "service": service_name,
        "timestamp": datetime.now().isoformat()
    }


def validate_position(pos: tuple[float, float]) -> bool:
    """Validate that a position is valid."""
    return (
        isinstance(pos, tuple) and
        len(pos) == 2 and
        isinstance(pos[0], (int, float)) and
        isinstance(pos[1], (int, float))
    )


def clamp_position(
    pos: tuple[float, float],
    bounds: tuple[float, float, float, float]  # (min_x, min_y, max_x, max_y)
) -> tuple[float, float]:
    """Clamp a position within bounds."""
    min_x, min_y, max_x, max_y = bounds
    x = max(min_x, min(max_x, pos[0]))
    y = max(min_y, min(max_y, pos[1]))
    return (x, y)
