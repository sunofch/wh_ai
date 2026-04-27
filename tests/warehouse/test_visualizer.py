# tests/warehouse/test_visualizer.py
import pytest
import tempfile
import os
from src.warehouse.maps.base import MapRegistry
from src.warehouse.fleet.map_builder import WarehouseMap
from src.warehouse.simulation.visualizer import Visualizer, ResultExporter, VisualStyle
from src.warehouse.simulation.agv import AGV
from src.warehouse.wms.config import WarehouseConfig
from src.warehouse.models import SimulationResult

import src.warehouse.maps.medium_50x50  # noqa: F401


@pytest.fixture
def viz():
    cfg = MapRegistry.get("medium_50x50")
    wmap = WarehouseMap(cfg)
    config = WarehouseConfig()
    return Visualizer(wmap, config), wmap


def test_plot_base_map(viz):
    v, _ = viz
    fig = v.plot_base_map()
    assert fig is not None
    import matplotlib.pyplot as plt
    plt.close(fig)


def test_plot_snapshot(viz):
    v, wmap = viz
    agv = AGV(1, (8, 6), max_steps=100)
    fig = v.plot_snapshot([agv], 0)
    assert fig is not None
    import matplotlib.pyplot as plt
    plt.close(fig)


def test_result_exporter_json():
    result = SimulationResult(makespan=100, total_distance=500)
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        ResultExporter.export_json(result, f.name)
        assert os.path.exists(f.name)
        os.unlink(f.name)


def test_result_exporter_summary():
    result = SimulationResult(makespan=100, agv_utilization=0.85)
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        ResultExporter.export_summary(result, f.name)
        assert os.path.exists(f.name)
        os.unlink(f.name)


def test_visual_style():
    assert len(VisualStyle.AGV_COLORS) == 8
    assert len(VisualStyle.ZONE_COLORS) == 3
