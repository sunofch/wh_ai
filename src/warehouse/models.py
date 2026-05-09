# src/warehouse/models.py
"""AGV仓储调度系统 - 所有Pydantic数据模型

数据模型按四层架构组织:
  WMS层: InventoryItem, OrderItem, WorkOrder
  WES层: TransportTask, TaskCluster
  Fleet层: AGVState, TrajectoryStep
  仿真结果: SimulationResult
配置: AblationFlags, RackZoneConfig, MapConfig
"""

from __future__ import annotations
from enum import Enum
from pydantic import BaseModel, Field


# ── 枚举 ──

class AGVStatus(str, Enum):
    """AGV状态机状态，仿真引擎按此记录轨迹"""
    IDLE = "idle"                     # 空闲
    MOVING_EMPTY = "moving_empty"     # 空载移动
    MOVING_LOADED = "moving_loaded"   # 载货移动
    LOADING = "loading"               # 装货
    UNLOADING = "unloading"           # 卸货
    CHARGING = "charging"             # 充电中
    MOVING_TO_CHARGE = "moving_to_charge"  # 前往充电桩


class TaskType(str, Enum):
    """任务方向，决定batch模式: OUTBOUND多取一送, INBOUND一取多送"""
    INBOUND = "INBOUND"     # 入库: 端口→货架
    OUTBOUND = "OUTBOUND"   # 出库: 货架→端口
    TRANSFER = "TRANSFER"   # 移库: 货架→货架 (按OUTBOUND模式处理)


class OrderPriority(int, Enum):
    """工单优先级，值越大越优先"""
    URGENT = 10
    NORMAL = 5
    LOW = 1


# ── WMS层数据 ──

class InventoryItem(BaseModel):
    """库存条目: 一个型号对应一个储位"""
    model: str
    part_name: str
    quantity: int
    location: str               # 储位名, 如 "Mech1_R2_B5"
    zone: str                   # 区域名, 如 "Mech1"
    max_capacity: int = 4


class OrderItem(BaseModel):
    """工单中的单项, 指明方向和目标位置"""
    item_id: int
    task_type: TaskType
    model: str = ""
    part_name: str = ""
    quantity: int = 1
    target_location: str = ""   # 端口名或储位名


class WorkOrder(BaseModel):
    """工单: 来自随机生成或VLM解析"""
    order_id: int
    source: str = "random"          # "vlm" | "batch" | "file" | "random"
    priority: OrderPriority = OrderPriority.NORMAL
    items: list[OrderItem] = []
    metadata: dict = {}


# ── WES层数据 ──

class TransportTask(BaseModel):
    """运输任务: 从pick位置取货, 送至dest位置"""
    task_id: int
    task_type: TaskType
    priority: OrderPriority = OrderPriority.NORMAL
    pick: str = ""              # 取货储位名
    dest: str = ""              # 送货储位名
    model: str = ""
    quantity: int = 1
    order_id: int = 0


class TaskCluster(BaseModel):
    """任务簇: 一组空间相近、方向一致的任务, 作为分配的最小单位"""
    cluster_id: int
    tasks: list[TransportTask] = []
    task_num: int = 0
    order_ids: list[int] = []
    priority: OrderPriority = OrderPriority.NORMAL
    zone: str = ""              # 主区域名, 用于标识簇所在位置


# ── Fleet层数据 ──

class AGVState(BaseModel):
    """AGV初始状态, 用于Fleet层分配计算"""
    agv_id: int
    init_pos: tuple[int, int]
    current_pos: tuple[int, int]
    battery: int = 100
    status: AGVStatus = AGVStatus.IDLE
    assigned_tasks: list[TransportTask] = []
    completed_count: int = 0


class TrajectoryStep(BaseModel):
    """轨迹单步: 记录AGV在每个时刻的位置和状态"""
    x: int
    y: int
    t: int
    state: str
    task_id: int


# ── 仿真结果 ──

class SimulationResult(BaseModel):
    """仿真结果汇总"""
    makespan: int = 0               # 最大完成时间步
    total_distance: int = 0         # 所有AGV移动总距离(曼哈顿)
    planning_time: float = 0.0      # 规划阶段耗时(秒)
    path_calc_count: int = 0        # A*路径计算次数
    task_variance: float = 0.0      # AGV间任务数方差
    agv_utilization: float = 0.0    # AGV平均利用率
    agv_trajectories: dict[int, list[TrajectoryStep]] = {}


# ── 消融开关 ──

class AblationFlags(BaseModel):
    """消融实验开关: M1路径缓存 / M2聚类 / M3 TSP排序, batch常驻不关闭"""
    enable_path_cache: bool = True       # M1: PathFinder缓存
    enable_clustering: bool = True       # M2: 方向感知空间聚类
    enable_tsp: bool = True              # M3: OR-Tools TSP排序


# ── 货架区域配置 ──

class RackZoneConfig(BaseModel):
    """货架区域配置: 一个区域内含多行货架, 每行多组储位"""
    zone_id: str
    zone_type: str           # "mechanical" | "electrical" | "consumable" | "safety" | "tool"
    pos: tuple[int, int]     # 左上角位置 (x, y)
    width: int = 14          # 区域宽度（列数）
    height: int = 10         # 区域高度（行数）
    color: str = ""


# ── 地图配置 ──

class MapConfig(BaseModel):
    """地图完整配置: 网格尺寸、货架区域、端口(含泊位)、AGV初始位置、充电桩"""
    name: str
    display_name: str
    grid_size: int              # grid宽度 (x维度)
    grid_height: int = 0        # grid高度 (y维度), 0则使用grid_size
    description: str = ""
    rack_zones: dict[str, RackZoneConfig] = {}
    ports: dict[str, dict] = {}  # 端口配置, 含 pos/area/type/berths
    agv_init_positions: list[tuple[int, int]] = []
    agv_count: int = 8
    charging_points: list[tuple[int, int]] = []
