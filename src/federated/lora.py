"""最小 LoRA 实现：冻结基座 + 低秩增量。"""
from __future__ import annotations

import torch
from torch import nn


class LoRALinear(nn.Module):
    """y = W₀x + (α/r)·B·A·x，W₀ 冻结，仅 A/B 参与训练。

    B 零初始化保证训练前行为与基座完全一致。
    """

    def __init__(self, in_features: int, out_features: int, rank: int = 4, alpha: float = 8.0):
        super().__init__()
        if rank < 1:
            raise ValueError(f"rank must be >= 1, got {rank}")
        self.base = nn.Linear(in_features, out_features)
        self.base.weight.requires_grad_(False)
        self.base.bias.requires_grad_(False)
        self.lora_a = nn.Parameter(torch.randn(rank, in_features) * 0.01)
        self.lora_b = nn.Parameter(torch.zeros(out_features, rank))
        self.scaling = alpha / rank

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.base(x) + (x @ self.lora_a.T @ self.lora_b.T) * self.scaling


def lora_state_dict(model: nn.Module) -> dict[str, torch.Tensor]:
    """抽取模型中所有 LoRA 增量参数（联邦上传的唯一内容）。"""
    return {
        name: param.detach().clone()
        for name, param in model.named_parameters()
        if "lora_" in name
    }


def load_lora_state(model: nn.Module, state: dict[str, torch.Tensor]) -> None:
    """把 LoRA 增量参数加载回模型（基座权重不受影响）。"""
    with torch.no_grad():
        params = dict(model.named_parameters())
        for name, tensor in state.items():
            if name not in params:
                raise KeyError(f"model has no LoRA parameter named {name}")
            params[name].copy_(tensor)
