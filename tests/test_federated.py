"""联邦 LoRA 微调框架测试。

对应 pj4 子课题 4.1：设备/运营/安全多部门异构数据协同微调，
数据不出部门（只交换 LoRA 增量），FedAvg 聚合 + 部门个性化路由。
"""
import pytest
import torch
from torch import nn

from src.federated.coordinator import DepartmentClient, FederatedCoordinator
from src.federated.fedavg import fed_average
from src.federated.lora import LoRALinear, lora_state_dict
from src.federated.router import AdapterRouter


def _toy_batch(slope: float, n: int = 64, seed: int = 0):
    g = torch.Generator().manual_seed(seed)
    x = torch.randn(n, 4, generator=g)
    y = slope * x.sum(dim=1, keepdim=True)
    return x, y


# ── LoRA 层 ──

class TestLoRALinear:
    def test_base_weight_frozen(self):
        layer = LoRALinear(4, 2, rank=2)
        x, y = _toy_batch(1.0)
        base_before = layer.base.weight.clone()
        opt = torch.optim.SGD([p for p in layer.parameters() if p.requires_grad], lr=0.1)
        loss = nn.functional.mse_loss(layer(x), y[:, :1].repeat(1, 2))
        loss.backward()
        opt.step()
        assert torch.equal(layer.base.weight, base_before)   # 基座不动
        assert not torch.equal(layer.lora_b, torch.zeros_like(layer.lora_b)) or \
               layer.lora_a.grad is not None                  # LoRA 参数有梯度

    def test_initial_output_equals_base(self):
        """B 零初始化 → 未训练时输出与基座一致（不破坏预训练行为）。"""
        layer = LoRALinear(4, 3, rank=2)
        x = torch.randn(5, 4)
        assert torch.allclose(layer(x), layer.base(x))

    def test_lora_state_dict_only_adapters(self):
        model = nn.Sequential(LoRALinear(4, 4, rank=2), nn.ReLU(), LoRALinear(4, 1, rank=2))
        state = lora_state_dict(model)
        assert state  # 非空
        assert all("lora_" in k for k in state)


# ── FedAvg 聚合 ──

class TestFedAvg:
    def test_weighted_average(self):
        s1 = {"w.lora_a": torch.ones(2, 2)}
        s2 = {"w.lora_a": torch.zeros(2, 2)}
        avg = fed_average([s1, s2], weights=[3.0, 1.0])
        assert torch.allclose(avg["w.lora_a"], torch.full((2, 2), 0.75))

    def test_mismatched_keys_raise(self):
        with pytest.raises(ValueError):
            fed_average([{"a": torch.ones(1)}, {"b": torch.ones(1)}], weights=[1, 1])

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            fed_average([], weights=[])


# ── 联邦协同微调 ──

class TestFederatedRounds:
    def _make_model(self):
        torch.manual_seed(0)
        return nn.Sequential(LoRALinear(4, 8, rank=2), nn.Tanh(), LoRALinear(8, 1, rank=2))

    def test_federated_training_reduces_global_loss(self):
        clients = [
            DepartmentClient("equipment", data=_toy_batch(1.0, seed=1)),
            DepartmentClient("operations", data=_toy_batch(1.2, seed=2)),
            DepartmentClient("safety", data=_toy_batch(0.8, seed=3)),
        ]
        coord = FederatedCoordinator(model_fn=self._make_model, clients=clients)
        history = coord.run(rounds=5, local_epochs=10, lr=5e-2)
        assert history[-1]["global_loss"] < history[0]["global_loss"] * 0.7

    def test_personalized_adapters_diverge(self):
        """个性化模式下各部门 adapter 不同（FlexLoRA 式部门专属）。"""
        clients = [
            DepartmentClient("equipment", data=_toy_batch(2.0, seed=1)),
            DepartmentClient("safety", data=_toy_batch(-2.0, seed=2)),
        ]
        coord = FederatedCoordinator(
            model_fn=self._make_model, clients=clients, personalization_alpha=0.5
        )
        coord.run(rounds=3, local_epochs=10, lr=5e-2)
        a = coord.client_adapters["equipment"]
        b = coord.client_adapters["safety"]
        assert any(not torch.allclose(a[k], b[k]) for k in a)

    def test_raw_data_never_leaves_client(self):
        """协调器只接触 LoRA 状态字典，不接触客户端原始数据。"""
        client = DepartmentClient("equipment", data=_toy_batch(1.0))
        model = self._make_model()
        update, n_samples = client.local_train(model, epochs=2, lr=1e-2)
        assert all("lora_" in k for k in update)
        assert n_samples == 64


# ── 部门路由 ──

class TestAdapterRouter:
    def test_routes_by_department(self):
        router = AdapterRouter(default="global")
        router.register("equipment", {"w": torch.ones(1)})
        router.register("global", {"w": torch.zeros(1)})
        assert torch.equal(router.route("equipment")["w"], torch.ones(1))

    def test_unknown_department_falls_back(self):
        router = AdapterRouter(default="global")
        router.register("global", {"w": torch.zeros(1)})
        assert torch.equal(router.route("unknown-dept")["w"], torch.zeros(1))

    def test_missing_default_raises(self):
        router = AdapterRouter(default="global")
        with pytest.raises(KeyError):
            router.route("anything")
