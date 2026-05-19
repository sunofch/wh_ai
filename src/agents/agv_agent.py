"""AGV 调度 Agent（纯算法）。

职责：接收一批 WorkOrders，执行调度流水线，返回调度结果。
不接 LLM，由 scheduler_loop 在队列满足触发条件时调用。

架构定位（参考 docs/reference/agv_agent_patterns.md）：
  instruction_agent (LLM)  → 语义解析
  inventory_agent   (LLM)  → 工单创建
  agv_agent         (算法) → AGV 批量调度  ← 本模块
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

from src.warehouse.wes.task_decomposer import TaskDecomposer
from src.warehouse.wes.clustering import OrderClusterer
from src.warehouse.simulation.simulator import Simulator
from src.api.models import ScheduleResult

if TYPE_CHECKING:
    from src.warehouse.models import WorkOrder
    from src.warehouse.fleet.fleet_manager import FleetManager
    from src.warehouse.fleet.map_builder import WarehouseMap
    from src.warehouse.wms.config import WarehouseConfig


def run(
    orders: list[WorkOrder],
    wmap: WarehouseMap,
    fleet: FleetManager,
    wh_config: WarehouseConfig,
    inbound_ports: list[str],
    outbound_ports: list[str],
    run_id: str,
    inv_db=None,
) -> tuple[ScheduleResult, object]:
    """执行 AGV 批量调度流水线。

    输入：scheduler_loop 从队列取出的一批 WorkOrders
    输出：(ScheduleResult, SimulationResult)
    """
    t0 = time.time()

    try:
        td = TaskDecomposer(
            None, inbound_ports, outbound_ports, seed=wh_config.RANDOM_SEED
        )
        tasks = td.decompose(orders, wmap.storage_list)

        clusterer = OrderClusterer(fleet.path_finder, wh_config)
        clusters = clusterer.cluster(
            tasks, wh_config.AGV_MAX_TASK_CAPACITY, wmap.zone_pos
        )

        agv_tasks = fleet.schedule(clusters)

        sim = Simulator(wmap, fleet, wh_config)
        sim_result = sim.run(agv_tasks)
        sim_result.planning_time = time.time() - t0
    except Exception:
        if inv_db:
            _release_orders(inv_db, orders)
        raise

    if inv_db:
        _confirm_orders(inv_db, orders)

    sched = ScheduleResult(
        run_id=run_id,
        order_count=len(orders),
        makespan=sim_result.makespan,
        total_distance=sim_result.total_distance,
        agv_utilization=sim_result.agv_utilization,
        planning_time=sim_result.planning_time,
        instructions=[
            o.metadata.get("raw_text", f"order_{o.order_id}") for o in orders
        ],
    )

    return sched, sim_result


def _confirm_orders(inv_db, orders: list[WorkOrder]) -> None:
    for order in orders:
        for item in order.items:
            if item.model:
                inv_db.confirm(
                    item.model, item.quantity or 1,
                    order_id=order.metadata.get("order_id", ""),
                )


def _release_orders(inv_db, orders: list[WorkOrder]) -> None:
    for order in orders:
        for item in order.items:
            if item.model:
                inv_db.release(
                    item.model, item.quantity or 1,
                    order_id=order.metadata.get("order_id", ""),
                )
