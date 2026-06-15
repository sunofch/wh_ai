"""MCP Server（Model Context Protocol）测试。

对应 pj4 子课题 4.1：MCP Host/Client/Server 标准化连接，
把库存查询、工单、预警、溯源能力暴露为标准 MCP 工具。
"""
import json
from unittest.mock import patch

import pytest

from src.warehouse.maps.base import MapRegistry
import src.warehouse.maps.medium_57x47  # noqa: F401
from src.warehouse.wms.inventory_db import StockManager


@pytest.fixture
def mgr(tmp_path):
    m = StockManager(db_path=str(tmp_path / "t.db"))
    m.seed_from_map(MapRegistry.get("medium_57x47"), seed=42)
    return m


def _find_item(mgr):
    for item in mgr.list_items():
        if item.available >= 1:
            return item
    raise AssertionError("无可用库存")


EXPECTED_TOOLS = {
    "query_stock",
    "list_stock",
    "stock_warnings",
    "trace_part",
    "scrap_part",
}


class TestRegistration:
    def test_all_tools_registered(self):
        from src.mcp_server.server import mcp

        import anyio

        tools = anyio.run(mcp.list_tools)
        names = {t.name for t in tools}
        assert EXPECTED_TOOLS <= names


class TestToolFunctions:
    def test_query_stock_found(self, mgr):
        item = _find_item(mgr)
        with patch("src.mcp_server.server._db", return_value=mgr):
            from src.mcp_server.server import query_stock
            data = json.loads(query_stock(model=item.model, part_name=""))
        assert data["model"] == item.model
        assert data["available"] == item.available

    def test_query_stock_not_found(self, mgr):
        with patch("src.mcp_server.server._db", return_value=mgr):
            from src.mcp_server.server import query_stock
            data = json.loads(query_stock(model="NO-SUCH", part_name=""))
        assert data == {"found": False}

    def test_list_stock_returns_all(self, mgr):
        with patch("src.mcp_server.server._db", return_value=mgr):
            from src.mcp_server.server import list_stock
            data = json.loads(list_stock())
        assert len(data) == len(mgr.list_items())

    def test_trace_part_chain_verified(self, mgr):
        item = _find_item(mgr)
        mgr.receive(item.model, 1)
        with patch("src.mcp_server.server._db", return_value=mgr):
            from src.mcp_server.server import trace_part
            data = json.loads(trace_part(model=item.model))
        assert data["chain_verified"] is True
        assert len(data["records"]) == 1

    def test_scrap_part_roundtrip(self, mgr):
        item = _find_item(mgr)
        with patch("src.mcp_server.server._db", return_value=mgr):
            from src.mcp_server.server import scrap_part
            data = json.loads(scrap_part(model=item.model, quantity=1, reason="测试报废"))
        assert data["ok"] is True
        assert mgr.query(item.model).quantity == item.quantity - 1

    def test_scrap_part_invalid_quantity(self, mgr):
        item = _find_item(mgr)
        with patch("src.mcp_server.server._db", return_value=mgr):
            from src.mcp_server.server import scrap_part
            data = json.loads(scrap_part(model=item.model, quantity=9999, reason=""))
        assert data["ok"] is False
        assert "error" in data

    def test_stock_warnings_report(self, mgr):
        item = _find_item(mgr)
        mgr.set_life_expectancy(item.model, 1)
        with patch("src.mcp_server.server._db", return_value=mgr):
            from src.mcp_server.server import stock_warnings
            data = json.loads(stock_warnings())
        assert "life_warnings" in data
        assert any(w["model"] == item.model for w in data["life_warnings"])
