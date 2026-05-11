# src/api/scheduler.py
"""调度协程：混合触发 → run_pipeline（线程池）→ 存结果"""
from __future__ import annotations
import asyncio
import logging
from uuid import uuid4
from collections import OrderedDict
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
    from src.api.queue_manager import OrderQueue

logger = logging.getLogger(__name__)

MAX_RESULTS = 50


def run_pipeline(
    orders: list[WorkOrder],
    wmap: WarehouseMap,
    fleet: FleetManager,
    wh_config: WarehouseConfig,
    inbound_ports: list[str],
    outbound_ports: list[str],
    run_id: str,
    inv_db=None,
) -> tuple[ScheduleResult, "SimulationResult"]:
    """同步调度流水线（在线程池中执行）。

    Returns: (ScheduleResult, SimulationResult) 元组
    """
    import time as _time
    t0 = _time.time()

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
        sim_result.planning_time = _time.time() - t0
    except Exception:
        # 调度失败 → release 所有预留
        if inv_db:
            _release_orders(inv_db, orders)
        raise

    # 调度成功 → confirm 所有预留
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


async def scheduler_loop(
    queue: OrderQueue,
    results: OrderedDict,
    wmap: WarehouseMap,
    fleet: FleetManager,
    wh_config: WarehouseConfig,
    inbound_ports: list[str],
    outbound_ports: list[str],
    state: dict | None = None,
) -> None:
    """后台协程：事件驱动调度，满足触发条件时批量调度。"""
    from datetime import datetime

    while True:
        await queue.wait_for_flush()

        orders = queue.drain()
        if not orders:
            continue

        run_id = str(uuid4())
        logger.info("调度触发: %d 条工单, run_id=%s", len(orders), run_id)
        try:
            inv_db = state.get("inv_db") if state else None
            sched_result, sim_result = await asyncio.to_thread(
                run_pipeline,
                orders, wmap, fleet, wh_config,
                inbound_ports, outbound_ports, run_id, inv_db,
            )
            results[run_id] = (sched_result, sim_result)
            while len(results) > MAX_RESULTS:
                results.popitem(last=False)
            if state is not None:
                state["last_run_id"] = run_id
                state["last_run_at"] = datetime.now()
                state["scheduler_status"] = "idle"
            logger.info(
                "调度完成: makespan=%d, util=%.1f%%",
                sched_result.makespan, sched_result.agv_utilization * 100,
            )
        except Exception:
            logger.exception("调度异常，run_id=%s", run_id)
            if queue.requeue(orders):
                logger.info("批次重入队等待重试")
            else:
                logger.warning("超过重试次数，批次标记 failed")
                results[run_id] = (ScheduleResult(
                    run_id=run_id, order_count=len(orders),
                    makespan=0, total_distance=0, agv_utilization=0,
                    planning_time=0, has_animation=False,
                ), None)
            if state is not None:
                state["scheduler_status"] = "failed"
