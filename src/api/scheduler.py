# src/api/scheduler.py
"""调度协程：队列触发 → agv_agent.run()（线程池）→ 存结果"""
from __future__ import annotations

import asyncio
import logging
from uuid import uuid4
from collections import OrderedDict
from typing import TYPE_CHECKING

from src.api.models import ScheduleResult

if TYPE_CHECKING:
    from src.warehouse.fleet.fleet_manager import FleetManager
    from src.warehouse.fleet.map_builder import WarehouseMap
    from src.warehouse.wms.config import WarehouseConfig
    from src.api.queue_manager import OrderQueue

logger = logging.getLogger(__name__)

MAX_RESULTS = 50


async def scheduler_loop(
    queue,
    results: OrderedDict,
    wmap: WarehouseMap,
    fleet: FleetManager,
    wh_config: WarehouseConfig,
    inbound_ports: list[str],
    outbound_ports: list[str],
    state: dict | None = None,
) -> None:
    """后台协程：等待队列满足触发条件，调用 agv_agent 执行批量调度。

    queue 可以是 OrderQueue（内存）或 RedisOrderQueue（生产），自动适配。
    """
    from datetime import datetime
    from src.api.queue_manager import RedisOrderQueue
    from src.agents import agv_agent

    is_redis = isinstance(queue, RedisOrderQueue)

    while True:
        await queue.wait_for_flush()

        orders = await queue.drain_async() if is_redis else queue.drain()
        if not orders:
            continue

        run_id = str(uuid4())
        logger.info("调度触发: %d 条工单, run_id=%s", len(orders), run_id)
        try:
            inv_db = state.get("inv_db") if state else None
            sched_result, sim_result = await asyncio.to_thread(
                agv_agent.run,
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
            requeued = (
                await queue.requeue_async(orders) if is_redis else queue.requeue(orders)
            )
            if requeued:
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
