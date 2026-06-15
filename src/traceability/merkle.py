"""默克尔树根 / 证明 / 校验。

用于把一段哈希链区块批量锚定为单一根哈希（联盟链上只需存根），
边缘轻客户端凭 proof 即可校验单条记录的存在性与完整性。
"""
from __future__ import annotations

import hashlib

# proof 路径中兄弟节点的方位标记
LEFT = "L"
RIGHT = "R"


def _hash_pair(left: str, right: str) -> str:
    return hashlib.sha256(f"{left}{right}".encode()).hexdigest()


def _next_level(level: list[str]) -> list[str]:
    """两两配对哈希；奇数个时末节点与自身配对（比特币式补齐）。"""
    if len(level) % 2 == 1:
        level = [*level, level[-1]]
    return [_hash_pair(level[i], level[i + 1]) for i in range(0, len(level), 2)]


def merkle_root(leaf_hashes: list[str]) -> str:
    """计算叶子哈希列表的默克尔根；空列表返回空串。"""
    if not leaf_hashes:
        return ""
    level = list(leaf_hashes)
    while len(level) > 1:
        level = _next_level(level)
    return level[0]


def merkle_proof(leaf_hashes: list[str], index: int) -> list[tuple[str, str]]:
    """生成第 index 个叶子的默克尔证明：[(side, sibling_hash), ...]。"""
    if not 0 <= index < len(leaf_hashes):
        raise IndexError(f"leaf index {index} out of range")
    proof: list[tuple[str, str]] = []
    level = list(leaf_hashes)
    pos = index
    while len(level) > 1:
        if len(level) % 2 == 1:
            level = [*level, level[-1]]
        sibling = pos + 1 if pos % 2 == 0 else pos - 1
        side = RIGHT if pos % 2 == 0 else LEFT
        proof.append((side, level[sibling]))
        level = [_hash_pair(level[i], level[i + 1]) for i in range(0, len(level), 2)]
        pos //= 2
    return proof


def verify_proof(leaf_hash: str, proof: list[tuple[str, str]], root: str) -> bool:
    """沿证明路径重算根哈希并与 root 比对。"""
    current = leaf_hash
    for side, sibling in proof:
        if side == RIGHT:
            current = _hash_pair(current, sibling)
        else:
            current = _hash_pair(sibling, current)
    return current == root
