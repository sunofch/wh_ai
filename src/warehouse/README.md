# AGV 智能仓储调度系统

港口备件仓库的 AGV 调度仿真系统，包含从订单生成到路径规划、仿真执行的完整流程。还通过 `src/api/` 提供 REST API 接口，支持从港口指令解析到 AGV 调度的全链路集成。

## 架构

四层调度架构：

```
WMS (仓库管理) → WES (执行系统) → Fleet (车队调度) → Simulation (仿真)
```

- **WMS** — 配置、库存（SQLite WAL持久化）、工单生成（随机/VLM来源）
- **WES** — 任务分解、精确batch键聚类
- **Fleet** — 地图构建、A*路径规划、簇间/簇内TSP排序、Makespan-aware Regret-2分配、充电调度
- **Simulation** — AGV状态机、batch检测执行、指标统计

## 调度流程

```
工单(WorkOrder)
  → 任务分解 → TransportTask(pick, dest, task_type)
  → 聚类(精确batch键分组 → 空间合并 → 容量拆分) → TaskCluster
  → Regret-2 分配(簇→AGV, makespan目标 + 位置感知 tie-breaker)
  → 簇间TSP排序(OR-Tools, 决定簇执行顺序)
  → 逐簇TSP排序(OR-Tools, 双向batch排序)
  → A*路径规划(方向感知+缓存)
  → 仿真执行(自动检测batch + 充电管理)
```

## 目录结构

```
src/warehouse/
  models.py              Pydantic v2 数据模型（TaskType, TaskCluster, AGVState,
                         InventoryItem[含reserved/available字段], WorkOrder等）
  maps/
    base.py              MapRegistry 地图注册中心 + BaseMap 基类
    medium_57x47.py      57×47 港口备件仓库地图（9区域、6端口、8台AGV 对称分布）
    medium_57x47_cluster.py
                         同布局但 8 台 AGV 起点聚集在左上角（负载均衡压力测试）
  wms/
    config.py            全局配置（Pydantic Settings）+ 消融开关
    inventory.py         内存库存管理（轻量版，用于仿真）
    inventory_db.py      SQLite持久化库存（WAL模式，双表：stock_quant+stock_move，
                         三阶段：reserve/confirm/release，支持审计追踪）
    order_manager.py     工单生成（随机/VLM双来源）
  wes/
    task_decomposer.py   WorkOrder → TransportTask 分解（按方向分配pick/dest）
    clustering.py        精确batch键聚类（按dest/pick分组→空间合并→容量拆分）
  fleet/
    map_builder.py       网格地图构建（区域、端口、泊位、充电桩）
    pathfinding.py       时空A*路径规划（方向感知、转弯/加速代价、冲突等待）
    tsp.py               OR-Tools TSP（双向batch：OUTBOUND多取一送 + INBOUND一取多送）
    allocator.py         Makespan-aware Regret-2 分配（三元组评分键 + regret 排序 + 距离破局）
    charging.py          电量感知充电调度（就近充电桩、低电量阈值触发）
    fleet_manager.py     Fleet层总编排（任务分配 → 簇间TSP → 逐簇TSP）
  simulation/
    agv.py               AGV状态机 + 非均匀时间步轨迹记录 + 电量管理
    simulator.py         仿真执行引擎（自动batch检测 + 充电 + 时空锁定）
    metrics.py           指标统计（makespan、距离、利用率、方差、动态列宽对比表）

src/api/                 REST API 集成层（FastAPI）
  app.py                 FastAPI工厂函数（create_app，依赖注入）
  models.py              请求/响应Pydantic模型（InstructionRequest/Response, ScheduleResult等）
  queue_manager.py       事件驱动工单队列（asyncio.Event，urgent优先队列，最多MAX_RETRIES次重试）
  scheduler.py           后台调度协程（事件驱动，成功confirm/失败release库存预留）
```

## 运行

```bash
# 基本仿真（默认 medium_57x47, 40 单）
python main_simulation.py

# 指定地图和订单数
python main_simulation.py medium_57x47 40
python main_simulation.py medium_57x47_cluster 40   # 负载均衡压力场景

# 同时生成可视化动画
python main_simulation.py --animate medium_57x47_cluster 40

# 消融实验（基线 + 3 档递进）
python main_simulation.py --ablation
python main_simulation.py --ablation medium_57x47_cluster 40

# REST API 服务（自动对接库存DB和调度器）
python main_api.py                    # 默认 0.0.0.0:8000
python main_api.py --port 9000
```

## 消融实验

3个可独立开关的优化模块，batch常驻：

| 实验 | 说明 |
|------|------|
| Baseline (Batch) | 仅保留batch检测，关闭所有优化模块 |
| M1 (+路径缓存) | 启用A*路径缓存，避免重复计算 |
| M1+M2 (+聚类) | + 精确batch键聚类（方向感知空间分组） |
| M1+M2+M3 (+TSP) | + OR-Tools TSP排序（簇间+簇内双向batch） |

## 核心设计

### 库存管理（inventory_db.py）

`StockManager` 使用 SQLite WAL 模式持久化库存，双表设计：

- **stock_quant**：当前库存快照（model, quantity, reserved, location）
- **stock_move**：每次操作的移动日志（审计追踪）

三阶段生命周期与 API 调度器协同：
1. `reserve(model, qty, order_id)` — 指令解析成功后预锁定库存，返回储位
2. `confirm(model, qty, order_id)` — 调度执行成功后扣减库存
3. `release(model, qty, order_id)` — 调度失败后释放预留，恢复 available

### 聚类（路线A）

按**精确batch键**分组（OUTBOUND按dest，INBOUND按pick），保证同目标的任务在同一个簇内，使batch机会在聚类阶段就被捕获。空间上相近的batch组通过Ward层次聚类合并，超过容量限制时按batch组为单位拆分（保持batch完整性）。

### 双向Batch

仿真器自动检测连续任务的模式：
- **OUTBOUND batch**：连续同dest → `[取→取→取]→送`（多取一送）
- **INBOUND batch**：连续同pick → `取→[送→送→送]`（一取多送）

Batch在整个流水线中**常驻**——无论消融开关如何设置，TSP和仿真器都会按batch分组处理。

### 保持簇边界执行

任务分配按簇映射到 AGV 后，FleetManager 不展平簇，而是：
1. OR-Tools TSP 排簇间执行顺序
2. 逐簇调用 TSP 排序簇内任务
3. 分配阶段的代价估算与实际执行口径一致，优化目标可信

### Makespan-aware Regret-2 任务分配

`allocator.py` 把簇映射到 AGV 时，三层组合策略：

1. **Makespan 评分键** — 每个 (簇, AGV) 候选按三元组 `(new_makespan, new_completion, dist_to_centroid)` 字典序最小化。主键 `new_makespan = max(agv_times[i] + cluster_time, current_makespan)`，显式压制最长 AGV 完成时间，而非旧贪心的累计和（后者在负载倾斜时会继续推高瓶颈 AGV）。

2. **Regret-2 insertion** — 同优先级组内每轮重新计算所有未分配簇的 regret = 次优 AGV makespan − 最优 AGV makespan，挑 regret 最大的簇先分配，让"必须给特定 AGV 否则代价激增"的簇优先锁定，留下"哪都行"的灵活簇填空。

3. **距离破局** — 评分相等时按 AGV 当前位置→簇质心曼哈顿距离破局，消除系统性偏向 agv_id 小的 AGV 的隐性 bias。

每个 (簇, AGV) 的 cluster_time 用 TSP 排序 + 关键点直线段近似累计移动/转弯/加速/装卸代价，带缓存 `(id(cluster), agv_pos) → (time, exit_pos)`，避免 regret 计算的重复 TSP 求解。簇执行后跟踪 AGV 出口位置，供后续簇感知 AGV 实际位置。

**实测**（`medium_57x47_cluster`，40 单 / 8 AGV）：相比纯贪心 makespan 改善约 16%，util 提升约 9pp。AGV 已对称分布时 regret≈0 自动退化为基础贪心，与原算法等价。

### 时空A*路径规划

方向感知的A*算法，考虑转弯代价（`AGV_TURN_TIME`）和起步加速代价（`AGV_ACCEL_TIME`）。时空占用表追踪每个位置在每个时刻的AGV占用情况，冲突时原地等待1步再重新搜索。路径缓存避免关键点之间的重复计算。

### 端口泊位

每个端口配置多个泊位（berths），AGV按ID取模分配泊位，避免同一端口的AGV聚集到同一位置。

### REST API 事件驱动调度

`OrderQueue` 使用 `asyncio.Event` 代替轮询，三种触发条件满足其一即批量调度：
- 普通队列达到 `SIZE_THRESHOLD`（默认10条）
- 等待超过 `WINDOW_SECONDS`（默认30秒）
- 存在 URGENT 优先级工单（立即触发）

失败批次自动重入队，超过 `MAX_RETRIES` 后标记 `failed` 并释放库存预留。

## 依赖

- Python 3.10+
- Pydantic v2
- OR-Tools（TSP求解）
- NumPy, SciPy（聚类）
- FastAPI + uvicorn（REST API，可选）
- SQLite（内置，用于持久化库存）
