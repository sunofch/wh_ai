"""跨模态需求优先级融合打分。

对应 pj4 子课题 4.1：把时序（库存/需求风险）、文本（指令语义紧急度）、
视觉（VLM 风险信号）三类模态信号统一编码到 [0,1]，加权融合为备件需求
优先级分数，并映射为工单优先级。

设计原则：
  - 纯函数、零外部依赖，调用方负责采集各模态信号；
  - 权重可配置，默认时序 > 文本 > 视觉（库存风险最客观）；
  - 只升不降：融合结果只用于把普通单提升为紧急单，不降级已有紧急单。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from src.warehouse.models import OrderPriority

# 各模态默认权重，和为 1
DEFAULT_WEIGHTS: dict[str, float] = {
    "temporal": 0.40,
    "text": 0.35,
    "visual": 0.25,
}

# 融合分数 ≥ 该阈值时映射为 URGENT
URGENT_THRESHOLD = 0.6

# 库存风险等级 → 时序风险分
_RISK_LEVEL_SCORES: dict[str, float] = {
    "normal": 0.1,
    "warning": 0.6,
    "critical": 1.0,
}

# 文本紧急度关键词（规则层语义信号，LLM 解析 is_urgent 之外的兜底）
_URGENT_KEYWORDS = ("紧急", "立刻", "立即", "马上", "故障", "停机", "抢修", "急需")
_KEYWORD_SCORE = 0.8
_BASE_TEXT_SCORE = 0.1


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def temporal_risk_from_level(risk_level: str) -> float:
    """库存风险等级（classify_inventory_risk 输出）→ 时序风险分。"""
    return _RISK_LEVEL_SCORES.get(risk_level, 0.0)


def text_urgency_score(is_urgent: bool, text: str) -> float:
    """文本模态紧急度：解析标记 is_urgent 优先，关键词兜底。"""
    if is_urgent:
        return 1.0
    if any(kw in text for kw in _URGENT_KEYWORDS):
        return _KEYWORD_SCORE
    return _BASE_TEXT_SCORE if text else 0.0


@dataclass(frozen=True)
class ModalitySignals:
    """三模态风险信号，均为 [0,1]，缺失模态置 0。"""
    temporal_risk: float = 0.0
    text_urgency: float = 0.0
    visual_risk: float = 0.0


@dataclass(frozen=True)
class PriorityScore:
    """融合结果：分数、各模态贡献、映射后的工单优先级。"""
    score: float
    priority: OrderPriority
    components: dict[str, float] = field(default_factory=dict)


def fuse_priority(
    signals: ModalitySignals,
    weights: dict[str, float] | None = None,
    urgent_threshold: float = URGENT_THRESHOLD,
) -> PriorityScore:
    """加权融合三模态信号为优先级分数。

    分数 ≥ urgent_threshold 映射为 URGENT，否则 NORMAL（不向下降级）。
    """
    w = weights or DEFAULT_WEIGHTS
    components = {
        "temporal": _clamp(signals.temporal_risk),
        "text": _clamp(signals.text_urgency),
        "visual": _clamp(signals.visual_risk),
    }
    score = _clamp(sum(components[name] * w.get(name, 0.0) for name in components))
    priority = OrderPriority.URGENT if score >= urgent_threshold else OrderPriority.NORMAL
    return PriorityScore(score=round(score, 4), priority=priority, components=components)
