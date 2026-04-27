# tests/warehouse/test_config.py
from src.warehouse.wms.config import WarehouseConfig
from src.warehouse.models import AblationFlags


def test_default_config():
    cfg = WarehouseConfig()
    assert cfg.MAP_NAME == "medium_50x50"
    assert cfg.AGV_MOVE_TIME == 1
    assert cfg.AGV_MAX_BATTERY == 100
    assert cfg.ORDER_NUM == 40
    assert cfg.RANDOM_SEED == 42


def test_ablation_defaults():
    cfg = WarehouseConfig()
    assert cfg.ablation.enable_path_cache is True
    assert cfg.ablation.enable_cp_sat is True


def test_custom_ablation():
    cfg = WarehouseConfig(ablation=AblationFlags(enable_tsp=False))
    assert cfg.ablation.enable_tsp is False
    assert cfg.ablation.enable_path_cache is True  # others unchanged


def test_config_from_env(monkeypatch):
    monkeypatch.setenv("WH_MAP_NAME", "large_100x100")
    monkeypatch.setenv("WH_ORDER_NUM", "100")
    cfg = WarehouseConfig()
    assert cfg.MAP_NAME == "large_100x100"
    assert cfg.ORDER_NUM == 100
