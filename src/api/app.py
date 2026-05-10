# src/api/app.py
from __future__ import annotations
import asyncio
import base64
import logging
from collections import OrderedDict
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request

from src.api.models import (
    InstructionRequest, InstructionResponse, ParsedInstruction,
    StatusResponse, ScheduleResult,
)
from src.api.queue_manager import OrderQueue
from src.api.scheduler import scheduler_loop

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
        app.state.last_run_id      = None
        app.state.last_run_at      = None
        app.state.scheduler_status = "idle"

        sched_task = None
        if wmap and fleet and wh_config:
            sched_task = asyncio.create_task(
                scheduler_loop(
                    app.state.queue, app.state.results,
                    wmap, fleet, wh_config,
                    inbound_ports or [], outbound_ports or [],
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

        # 库存查询 + 扣减
        resolved_location = ""
        target_port = ""
        if st.inv_db:
            inv_item = None
            if instruction.model:
                inv_item = st.inv_db.query_by_model(instruction.model)
            if inv_item is None and instruction.part_name:
                inv_item = st.inv_db.query_by_part_name(instruction.part_name)
            if inv_item:
                qty = instruction.quantity or 1
                location = st.inv_db.allocate_stock(inv_item.model, qty)
                if not location:
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "error": "insufficient_stock",
                            "part_name": instruction.part_name,
                            "requested": qty,
                            "available": inv_item.quantity,
                        }
                    )
                resolved_location = location

        # 生成工单并入队
        import src.warehouse.maps.medium_57x47  # noqa: F401
        from src.warehouse.maps.base import MapRegistry
        from src.warehouse.wms.order_manager import OrderManager, _ACTION_MAP
        from src.warehouse.models import TaskType
        import random

        map_config = MapRegistry.get("medium_57x47")
        om = OrderManager(map_config)
        order = om.from_port_instruction(instruction, inventory_db=None)

        if order and resolved_location:
            action = instruction.action_required or "出库"
            task_type = _ACTION_MAP.get(action, TaskType.OUTBOUND)
            inbound_p = [n for n, c in map_config.ports.items() if c["type"] == "INBOUND"]
            outbound_p = [n for n, c in map_config.ports.items() if c["type"] == "OUTBOUND"]
            rng = random.Random(42)
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
            st.queue.push(order)

        return InstructionResponse(
            instruction_id=str(uuid4()),
            status="queued",
            vlm_available=st.vlm_available,
            parsed=ParsedInstruction(**instruction.model_dump()),
            resolved_location=resolved_location,
            target_port=target_port,
        )

    @app.get("/status", response_model=StatusResponse)
    async def get_status(request: Request):
        st = request.app.state
        return StatusResponse(
            queue_size=st.queue.size(),
            last_run_id=st.last_run_id,
            last_run_at=st.last_run_at,
            scheduler_status=st.scheduler_status,
        )

    @app.get("/result/{run_id}", response_model=ScheduleResult)
    async def get_result(run_id: str, request: Request):
        result = request.app.state.results.get(run_id)
        if result is None:
            raise HTTPException(status_code=404, detail="run_id not found")
        return result
