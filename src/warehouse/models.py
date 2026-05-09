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
    enable_clustering: bool = True       # M2: 方向感知空间聚类
    enable_tsp: bool = True              # M3: OR-Tools TSP排序
    enable_batch: bool = True            # M4: 双向Batch（多取一送/一取多送）


# ── 货架区域配置 ──

class RackZoneConfig(BaseModel):
    """货架区域配置"""
    zone_id: str
    zone_type: str           # "mechanical" | "electrical" | "consumable" | "safety" | "tool"
    pos: tuple[int, int]     # 左上角位置
    width: int = 14          # 区域宽度（列数）
    height: int = 10         # 区域高度（行数）
    color: str = ""


# ── 地图配置 ──

class MapConfig(BaseModel):
    name: str
    display_name: str
    grid_size: int              # grid width (x dimension)
    grid_height: int = 0        # grid height (y dimension), 0 means use grid_size
    description: str = ""
    rack_zones: dict[str, RackZoneConfig] = {}
    ports: dict[str, dict] = {}
    agv_init_positions: list[tuple[int, int]] = []
    agv_count: int = 8
    charging_points: list[tuple[int, int]] = []
