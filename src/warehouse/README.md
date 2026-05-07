# AGV 智能仓储调度系统

港口备件仓库的 AGV 调度仿真系统，包含从订单生成到路径规划、仿真执行的完整流程。

## 架构

四层调度架构：

```
WMS (仓库管理) → WES (执行系统) → Fleet (车队调度) → Simulation (仿真)
```

- **WMS** — 配置、库存、工单生成（随机/VLM来源）
- **WES** — 任务分解、精确batch键聚类
- **Fleet** — 地图构建、A*路径规划、簇间/簇内TSP排序、CP-SAT分配、充电调度
- **Simulation** — AGV状态机、batch检测执行、指标统计

## 调度流程

```
工单(WorkOrder)
  → 任务分解 → TransportTask(pick, dest, task_type)
  → 聚类(精确batch键分组 → 空间合并 → 容量拆分) → TaskCluster
  → CP-SAT分配(簇→AGV, 最小化makespan)
  → 簇间TSP排序(OR-Tools, 决定簇执行顺序)
  → 逐簇TSP排序(OR-Tools, 双向batch排序)
  → A*路径规划(方向感知+缓存)
  → 仿真执行(自动检测batch + 充电管理)
```

## 目录结构

```
src/warehouse/
  models.py              Pydantic v2 数据模型（TaskType, TaskCluster, AGVState等）
  maps/
    base.py              MapRegistry 地图注册中心 + BaseMap 基类
    medium_57x47.py      57×47 港口备件仓库地图（9区域、6端口、8台AGV）
  wms/
    config.py            全局配置（Pydantic Settings）+ 消融开关
    inventory.py         库存管理（储位分配）
    order_manager.py     工单生成（随机/VLM双来源）
  wes/
    task_decomposer.py   WorkOrder → TransportTask 分解
    clustering.py        精确batch键聚类（按dest/pick分组→空间合并→容量拆分）
  fleet/
    map_builder.py       网格地图构建（区域、端口、通道、充电桩）
    pathfinding.py       A*路径规划 + BFS预计算缓存
    tsp.py               OR-Tools TSP（双向batch：OUTBOUND多取一送 + INBOUND一取多送）
    allocator.py         CP-SAT全局簇→AGV分配 + 贪心降级
    charging.py          电量感知充电调度
    fleet_manager.py     Fleet层总编排（簇间TSP + 逐簇TSP）
  simulation/
    agv.py               AGV状态机 + 轨迹记录 + 电量管理
    simulator.py         仿真执行引擎（自动batch检测 + 充电）
    metrics.py           指标统计（makespan、距离、利用率、方差）
```

## 运行

```bash
# 基本仿真
python main_simulation.py

# 指定地图和订单数
python main_simulation.py medium_57x47 40

# 消融实验（4级对比）
python main_simulation.py --ablation

# 运行测试
python -m pytest tests/warehouse/ -v
```

## 消融实验

4个可独立开关的优化模块，10组随机种子均值：

| 实验 | makespan | 距离 | 边际提升 |
|------|----------|------|---------|
| Baseline (无优化) | 1933 | 8616 | - |
| M1+M2 (路径缓存+聚类) | 1033 | 3790 | 46.5% |
| M1+M2+M3 (+TSP) | 643 | 1849 | 37.8% |
| M1+M2+M3+M4 (+CP-SAT) | 590 | 1700 | 8.2% |

## 核心设计

### 聚类（路线A）

按**精确batch键**分组（OUTBOUND按dest，INBOUND按pick），保证同目标的任务在同一个簇内，使batch机会在聚类阶段就被捕获。空间上相近的batch组通过Ward层次聚类合并，超过容量限制时按batch组为单位拆分（保持batch完整性）。

### 双向Batch

仿真器自动检测连续任务的模式：
- **OUTBOUND batch**：连续同dest → `[取→取→取]→送`（多取一送）
- **INBOUND batch**：连续同pick → `取→[送→送→送]`（一取多送）

### 保持簇边界执行

CP-SAT按簇分配后，FleetManager不展平簇，而是：
1. OR-Tools TSP排簇间执行顺序
2. 逐簇调用TSP排序簇内任务
3. CP-SAT代价估算与实际执行一致，优化目标可信

### CP-SAT全局分配

为每个(AGV, 簇)组合用TSP精确计算执行代价，构建代价矩阵后CP-SAT求解最小化makespan的簇→AGV分配方案。30秒超时，失败降级为贪心分配。

## 依赖

- Python 3.10+
- Pydantic v2
- OR-Tools（TSP + CP-SAT）
- NumPy, SciPy（聚类）
