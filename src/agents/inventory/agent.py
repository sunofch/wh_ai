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
    build_warning_report,
    create_restock_order,
    create_work_order,
    lookup_stock_item,
    query_inventory,
)
from src.agents.schemas import InventoryReport
from src.agents.state import AgentState
from src.optimization.fusion import ModalitySignals, fuse_priority, text_urgency_score
from src.warehouse.models import OrderItem, OrderPriority, TaskType, WorkOrder

# 时序风险信号的粗粒度编码：本单触发了缺货补货 → 高风险，否则低风险
_TEMPORAL_RISK_SHORTAGE = 0.7
_TEMPORAL_RISK_SUFFICIENT = 0.2

AGENT_NAME = "inventory_agent"

# 出入库动作关键词；指令中出现任一即判为出入库意图，否则视为查询意图。
_ORDER_ACTIONS = {"出库", "入库", "调库"}

# 预警分析关键词；用户输入或指令描述命中任一即判为预警意图（优先级低于出入库）。
_WARNING_KEYWORDS = ("预警", "风险", "到期", "寿命", "临期", "补货建议")


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

def _classify_intent(instructions: list, user_input: str = "") -> str:
    """规则意图分类（第2层）：order / warning / query 三路由。

    优先级：出入库动作 > 预警关键词 > 查询。
    复用 instruction_agent 已抽取的 action_required 字段，不额外调用 LLM。
    无解析结果且无预警关键词时回退为 order（保持旧默认：建空工单）。
    """
    if any((inst.action_required or "") in _ORDER_ACTIONS for inst in instructions):
        return "order"
    texts = [user_input, *((inst.description or "") for inst in instructions)]
    if any(kw in text for kw in _WARNING_KEYWORDS for text in texts if text):
        return "warning"
    if not instructions:
        return "order"
    return "query"


def _apply_priority_fusion(order: WorkOrder, state: AgentState) -> WorkOrder:
    """跨模态优先级融合：时序（缺货信号）+ 文本（紧急度）+ 视觉（VLM 风险）。

    融合分数与各模态贡献写入 metadata，分数达到阈值时把工单提升为 URGENT
    （只升不降，不动已是紧急的工单）。
    """
    signals = ModalitySignals(
        temporal_risk=(
            _TEMPORAL_RISK_SHORTAGE
            if order.metadata.get("restock_order_id")
            else _TEMPORAL_RISK_SUFFICIENT
        ),
        text_urgency=text_urgency_score(
            any(inst.is_urgent for inst in state.instructions),
            state.user_input,
        ),
        visual_risk=float(state.metadata.get("visual_risk", 0.0)),
    )
    fused = fuse_priority(signals)
    return order.model_copy(update={
        "priority": max(order.priority, fused.priority),
        "metadata": {
            **order.metadata,
            "priority_score": fused.score,
            "priority_components": fused.components,
        },
    })


def _summarize_stock(items: list) -> str:
    """把库存明细拼成简短的自然语言概述。"""
    if not items:
        return "未查询到匹配备件"
    return "；".join(
        f"{it.part_name}({it.model}) 可用{it.available}/在库{it.quantity}，库位{it.location}"
        for it in items
    )


class InventoryAgent:
    """库存管理 Agent 的 BaseAgent 封装。

    内部规则细分三类意图（第2层路由）：
      - order：  逐条查库存 / 建工单 / 不足补货（fan-out），合并为单个 work_order
      - warning：库存风险 + 寿命到期分析，产出 warning_report（不动库存）
      - query：  逐条查库存明细，产出 inventory_report（不建工单）
    """

    name = AGENT_NAME
    description = (
        "处理库存相关请求。支持三种意图："
        "① 查询——回报备件的库存数量 / 可用量 / 库位；"
        "② 出入库——按指令创建出入库工单、库存不足时自动补货；"
        "③ 预警——分析备件库存风险、寿命到期/临期并给出补货建议。"
        "需在 instruction_agent 解析出 instructions 之后调用。"
    )

    def run(self, state: AgentState) -> AgentState:
        intent = _classify_intent(state.instructions, state.user_input)
        if intent == "warning":
            report = build_warning_report(state.instructions, state.user_input)
            return state.with_updates(intent="warning", warning_report=report)
        if intent == "query":
            items = [
                item
                for inst in state.instructions
                if (item := lookup_stock_item(inst.model, inst.part_name)) is not None
            ]
            report = InventoryReport(items=items, summary=_summarize_stock(items))
            return state.with_updates(intent="query", inventory_report=report)

        pipeline = get_inventory_agent()
        orders = [
            pipeline.run(json.dumps(inst.model_dump(), ensure_ascii=False))
            for inst in state.instructions
        ]
        merged = _apply_priority_fusion(_merge_work_orders(orders), state)
        return state.with_updates(intent="order", work_order=merged)
