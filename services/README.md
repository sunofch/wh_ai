# Warehouse Scheduling System - MVP

全天候无人值守仓储运行机制研究 - 最小可行产品（MVP）

## 项目概述 (Project Overview)

本项目实现了课题四中的子课题4.2核心功能，包括：
1. **LLM增强的智能调度系统** - 利用VLM理解任务，结合OR-Tools进行调度
2. **VLM仲裁者** - 多AGV冲突时，VLM作为仲裁者分析场景并推荐方案
3. **Gymnasium仿真环境** - 标准RL环境接口，便于后续强化学习集成
4. **微服务化架构** - 服务解耦，便于独立开发和部署

## 架构 (Architecture)

```
用户输入: "3号传送带需要5个电机，紧急"
    ↓
┌──────────────────────────────────────────────────────────┐
│ 指令解析服务 (localhost:8001)                             │
│ - FastAPI + VLM/RAG复用                                   │
│ - PortInstruction → WarehouseTask转换                     │
└──────────────────────────────────────────────────────────┘
    ↓
┌──────────────────────────────────────────────────────────┐
│ 任务调度服务 (localhost:8002)                             │
│ - OR-Tools CP-SAT调度                                     │
│ - 冲突检测 + VLM仲裁（阈值触发）                           │
└──────────────────────────────────────────────────────────┘
    ↓
┌──────────────────────────────────────────────────────────┐
│ 仿真执行服务 (localhost:8003)                             │
│ - Gymnasium环境                                           │
│ - AGV智能体执行                                           │
└──────────────────────────────────────────────────────────┘
```

## 快速开始 (Quick Start)

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

主要依赖：
- FastAPI >= 0.104.0
- OR-Tools >= 9.8.3296
- Gymnasium >= 0.29.0

### 2. 启动所有服务

```bash
python main_warehouse.py start
```

启动单个服务：
```bash
python main_warehouse.py start --services parser_service
python main_warehouse.py start --services scheduler_service
python main_warehouse.py start --services simulation_service
```

### 3. 健康检查

```bash
# Parser服务
curl http://localhost:8001/health

# Scheduler服务
curl http://localhost:8002/health

# Simulation服务
curl http://localhost:8003/health
```

### 4. 运行测试

```bash
python test_warehouse_system.py
```

## API接口 (API Endpoints)

### Parser Service (端口 8001)

**POST /api/v1/parse**
- 解析指令为WarehouseTask
- 支持文本、图像、音频输入
- 复用现有VLM/RAG系统

```python
import requests

response = requests.post("http://localhost:8001/api/v1/parse", json={
    "text": "3号传送带需要5个电机，紧急"
})
task = response.json()["task"]
```

### Scheduler Service (端口 8002)

**POST /api/v1/schedule**
- 使用OR-Tools CP-SAT进行调度
- 检测冲突并调用VLM仲裁
- 返回任务分配和完成时间估计

```python
response = requests.post("http://localhost:8002/api/v1/schedule", json={
    "tasks": [...],
    "agv_states": [...]
})
schedule = response.json()
```

### Simulation Service (端口 8003)

**POST /api/v1/execute**
- 在Gymnasium环境中执行调度
- 模拟AGV移动和任务完成
- 返回执行结果和统计信息

```python
response = requests.post("http://localhost:8003/api/v1/execute", json={
    "schedule_id": schedule_id,
    "assignments": assignments,
    "tasks": tasks,
    "initial_agv_states": agv_states
})
result = response.json()
```

## 核心功能 (Core Features)

### 1. 智能调度器 (OR-Tools Scheduler)

- 使用CP-SAT约束求解器
- 支持多约束：容量、时间、电池
- 最小化完成时间（makespan）

### 2. 冲突检测器 (Conflict Detector)

检测以下冲突类型：
- 路径交叉（PATH_CROSSING）
- 资源竞争（RESOURCE_CONTENTION）
- 电池耗尽（BATTERY_DEPLETION）
- 容量超限（CAPACITY_EXCEEDED）

### 3. VLM仲裁器 (VLM Arbitrator)

- 当OR-Tools无法求解时触发
- 使用VLM分析冲突场景
- 提供冲突解决建议

### 4. 仿真环境 (Gymnasium Environment)

- 标准RL接口（observation_space, action_space）
- 多AGV智能体支持
- 可视化和日志记录

## 项目结构 (Project Structure)

```
wh_graphrag_re/
├── services/                        # 微服务目录
│   ├── parser_service/             # 指令解析服务
│   │   ├── main.py                 # FastAPI入口
│   │   └── converter.py            # PortInstruction→Task
│   │
│   ├── scheduler_service/          # 任务调度服务
│   │   ├── main.py
│   │   ├── scheduler.py            # OR-Tools调度器
│   │   ├── arbitrator.py           # VLM仲裁器
│   │   └── conflict_detector.py    # 冲突检测
│   │
│   ├── simulation_service/         # 仿真执行服务
│   │   ├── main.py
│   │   ├── gym_env.py              # Gymnasium环境
│   │   └── agv_agent.py            # AGV智能体
│   │
│   └── shared/                     # 共享代码
│       ├── models.py               # Pydantic模型
│       ├── config.py               # 服务配置
│       └── utils.py
│
├── main_warehouse.py               # 统一启动脚本
├── test_warehouse_system.py        # 集成测试
└── requirements.txt
```

## 数据模型 (Data Models)

### WarehouseTask
- `task_id`: 任务唯一标识
- `task_type`: 任务类型（RETRIEVAL/STORAGE/TRANSPORT/CHARGING）
- `priority`: 优先级（CRITICAL/HIGH/MEDIUM/LOW）
- `source`: 起始位置 (x, y)
- `destination`: 目标位置 (x, y)
- `required_capacity`: 所需容量
- `deadline`: 截止时间（可选）

### AGVState
- `agv_id`: AGV唯一标识
- `position`: 当前位置 (x, y)
- `battery_level`: 电池电量百分比
- `load_capacity`: 最大载重
- `current_load`: 当前载重
- `status`: 状态（IDLE/MOVING/LOADING/UNLOADING/CHARGING）

## 性能指标 (Performance Metrics)

验证标准：
- VLM仲裁成功率 > 80%
- 调度算法响应时间 < 1秒
- VLM仲裁响应时间 < 3秒
- 端到端流程 < 5秒

## 参考资源 (References)

基于以下开源项目：
- [TA-RWARE](https://github.com/uoe-agents/task-assignment-robotic-warehouse) - 仓储多智能体RL环境
- [agv_simulator](https://github.com/shivirity/agv_simulator) - AGV调度仿真器
- [OR-Tools Scheduling](https://github.com/google/or-tools/blob/stable/ortools/sat/docs/scheduling.md) - 官方调度指南

## 后续工作 (Future Work)

### Phase 2: 核心功能实现
- [ ] 完善VLM仲裁逻辑
- [ ] 任务状态持久化（SQLite）
- [ ] 服务间调用日志

### Phase 3: 优化完善
- [ ] 异常处理和重试机制
- [ ] 性能监控仪表板
- [ ] 单元测试和集成测试

## 许可证 (License)

本项目遵循项目主仓库的许可证。
