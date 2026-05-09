# tests/warehouse/test_config.py
"""配置测试"""

from src.warehouse.wms.config import WarehouseConfig
from src.warehouse.models import AblationFlags


def test_default_config():
    config = WarehouseConfig()
    assert config.MAP_NAME == "medium_57x47"
    assert config.AGV_MOVE_TIME == 1
    assert config.ORDER_NUM == 40


def test_ablation_flags():
    flags = AblationFlags()
    assert flags.enable_path_cache is True
    assert flags.enable_clustering is True
    assert flags.enable_tsp is True
    assert flags.enable_batch is True


def test_ablation_flags_custom():
    flags = AblationFlags(enable_path_cache=False, enable_clustering=False)
    assert flags.enable_path_cache is False
    assert flags.enable_clustering is False
    assert flags.enable_tsp is True


def test_config_custom():
    config = WarehouseConfig(ORDER_NUM=20, RANDOM_SEED=99)
    assert config.ORDER_NUM == 20
    assert config.RANDOM_SEED == 99
