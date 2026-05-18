import json
import uuid

from langchain_core.tools import tool

from src.parser.parser import PortInstruction
from src.warehouse.wms.order_manager import OrderManager
from src.warehouse.maps.base import MapRegistry
import src.warehouse.maps.medium_57x47  # noqa: F401 触发注册


def create_restock(
    model: str, part_name: str, shortage: int, is_urgent: bool
) -> dict:
    """出库缺货时由代码直接调用，创建补货入库订单。"""
    map_cfg = MapRegistry.get("medium_57x47")
    inst = PortInstruction(
        part_name=part_name,
        model=model,
        quantity=shortage,
        action_required="入库",
        is_urgent=is_urgent,
    )
    om = OrderManager(map_cfg)
    om.from_port_instruction(inst)

    order_id = f"RS-{uuid.uuid4().hex[:8].upper()}"
    return {
        "order_id": order_id,
        "status": "created",
        "message": f"已生成补货入库订单，缺口数量: {shortage}",
    }


@tool
def create_work_order(
    part_name: str,
    model: str,
    quantity: int,
    action_required: str,
    is_urgent: bool = False,
) -> str:
    """根据领料指令创建出入库工单。action_required 为 '出库'/'入库'/'调库'。"""
    from src.warehouse.wms.inventory_db import StockManager

    map_cfg = MapRegistry.get("medium_57x47")
    db = StockManager()
    om = OrderManager(map_cfg)
    inst = PortInstruction(
        part_name=part_name,
        model=model,
        quantity=quantity,
        action_required=action_required,
        is_urgent=is_urgent,
    )
    order = om.from_port_instruction(inst, inventory_db=db)
    if order is None:
        return json.dumps(
            {"status": "failed", "message": "字段不足，无法创建工单"},
            ensure_ascii=False,
        )
    return json.dumps(
        {
            "status": "created",
            "order_id": order.order_id,
            "items": [
                {
                    "task_type": i.task_type.value,
                    "quantity": i.quantity,
                    "pick": i.resolved_pick,
                    "dest": i.resolved_dest,
                }
                for i in order.items
            ],
        },
        ensure_ascii=False,
    )


@tool
def create_restock_order(
    model: str,
    part_name: str,
    shortage: int,
    is_urgent: bool = False,
) -> str:
    """库存不足时创建补货入库订单。shortage 为缺口数量。"""
    result = create_restock(
        model=model,
        part_name=part_name,
        shortage=shortage,
        is_urgent=is_urgent,
    )
    return json.dumps(result, ensure_ascii=False)
