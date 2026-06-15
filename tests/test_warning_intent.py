"""预警分析意图（第2层第三路由：query / order / warning）测试。

对应 pj4 TODO P1-1：工单创建 / 库存查询 / 预警分析三类语义路由。
"""
from unittest.mock import patch

import pytest

from src.agents.inventory.agent import _classify_intent
from src.agents.schemas import ParsedInstruction, WarningReport
from src.warehouse.maps.base import MapRegistry
import src.warehouse.maps.medium_57x47  # noqa: F401
from src.warehouse.wms.inventory_db import StockManager


@pytest.fixture
def mgr(tmp_path):
    path = str(tmp_path / "test.db")
    mgr = StockManager(db_path=path)
    mgr.seed_from_map(MapRegistry.get("medium_57x47"), seed=42)
    return mgr


def _find_model(mgr, min_available: int = 3) -> str:
    from src.warehouse.wms.inventory_db import _PARTS_CATALOG
    mc = MapRegistry.get("medium_57x47")
    for zn, zc in mc.rack_zones.items():
        for part in _PARTS_CATALOG.get(zc.zone_type, []):
            model = f"{part['model_base']}-{zn}"
            item = mgr.query(model)
            if item and item.available >= min_available:
                return model
    raise AssertionError("seed 库存中找不到可用 model")


# ── 第2层意图分类 ──

class TestClassifyIntent:
    def test_warning_by_user_input(self):
        insts = [ParsedInstruction(part_name="滤芯")]
        assert _classify_intent(insts, user_input="分析滤芯的库存预警情况") == "warning"

    def test_warning_by_global_question(self):
        assert _classify_intent([], user_input="哪些备件存在库存风险？") == "warning"

    def test_warning_by_description(self):
        insts = [ParsedInstruction(part_name="轴承", description="检查寿命到期预警")]
        assert _classify_intent(insts, user_input="") == "warning"

    def test_order_unaffected(self):
        insts = [ParsedInstruction(part_name="轴承", action_required="出库")]
        assert _classify_intent(insts, user_input="出库2个轴承") == "order"

    def test_query_unaffected(self):
        insts = [ParsedInstruction(part_name="轴承")]
        assert _classify_intent(insts, user_input="轴承还有多少库存") == "query"


# ── 周需求历史（从 stock_move 派生）──

class TestWeeklyDemandHistory:
    def test_confirm_moves_counted_in_latest_week(self, mgr):
        model = _find_model(mgr)
        mgr.reserve(model, 2, order_id="o1")
        mgr.confirm(model, 2, order_id="o1")
        history = mgr.weekly_demand_history(model, weeks=4)
        assert len(history) == 4
        assert history[-1] == 2          # 最近一周
        assert sum(history[:-1]) == 0

    def test_no_moves_returns_zeros(self, mgr):
        model = _find_model(mgr)
        assert mgr.weekly_demand_history(model, weeks=4) == [0, 0, 0, 0]


# ── 预警报告构建（inventory_agent warning 路由）──

class TestWarningReport:
    def _run_agent(self, mgr, instructions, user_input):
        from src.agents.inventory.agent import InventoryAgent
        from src.agents.state import AgentState

        with patch("src.agents.inventory.tools._get_stock_manager", return_value=mgr):
            state = AgentState(user_input=user_input, instructions=instructions)
            return InventoryAgent().run(state)

    def test_specific_part_warning(self, mgr):
        model = _find_model(mgr)
        item = mgr.query(model)
        insts = [ParsedInstruction(part_name=item.part_name, model=model)]
        result = self._run_agent(mgr, insts, f"分析{item.part_name}的库存风险")

        assert result.intent == "warning"
        report = result.warning_report
        assert isinstance(report, WarningReport)
        assert len(report.stock_warnings) == 1
        w = report.stock_warnings[0]
        assert w["model"] == model
        assert w["risk_level"] in ("normal", "warning", "critical")
        assert report.summary != ""

    def test_global_warning_includes_life_warnings(self, mgr):
        model = _find_model(mgr)
        mgr.set_life_expectancy(model, 1)  # 1周寿命 → 处于临期窗口
        result = self._run_agent(mgr, [], "哪些备件需要预警？")

        assert result.intent == "warning"
        report = result.warning_report
        assert any(w["model"] == model for w in report.life_warnings)

    def test_supervisor_envelope_for_warning(self, mgr):
        """supervisor 最终结果信封应携带 WarningReport。"""
        from src.agents.supervisor import _assemble_result

        model = _find_model(mgr)
        item = mgr.query(model)
        insts = [ParsedInstruction(part_name=item.part_name, model=model)]
        state = self._run_agent(mgr, insts, "库存风险分析")

        envelope = _assemble_result(state)
        assert envelope.intent == "warning"
        assert envelope.result.kind == "warning_report"
