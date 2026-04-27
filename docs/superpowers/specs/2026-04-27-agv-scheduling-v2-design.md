# AGV智能仓储调度系统 v2 设计文档

> 日期: 2026-04-27
> 分支: feature/agv-scheduling-v2
> 状态: 设计确认（已修正审查问题），待实施

---

## 1. 概述

### 1.1 目标

将 `Code_20260420.py`（单文件1221行）重构为模块化架构，对齐实际智能仓储系统标准分层（WMS → WES → Fleet），与现有指令解析模块整合，优化仿真可视化美观度，提供可配置的测试地图方案。

### 1.2 约束

- 以当前 `Code_20260420.py` 的算法为基础，不额外扩展
- 仿真可视化保持学术风格（Matplotlib），增强美观性
- `main_interaction.py` 不修改，新建独立入口
- 保留单独测试功能

### 1.3 整合方式

- **主流程**: VLM解析 PortInstruction → WMS生成工单 → WES分解任务 → Fleet调度执行 → 仿真可视化
- **独立测试**: 支持批量仿真、消融实验、随机订单等模式
- **批量指令**: 支持逐行输入或文件加载多条指令，聚合后统一调度

---

## 2. 架构设计

### 2.1 四层对齐架构

参考 Geek+/Quicktron/HikRobot 等实际智能仓储系统的标准分层：

```
ERP/AI大模型 (PortInstruction)
    ↓
WMS层: 库存管理、工单生成、库位策略
    ↓
WES层: 订单分波、任务分解、聚类分组
    ↓
Fleet层: 路径规划→TSP排序→CP-SAT分配→冲突管理→充电调度
    ↓
仿真层: 轨迹执行、可视化、指标统计
```

### 2.2 目录结构

```
src/warehouse/
├── __init__.py
├── models.py                    # 所有Pydantic数据模型
│
├── wms/                         # WMS层
│   ├── __init__.py
│   ├── config.py                # Pydantic Settings 配置
│   ├── inventory.py             # 库存管理
│   └── order_manager.py         # 工单生成
│
├── wes/                         # WES层
│   ├── __init__.py
│   ├── task_decomposer.py       # WorkOrder → TransportTask
│   └── clustering.py            # 容量约束层次聚类
│
├── fleet/                       # Fleet层
│   ├── __init__.py
│   ├── map_builder.py           # 仓库地图构建
│   ├── pathfinding.py           # 时空A*寻路 + 缓存
│   ├── tsp.py                   # OR-Tools TSP排序
│   ├── allocator.py             # CP-SAT全局分配
│   ├── conflict.py              # 冲突路段 + 避让
│   ├── charging.py              # 充电感知调度
│   └── fleet_manager.py         # Fleet总调度编排
│
├── simulation/                  # 仿真层
│   ├── __init__.py
│   ├── agv.py                   # AGV状态机 + 轨迹记录
│   ├── simulator.py             # 仿真执行引擎
│   ├── metrics.py               # 指标统计
│   └── visualizer.py            # 可视化 + 动画 + 导出
│
└── maps/                        # 地图配置
    ├── __init__.py
    ├── base.py                  # 基类 + 注册机制
    ├── medium_50x50.py          # 中型地图
    ├── large_100x100.py         # 大型地图
    └── extreme.py               # 极端分布地图

项目根目录/
├── main_agv.py                  # AGV调度 + 指令解析整合入口
├── main_simulation.py           # 纯仿真测试入口（消融实验）
├── main_interaction.py          # 原指令解析入口（不动）
```

### 2.3 数据流

```
单条指令 ──→ VLM/Parser ──→ PortInstruction ──┐
批量指令 ──→ 逐行解析 ──→ List[PortInstruction]─┤
随机生成 ──→ OrderManager.from_random() ────────┤
                                                 ↓
                                    OrderManager → List[WorkOrder]
                                                 ↓
                                    TaskDecomposer → List[TransportTask]
                                                 ↓
                                    OrderClusterer → List[TaskCluster]
                                                 ↓
                                    FleetManager.schedule()
                                      ├─ PathFinder.precompute()
                                      ├─ TSPSolver.optimize()
                                      ├─ TaskAllocator.allocate()
                                      └─ ChargingScheduler + ConflictManager
                                                 ↓
                                    List[AGVState] + makespan
                                                 ↓
                                    Simulator.execute_trajectories()
                                                 ↓
                                    SimulationResult
                                                 ↓
                              ┌─────────────┬──────────────┐
                              ↓             ↓              ↓
                        控制台输出    Visualizer动画    ResultExporter文件
```

---

## 3. 数据模型 (`models.py`)

### 3.1 枚举

```python
class AGVStatus(str, Enum):
    IDLE = "idle"
    MOVING_EMPTY = "moving_empty"
    MOVING_LOADED = "moving_loaded"
    LOADING = "loading"
    UNLOADING = "unloading"
    CHARGING = "charging"
    YIELDING = "yielding"

class TaskType(str, Enum):
    INBOUND = "INBOUND"
    OUTBOUND = "OUTBOUND"
    TRANSFER = "TRANSFER"

class OrderPriority(int, Enum):
    URGENT = 10
    NORMAL = 5
    LOW = 1
```

### 3.2 WMS层数据

```python
class InventoryItem(BaseModel):
    model: str
    part_name: str
    quantity: int
    location: str
    zone: str
    max_capacity: int = 4

class WorkOrder(BaseModel):
    order_id: int
    source: str                   # "vlm" | "batch" | "file" | "random"
    priority: OrderPriority
    items: list[OrderItem]

class OrderItem(BaseModel):
    item_id: int
    task_type: TaskType
    model: str
    part_name: str
    quantity: int
    target_location: str = ""
```

### 3.3 WES层数据

```python
class TransportTask(BaseModel):
    task_id: int
    task_type: TaskType
    priority: OrderPriority
    pick: str
    dest: str
    model: str
    quantity: int
    order_id: int

class TaskCluster(BaseModel):
    cluster_id: int
    tasks: list[TransportTask]
    task_num: int
    order_ids: list[int]
    priority: OrderPriority
    zone: str = ""
```

### 3.4 Fleet层数据

```python
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
```

### 3.5 仿真结果

```python
class SimulationResult(BaseModel):
    makespan: int
    total_distance: int
    conflict_count: int
    yield_count: int
    yield_time: int
    planning_time: float
    path_calc_count: int
    task_variance: float
    agv_utilization: float
    agv_trajectories: dict[int, list[TrajectoryStep]]
```

### 3.6 地图配置

```python
class MapConfig(BaseModel):
    name: str
    display_name: str
    grid_size: int
    description: str
    warehouse_zones: dict
    ports: dict
    agv_init_positions: list[tuple[int, int]]
    agv_count: int
    conflict_segments: dict
    yield_points: dict
    charging_points: list[tuple[int, int]]
    main_channels_x: list[int]
    main_channels_y: list[int]
```

---

## 4. WMS层详细设计

### 4.1 config.py — 全局配置

```python
class WarehouseConfig(BaseSettings):
    MAP_NAME: str = "medium_50x50"

    AGV_MOVE_TIME: int = 1
    AGV_ACCEL_TIME: int = 2
    AGV_DECEL_TIME: int = 2
    AGV_TURN_TIME: int = 3
    AGV_LOAD_UNLOAD_TIME: int = 8

    AGV_MAX_BATTERY: int = 100
    AGV_CHARGE_RATE: int = 5
    AGV_CONSUME_RATE: int = 1
    AGV_CHARGE_TIME: int = 20
    AGV_LOW_BATTERY_THRESHOLD: int = 20

    AGV_MAX_TASK_CAPACITY: int = 20
    ORDER_NUM: int = 40
    MIN_SUBTASK_PER_ORDER: int = 2
    MAX_SUBTASK_PER_ORDER: int = 6

    TSP_TIME_LIMIT: int = 1
    CP_SAT_TIME_LIMIT: int = 30
    A_MAX_SEARCH: int = 5000
    RANDOM_SEED: int = 42

    FIG_SIZE: tuple[int, int] = (18, 18)
    FIG_DPI: int = 100
    ANIM_INTERVAL: int = 30

    class Config:
        env_prefix = "WH_"
```

### 4.2 inventory.py — 库存管理

```python
class InventoryManager:
    def __init__(self, map_config: MapConfig): ...
    def query_by_model(self, model: str) -> InventoryItem | None: ...
    def query_by_zone(self, zone: str) -> list[InventoryItem]: ...
    def allocate_stock(self, model: str, quantity: int) -> str: ...
    def receive_stock(self, model: str, quantity: int, zone: str = "") -> str: ...
    def get_all_locations(self) -> dict[str, tuple[int, int]]: ...
    def get_status(self) -> dict[str, int]: ...
```

### 4.3 order_manager.py — 工单生成

```python
class OrderManager:
    def __init__(self, inventory: InventoryManager): ...
    def from_port_instruction(self, instruction: PortInstruction) -> WorkOrder | None: ...
    def from_instructions(self, instructions: list[PortInstruction]) -> list[WorkOrder]: ...
    def from_random(self, count: int, inventory: InventoryManager) -> list[WorkOrder]: ...
    def from_file(self, filepath: str) -> list[WorkOrder]: ...
```

---

## 5. WES层详细设计

### 5.1 task_decomposer.py

```python
class TaskDecomposer:
    def __init__(self, inventory: InventoryManager, config: WarehouseConfig): ...
    def decompose(self, work_orders: list[WorkOrder]) -> list[TransportTask]: ...
    def _resolve_locations(self, item: OrderItem) -> tuple[str, str]: ...
```

### 5.2 clustering.py

```python
class OrderClusterer:
    def __init__(self, path_finder: PathFinder, config: WarehouseConfig): ...
    def cluster(self, tasks: list[TransportTask],
                max_capacity: int,
                zone_pos: dict[str, tuple[int, int]]) -> list[TaskCluster]: ...
```

依赖Fleet层 `PathFinder` 计算距离，通过构造函数注入。

---

## 6. Fleet层详细设计

### 6.1 map_builder.py

```python
class WarehouseMap:
    def __init__(self, map_config: MapConfig): ...
    def _build(self): ...
    def get_distance_matrix(self) -> dict[str, int]: ...
    def visualize_base_map(self) -> plt.Figure: ...
```

封装原代码的11个全局变量（grid_map, ZONE_POS, PORT_INFO, STORAGE_LIST, WAREHOUSE_ZONES等）。

### 6.2 pathfinding.py

```python
class PathFinder:
    def __init__(self, warehouse_map: WarehouseMap, config: WarehouseConfig): ...
    def precompute_all_paths(self): ...
    def find_base_path(self, start, end) -> tuple[list, int]: ...
    def find_path(self, start, end, load_state, init_dir, step, agv_id) -> tuple[list, int, int]: ...
    def get_distance(self, start, end) -> int: ...
```

### 6.3 tsp.py

```python
class TSPSolver:
    def __init__(self, path_finder: PathFinder, config: WarehouseConfig): ...
    def optimize(self, tasks, agv_pos, zone_pos) -> tuple[list, int]: ...
```

### 6.4 allocator.py

```python
class TaskAllocator:
    def __init__(self, path_finder: PathFinder, tsp: TSPSolver, config: WarehouseConfig): ...
    def allocate(self, clusters, agv_states) -> tuple[dict, int]: ...
    def _greedy_allocate(self, ...) -> tuple[dict, int]: ...
```

### 6.5 conflict.py

```python
class ConflictManager:
    def __init__(self, warehouse_map: WarehouseMap, st_table): ...
    def request_segment(self, agv, seg_id, direction, time_step) -> bool: ...
    def request_yield(self, agv, seg_id, time_step): ...
    def release_segment(self, agv, seg_id): ...
```

### 6.6 charging.py

```python
class ChargingScheduler:
    def __init__(self, path_finder, warehouse_map, config): ...
    def plan_charging(self, agv_state, current_pos, current_t) -> tuple[list, int]: ...
    def estimate_battery_usage(self, path_length: int) -> int: ...
```

### 6.7 fleet_manager.py

```python
class FleetManager:
    def __init__(self, warehouse_map: WarehouseMap, config: WarehouseConfig): ...
    def schedule(self, tasks: list[TransportTask]) -> tuple[list[AGVState], int]: ...
```

编排五步流程：路径预计算 → (WES已完成聚类) → TSP排序 → CP-SAT分配 → 充电+冲突→轨迹。

Fleet层依赖关系：
```
MapConfig → WarehouseMap ←── 所有模块
WarehouseMap → PathFinder ←── TSPSolver ←── TaskAllocator
PathFinder → ConflictManager, ChargingScheduler
所有子模块 → FleetManager（编排）
```

---

## 7. 仿真层详细设计

### 7.1 agv.py — AGV状态机

```python
class AGV:
    def __init__(self, agv_id: int, init_pos: tuple, max_steps: int): ...
    def record_path(self, path, start_t, state, task_id) -> int: ...
    def record_wait(self, pos, start_t, duration, state, task_id) -> int: ...
    def update_position(self, path): ...
    def consume_battery(self, steps: int): ...
    def charge_full(self): ...
```

### 7.2 simulator.py — 仿真引擎

```python
class Simulator:
    def __init__(self, warehouse_map, fleet, config): ...
    def run(self, work_orders: list[WorkOrder]) -> SimulationResult: ...
    def run_from_tasks(self, clusters, allocation) -> SimulationResult: ...
    def _execute_agv_trajectory(self, agv: AGV, tasks: list[TransportTask]) -> int: ...
```

### 7.3 metrics.py — 指标统计

```python
class MetricsCollector:
    @staticmethod
    def collect(agvs, makespan, planning_time, st_table) -> SimulationResult: ...
    @staticmethod
    def compare(results: dict[str, SimulationResult]) -> str: ...
```

### 7.4 visualizer.py — 可视化

#### 视觉风格常量

```python
class VisualStyle:
    ZONE_COLORS = {
        "Raw":      {"fill": "#FFE0B2", "edge": "#FF9800", "label": "#E65100"},
        "Finished": {"fill": "#C8E6C9", "edge": "#4CAF50", "label": "#1B5E20"},
        "Spare":    {"fill": "#E1BEE7", "edge": "#9C27B0", "label": "#4A148C"},
    }
    PORT_COLORS = {
        "INBOUND":  {"fill": "#BBDEFB", "edge": "#2196F3", "label": "#0D47A1"},
        "OUTBOUND": {"fill": "#FFCDD2", "edge": "#F44336", "label": "#B71C1C"},
    }
    AGV_COLORS = ["#E74C3C", "#3498DB", "#2ECC71", "#F39C12",
                  "#9B59B6", "#1ABC9C", "#E91E63", "#8BC34A"]
    ROAD_COLOR = "#ECEFF1"
    OBSTACLE_COLOR = "#37474F"
    CHARGE_COLOR = "#FFF176"
    YIELD_COLOR = "#80CBC4"
    TITLE_FONT = {"family": "SimHei", "size": 16, "weight": "bold"}
    LABEL_FONT = {"family": "SimHei", "size": 9}
    STATUS_FONT = {"family": "DejaVu Sans Mono", "size": 10}
    ANIM_INTERVAL = 30
    TRAIL_ALPHA = 0.15
    AGV_SIZE = 120
    AGV_EDGE_WIDTH = 1.5
```

#### 可视化方法

```python
class Visualizer:
    def __init__(self, warehouse_map, config): ...
    def plot_base_map(self) -> plt.Figure: ...
    def plot_snapshot(self, agvs, step) -> plt.Figure: ...
    def animate(self, agvs, makespan, export=None, show=True): ...
    def plot_metrics_comparison(self, results) -> plt.Figure: ...
    def plot_gantt(self, agvs, makespan) -> plt.Figure: ...
```

#### 导出能力

```python
class ExportConfig(BaseModel):
    format: str = "gif"              # "gif" | "mp4" | "frames" | None
    path: str = "output/"
    fps: int = 15
    dpi: int = 150
    static_formats: list[str] = ["png", "pdf"]
    save_static: bool = True

class ResultExporter:
    @staticmethod
    def export_json(result, path): ...
    @staticmethod
    def export_summary(result, path): ...
    @staticmethod
    def export_trajectory(result, path): ...

class Visualizer:  # 导出方法
    def export_animation_frames(self, agvs, makespan, output_dir, dpi=150): ...
    def export_gif(self, agvs, makespan, path, fps=15, dpi=100): ...
    def export_mp4(self, agvs, makespan, path, fps=15, dpi=150): ...
    def export_static_plots(self, agvs, makespan, output_dir, formats=["png", "pdf"]): ...
```

输出内容：
- 动画GIF / MP4视频
- 帧序列（PNG）
- 最终状态地图（PNG + PDF）
- AGV甘特图（PNG + PDF）
- 利用率对比柱状图（PNG + PDF）
- 指标数据（JSON）
- 轨迹数据（CSV）

依赖：
- GIF: matplotlib PillowWriter + pillow
- MP4: ffmpeg
- 静态图: matplotlib

---

## 8. 地图配置详细设计

### 8.1 注册机制

```python
class MapRegistry:
    _maps: dict[str, type] = {}
    @classmethod
    def register(cls, name: str): ...   # 装饰器
    @classmethod
    def get(cls, name: str) -> MapConfig: ...
    @classmethod
    def list_all(cls) -> list[tuple[str, str]]: ...

class BaseMap(ABC):
    @abstractmethod
    def build(self) -> MapConfig: ...
```

### 8.2 预设地图

| 地图名 | 网格 | AGV | 仓库区 | 端口 | 冲突路段 | 用途 |
|--------|------|-----|--------|------|----------|------|
| medium_50x50 | 50x50 | 8 | 12 | 4 | 4 | 默认中规模 |
| large_100x100 | 100x100 | 20 | 24 | 8 | 8 | 大规模压力测试 |
| extreme_corner | 50x50 | 8 | 12 | 4 | 4 | 仓库集中在四角 |
| extreme_corridor | 50x50 | 8 | 8 | 4 | 2 | 单通道瓶颈 |
| extreme_cluster | 50x50 | 8 | 12 | 4 | 4 | 储位高度集中 |

### 8.3 自定义扩展

用户创建文件，继承 `BaseMap`，使用 `@MapRegistry.register()` 装饰器注册，填充 `MapConfig` 即可。

---

## 9. 入口文件设计

### 9.1 main_agv.py

```python
class AGVSystemApp:
    def __init__(self):
        self.config = WarehouseConfig()
        self.wms = WarehouseManager(self.config)
        self.simulator = Simulator(...)
        self.visualizer = Visualizer(...)

    def run_interactive_mode(self):
        """模式1：单条指令 → 自动调度"""

    def run_batch_instruction_mode(self):
        """模式2：批量指令（逐行输入/文件加载）→ 聚合调度"""

    def run_batch_simulation(self):
        """模式3：随机订单 → 性能测试"""

    def run_ablation_suite(self):
        """模式4：消融实验"""

    def select_map(self):
        """模式5：地图选择"""
```

CLI菜单：
```
╔══════════════════════════════════════════════════╗
║        AGV 智能仓储调度系统  v2.0                 ║
╠══════════════════════════════════════════════════╣
║  [1] 单条指令调度（自然语言 → 自动调度）          ║
║  [2] 批量指令调度（多行/文件输入 → 批量调度）     ║
║  [3] 批量仿真测试（随机订单 → 性能测试）          ║
║  [4] 消融实验（对比各模块贡献）                   ║
║  [5] 地图选择（当前：中型50x50）                  ║
║  [q] 退出                                       ║
╚══════════════════════════════════════════════════╝
```

控制台输出使用Unicode盒子字符 + 进度条 + 格式化面板。美观规范包括：
- 进度条显示各阶段耗时
- 结果面板用表格展示关键指标
- AGV利用率用进度条可视化
- 消融对比用对齐表格

### 9.2 main_simulation.py

纯仿真测试入口，直接调用 Simulator + Visualizer，不依赖VLM/Parser。支持命令行参数指定地图、订单数、AGV数等。

---

## 10. 依赖变更

`requirements.txt` 新增：
```
ortools>=9.8.3296
matplotlib>=3.7.0
pillow>=10.0.0
```

---

## 11. 与原代码的对应关系

| 原代码 (Code_20260420.py) | 新模块 |
|---|---|
| `Config` | `wms/config.py: WarehouseConfig` |
| `AblationConfig` | `simulator/simulator.py` 内部开关 |
| `AGVStatus`, `LoadStatus` | `models.py: AGVStatus` |
| 全局变量 (grid_map, ZONE_POS等11个) | `fleet/map_builder.py: WarehouseMap` |
| `SpaceTimeTable` | `fleet/pathfinding.py` 内部类 |
| `SpaceTimeAStar` | `fleet/pathfinding.py: PathFinder` |
| `OrderClustering` | `wes/clustering.py: OrderClusterer` |
| `TSPTaskOptimizer` | `fleet/tsp.py: TSPSolver` |
| `MILPTaskAllocator` | `fleet/allocator.py: TaskAllocator` |
| `RoadSegment`, `YieldPoint` | `fleet/conflict.py` 内部类 |
| `ConflictScheduler` | `fleet/conflict.py: ConflictManager` |
| `AGVSchedule` | `simulation/agv.py: AGV` |
| `BatchTaskScheduler` | `simulation/simulator.py: Simulator` |
| `calculate_metrics` | `simulation/metrics.py: MetricsCollector` |
| `run_ablation_experiment` | `main_simulation.py` |
| `init_map` | `fleet/map_builder.py: WarehouseMap._build()` |
| matplotlib绘图代码 | `simulation/visualizer.py: Visualizer` |

---

## 12. PortInstruction → WorkOrder 映射（审查补充）

### 12.1 字段映射规则

| PortInstruction字段 | WorkOrder/OrderItem字段 | 映射逻辑 |
|---------------------|------------------------|----------|
| `part_name` | `OrderItem.part_name` | 直接映射 |
| `model` | `OrderItem.model` | 零件型号（主键），用于查询InventoryItem定位储位 |
| `quantity` | `OrderItem.quantity` | 直接映射 |
| `action_required` | `OrderItem.task_type` | "更换"/"领取"/"出库" → OUTBOUND; "入库"/"补充"/"补货" → INBOUND; 其他默认 OUTBOUND |
| `location` | `OrderItem.target_location` | 自由文本，记录目标但不参与储位解析 |
| `installation_equipment` | 不直接映射 | 辅助信息，记录在WorkOrder.metadata中 |
| `description` | 不直接映射 | 辅助信息，记录在WorkOrder.metadata中 |

### 12.2 空字段处理

- `model` 为 None 时：按 `part_name` 模糊匹配库存，仍无结果则返回错误提示
- `quantity` 为 None 时：默认为 1
- `action_required` 为 None 时：默认为 OUTBOUND（领料场景为主）
- 所有字段均为 None 时：拒绝生成工单，提示重新输入

### 12.3 model字段语义统一

`InventoryItem.model` = 零件型号（如 "M200", "HYD-500"），是库存查询的主键。
`OrderItem.model` = 同零件型号，用于关联库存。
初始库存由地图配置决定，各储位预填随机零件型号和数量（仿真模式）。
实际部署时对接真实WMS数据。

### 12.4 映射示例

```
输入: PortInstruction(part_name="电机", model="M200", quantity=5,
                      action_required="领取", location="1号桥吊")

处理流程:
1. task_type = "领取" → OUTBOUND
2. InventoryManager.query_by_model("M200") → InventoryItem(location="Raw1_S2", quantity=12)
3. InventoryManager.allocate_stock("M200", 5) → "Raw1_S2" (库存扣减为7)
4. 出库端口选择 → "出库南"

输出: WorkOrder(order_id=1, source="vlm", priority=NORMAL, items=[
    OrderItem(task_type=OUTBOUND, model="M200", part_name="电机", quantity=5,
              pick="Raw1_S2", dest="出库南", target_location="1号桥吊")
])
```

---

## 13. 系统初始化与生命周期（审查补充）

### 13.1 初始化顺序

由于WES层聚类需要Fleet层PathFinder的距离数据，实际初始化顺序为：

```
1. WarehouseConfig        ← 加载配置
2. MapConfig              ← 选择地图
3. WarehouseMap           ← 构建地图（所有层共享）
4. PathFinder             ← 预计算路径缓存
5. InventoryManager       ← 初始化库存
6. OrderManager           ← 依赖 InventoryManager
7. TaskDecomposer         ← 依赖 InventoryManager
8. OrderClusterer         ← 依赖 PathFinder（距离计算）
9. TSPSolver              ← 依赖 PathFinder
10. TaskAllocator         ← 依赖 PathFinder + TSPSolver
11. ConflictManager       ← 依赖 WarehouseMap
12. ChargingScheduler     ← 依赖 PathFinder + WarehouseMap
13. FleetManager          ← 编排 4-12 所有Fleet子模块
14. Simulator             ← 依赖 FleetManager
15. Visualizer            ← 依赖 WarehouseMap
```

### 13.2 依赖注入方式

`Simulator`（或 `main_agv.py` 中的 `AGVSystemApp`）负责按上述顺序创建所有组件，通过构造函数注入。不使用全局变量或服务定位器。

### 13.3 SpaceTimeTable所有权

`SpaceTimeTable` 由 `PathFinder` 内部创建并持有。`ConflictManager` 和 `MetricsCollector` 通过方法参数或构造函数注入获取引用。`PathFinder` 是唯一创建者。

---

## 14. 充电编排流程（审查补充）

### 14.1 Simulator与ChargingScheduler交互

```python
# Simulator._execute_agv_trajectory 伪代码
for task in agv.assigned_tasks:
    # 检查电量
    if agv.battery < config.AGV_LOW_BATTERY_THRESHOLD:
        # 1. 充电调度器计算最近充电桩 + 路径
        charge_path, charge_end_t = charging.plan_charging(
            agv.state, agv.current_pos, current_t
        )
        # 2. 记录移动到充电桩
        current_t = agv.record_path(charge_path, current_t, "moving_to_charge", -1)
        # 3. 记录充电等待
        current_t = agv.record_wait(charge_pos, current_t, config.AGV_CHARGE_TIME, "charging", -1)
        # 4. 恢复电量
        agv.charge_full()
        agv.current_pos = charge_pos

    # 正常任务执行...
    path_to_pick = pathfinder.find_path(...)
    current_t = agv.record_path(path_to_pick, current_t, "moving_empty", task.task_id)
    agv.consume_battery(len(path_to_pick))
    # ... 装载、移动、卸载 ...
```

关键：ChargingScheduler 只返回数据和路径，不修改AGV状态。状态变更全由Simulator通过AGV对象方法完成。

---

## 15. 消融开关传播（审查补充）

### 15.1 AblationFlags

```python
class AblationFlags(BaseModel):
    """消融实验开关，放在 models.py 中"""
    enable_path_cache: bool = True      # M1: PathFinder缓存
    enable_clustering: bool = True      # M2: OrderClusterer
    enable_tsp: bool = True             # M3: TSPSolver
    enable_cp_sat: bool = True          # M4: TaskAllocator CP-SAT
    enable_conflict_avoid: bool = True  # M5: ConflictManager
```

### 15.2 传播方式

- `AblationFlags` 作为 `WarehouseConfig` 的子字段
- 各模块在构造时接收 `config`，内部读取对应标志
- 禁用时降级行为：
  - M1关：每次都重新计算路径
  - M2关：每个订单独立为单任务簇
  - M3关：按优先级排序替代TSP
  - M4关：贪心分配替代CP-SAT
  - M5关：忽略冲突路段，直线路径

---

## 16. 目录迁移（审查补充）

### 16.1 现有目录清理

`src/warehouse/` 当前仅有 `__pycache__/` 目录（源码已被删除）。
实施时先清理所有 `__pycache__/` 目录，然后按新结构创建。

### 16.2 清理命令

```bash
find src/warehouse/ -name "__pycache__" -type d -exec rm -rf {} +
```

---

## 17. 其他修正（审查补充）

### 17.1 Pydantic v2配置风格

```python
class WarehouseConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WH_")
    # ... 字段 ...
```

### 17.2 AGV颜色循环

```python
# VisualStyle
AGV_COLORS = ["#E74C3C", "#3498DB", "#2ECC71", "#F39C12",
              "#9B59B6", "#1ABC9C", "#E91E63", "#8BC34A"]
# 使用时：AGV_COLORS[i % len(AGV_COLORS)] 循环取色
```

### 17.3 字体回退链

```python
TITLE_FONT = {"family": ["SimHei", "DejaVu Sans"], "size": 16, "weight": "bold"}
```

### 17.4 移除time.sleep

原始代码中 `ConflictScheduler.request_yield()` 的 `time.sleep(0.05)` 在仿真中无意义（基于时间步规划，非实时执行）。重构后移除所有 `time.sleep` 调用。

### 17.5 极端地图统一在extreme.py

三个极端变体（extreme_corner, extreme_corridor, extreme_cluster）统一放在 `extreme.py` 一个文件中，每个是独立的类。

### 17.6 ResultExporter类型注解

```python
class ResultExporter:
    @staticmethod
    def export_json(result: SimulationResult, path: str) -> None: ...
    @staticmethod
    def export_summary(result: SimulationResult, path: str) -> None: ...
    @staticmethod
    def export_trajectory(result: SimulationResult, path: str) -> None: ...
```

---

## 18. 风险评估

| 风险 | 等级 | 缓解措施 |
|------|------|----------|
| OR-Tools版本兼容性 | 中 | time_limit使用整数秒，已验证 |
| Pydantic v2序列化tuple | 低 | 使用 SettingsConfigDict，tuple字段作为不可配置常量 |
| 大地图(100x100)性能 | 中 | 路径缓存预计算，CP-SAT限时 |
| ffmpeg缺失导致MP4导出失败 | 低 | 降级为GIF，提示安装 |
| PortInstruction空字段 | 中 | 默认值+模糊匹配+错误提示（见12.2节） |

---

## 19. 验收标准

1. `main_agv.py` 五种模式均可运行
2. `main_simulation.py` 消融实验结果与原代码一致（makespan误差 <5%）
3. 三类预设地图可加载运行
4. 仿真动画流畅，静态图可导出PNG/PDF
5. 控制台输出格式化美观
6. 所有模块无全局变量依赖
7. 用户可通过 `@MapRegistry.register()` 扩展地图
