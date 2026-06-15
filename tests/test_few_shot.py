"""小样本寿命预测模型测试。

对应 pj4 子课题 4.3：主成分分析辨识关键寿命影响因素 +
Encoder-Decoder 小样本学习，解决备件寿命样本稀缺问题。
"""
import numpy as np
import pytest
import torch

from src.optimization.models.few_shot import (
    EncoderDecoderLifePredictor,
    identify_key_factors,
)


def _synthetic_dataset(n: int = 20, seq_len: int = 8, n_features: int = 4, seed: int = 0):
    """合成退化序列：寿命由特征0的退化斜率决定，其余特征为噪声。"""
    rng = np.random.default_rng(seed)
    xs, ys = [], []
    for _ in range(n):
        slope = rng.uniform(0.05, 0.5)
        t = np.arange(seq_len)
        seq = rng.normal(0, 0.05, size=(seq_len, n_features))
        seq[:, 0] += slope * t                  # 关键退化因子
        xs.append(seq)
        ys.append(10.0 / slope)                 # 剩余寿命与退化速度成反比
    return (
        torch.tensor(np.array(xs), dtype=torch.float32),
        torch.tensor(np.array(ys), dtype=torch.float32),
    )


# ── PCA 关键因素辨识 ──

class TestKeyFactors:
    def test_dominant_factor_identified(self):
        rng = np.random.default_rng(1)
        n = 100
        X = rng.normal(0, 0.1, size=(n, 4))
        X[:, 2] += rng.normal(0, 5.0, size=n)   # 特征2方差占主导
        result = identify_key_factors(X, ["温度", "振动", "载荷", "湿度"])
        assert result["ranked_factors"][0]["name"] == "载荷"
        assert result["n_components"] >= 1

    def test_explained_variance_threshold(self):
        rng = np.random.default_rng(2)
        X = rng.normal(size=(50, 6))
        result = identify_key_factors(X, [f"f{i}" for i in range(6)], variance_threshold=0.99)
        assert sum(result["explained_variance_ratio"][: result["n_components"]]) >= 0.99

    def test_input_validation(self):
        with pytest.raises(ValueError):
            identify_key_factors(np.zeros((3, 2)), ["a"])  # 名称数不匹配


# ── Encoder-Decoder 小样本预测 ──

class TestFewShotPredictor:
    def test_fit_reduces_loss(self):
        torch.manual_seed(0)
        x, y = _synthetic_dataset(n=16)
        model = EncoderDecoderLifePredictor(n_features=4, hidden_dim=16, latent_dim=8)
        history = model.fit_few_shot(x, y, epochs=60, lr=1e-2)
        assert history[-1] < history[0] * 0.5   # 损失显著下降

    def test_predict_shape_and_finite(self):
        torch.manual_seed(0)
        x, y = _synthetic_dataset(n=8)
        model = EncoderDecoderLifePredictor(n_features=4, hidden_dim=16, latent_dim=8)
        model.fit_few_shot(x, y, epochs=10)
        preds = model.predict(x)
        assert preds.shape == (8,)
        assert np.isfinite(preds).all()
        assert (preds > 0).all()                # 剩余寿命非负

    def test_few_shot_generalizes_direction(self):
        """小样本训练后，退化快的序列预测寿命应短于退化慢的。"""
        torch.manual_seed(0)
        x, y = _synthetic_dataset(n=24, seed=3)
        model = EncoderDecoderLifePredictor(n_features=4, hidden_dim=24, latent_dim=12)
        model.fit_few_shot(x, y, epochs=500, lr=1e-2)

        fast = torch.zeros(1, 8, 4)
        fast[0, :, 0] = 0.5 * torch.arange(8, dtype=torch.float32)
        slow = torch.zeros(1, 8, 4)
        slow[0, :, 0] = 0.05 * torch.arange(8, dtype=torch.float32)
        assert model.predict(fast)[0] < model.predict(slow)[0]
