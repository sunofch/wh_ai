# src/api/app.py
from __future__ import annotations
import asyncio
import base64
import logging
import random
from collections import OrderedDict
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse

from src.api.models import (
    InstructionRequest, InstructionResponse, ParsedInstruction,
    StatusResponse, ScheduleResult,
)
from src.api.queue_manager import OrderQueue
from src.api.scheduler import scheduler_loop
from src.warehouse.maps.base import MapRegistry
from src.warehouse.wms.order_manager import OrderManager, _ACTION_MAP
from src.warehouse.models import TaskType

import src.warehouse.maps.medium_57x47  # noqa: F401

logger = logging.getLogger(__name__)


def create_app(
    parser=None,
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
        app.state.parser           = parser
        app.state.inv_db           = inv_db
        app.state.vlm_available    = vlm_available
        app.state.queue            = OrderQueue()
        app.state.results          = OrderedDict()
        app.state.wmap             = wmap

        state_meta = {
            "last_run_id": None,
            "last_run_at": None,
            "scheduler_status": "idle",
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
                detail={"error": "parse_failed", "detail": "无有效输入"}
            )

        # 解码 base64 音频/图片
        audio = None
        image = None
        if req.audio_base64:
            try:
                audio = base64.b64decode(req.audio_base64)
            except Exception:
                raise HTTPException(
                    status_code=422,
                    detail={"error": "invalid_base64", "field": "audio_base64"}
                )
        if req.image_base64:
            try:
                image = base64.b64decode(req.image_base64)
            except Exception:
                raise HTTPException(
                    status_code=422,
                    detail={"error": "invalid_base64", "field": "image_base64"}
                )

        # VLM/规则解析
        instruction = await asyncio.to_thread(
            st.parser.parse,
            text=req.text, audio=audio, image=image,
        )

        # 全空检查
        if all(v is None for v in [
            instruction.part_name, instruction.model,
            instruction.quantity, instruction.action_required,
        ]):
            raise HTTPException(
                status_code=400,
                detail={"error": "parse_failed", "detail": "无法从输入中提取有效指令"}
            )

        # 库存查询 + 预留
        resolved_location = ""
        resolved_en_name  = ""
        target_port = ""
        instruction_id = str(uuid4())
        if st.inv_db:
            inv_item = None
            if instruction.model:
                inv_item = st.inv_db.query(instruction.model)
            if inv_item is None and instruction.part_name:
                inv_item = st.inv_db.query_by_name(instruction.part_name)
            if inv_item:
                qty = instruction.quantity if instruction.quantity is not None else 1
                location = st.inv_db.reserve(
                    inv_item.model, qty, order_id=instruction_id
                )
                if not location:
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "error": "insufficient_stock",
                            "part_name": instruction.part_name,
                            "requested": qty,
                            "available": inv_item.available,
                        }
                    )
                resolved_location = location
                resolved_en_name  = inv_item.en_name

        # 生成工单并入队
        map_config = MapRegistry.get("medium_57x47")
        om = OrderManager(map_config)
        order = om.from_port_instruction(instruction, inventory_db=None)

        if order and resolved_location:
            action = instruction.action_required or "出库"
            task_type = _ACTION_MAP.get(action, TaskType.OUTBOUND)
            inbound_p = [n for n, c in map_config.ports.items() if c["type"] == "INBOUND"]
            outbound_p = [n for n, c in map_config.ports.items() if c["type"] == "OUTBOUND"]
            rng = random.Random()
            if task_type == TaskType.INBOUND:
                port = rng.choice(inbound_p) if inbound_p else ""
                order.items[0].resolved_pick = port
                order.items[0].resolved_dest = resolved_location
            else:
                port = rng.choice(outbound_p) if outbound_p else ""
                order.items[0].resolved_pick = resolved_location
                order.items[0].resolved_dest = port
            target_port = port

        if order:
            order.metadata["raw_text"] = req.text or ""
            order.metadata["order_id"] = instruction_id
            st.queue.push(order)

        return InstructionResponse(
            instruction_id=instruction_id,
            status="queued",
            vlm_available=st.vlm_available,
            parsed=ParsedInstruction(**instruction.model_dump()),
            resolved_location=resolved_location,
            resolved_en_name=resolved_en_name,
            target_port=target_port,
        )

    @app.get("/status", response_model=StatusResponse)
    async def get_status(request: Request):
        st = request.app.state
        meta = getattr(st, "state_meta", {})
        return StatusResponse(
            queue_size=st.queue.size(),
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
        """按需生成调度动画 GIF"""
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
