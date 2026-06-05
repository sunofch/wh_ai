"""Agent 2：库存管理 Agent（Inventory Management Agent）。

职责：
  1. 查询库存可用量
  2. 创建出入库工单
  3. 库存不足时自主触发补货

图结构（纯 Python 节点，不走 LLM，零 token 消耗）：
  node_query → node_work_order → (sufficient=False) → node_restock → END
                               → (sufficient=True)  → END
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from src.agents.inventory.tools import (
    create_restock_order,
    create_work_order,
    query_inventory,
)
from src.agents.state import AgentState
from src.warehouse.models import OrderItem, OrderPriority, TaskType, WorkOrder

AGENT_NAME = "inventory_agent"


def _merge_work_orders(orders: list[WorkOrder]) -> WorkOrder:
    """将多个 WorkOrder 合并为一个，取最高优先级，合并并重新编号所有 items。"""
    if not orders:
        return WorkOrder(order_id=0, source="vlm", priority=OrderPriority.NORMAL)
    if len(orders) == 1:
        return orders[0]

    merged_priority = max(o.priority for o in orders)
    merged_metadata: dict = {}
    for o in orders:
        merged_metadata.update(o.metadata)

    all_items = [item for o in orders for item in o.items]
    renumbered = [item.model_copy(update={"item_id": i + 1}) for i, item in enumerate(all_items)]

    return WorkOrder(
        order_id=orders[0].order_id,
        source="vlm",
        priority=merged_priority,
        items=renumbered,
        metadata=merged_metadata,
    )


class InventoryState(TypedDict):
    instruction: dict
    inventory_data: dict
    work_order: WorkOrder | None


def _parse_json(text: str) -> dict:
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return {}


def _build_work_order(data: dict) -> WorkOrder | None:
    if data.get("status") != "created":
        return None
    priority_value = data.get("priority", OrderPriority.NORMAL.value)
    if isinstance(priority_value, str) and priority_value in OrderPriority.__members__:
        priority = OrderPriority[priority_value]
    else:
        priority = OrderPriority(priority_value)
    items = [
        OrderItem(
            item_id=i + 1,
            task_type=TaskType(item["task_type"]),
            model=item.get("model", ""),
            part_name=item.get("part_name", ""),
            quantity=item.get("quantity", 1),
            resolved_pick=item.get("pick", ""),
            resolved_dest=item.get("dest", ""),
        )
        for i, item in enumerate(data.get("items", []))
    ]
    return WorkOrder(
        order_id=data.get("order_id", 0),
        source="vlm",
        priority=priority,
        items=items,
        metadata=data.get("metadata", {}),
    )


class _InventoryPipeline:
    def __init__(self, graph):
        self._graph = graph

    def run(self, parsed_text: str) -> WorkOrder:
        result = self._graph.invoke({
            "instruction": _parse_json(parsed_text),
            "inventory_data": {},
            "work_order": None,
        })
        return result.get("work_order") or WorkOrder(
            order_id=0, source="vlm", priority=OrderPriority.NORMAL
        )


@lru_cache(maxsize=1)
def get_inventory_agent() -> _InventoryPipeline:
    """返回库存管理 Pipeline（LangGraph 自定义图，纯 Python 节点）。"""

    def node_query(state: InventoryState) -> dict:
        inst = state["instruction"]
        result = query_inventory.invoke({
            "model": inst.get("model") or "",
            "part_name": inst.get("part_name") or "",
            "quantity": inst.get("quantity") or 1,
        })
        return {"inventory_data": json.loads(result)}

    def node_work_order(state: InventoryState) -> dict:
        inst = state["instruction"]
        result = create_work_order.invoke({
            "part_name": inst.get("part_name") or "",
            "model": inst.get("model") or "",
            "quantity": inst.get("quantity") or 1,
            "action_required": inst.get("action_required") or "出库",
            "is_urgent": inst.get("is_urgent") or False,
        })
        return {"work_order": _build_work_order(json.loads(result))}

    def node_restock(state: InventoryState) -> dict:
        inst = state["instruction"]
        inv = state["inventory_data"]
        result = create_restock_order.invoke({
            "model": inst.get("model") or "",
            "part_name": inst.get("part_name") or "",
            "shortage": inv.get("shortage") or inst.get("quantity") or 1,
            "is_urgent": inst.get("is_urgent") or False,
        })
        restock_data = json.loads(result)
        order = state["work_order"]
        if order and restock_data.get("order_id"):
            new_metadata = {**order.metadata, "restock_order_id": restock_data["order_id"]}
            order = order.model_copy(update={"metadata": new_metadata})
        return {"work_order": order}

    def _route_restock(state: InventoryState) -> str:
        return "node_restock" if not state["inventory_data"].get("sufficient", True) else END

    graph = StateGraph(InventoryState)
    graph.add_node("node_query", node_query)
    graph.add_node("node_work_order", node_work_order)
    graph.add_node("node_restock", node_restock)
    graph.add_edge(START, "node_query")
    graph.add_edge("node_query", "node_work_order")
    graph.add_conditional_edges("node_work_order", _route_restock, {
        "node_restock": "node_restock",
        END: END,
    })
    graph.add_edge("node_restock", END)

    return _InventoryPipeline(graph.compile())


# ── BaseAgent 包装 ────────────────────────────────────────────────────────────

class InventoryAgent:
    """库存管理 Agent 的 BaseAgent 封装。

    对 state.instructions 逐条查库存 / 建工单 / 不足补货（fan-out），
    合并为单个 work_order 写回 state。
    """

    name = AGENT_NAME
    description = (
        "对已解析的指令列表 instructions 逐条查询库存、创建出入库工单、"
        "库存不足时自动补货，并合并为单个 work_order。"
        "需在 instruction_agent 解析出 instructions 之后调用。"
    )

    def run(self, state: AgentState) -> AgentState:
        pipeline = get_inventory_agent()
        orders = [
            pipeline.run(json.dumps(inst.model_dump(), ensure_ascii=False))
            for inst in state.instructions
        ]
        return state.with_updates(work_order=_merge_work_orders(orders))
