"""端到端冒烟测试——不需要VLM，使用规则解析 + 真实调度仿真"""
import pytest
from src.parser.parser import PortInstruction, PortInstructionParser
from src.warehouse.wms.inventory_db import InventoryDB
from src.warehouse.wms.order_manager import OrderManager
from src.warehouse.wes.task_decomposer import TaskDecomposer
from src.warehouse.wes.clustering import OrderClusterer
from src.warehouse.fleet.map_builder import WarehouseMap
from src.warehouse.fleet.fleet_manager import FleetManager
from src.warehouse.wms.config import WarehouseConfig
from src.warehouse.simulation.simulator import Simulator
from src.warehouse.maps.base import MapRegistry
import src.warehouse.maps.medium_57x47  # noqa: F401


@pytest.fixture(scope="module")
def warehouse(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("data")
    wh_config = WarehouseConfig()
    map_config = MapRegistry.get("medium_57x47")
    wmap = WarehouseMap(map_config)
    fleet = FleetManager(wmap, wh_config)
    fleet.precompute()
    inv_db = InventoryDB(db_path=str(tmp / "inv.db"))
    inv_db.seed_from_map(map_config, seed=42)
    om = OrderManager(map_config, seed=42)
    return wh_config, map_config, wmap, fleet, inv_db, om


def test_full_pipeline_outbound(warehouse):
    """规则解析 → 库存查询 → 工单 → 调度仿真"""
    wh_config, map_config, wmap, fleet, inv_db, om = warehouse
    instruction = PortInstruction(
        part_name="轴承", quantity=2, action_required="出库"
    )
    order = om.from_port_instruction(instruction, inventory_db=inv_db)
    assert order is not None

    td = TaskDecomposer(
        None, om.inbound_ports, om.outbound_ports, seed=42
    )
    tasks = td.decompose([order], wmap.storage_list)
    assert len(tasks) > 0

    clusterer = OrderClusterer(fleet.path_finder, wh_config)
    clusters = clusterer.cluster(
        tasks, wh_config.AGV_MAX_TASK_CAPACITY, wmap.zone_pos
    )
    agv_tasks = fleet.schedule(clusters)
    sim = Simulator(wmap, fleet, wh_config)
    result = sim.run(agv_tasks)
    assert result.makespan > 0
    assert result.total_distance > 0


def test_full_pipeline_inbound(warehouse):
    wh_config, map_config, wmap, fleet, inv_db, om = warehouse
    instruction = PortInstruction(
        part_name="电机", quantity=1, action_required="入库"
    )
    order = om.from_port_instruction(instruction, inventory_db=inv_db)
    assert order is not None
    assert order.items[0].task_type.value == "INBOUND"
