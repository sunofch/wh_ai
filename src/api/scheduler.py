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
) -> tuple[ScheduleResult, "SimulationResult"]:
    """同步调度流水线（在线程池中执行）。

    Returns: (ScheduleResult, SimulationResult) 元组
    """
    import time as _time
    t0 = _time.time()

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
    """后台协程：轮询队列，满足触发条件时批量调度。"""
    from datetime import datetime

    while True:
        await asyncio.sleep(1)
        if not queue.should_flush():
            continue

        orders = queue.drain()
        if not orders:
            continue

        run_id = str(uuid4())
        logger.info("调度触发: %d 条工单, run_id=%s", len(orders), run_id)
        try:
            sched_result, sim_result = await asyncio.to_thread(
                run_pipeline,
                orders, wmap, fleet, wh_config,
                inbound_ports, outbound_ports, run_id,
            )
            results[run_id] = (sched_result, sim_result)
            # LRU: 超过上限时删最旧的
            while len(results) > MAX_RESULTS:
                results.popitem(last=False)
            # 更新 state 元数据
            if state is not None:
                state["last_run_id"] = run_id
                state["last_run_at"] = datetime.now()
                state["scheduler_status"] = "idle"
            logger.info(
                "调度完成: makespan=%d, util=%.1f%%",
                sched_result.makespan, sched_result.agv_utilization * 100,
            )
        except Exception:
            logger.exception("调度异常，跳过本批次 run_id=%s", run_id)
