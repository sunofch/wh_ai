"""Agent 结构化输出 Schema 定义。"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, SerializeAsAny

from src.warehouse.models import InventoryItem, WorkOrder


class ParsedInstruction(BaseModel):
    """instruction_agent 的结构化输出 schema。"""
    part_name: str
    model: Optional[str] = None
    quantity: Optional[int] = None
    action_required: Optional[str] = None
    is_urgent: bool = False
    description: Optional[str] = None


# ── 统一结果载荷（DomainResult 多态）────────────────────────────────────────────

class DomainResult(BaseModel):
    """所有 Agent 结果的共同基类。

    kind 是判别标签，调用方据此分支处理。新增一种结果只需继承本类、
    固定自己的 kind，AgentResult 信封无需改动。
    """
    kind: str


class InventoryReport(DomainResult):
    """库存查询结果（查询意图产出，不建工单）。"""
    kind: Literal["inventory_report"] = "inventory_report"
    items: list[InventoryItem] = Field(default_factory=list)
    summary: str = ""


class WorkOrderResult(DomainResult):
    """出入库结果（出入库意图产出）。"""
    kind: Literal["work_order"] = "work_order"
    order: WorkOrder


class WarningReport(DomainResult):
    """库存预警分析结果（预警意图产出，不动库存、不建工单）。

    stock_warnings: 每个备件的需求预测 + 风险等级 + 补货建议（OptimizationResult.to_dict()）
    life_warnings:  寿命到期/临期备件清单（StockManager.list_life_warnings()）
    """
    kind: Literal["warning_report"] = "warning_report"
    stock_warnings: list[dict] = Field(default_factory=list)
    life_warnings: list[dict] = Field(default_factory=list)
    summary: str = ""


class GeneralReply(DomainResult):
    """通用/闲聊回复结果（general 意图产出，不动库存、不建工单）。"""
    kind: Literal["general_reply"] = "general_reply"
    text: str = ""


class AgentResult(BaseModel):
    """supervisor.run() 的统一结果信封。

    单入口 + 运行时 LLM 路由，调用方拿到结果前不知其类型，
    故用 intent + 带 kind 的 result 载荷让调用方分支。
    SerializeAsAny 保证多态载荷序列化时保留子类字段。
    """
    intent: str
    result: SerializeAsAny[DomainResult]
