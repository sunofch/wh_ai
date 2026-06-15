"""仓储 MCP Server：库存 / 预警 / 溯源 / 报废 标准化工具。

启动（stdio 传输，供 MCP Host 拉起）：
    python main_mcp.py

所有工具返回 JSON 字符串，错误统一为 {"ok": false, "error": "..."} 信封，
不向客户端泄露内部堆栈。
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache

from mcp.server.fastmcp import FastMCP

from src.warehouse.maps.base import MapRegistry
from src.warehouse.wms.inventory_db import StockManager
import src.warehouse.maps.medium_57x47  # noqa: F401 触发地图注册

logger = logging.getLogger(__name__)

mcp = FastMCP("port-warehouse")


@lru_cache(maxsize=1)
def _db() -> StockManager:
    db = StockManager()
    db.seed_from_map(MapRegistry.get("medium_57x47"))
    return db


def _dumps(data) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


@mcp.tool()
def query_stock(model: str = "", part_name: str = "") -> str:
    """查询备件库存明细。model（型号）与 part_name（名称，支持模糊）至少给一个。"""
    db = _db()
    item = db.query(model) if model else None
    if item is None and part_name:
        item = db.query_by_name(part_name)
    if item is None:
        return _dumps({"found": False})
    return _dumps(item.model_dump())


@mcp.tool()
def list_stock() -> str:
    """列出全部在库备件（含生命周期字段）。"""
    return _dumps([item.model_dump() for item in _db().list_items()])


@mcp.tool()
def stock_warnings(warn_weeks: int = 2) -> str:
    """库存预警报告：寿命到期/临期清单 + 全库风险扫描摘要。"""
    db = _db()
    life_warnings = db.list_life_warnings(warn_weeks=warn_weeks)
    return _dumps({
        "life_warnings": life_warnings,
        "summary": f"{len(life_warnings)}条备件寿命到期/临期。",
    })


@mcp.tool()
def trace_part(model: str) -> str:
    """备件全生命周期可信溯源：上链流转记录 + 哈希链完整性校验结果。"""
    return _dumps(_db().trace(model))


@mcp.tool()
def scrap_part(model: str, quantity: int, reason: str = "") -> str:
    """报废备件：扣减库存并上链存证。返回 {"ok": bool, ...}。"""
    try:
        ok = _db().scrap(model, quantity, reason=reason)
    except ValueError as exc:
        return _dumps({"ok": False, "error": str(exc)})
    if not ok:
        return _dumps({"ok": False, "error": f"unknown model: {model}"})
    return _dumps({"ok": True, "model": model, "quantity": quantity})


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    logger.info("starting port-warehouse MCP server (stdio)")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
