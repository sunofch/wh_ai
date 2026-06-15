"""跨模态需求优先级融合打分测试。

对应 pj4 子课题 4.1：时序 + 文本 + 视觉三模态风险信号统一编码 → 备件需求优先级。
"""
from unittest.mock import patch

import pytest

from src.optimization.fusion import (
    DEFAULT_WEIGHTS,
    ModalitySignals,
    PriorityScore,
    fuse_priority,
    temporal_risk_from_level,
    text_urgency_score,
)
from src.warehouse.models import OrderPriority


# ── 单模态编码 ──

class TestModalityEncoding:
    def test_temporal_risk_mapping(self):
        assert temporal_risk_from_level("critical") == 1.0
        assert temporal_risk_from_level("warning") > temporal_risk_from_level("normal")
        assert 0.0 <= temporal_risk_from_level("normal") < 0.5
        assert temporal_risk_from_level("unknown-level") == 0.0

    def test_text_urgency_flag_dominates(self):
        assert text_urgency_score(True, "随便什么文本") == 1.0

    def test_text_urgency_keywords(self):
        score = text_urgency_score(False, "设备故障停机，马上要这个备件")
        assert score > text_urgency_score(False, "下周需要的常规领料")

    def test_text_urgency_bounded(self):
        for text in ("", "紧急！立刻！故障！停机！抢修！"):
            assert 0.0 <= text_urgency_score(False, text) <= 1.0


# ── 融合打分 ──

class TestFusePriority:
    def test_weights_sum_to_one(self):
        assert sum(DEFAULT_WEIGHTS.values()) == pytest.approx(1.0)

    def test_all_high_gives_urgent(self):
        signals = ModalitySignals(temporal_risk=1.0, text_urgency=1.0, visual_risk=1.0)
        ps = fuse_priority(signals)
        assert isinstance(ps, PriorityScore)
        assert ps.score == pytest.approx(1.0)
        assert ps.priority == OrderPriority.URGENT

    def test_all_low_stays_normal(self):
        signals = ModalitySignals(temporal_risk=0.1, text_urgency=0.1, visual_risk=0.0)
        ps = fuse_priority(signals)
        assert ps.priority == OrderPriority.NORMAL
        assert ps.score < 0.3

    def test_single_modality_urgent_text(self):
        """仅文本模态强紧急也应推高分数（人在回路语义信号）。"""
        ps = fuse_priority(ModalitySignals(text_urgency=1.0))
        assert ps.score >= DEFAULT_WEIGHTS["text"] * 0.99

    def test_components_recorded(self):
        signals = ModalitySignals(temporal_risk=0.5, text_urgency=0.4, visual_risk=0.3)
        ps = fuse_priority(signals)
        assert set(ps.components) == {"temporal", "text", "visual"}

    def test_signals_clamped(self):
        """越界输入被钳制到 [0,1]，不会产生超界分数。"""
        ps = fuse_priority(ModalitySignals(temporal_risk=5.0, text_urgency=-1.0, visual_risk=2.0))
        assert 0.0 <= ps.score <= 1.0


# ── 工单链路集成 ──

class TestWorkOrderIntegration:
    def _run_order(self, mgr, user_input, instructions, metadata=None):
        from src.agents.inventory.agent import InventoryAgent
        from src.agents.state import AgentState

        with patch("src.agents.inventory.tools._get_stock_manager", return_value=mgr):
            state = AgentState(
                user_input=user_input,
                instructions=instructions,
                metadata=metadata or {},
            )
            return InventoryAgent().run(state)

    @pytest.fixture
    def mgr(self, tmp_path):
        from src.warehouse.maps.base import MapRegistry
        import src.warehouse.maps.medium_57x47  # noqa: F401
        from src.warehouse.wms.inventory_db import StockManager

        m = StockManager(db_path=str(tmp_path / "t.db"))
        m.seed_from_map(MapRegistry.get("medium_57x47"), seed=42)
        return m

    def _find_part(self, mgr):
        for item in mgr.list_items():
            if item.available >= 1:
                return item
        raise AssertionError("无可用库存")

    def test_order_metadata_contains_priority_score(self, mgr):
        from src.agents.schemas import ParsedInstruction

        item = self._find_part(mgr)
        insts = [ParsedInstruction(
            part_name=item.part_name, model=item.model,
            quantity=1, action_required="出库",
        )]
        state = self._run_order(mgr, f"出库1个{item.part_name}", insts)
        order = state.work_order
        assert order is not None
        assert "priority_score" in order.metadata
        assert 0.0 <= order.metadata["priority_score"] <= 1.0

    def test_urgent_text_upgrades_priority(self, mgr):
        from src.agents.schemas import ParsedInstruction

        item = self._find_part(mgr)
        insts = [ParsedInstruction(
            part_name=item.part_name, model=item.model,
            quantity=1, action_required="出库", is_urgent=True,
        )]
        state = self._run_order(mgr, f"设备故障停机，紧急出库{item.part_name}", insts)
        assert state.work_order.priority == OrderPriority.URGENT

    def test_visual_risk_signal_raises_score(self, mgr):
        from src.agents.schemas import ParsedInstruction

        item = self._find_part(mgr)
        insts = [ParsedInstruction(
            part_name=item.part_name, model=item.model,
            quantity=1, action_required="出库",
        )]
        base = self._run_order(mgr, "出库", insts)
        risky = self._run_order(mgr, "出库", insts, metadata={"visual_risk": 1.0})
        assert (risky.work_order.metadata["priority_score"]
                > base.work_order.metadata["priority_score"])
