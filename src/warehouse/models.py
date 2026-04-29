# src/warehouse/models.py
"""AGV仓储调度系统 - 所有Pydantic数据模型"""

from __future__ import annotations
from enum import Enum
from pydantic import BaseModel, Field


# ── 枚举 ──

class AGVStatus(str, Enum):
    IDLE = "idle"
    MOVING_EMPTY = "moving_empty"
    MOVING_LOADED = "moving_loaded"
    LOADING = "loading"
    UNLOADING = "unloading"
    CHARGING = "charging"
    YIELDING = "yielding"
    MOVING_TO_CHARGE = "moving_to_charge"


class TaskType(str, Enum):
    INBOUND = "INBOUND"
    OUTBOUND = "OUTBOUND"
    TRANSFER = "TRANSFER"


class OrderPriority(int, Enum):
    URGENT = 10
    NORMAL = 5
    LOW = 1


# ── WMS层数据 ──

class InventoryItem(BaseModel):
    model: str
    part_name: str
    quantity: int
    location: str
    zone: str
    max_capacity: int = 4


class OrderItem(BaseModel):
    item_id: int
    task_type: TaskType
    model: str = ""
    part_name: str = ""
    quantity: int = 1
    target_location: str = ""


class WorkOrder(BaseModel):
    order_id: int
    source: str = "random"          # "vlm" | "batch" | "file" | "random"
    priority: OrderPriority = OrderPriority.NORMAL
    items: list[OrderItem] = []
    metadata: dict = {}


# ── WES层数据 ──

class TransportTask(BaseModel):
    task_id: int
    task_type: TaskType
    priority: OrderPriority = OrderPriority.NORMAL
    pick: str = ""
    dest: str = ""
    model: str = ""
    quantity: int = 1
    order_id: int = 0


class TaskCluster(BaseModel):
    cluster_id: int
    tasks: list[TransportTask] = []
    task_num: int = 0
    order_ids: list[int] = []
    priority: OrderPriority = OrderPriority.NORMAL
    zone: str = ""


# ── Fleet层数据 ──

class AGVState(BaseModel):
    agv_id: int
    init_pos: tuple[int, int]
    current_pos: tuple[int, int]
    battery: int = 100
    status: AGVStatus = AGVStatus.IDLE
    assigned_tasks: list[TransportTask] = []
    completed_count: int = 0


class TrajectoryStep(BaseModel):
    x: int
    y: int
    t: int
    state: str
    task_id: int


# ── 仿真结果 ──

class SimulationResult(BaseModel):
    makespan: int = 0
    total_distance: int = 0
    conflict_count: int = 0
    yield_count: int = 0
    yield_time: int = 0
    planning_time: float = 0.0
    path_calc_count: int = 0
    task_variance: float = 0.0
    agv_utilization: float = 0.0
    agv_trajectories: dict[int, list[TrajectoryStep]] = {}


# ── 消融开关 ──

class AblationFlags(BaseModel):
    enable_path_cache: bool = True       # M1: PathFinder缓存
    enable_clustering: bool = True       # M2: OrderClusterer
    enable_tsp: bool = True              # M3: TSPSolver
    enable_cp_sat: bool = True           # M4: CP-SAT全局分配
    enable_conflict_avoid: bool = True   # M5: ConflictManager


# ── 货架区域配置 ──

class RackRow(BaseModel):
    """一行货架"""
    row_id: str
    positions: list[str]
    y_offset: int


class AisleConfig(BaseModel):
    """巷道配置"""
    aisle_id: str
    direction: str           # "down" | "up"
    y_offset: int


class RackZoneConfig(BaseModel):
    """货架区域配置"""
    zone_id: str
    zone_type: str           # "mechanical" | "electrical" | "consumable" | "safety" | "tool"
    pos: tuple[int, int]
    width: int = 14
    height: int = 10
    num_rows: int = 5
    bays_per_row: int = 10
    sub_aisle_cols: list[int] = Field(default_factory=lambda: [3, 6, 9, 12])
    color: str = ""


# ── 地图配置 ──

class MapConfig(BaseModel):
    name: str
    display_name: str
    grid_size: int
    description: str = ""
    rack_zones: dict[str, RackZoneConfig] = {}
    main_aisle_width: int = 3
    sub_aisle_width: int = 1
    ports: dict[str, dict] = {}
    agv_init_positions: list[tuple[int, int]] = []
    agv_count: int = 8
    conflict_segments: dict[str, dict] = {}
    yield_points: dict[str, tuple[int, int]] = {}
    charging_points: list[tuple[int, int]] = []
    main_channels_x: list[int] = []
    main_channels_y: list[int] = []
