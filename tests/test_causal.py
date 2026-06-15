"""动态结构因果图模型（SCM）测试。

对应 pj4 子课题 4.2：构建结构因果模型分析需求波动驱动因子，
区分季节性/趋势性/突发性需求，量化设备工况对备件需求的因果效应。
"""
import numpy as np
import pytest

from src.optimization.causal import (
    DynamicCausalGraph,
    classify_demand_pattern,
    decompose_demand,
)


def _seasonal_series(n=104, period=52, amp=10.0, seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    return 20 + amp * np.sin(2 * np.pi * t / period) + rng.normal(0, 0.5, n)


# ── 需求分解与模式区分 ──

class TestDemandDecomposition:
    def test_components_shape(self):
        series = _seasonal_series()
        parts = decompose_demand(series, period=52)
        for key in ("trend", "seasonal", "residual"):
            assert len(parts[key]) == len(series)

    def test_seasonal_pattern_detected(self):
        assert classify_demand_pattern(_seasonal_series(), period=52) == "seasonal"

    def test_trend_pattern_detected(self):
        rng = np.random.default_rng(1)
        series = 5 + 0.8 * np.arange(80) + rng.normal(0, 0.5, 80)
        assert classify_demand_pattern(series, period=52) == "trending"

    def test_burst_pattern_detected(self):
        rng = np.random.default_rng(2)
        series = 10 + rng.normal(0, 1.0, 80)
        series[40] += 60  # 突发需求
        result = decompose_demand(series, period=52)
        assert 40 in result["burst_indices"]
        assert classify_demand_pattern(series, period=52) == "bursty"

    def test_stable_pattern(self):
        rng = np.random.default_rng(3)
        series = 10 + rng.normal(0, 0.3, 80)
        assert classify_demand_pattern(series, period=52) == "stable"

    def test_short_series_raises(self):
        with pytest.raises(ValueError):
            decompose_demand(np.ones(3), period=52)


# ── 动态因果图 ──

class TestDynamicCausalGraph:
    def _synthetic(self, n=200, seed=0):
        """demand_t = 2*load_{t-1} + 0.5 + noise；humidity 无因果作用。"""
        rng = np.random.default_rng(seed)
        load = rng.normal(5, 1.0, n)
        humidity = rng.normal(50, 5.0, n)
        demand = np.zeros(n)
        demand[1:] = 2.0 * load[:-1] + 0.5 + rng.normal(0, 0.2, n - 1)
        return {"load": load, "humidity": humidity, "demand": demand}

    def test_true_driver_identified(self):
        data = self._synthetic()
        g = DynamicCausalGraph(target="demand")
        g.fit(data)
        effects = g.causal_effects()
        assert effects["load"] == pytest.approx(2.0, abs=0.3)
        assert abs(effects["humidity"]) < 0.2

    def test_strongest_drivers_ranked(self):
        g = DynamicCausalGraph(target="demand")
        g.fit(self._synthetic())
        drivers = g.strongest_drivers(k=1)
        assert drivers[0][0] == "load"

    def test_dynamic_update_tracks_regime_change(self):
        """滑动窗口更新应跟踪因果效应的时变（动态 SCM 核心）。"""
        rng = np.random.default_rng(5)
        n = 300
        load = rng.normal(5, 1.0, n)
        demand = np.zeros(n)
        # 前半段效应 2.0，后半段效应骤降为 0.2（设备大修后工况变化）
        demand[1:150] = 2.0 * load[:149] + rng.normal(0, 0.2, 149)
        demand[150:] = 0.2 * load[149:-1] + rng.normal(0, 0.2, 150)

        g = DynamicCausalGraph(target="demand", window=100)
        early = g.update({"load": load[:120], "demand": demand[:120]})
        late = g.update({"load": load[-120:], "demand": demand[-120:]})
        assert early["load"] > 1.5
        assert late["load"] < 0.6
        assert len(g.effect_history) == 2

    def test_missing_target_raises(self):
        g = DynamicCausalGraph(target="demand")
        with pytest.raises(ValueError):
            g.fit({"load": np.ones(50)})
