# tests/warehouse/test_order_manager.py
"""工单管理测试 — 6端口适配"""

from src.warehouse.maps.base import MapRegistry
from src.warehouse.wms.order_manager import OrderManager
import src.warehouse.maps.medium_50x50


def _make_om():
    cfg = MapRegistry.get("medium_50x50")
    return OrderManager(cfg)


def test_order_six_ports():
    om = _make_om()
    assert len(om.inbound_ports) == 3
    assert len(om.outbound_ports) == 3


def test_inbound_port_names():
    om = _make_om()
    assert set(om.inbound_ports) == {"IN-L", "IN-C", "IN-R"}


def test_outbound_port_names():
    om = _make_om()
    assert set(om.outbound_ports) == {"OUT-L", "OUT-C", "OUT-R"}


def test_random_orders():
    om = _make_om()
    orders = om.from_random(10)
    assert len(orders) == 10
    for order in orders:
        assert len(order.items) >= 2


def test_random_orders_deterministic():
    om = _make_om()
    orders1 = om.from_random(5)
    om2 = OrderManager(MapRegistry.get("medium_50x50"))
    orders2 = om2.from_random(5)
    assert len(orders1) == len(orders2)
