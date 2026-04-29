# AGV 智能仓储调度系统 v2.0

港口备件仓储场景下的多 AGV 协同调度仿真系统。支持双向任务流（出库 + 入库）、方向感知聚类、时空 A* 路径规划、CP-SAT 全局分配和消融实验。

## 架构概览

```
┌─────────────────────────────────────────────────────┐
│                    Simulation Layer                   │
│  Simulator ─ AGV State Machine ─ Metrics ─ Visualizer │
├─────────────────────────────────────────────────────┤
│                     Fleet Layer                       │
│  FleetManager ─ TaskAllocator ─ TSPSolver ─ PathFinder │
│               ConflictManager   ChargingScheduler     │
├─────────────────────────────────────────────────────┤
│                      WES Layer                        │
│            TaskDecomposer ─ OrderClusterer             │
├─────────────────────────────────────────────────────┤
│                      WMS Layer                        │
│      WarehouseConfig ─ InventoryManager ─ OrderManager │
├─────────────────────────────────────────────────────┤
│              Data & Infrastructure                    │
│   Pydantic Models ─ MapConfig ─ MapRegistry ─ Maps    │
└─────────────────────────────────────────────────────┘
```

系统采用四层架构，数据流自上而下贯穿：

1. **WMS Layer** — 仓库管理：配置管理、库存管理、工单生成
2. **WES Layer** — 仓储执行：工单分解为运输任务、方向感知层次聚类
3. **Fleet Layer** — 车队调度：路径规划、TSP 排序、CP-SAT 分配、冲突管理、充电调度
4. **Simulation Layer** — 仿真执行：AGV 状态机、仿真引擎、指标统计、可视化

## 核心特性

### 双向 Batch 模式

系统区分出库（OUTBOUND）和入库（INBOUND）任务，采用不同的批量优化策略：

- **OUTBOUND 多取一送**：多个取货点共享同一目的地时，按 dest 分组，AGV 依次取货后一次性送达 `[取→取→取]→送`
- **INBOUND 一取多送**：多个目的地共享同一取货点时，按 pick 分组，AGV 一次性取货后依次送达 `取→[送→送→送]`

典型任务比例：OUTBOUND + TRANSFER 约 67%（dest 固定为 Port），INBOUND 约 33%（pick 固定为 Port）。

### 方向感知聚类

基于 scipy 层次聚类（Ward linkage，距离阈值 25），但根据任务方向采用不同聚类维度：

- OUTBOUND：按 dest 所在区域聚类 → 同 Port 任务可 batch 送货
- INBOUND：按 pick 所在区域聚类 → 同 Port 任务可 batch 取货

### 五大优化模块（消融实验）

| 模块 | 代号 | 说明 |
|------|------|------|
| 路径缓存 | M1 | PathFinder 预计算关键点间路径，避免重复寻路 |
| 方向感知聚类 | M2 | 按任务方向选择聚类维度，合并同区域任务 |
| 双向 Batch TSP | M3 | OR-Tools TSP 求解任务排序，支持 batch 粒度距离矩阵 |
| CP-SAT 全局分配 | M4 | OR-Tools CP-SAT 约束规划最小化 makespan |
| 冲突避免 | M5 | 时空占用表 + 冲突路段 + 避让点机制 |

消融实验结果（medium_50x50，40 订单）：

| 实验 | Makespan | 总距离 |
|------|----------|--------|
| Baseline（无优化） | 1773 | 11078 |
| M1+M2（+聚类） | 1764 | 8892 |
| M1+M2+M3（+TSP） | 1038 | 3584 |
| Full（全模块） | **994** | **3558** |

## 目录结构

```
src/warehouse/
├── models.py                 # 所有 Pydantic 数据模型（枚举、任务、结果、地图配置）
├── __init__.py
│
├── maps/                     # 地图预设
│   ├── base.py               # MapRegistry 注册机制 + BaseMap 抽象基类
│   ├── medium_50x50.py       # 中型地图：50×50, 12 仓库区, 4 端口, 8 AGV
│   ├── large_100x100.py      # 大型地图：100×100, 24 仓库区, 8 端口, 20 AGV
│   └── extreme.py            # 三种极端分布地图（corner/corridor/cluster）
│
├── wms/                      # WMS 层 — 仓库管理
│   ├── config.py             # WarehouseConfig（Pydantic Settings，WH_ 前缀环境变量）
│   ├── inventory.py          # InventoryManager（库存初始化、查询、扣减、入库）
│   └── order_manager.py      # OrderManager（随机工单生成、PortInstruction 工单生成）
│
├── wes/                      # WES 层 — 仓储执行
│   ├── task_decomposer.py    # TaskDecomposer（WorkOrder → TransportTask，分配 pick/dest）
│   └── clustering.py         # OrderClusterer（方向感知层次聚类，按 dest/pick 分组）
│
├── fleet/                    # Fleet 层 — 车队调度
│   ├── map_builder.py        # WarehouseMap（网格构建、位置映射、通道/端口/仓库区/充电桩）
│   ├── pathfinding.py        # PathFinder + SpaceTimeTable（时空 A*、路径缓存、冲突检测）
│   ├── tsp.py                # TSPSolver（OR-Tools TSP、双向 batch 分组与排序）
│   ├── allocator.py          # TaskAllocator（CP-SAT 全局分配、贪心降级）
│   ├── conflict.py           # ConflictManager + RoadSegment（冲突路段管理、避让）
│   ├── charging.py           # ChargingScheduler（低电量充电规划）
│   └── fleet_manager.py      # FleetManager（调度编排入口：分配 → TSP 排序）
│
└── simulation/               # Simulation 层 — 仿真执行
    ├── agv.py                # AGV 状态机（轨迹记录、电量管理）
    ├── simulator.py          # Simulator（仿真引擎，双向 batch 执行）
    ├── metrics.py            # MetricsCollector（指标统计与对比）
    └── visualizer.py         # Visualizer + ResultExporter（地图可视化、GIF 动画、JSON/CSV 导出）

tests/warehouse/              # 19 个测试文件，98 个测试用例
```

## 数据流

```
工单生成 (OrderManager)
  ↓
工单分解 (TaskDecomposer → TransportTask[])
  ↓
方向感知聚类 (OrderClusterer → TaskCluster[])
  ↓
Fleet 调度 (FleetManager)
  ├─ CP-SAT 分配 (TaskAllocator → AGV→Cluster[])
  └─ TSP 排序 (TSPSolver → AGV→Task[] 有序)
  ↓
仿真执行 (Simulator)
  ├─ 时空 A* 路径规划 (PathFinder)
  ├─ 冲突避免 (ConflictManager)
  ├─ 充电调度 (ChargingScheduler)
  └─ AGV 状态机 (AGV)
  ↓
指标统计 (MetricsCollector → SimulationResult)
  ↓
可视化导出 (Visualizer + ResultExporter)
```

## 数据模型

所有数据模型定义在 `models.py`，使用 Pydantic v2：

| 模型 | 用途 |
|------|------|
| `AGVStatus` | AGV 状态枚举（idle/moving_empty/moving_loaded/loading/unloading/charging/yielding） |
| `TaskType` | 任务类型枚举（INBOUND/OUTBOUND/TRANSFER） |
| `OrderPriority` | 优先级（URGENT=10, NORMAL=5, LOW=1） |
| `InventoryItem` | 库存项（型号、零件名、数量、位置、区域） |
| `WorkOrder` / `OrderItem` | 工单及其子项 |
| `TransportTask` | 运输任务（pick→dest，含任务类型、优先级） |
| `TaskCluster` | 任务聚类簇 |
| `AGVState` | AGV 初始状态 |
| `SimulationResult` | 仿真结果（makespan、距离、利用率、轨迹等） |
| `AblationFlags` | 消融实验开关（5 个独立模块控制） |
| `MapConfig` | 地图配置（网格、仓库区、端口、通道、冲突路段等） |

## 地图预设

| 名称 | 网格 | 仓库区 | 端口 | AGV | 特点 |
|------|------|--------|------|-----|------|
| `medium_50x50` | 50×50 | 12 (3类型×4) | 4 (2入2出) | 8 | 默认中等规模 |
| `large_100x100` | 100×100 | 24 (3类型×8) | 8 (4入4出) | 20 | 大规模压力测试 |
| `extreme_corner` | 50×50 | 12 | 4 | 8 | 仓库集中在四角 |
| `extreme_corridor` | 50×50 | 8 | 4 | 8 | 单通道瓶颈，少量冲突路段 |
| `extreme_cluster` | 50×50 | 12 | 4 | 8 | 储位集中在中心区域 |

地图通过 `MapRegistry` 注册机制管理，新增地图只需继承 `BaseMap` 并使用 `@MapRegistry.register("name")` 装饰器。

### 地图结构（以 medium_50x50 为例）

- 50×50 网格，6 条水平主通道 + 6 条垂直主通道
- 12 个仓库区（Raw×4、Finished×4、Spare×4），每区含 4 个储位，共 48 个储位
- 4 个端口：入库北、出库南、紧急出库西、备件入库东
- 4 条冲突路段（2 水平 + 2 垂直），各配 3 个避让点
- 4 个充电桩（四角）
- 8 台 AGV 初始位置

## 关键算法

### 时空 A* 路径规划 (`pathfinding.py`)

- 基础 A* 寻路支持路径缓存，预计算所有关键点对之间的最短路径
- 时空 A* 在基础 A* 上加入时间维度，避免 AGV 在同一时刻占据同一位置
- 单向主干道约束：冲突路段只允许单向通行（RIGHT/DOWN）
- 遇到冲突路段被占用时，AGV 进入避让点等待

### 双向 Batch TSP (`tsp.py`)

1. 按方向分离任务（OUTBOUND vs INBOUND）
2. OUTBOUND 按 dest 分组 → 多取一送 batch；INBOUND 按 pick 分组 → 一取多送 batch
3. 构建 batch 粒度距离矩阵（entry/exit 点对）
4. OR-Tools TSP 求解 batch 间最优排序
5. batch 内用最近邻启发式排序取/送点

### CP-SAT 全局分配 (`allocator.py`)

- 为每个 (AGV, Cluster) 组合计算预估完成时间
- 约束：每个簇恰好分配给一个 AGV、容量上限、紧急优先级约束
- 目标：最小化 makespan（所有 AGV 中最晚完成时间）
- 降级：CP-SAT 无解时自动切换贪心分配（按负载均衡分配）

### 方向感知聚类 (`clustering.py`)

1. 分离 OUTBOUND/TRANSFER 和 INBOUND 任务
2. 将任务按 order_id 分组
3. OUTBOUND 用 dest 坐标计算订单中心，INBOUND 用 pick 坐标
4. 按区域（Raw/Finished/Spare）分组后，对每组做 Ward linkage 层次聚类
5. 超过容量上限的簇自动拆分

## 配置参数

所有参数通过 `WarehouseConfig`（Pydantic Settings）管理，支持 `WH_` 前缀环境变量覆盖：

```bash
# AGV 运动参数
WH_AGV_MOVE_TIME=1           # 每步移动耗时
WH_AGV_ACCEL_TIME=2          # 加速耗时
WH_AGV_DECEL_TIME=2          # 减速耗时
WH_AGV_TURN_TIME=3           # 转弯耗时
WH_AGV_LOAD_UNLOAD_TIME=8    # 装卸耗时

# AGV 电量参数
WH_AGV_MAX_BATTERY=100
WH_AGV_CHARGE_RATE=5
WH_AGV_CONSUME_RATE=1
WH_AGV_CHARGE_TIME=20
WH_AGV_LOW_BATTERY_THRESHOLD=20

# 任务参数
WH_AGV_MAX_TASK_CAPACITY=20
WH_ORDER_NUM=40
WH_RANDOM_SEED=42

# 求解器参数
WH_TSP_TIME_LIMIT=1          # TSP 求解时间限制（秒）
WH_CP_SAT_TIME_LIMIT=30      # CP-SAT 求解时间限制（秒）
WH_A_MAX_SEARCH=5000         # A* 最大搜索节点数
```

## 运行方式

```bash
# 默认运行（50×50 地图，40 订单）
python main_simulation.py

# 指定地图和订单数
python main_simulation.py large_100x100 60

# 极端地图测试
python main_simulation.py extreme_corner 30

# 消融实验（6 组对比）
python main_simulation.py --ablation

# 消融实验 + 指定地图
python main_simulation.py --ablation extreme_cluster 20

# 运行测试
python -m pytest tests/warehouse/ -v
```

## 输出

运行后输出到 `output/` 目录：

| 文件 | 说明 |
|------|------|
| `final_state.png` | 最终状态快照（AGV 位置 + 地图） |
| `result.json` | 仿真结果 JSON（makespan、距离、利用率等） |
| `animation.gif` | AGV 运行动画（可选） |

## 依赖

```
pydantic >= 2.0
pydantic-settings
numpy
scipy
ortools
matplotlib
Pillow
```

## 测试

```
tests/warehouse/
├── test_models.py           # 数据模型验证
├── test_config.py           # 配置加载
├── test_maps.py             # 地图注册与构建
├── test_map_builder.py      # 地图网格构建
├── test_inventory.py        # 库存管理
├── test_order_manager.py    # 工单生成
├── test_task_decomposer.py  # 任务分解
├── test_clustering.py       # 聚类算法
├── test_pathfinding.py      # 路径规划
├── test_tsp.py              # TSP 求解
├── test_allocator.py        # 任务分配
├── test_conflict.py         # 冲突管理
├── test_charging.py         # 充电调度
├── test_fleet_manager.py    # Fleet 编排
├── test_agv.py              # AGV 状态机
├── test_simulator.py        # 仿真引擎
├── test_metrics.py          # 指标统计
├── test_visualizer.py       # 可视化
└── test_integration.py      # 端到端集成测试
```

共 98 个测试用例，覆盖所有模块单元测试和端到端集成测试。

## 与论文的关系

本系统基于 Choi et al. (Mathematics, 2025) 的 5 步调度框架实现并扩展：

| 论文步骤 | 本系统实现 | 扩展 |
|----------|-----------|------|
| 1. 订单生成 | OrderManager | 支持 PortInstruction 输入 |
| 2. 任务分解 | TaskDecomposer | 区分 INBOUND/OUTBOUND/TRANSFER |
| 3. 任务聚类 | OrderClusterer | 方向感知聚类（Ward linkage） |
| 4. 任务排序 | TSPSolver | 双向 Batch（多取一送 + 一取多送） |
| 5. 任务分配 | TaskAllocator | CP-SAT 全局优化 + 贪心降级 |

核心差异：论文针对电商 zone-picking 场景（dest 固定为 packing station），本系统扩展至港口备件仓储的双向任务流。
