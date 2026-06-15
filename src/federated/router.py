"""部门专属 adapter 路由：按请求来源部门选择 LoRA adapter。"""
from __future__ import annotations

import torch


class AdapterRouter:
    """注册各部门 adapter，按部门名路由；未知部门回退默认 adapter。"""

    def __init__(self, default: str = "global"):
        self._default = default
        self._adapters: dict[str, dict[str, torch.Tensor]] = {}

    def register(self, department: str, adapter: dict[str, torch.Tensor]) -> None:
        self._adapters[department] = adapter

    def route(self, department: str) -> dict[str, torch.Tensor]:
        if department in self._adapters:
            return self._adapters[department]
        if self._default in self._adapters:
            return self._adapters[self._default]
        raise KeyError(
            f"no adapter for department '{department}' and default "
            f"'{self._default}' is not registered"
        )

    @property
    def departments(self) -> list[str]:
        return sorted(self._adapters)
