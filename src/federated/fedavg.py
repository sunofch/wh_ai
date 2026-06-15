"""FedAvg：按样本量加权平均各客户端的 LoRA 增量。"""
from __future__ import annotations

import torch


def fed_average(
    states: list[dict[str, torch.Tensor]],
    weights: list[float],
) -> dict[str, torch.Tensor]:
    """加权平均参数字典列表。weights 通常取各客户端样本数。"""
    if not states:
        raise ValueError("states must not be empty")
    if len(states) != len(weights):
        raise ValueError(f"{len(states)} states but {len(weights)} weights")
    keys = set(states[0])
    for i, state in enumerate(states[1:], start=1):
        if set(state) != keys:
            raise ValueError(f"state #{i} keys mismatch: {set(state) ^ keys}")

    total = float(sum(weights))
    if total <= 0:
        raise ValueError("sum of weights must be positive")

    return {
        key: torch.stack(
            [state[key] * (w / total) for state, w in zip(states, weights)]
        ).sum(dim=0)
        for key in keys
    }
