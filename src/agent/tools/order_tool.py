import json
import uuid
from langchain_core.tools import tool
from src.parser.parser import PortInstruction
from src.warehouse.wms.order_manager import OrderManager
from src.warehouse.maps.base import MapRegistry
import src.warehouse.maps.medium_57x47  # noqa: F401 触发注册


@tool
def create_restock_order(
    model: str, part_name: str, shortage: int, is_urgent: bool
) -> str:
    """库存不足且为出库指令时，自动生成补货入库订单。"""
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
    return json.dumps(
        {
            "order_id": order_id,
            "status": "created",
            "message": f"已生成补货入库订单，缺口数量: {shortage}",
        },
        ensure_ascii=False,
    )
