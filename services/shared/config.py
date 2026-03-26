"""
Shared configuration for warehouse scheduling system.
Uses environment variables for service configuration.
"""
import os
from typing import List
from pydantic_settings import BaseSettings
from functools import lru_cache


class ParserServiceConfig(BaseSettings):
    """Configuration for Parser Service."""
    service_name: str = "parser_service"
    host: str = "127.0.0.1"
    port: int = 8001
    log_level: str = "INFO"

    # VLM integration
    vlm_timeout: int = 30
    use_rag: bool = True
    max_retries: int = 3

    model_config = {"extra": "ignore"}


class SchedulerServiceConfig(BaseSettings):
    """Configuration for Scheduler Service."""
    service_name: str = "scheduler_service"
    host: str = "127.0.0.1"
    port: int = 8002
    log_level: str = "INFO"

    # OR-Tools settings
    solver_timeout_seconds: int = 30
    max_solutions: int = 1

    # VLM arbitration
    enable_vlm_arbitration: bool = True
    vlm_arbitration_threshold: float = 0.7  # Trigger VLM if confidence below this
    vlm_timeout: int = 10

    # Conflict detection
    enable_conflict_detection: bool = True
    min_distance_threshold: float = 2.0  # Minimum distance between AGVs

    model_config = {"extra": "ignore"}


class SimulationServiceConfig(BaseSettings):
    """Configuration for Simulation Service."""
    service_name: str = "simulation_service"
    host: str = "127.0.0.1"
    port: int = 8003
    log_level: str = "INFO"

    # Gymnasium environment
    warehouse_width: float = 100.0
    warehouse_height: float = 100.0
    time_step: float = 0.1  # seconds
    max_episode_steps: int = 1000

    # AGV settings
    agv_speed: float = 1.0  # m/s
    agv_battery_drain_rate: float = 0.01  # per second
    agv_charging_rate: float = 1.0  # per second

    model_config = {"extra": "ignore"}


class ServiceConfig(BaseSettings):
    """Global service configuration."""
    environment: str = os.getenv("ENVIRONMENT", "development")
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # Service endpoints
    parser_url: str = os.getenv("PARSER_URL", "http://127.0.0.1:8001")
    scheduler_url: str = os.getenv("SCHEDULER_URL", "http://127.0.0.1:8002")
    simulation_url: str = os.getenv("SIMULATION_URL", "http://127.0.0.1:8003")

    # HTTP client settings
    http_timeout: int = 5
    http_max_retries: int = 3

    model_config = {"extra": "ignore"}


@lru_cache()
def get_parser_config() -> ParserServiceConfig:
    """Get parser service configuration (cached)."""
    return ParserServiceConfig()


@lru_cache()
def get_scheduler_config() -> SchedulerServiceConfig:
    """Get scheduler service configuration (cached)."""
    return SchedulerServiceConfig()


@lru_cache()
def get_simulation_config() -> SimulationServiceConfig:
    """Get simulation service configuration (cached)."""
    return SimulationServiceConfig()


@lru_cache()
def get_service_config() -> ServiceConfig:
    """Get global service configuration (cached)."""
    return ServiceConfig()
