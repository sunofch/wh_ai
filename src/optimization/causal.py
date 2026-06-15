"""动态结构因果图模型（Dynamic SCM）。

对应 pj4 子课题 4.2：
  - decompose_demand / classify_demand_pattern：把备件需求序列分解为
    趋势 + 季节 + 残差，区分季节性 / 趋势性 / 突发性 / 平稳需求；
  - DynamicCausalGraph：以滞后线性 SCM 量化设备工况变量对备件需求的
    因果效应，滑动窗口 update() 跟踪效应的时变（动态因果图）。

实现只依赖 numpy；真实部署时输入由 IoT 感知层（src/iot）提供。
"""
from __future__ import annotations

import numpy as np

# 残差稳健 z 分数超过该阈值视为突发需求点
BURST_Z_THRESHOLD = 5.0
# 成分强度（1 - var(residual)/var(component+residual)）阈值
STRENGTH_THRESHOLD = 0.6
# 趋势须与时间高度相关才判定为趋势性（排除边缘效应假趋势）
TREND_CORR_THRESHOLD = 0.8


def _moving_average(series: np.ndarray, window: int) -> np.ndarray:
    """反射填充的居中滑动平均，输出与输入等长。"""
    if window % 2 == 0:
        window += 1
    half = window // 2
    padded = np.pad(series, half, mode="reflect")
    kernel = np.ones(window) / window
    return np.convolve(padded, kernel, mode="valid")


def decompose_demand(series: np.ndarray, period: int = 52) -> dict:
    """加性分解需求序列：series = trend + seasonal + residual。

    返回 trend/seasonal/residual 三个等长数组与 burst_indices（突发点）。
    季节成分仅在样本覆盖 ≥ 2 个完整周期时估计，否则置零。
    """
    series = np.asarray(series, dtype=np.float64)
    if series.ndim != 1 or len(series) < 8:
        raise ValueError(f"series must be 1-D with >= 8 points, got shape {series.shape}")

    n = len(series)
    # 经典分解：覆盖 ≥2 个完整周期时趋势窗口取整周期，完全滤掉季节成分；
    # 样本不足时退化为 n/4 短窗口（此时季节成分也不估计）
    window = period if n >= 2 * period else max(5, n // 4)
    trend = _moving_average(series, window)
    detrended = series - trend

    seasonal = np.zeros(n)
    if n >= 2 * period:
        phases = np.arange(n) % period
        for p in range(period):
            mask = phases == p
            seasonal[mask] = detrended[mask].mean()
        seasonal -= seasonal.mean()

    residual = detrended - seasonal

    # 稳健 z 分数（MAD）检测突发需求点；
    # 滑动平均在首尾半窗内失真，突发检测只看趋势估计有效的内部区间
    half = (window if window % 2 == 1 else window + 1) // 2
    interior = residual[half: n - half]
    median = np.median(interior)
    mad = np.median(np.abs(interior - median))
    scale = mad * 1.4826 if mad > 0 else (interior.std() or 1.0)
    z_scores = np.abs(interior - median) / scale
    burst_indices = [int(i) + half for i in np.flatnonzero(z_scores > BURST_Z_THRESHOLD)]

    return {
        "trend": trend,
        "seasonal": seasonal,
        "residual": residual,
        "burst_indices": burst_indices,
    }


def _strength(component: np.ndarray, residual: np.ndarray) -> float:
    """成分强度（STL 风格）：1 - var(residual) / var(component + residual)。"""
    denom = np.var(component + residual)
    if denom <= 0:
        return 0.0
    return max(0.0, 1.0 - np.var(residual) / denom)


def classify_demand_pattern(series: np.ndarray, period: int = 52) -> str:
    """需求模式四分类：bursty / trending / seasonal / stable。"""
    parts = decompose_demand(series, period=period)
    if parts["burst_indices"]:
        return "bursty"

    trend_centered = parts["trend"] - parts["trend"].mean()
    t = np.arange(len(trend_centered), dtype=np.float64)
    trend_std = trend_centered.std()
    trend_corr = (
        abs(np.corrcoef(trend_centered, t)[0, 1]) if trend_std > 0 else 0.0
    )
    if (
        _strength(trend_centered, parts["residual"]) > STRENGTH_THRESHOLD
        and trend_corr > TREND_CORR_THRESHOLD
    ):
        return "trending"

    if _strength(parts["seasonal"], parts["residual"]) > STRENGTH_THRESHOLD:
        return "seasonal"

    return "stable"


class DynamicCausalGraph:
    """滞后线性结构因果模型：target_t = Σ β_f · f_{t-lag} + b + ε。

    β_f 即工况变量 f 对需求的因果效应估计（最小二乘）。
    update() 以滑动窗口重估，effect_history 记录效应随时间的演化，
    支撑"自主演化、动态抗扰"的库存策略调整。
    """

    def __init__(
        self,
        target: str,
        lag: int = 1,
        window: int | None = None,
        edge_threshold: float = 0.1,
    ):
        if lag < 1:
            raise ValueError(f"lag must be >= 1, got {lag}")
        self.target = target
        self.lag = lag
        self.window = window
        self.edge_threshold = edge_threshold
        self._effects: dict[str, float] = {}
        self.effect_history: list[dict[str, float]] = []

    def fit(self, data: dict[str, np.ndarray]) -> dict[str, float]:
        """在给定多源序列上估计因果效应。data 必须包含 target 序列。"""
        if self.target not in data:
            raise ValueError(f"data missing target series '{self.target}'")
        features = [name for name in data if name != self.target]
        if not features:
            raise ValueError("data must contain at least one driver series")

        lengths = {len(np.asarray(v)) for v in data.values()}
        if len(lengths) != 1:
            raise ValueError(f"all series must share the same length, got {lengths}")
        n = lengths.pop()
        if n - self.lag <= len(features) + 1:
            raise ValueError("not enough samples to estimate causal effects")

        y = np.asarray(data[self.target], dtype=np.float64)[self.lag:]
        X = np.column_stack(
            [np.asarray(data[name], dtype=np.float64)[: -self.lag] for name in features]
            + [np.ones(n - self.lag)]
        )
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        self._effects = {
            name: round(float(beta[i]), 4) for i, name in enumerate(features)
        }
        return dict(self._effects)

    def update(self, data: dict[str, np.ndarray]) -> dict[str, float]:
        """滑动窗口重估因果效应并记入演化历史。"""
        if self.window is not None:
            keep = self.window + self.lag
            data = {name: np.asarray(v)[-keep:] for name, v in data.items()}
        effects = self.fit(data)
        self.effect_history.append(effects)
        return effects

    def causal_effects(self) -> dict[str, float]:
        """最近一次估计的因果效应（β 系数）。"""
        return dict(self._effects)

    def edges(self) -> list[tuple[str, str, float]]:
        """因果图边：|效应| 超过阈值的 (driver, target, effect)。"""
        return [
            (name, self.target, effect)
            for name, effect in self._effects.items()
            if abs(effect) >= self.edge_threshold
        ]

    def strongest_drivers(self, k: int = 3) -> list[tuple[str, float]]:
        """按效应绝对值降序返回前 k 个驱动因子。"""
        ranked = sorted(
            self._effects.items(), key=lambda kv: abs(kv[1]), reverse=True
        )
        return ranked[:k]
