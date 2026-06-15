"""联盟链适配层协议。

本地哈希链是默认实现（零部署成本）；接入真实联盟链时实现
ChainAdapter 协议即可替换：
  - Hyperledger Fabric: fabric-sdk-py，多通道隔离设备/运营/安全各部门数据
  - FISCO BCOS: python-sdk，国产化场景

锚定策略：本地链每 N 块计算一次默克尔根，仅把根哈希提交到联盟链，
边缘设备通过轻量级客户端持 merkle proof 校验，无需同步全链。
"""
from __future__ import annotations

from typing import Protocol


class ChainAdapter(Protocol):
    """真实链适配器需要实现的最小能力。"""

    def anchor(self, merkle_root: str, height: int) -> str:
        """把默克尔根锚定上链，返回链上交易哈希。"""
        ...

    def fetch_anchor(self, height: int) -> str | None:
        """按本地链高取回已锚定的默克尔根，无则返回 None。"""
        ...


class LocalAnchorStore:
    """本地锚定存储（开发/演示用），实现 ChainAdapter 协议。"""

    def __init__(self) -> None:
        self._anchors: dict[int, str] = {}

    def anchor(self, merkle_root: str, height: int) -> str:
        self._anchors[height] = merkle_root
        return f"local-tx-{height}-{merkle_root[:8]}"

    def fetch_anchor(self, height: int) -> str | None:
        return self._anchors.get(height)
