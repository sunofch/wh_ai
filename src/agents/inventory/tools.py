"""库存管理 Agent 的工具集合。

合并自原 agent_tools/inventory_tool.py 与 agent_tools/order_tool.py：
  - query_inventory       查询库存是否充足（出入库链路用）
  - lookup_stock_item     查询备件完整库存明细（查询意图用，返回 InventoryItem）
  - create_work_order     创建出入库工单
  - create_restock_order  库存不足时创建补货入库订单
  - create_restock        代码内部直接调用的补货逻辑（非 @tool）
  - build_warning_report  库存风险 + 寿命到期预警报告（预警意图用）
"""
import json
import uuid
from functools import lru_cache

from langchain_core.tools import tool

from src.agents.schemas import ParsedInstruction, WarningReport
from src.optimization.pipeline import analyze_inventory_optimization
from src.parser.parser import PortInstruction
from src.warehouse.maps.base import MapRegistry
from src.warehouse.models import InventoryItem
from src.warehouse.wms.inventory_db import StockManager
from src.warehouse.wms.order_manager import OrderManager
import src.warehouse.maps.medium_57x47  # noqa: F401 触发注册


@lru_cache(maxsize=1)
def _get_stock_manager() -> StockManager:
    return StockManager()


def lookup_stock_item(model: str | None, part_name: str | None) -> InventoryItem | None:
    """按型号优先、名称兜底，返回备件完整库存明细（查询意图用）。"""
    db = _get_stock_manager()
    item = db.query(model) if model else None
    if item is None and part_name:
        item = db.query_by_name(part_name)
    return item


def _analyze_item_risk(item: InventoryItem, db: StockManager) -> dict:
    """对单个库存条目做需求预测 + 风险分级，需求历史从出库履历派生。"""
    result = analyze_inventory_optimization(
        part_name=item.part_name,
        model=item.model,
        current_stock=item.available,
        demand_history=db.weekly_demand_history(item.model),
    )
    return result.to_dict()


def build_warning_report(
    instructions: list[ParsedInstruction],
    user_input: str = "",
) -> WarningReport:
    """构建库存预警报告（预警意图）。

    - 指令点名了具体备件 → 仅分析这些备件（无论风险高低都纳入报告）；
    - 未点名（全局提问）→ 扫描全库，只保留风险等级非 normal 的条目。
    同时附带寿命到期/临期清单。
    """
    db = _get_stock_manager()

    targets: dict[str, InventoryItem] = {}
    for inst in instructions:
        item = lookup_stock_item(inst.model, inst.part_name)
        if item is not None:
            targets[item.model] = item

    if targets:
        stock_warnings = [_analyze_item_risk(it, db) for it in targets.values()]
    else:
        stock_warnings = [
            risk
            for it in db.list_items()
            if (risk := _analyze_item_risk(it, db))["risk_level"] != "normal"
        ]

    life_warnings = db.list_life_warnings()
    risky = sum(1 for w in stock_warnings if w["risk_level"] != "normal")
    if targets:
        head = f"共分析{len(stock_warnings)}条备件库存，{risky}条存在库存风险"
    else:
        head = f"全库扫描发现{len(stock_warnings)}条风险备件"
    summary = f"{head}，{len(life_warnings)}条寿命到期/临期。"
    return WarningReport(
        stock_warnings=stock_warnings,
        life_warnings=life_warnings,
        summary=summary,
    )


@tool
def query_inventory(model: str, part_name: str, quantity: int) -> str:
    """检查指定备件的库存是否满足需求。model 或 part_name 至少提供一个。"""
    db = _get_stock_manager()
    item = db.query(model) if model else None
    if item is None and part_name:
        item = db.query_by_name(part_name)

    if item is None:
        return json.dumps(
            {"available": 0, "location": "", "sufficient": False},
            ensure_ascii=False,
        )

    available = item.quantity - item.reserved
    sufficient = available >= quantity
    return json.dumps(
        {
            "available": available,
            "location": item.location,
            "sufficient": sufficient,
            "shortage": 0 if sufficient else quantity - available,
        },
        ensure_ascii=False,
    )


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
            "priority": order.priority.value,
            "metadata": order.metadata,
            "items": [
                {
                    "task_type": i.task_type.value,
                    "model": i.model,
                    "part_name": i.part_name,
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
