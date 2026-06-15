"""多 AGV 协同博弈：竞价决定规划顺序（路权分配）。

仿真引擎按顺序为各 AGV 规划路径并锁定时空资源，先规划者优先获得
无冲突路径——规划顺序即路权。本模块把"谁先规划"建模为一次密封
竞价博弈：每台 AGV 按任务紧急度、工作负载、电量出价，出价高者
先规划，从机制上消解冲突，替代原先按 agv_id 的任意顺序。

对应 pj4 子课题 4.2"基于协同博弈的多 AGV 及输送线调度算法"。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from src.warehouse.models import OrderPriority, TransportTask

# 竞价权重：紧急度 > 工作负载 > 电量
BID_WEIGHTS: dict[str, float] = {
    "urgency": 0.5,
    "workload": 0.3,
    "battery": 0.2,
}

# 工作负载归一化基准（任务数达到该值视为满载）
_WORKLOAD_NORM = 10.0


@dataclass(frozen=True)
class Bid:
    """一台 AGV 的密封出价。components 记录各因素得分便于审计。"""
    agv_id: int
    value: float
    components: dict[str, float] = field(default_factory=dict)


def compute_bid(
    agv_id: int,
    tasks: list[TransportTask],
    battery: float,
    weights: dict[str, float] | None = None,
) -> Bid:
    """计算 AGV 出价。

    - urgency：所属任务的最高优先级（URGENT=1.0，NORMAL≈0.5）
    - workload：任务数（重载先规划，利于整体 makespan 均衡）
    - battery：电量充足者优先（低电量 AGV 可能中途充电，路权价值低）
    """
    w = weights or BID_WEIGHTS
    if tasks:
        max_priority = max(t.priority for t in tasks)
        urgency = max_priority.value / OrderPriority.URGENT.value
    else:
        urgency = 0.0
    workload = min(1.0, len(tasks) / _WORKLOAD_NORM)
    battery_score = max(0.0, min(1.0, battery / 100.0))

    components = {
        "urgency": round(urgency, 4),
        "workload": round(workload, 4),
        "battery": round(battery_score, 4),
    }
    value = sum(components[name] * w.get(name, 0.0) for name in components)
    return Bid(agv_id=agv_id, value=round(value, 6), components=components)


def plan_order(bids: list[Bid]) -> list[int]:
    """按出价降序返回 AGV 规划顺序；同价按 agv_id 升序保证确定性。"""
    ranked = sorted(bids, key=lambda b: (-b.value, b.agv_id))
    return [b.agv_id for b in ranked]
