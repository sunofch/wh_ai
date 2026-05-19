# src/api/app.py
from __future__ import annotations
import asyncio
import base64
import logging
import os
from collections import OrderedDict
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse

from src.api.models import (
    InstructionRequest, InstructionResponse, ParsedInstruction,
    StatusResponse, ScheduleResult, AgentResultResponse,
)
from src.api.queue_manager import OrderQueue, RedisOrderQueue
from src.api.scheduler import scheduler_loop
from src.warehouse.maps.base import MapRegistry

import src.warehouse.maps.medium_57x47  # noqa: F401

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


def _try_build_redis_queue() -> RedisOrderQueue | None:
    """尝试连接 Redis，失败则返回 None（降级到内存队列）。"""
    try:
        import redis as _redis
        client = _redis.from_url(REDIS_URL)
        client.ping()
        client.close()
        return RedisOrderQueue(REDIS_URL)
    except Exception as e:
        logger.warning("Redis 不可用，使用内存队列降级: %s", e)
        return None


def create_app(
    inv_db=None,
    vlm_available: bool = False,
    wmap=None,
    fleet=None,
    wh_config=None,
    inbound_ports: list[str] | None = None,
    outbound_ports: list[str] | None = None,
) -> FastAPI:
    """工厂函数，便于测试时注入依赖。"""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # 优先使用 Redis 队列，不可用时降级到内存队列
        redis_queue = _try_build_redis_queue()
        app.state.queue        = redis_queue or OrderQueue()
        app.state.using_redis  = redis_queue is not None
        app.state.results      = OrderedDict()
        app.state.inv_db       = inv_db
        app.state.vlm_available = vlm_available
        app.state.wmap         = wmap

        state_meta = {
            "last_run_id": None,
            "last_run_at": None,
            "scheduler_status": "idle",
            "inv_db": inv_db,
        }
        app.state.state_meta = state_meta

        sched_task = None
        if wmap and fleet and wh_config:
            sched_task = asyncio.create_task(
                scheduler_loop(
                    app.state.queue, app.state.results,
                    wmap, fleet, wh_config,
                    inbound_ports or [], outbound_ports or [],
                    state=state_meta,
                )
            )

        yield

        if sched_task:
            sched_task.cancel()
            try:
                await sched_task
            except asyncio.CancelledError:
                pass

        if redis_queue:
            await redis_queue.close()

    app = FastAPI(title="AGV Warehouse API", lifespan=lifespan)
    _register_routes(app)
    return app


def _register_routes(app: FastAPI):

    @app.post("/instructions", response_model=InstructionResponse)
    async def post_instruction(req: InstructionRequest, request: Request):
        st = request.app.state

        if not req.text and not req.audio_base64 and not req.image_base64:
            raise HTTPException(
                status_code=400,
                detail={"error": "parse_failed", "detail": "无有效输入"},
            )

        # 验证 base64 格式（不解码完整内容，只检查格式）
        if req.audio_base64:
            try:
                base64.b64decode(req.audio_base64, validate=True)
            except Exception:
                raise HTTPException(
                    status_code=422,
                    detail={"error": "invalid_base64", "field": "audio_base64"},
                )
        if req.image_base64:
            try:
                base64.b64decode(req.image_base64, validate=True)
            except Exception:
                raise HTTPException(
                    status_code=422,
                    detail={"error": "invalid_base64", "field": "image_base64"},
                )

        instruction_id = str(uuid4())

        if st.vlm_available:
            # 异步路径：提交 Celery 任务，立即返回
            from src.api.celery_app import process_order, process_order_urgent
            is_urgent = bool(req.text and "紧急" in req.text)
            task_fn = process_order_urgent if is_urgent else process_order
            task_fn.apply_async(
                args=[req.text, req.image_base64, instruction_id],
                task_id=instruction_id,
            )
            return InstructionResponse(
                instruction_id=instruction_id,
                status="queued",
                vlm_available=True,
            )
        else:
            # 降级路径：规则解析，同步返回
            from src.parser.parser import PortInstructionParser
            from src.warehouse.wms.order_manager import OrderManager
            from src.warehouse.wms.config import WarehouseConfig
            map_config = MapRegistry.get("medium_57x47")
            wh_config_local = WarehouseConfig()
            om = OrderManager(map_config, seed=wh_config_local.RANDOM_SEED)
            parser = PortInstructionParser()
            instruction = parser._rule_based_parse(req.text or "")
            order = om.from_port_instruction(instruction, inventory_db=None)
            if order:
                order.metadata["raw_text"] = req.text or ""
                order.metadata["instruction_id"] = instruction_id
                if isinstance(st.queue, RedisOrderQueue):
                    import json
                    from src.api.queue_manager import _work_order_to_dict, PENDING_ORDERS_KEY
                    import redis as _redis
                    rc = _redis.from_url(REDIS_URL)
                    rc.rpush(PENDING_ORDERS_KEY, json.dumps(_work_order_to_dict(order), ensure_ascii=False))
                    rc.close()
                else:
                    st.queue.push(order)
            _item = order.items[0] if order and order.items else None
            return InstructionResponse(
                instruction_id=instruction_id,
                status="queued",
                vlm_available=False,
                parsed=ParsedInstruction(
                    part_name=_item.part_name if _item else None,
                    model=_item.model if _item else None,
                    quantity=_item.quantity if _item else None,
                ) if _item else None,
            )

    @app.get("/agent-result/{instruction_id}", response_model=AgentResultResponse)
    async def get_agent_result(instruction_id: str):
        """查询单条指令的 Agent 处理结果（WorkOrder）。"""
        from celery.result import AsyncResult
        from src.api.celery_app import celery_app

        result = AsyncResult(instruction_id, app=celery_app)

        if result.state == "PENDING":
            return AgentResultResponse(instruction_id=instruction_id, status="pending")
        if result.state == "FAILURE":
            return AgentResultResponse(
                instruction_id=instruction_id,
                status="failed",
                error=str(result.info),
            )
        if result.state == "SUCCESS":
            data = result.result or {}
            return AgentResultResponse(
                instruction_id=instruction_id,
                status="completed",
                work_order=data.get("work_order"),
            )
        return AgentResultResponse(instruction_id=instruction_id, status=result.state.lower())

    @app.get("/status", response_model=StatusResponse)
    async def get_status(request: Request):
        st = request.app.state
        meta = getattr(st, "state_meta", {})
        queue = st.queue
        if isinstance(queue, RedisOrderQueue):
            queue_size = await queue.size()
        else:
            queue_size = queue.size()
        return StatusResponse(
            queue_size=queue_size,
            last_run_id=meta.get("last_run_id"),
            last_run_at=meta.get("last_run_at"),
            scheduler_status=meta.get("scheduler_status", "idle"),
        )

    @app.get("/result/{run_id}", response_model=ScheduleResult)
    async def get_result(run_id: str, request: Request):
        entry = request.app.state.results.get(run_id)
        if entry is None:
            raise HTTPException(status_code=404, detail="run_id not found")
        return entry[0]

    @app.get("/result/{run_id}/animation")
    async def get_animation(run_id: str, request: Request):
        """按需生成调度动画 GIF。"""
        entry = request.app.state.results.get(run_id)
        if entry is None:
            raise HTTPException(status_code=404, detail="run_id not found")

        sched: ScheduleResult = entry[0]
        if not sched.has_animation:
            raise HTTPException(status_code=404, detail="animation not enabled for this run")

        sim_result = entry[1]
        wmap = request.app.state.wmap
        if wmap is None or sim_result is None:
            raise HTTPException(status_code=404, detail="animation data not available")

        gif_path = Path(f"output/animation_{run_id}.gif")
        if not gif_path.exists():
            gif_path.parent.mkdir(parents=True, exist_ok=True)
            from src.warehouse.visualize_animation import create_animation
            await asyncio.to_thread(create_animation, wmap, sim_result, str(gif_path), fps=10)

        return FileResponse(str(gif_path), media_type="image/gif",
                            filename=f"animation_{run_id}.gif")
