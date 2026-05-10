import pytest
from src.parser.parser import PortInstruction
from src.warehouse.wms.order_manager import OrderManager
from src.warehouse.wms.inventory_db import InventoryDB
from src.warehouse.models import TaskType, OrderPriority
from src.warehouse.maps.base import MapRegistry
import src.warehouse.maps.medium_57x47  # noqa: F401


@pytest.fixture
def setup(tmp_path):
    map_config = MapRegistry.get("medium_57x47")
    db = InventoryDB(db_path=str(tmp_path / "inv.db"))
    db.seed_from_map(map_config, seed=42)
    om = OrderManager(map_config, seed=42)
    return om, db, map_config


def test_outbound_maps_to_outbound_port(setup):
    om, db, _ = setup
    inst = PortInstruction(part_name="轴承", quantity=2, action_required="出库")
    order = om.from_port_instruction(inst, inventory_db=db)
    assert order is not None
    assert order.items[0].task_type == TaskType.OUTBOUND
    assert "OUT" in order.items[0].resolved_dest


def test_inbound_maps_to_inbound_port(setup):
    om, db, _ = setup
    inst = PortInstruction(part_name="电机", quantity=1, action_required="入库")
    order = om.from_port_instruction(inst, inventory_db=db)
    assert order is not None
    assert order.items[0].task_type == TaskType.INBOUND
    # 入库: pick=入库端口(含IN), dest=货架储位
    assert "IN" in order.items[0].resolved_pick


def test_urgent_sets_priority(setup):
    om, db, _ = setup
    inst = PortInstruction(part_name="轴承", quantity=1,
                           action_required="出库", is_urgent=True)
    order = om.from_port_instruction(inst, inventory_db=db)
    assert order.priority == OrderPriority.URGENT


def test_resolved_pick_set_from_db(setup):
    om, db, _ = setup
    inst = PortInstruction(part_name="轴承", quantity=1, action_required="出库")
    order = om.from_port_instruction(inst, inventory_db=db)
    assert order.items[0].resolved_pick != ""


def test_all_none_returns_none(setup):
    om, db, _ = setup
    inst = PortInstruction()
    order = om.from_port_instruction(inst, inventory_db=db)
    assert order is None
