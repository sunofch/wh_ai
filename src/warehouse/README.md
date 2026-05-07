# AGV 智能仓储调度系统

港口备件仓库的 AGV 调度仿真系统，包含从订单生成到路径规划、冲突避免、仿真执行的完整流程。

## 架构

系统分为四层：

```
WMS (仓库管理) → WES (执行系统) → Fleet (车队调度) → Simulation (仿真)
```

- **WMS** — 配置、库存、工单生成
- **WES** — 任务分解、方向感知聚类
- **Fleet** — 地图构建、A*路径规划、TSP排序、CP-SAT分配、冲突避免、充电调度
- **Simulation** — AGV状态机、仿真引擎、指标统计

## 目录结构

```
src/warehouse/
  models.py              所有 Pydantic 数据模型（AGV、任务、订单等）
  maps/
    base.py              MapRegistry 地图注册中心 + BaseMap 基类
    medium_50x50.py      50×50 港口备件仓库（9区域、6端口、450储位）
  wms/
    config.py            全局配置（Pydantic Settings）
    inventory.py         库存管理
    order_manager.py     工单生成
  wes/
    task_decomposer.py   WorkOrder → TransportTask 分解
    clustering.py        方向感知层次聚类
  fleet/
    map_builder.py       网格地图构建（通道、货架、端口、充电桩）
    pathfinding.py       时空 A* 路径规划 + 缓存
    tsp.py               OR-Tools TSP 任务排序
    allocator.py         CP-SAT 全局任务分配 + 贪心降级
    conflict.py          冲突路段管理 + 避让
    charging.py          充电感知调度
    fleet_manager.py     车队管理入口
  simulation/
    agv.py               AGV 状态机 + 轨迹记录
    simulator.py         仿真执行引擎
    metrics.py           指标统计（makespan、距离、利用率等）
```

## 运行

```bash
# 基本仿真
python main_simulation.py

# 消融实验（逐个关闭模块对比效果）
python main_simulation.py --ablation

# 运行测试
python -m pytest tests/warehouse/ -v
```

## 核心特性

- **双向 Batch 调度** — OUTBOUND 多取一送、INBOUND 一取多送
- **方向感知聚类** — Ward linkage，按区域聚类减少空驶
- **时空 A\*** — 考虑时间维度的路径规划，带路径缓存
- **冲突避免** — 单向通道 + 时空避让
- **CP-SAT 优化** — 全局最优任务分配，失败时贪心降级
- **充电调度** — 电量感知的自动充电规划

## 依赖

- Python 3.11+
- Pydantic v2
- OR-Tools（TSP + CP-SAT）
- NumPy
