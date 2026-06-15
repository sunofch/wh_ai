"""联邦协调器：部门客户端本地训练 + 中心 FedAvg 聚合 + 个性化混合。

数据流（隐私边界用 ─║─ 标注）：
    部门本地数据 → local_train ─║─ LoRA 增量 → FedAvg → 全局 adapter
                                            ↘ α·本地 + (1-α)·全局 → 部门专属 adapter
"""
from __future__ import annotations

import torch
from torch import nn

from src.federated.fedavg import fed_average
from src.federated.lora import load_lora_state, lora_state_dict


class DepartmentClient:
    """一个部门（设备/运营/安全）的联邦客户端。数据永不离开本类。"""

    def __init__(self, department: str, data: tuple[torch.Tensor, torch.Tensor]):
        self.department = department
        self._x, self._y = data

    @property
    def n_samples(self) -> int:
        return len(self._x)

    def local_train(
        self, model: nn.Module, epochs: int, lr: float
    ) -> tuple[dict[str, torch.Tensor], int]:
        """在本地数据上训练 LoRA 参数，返回 (LoRA 增量, 样本数)。"""
        trainable = [p for p in model.parameters() if p.requires_grad]
        optimizer = torch.optim.Adam(trainable, lr=lr)
        loss_fn = nn.MSELoss()
        model.train()
        for _ in range(epochs):
            optimizer.zero_grad()
            loss = loss_fn(model(self._x), self._y)
            loss.backward()
            optimizer.step()
        return lora_state_dict(model), self.n_samples

    @torch.no_grad()
    def evaluate(self, model: nn.Module) -> float:
        model.eval()
        return float(nn.functional.mse_loss(model(self._x), self._y))


class FederatedCoordinator:
    """中心协调器：广播全局 adapter → 各部门本地训练 → 聚合 → 个性化混合。

    personalization_alpha=0 时退化为纯 FedAvg（所有部门共享全局 adapter）；
    >0 时各部门保留 α 比例的本地个性，对应 FlexLoRA 式部门专属 adapter。
    """

    def __init__(
        self,
        model_fn,
        clients: list[DepartmentClient],
        personalization_alpha: float = 0.0,
    ):
        if not clients:
            raise ValueError("clients must not be empty")
        if not 0.0 <= personalization_alpha <= 1.0:
            raise ValueError(f"personalization_alpha must be in [0,1], got {personalization_alpha}")
        self._model_fn = model_fn
        self.clients = clients
        self.alpha = personalization_alpha
        self.global_adapter: dict[str, torch.Tensor] = lora_state_dict(model_fn())
        self.client_adapters: dict[str, dict[str, torch.Tensor]] = {
            c.department: {k: v.clone() for k, v in self.global_adapter.items()}
            for c in clients
        }

    def _blend(
        self, local: dict[str, torch.Tensor], global_: dict[str, torch.Tensor]
    ) -> dict[str, torch.Tensor]:
        return {
            key: self.alpha * local[key] + (1.0 - self.alpha) * global_[key]
            for key in global_
        }

    def run(self, rounds: int, local_epochs: int, lr: float) -> list[dict]:
        """执行联邦训练。返回每轮 {round, global_loss} 历史。"""
        history: list[dict] = []
        for round_idx in range(rounds):
            updates: list[dict[str, torch.Tensor]] = []
            weights: list[float] = []
            for client in self.clients:
                model = self._model_fn()
                # 广播：个性化 adapter（首轮即全局）作为本地起点
                load_lora_state(model, self.client_adapters[client.department])
                update, n_samples = client.local_train(model, local_epochs, lr)
                updates.append(update)
                weights.append(float(n_samples))
                self.client_adapters[client.department] = update

            self.global_adapter = fed_average(updates, weights)
            for client in self.clients:
                self.client_adapters[client.department] = self._blend(
                    self.client_adapters[client.department], self.global_adapter
                )

            history.append({
                "round": round_idx + 1,
                "global_loss": self.evaluate_global(),
            })
        return history

    def evaluate_global(self) -> float:
        """全局 adapter 在所有部门数据上的平均损失。"""
        model = self._model_fn()
        load_lora_state(model, self.global_adapter)
        losses = [client.evaluate(model) for client in self.clients]
        return sum(losses) / len(losses)
