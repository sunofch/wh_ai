# tests/warehouse/test_clustering.py
"""聚类测试 — _get_zone 新储位格式"""

from src.warehouse.wes.clustering import OrderClusterer


def test_get_zone_new_format():
    # _get_zone extracts zone prefix from storage name
    # Create minimal mock objects
    class MockPathFinder:
        pass

    class MockConfig:
        ablation = type("A", (), {"enable_clustering": True})()

    pf = MockPathFinder()
    config = MockConfig()
    clusterer = OrderClusterer(pf, config)

    assert clusterer._get_zone("Mech1_R1_B1") == "Mech1"
    assert clusterer._get_zone("Cons2_R3_B7") == "Cons2"
    assert clusterer._get_zone("Safety_R5_B10") == "Safety"
    assert clusterer._get_zone("Elec1_R1_B1") == "Elec1"
    assert clusterer._get_zone("Tool_R2_B5") == "Tool"
    assert clusterer._get_zone("Unknown") == "Unknown"


def test_get_zone_consistent():
    class MockPathFinder:
        pass

    class MockConfig:
        ablation = type("A", (), {"enable_clustering": True})()

    clusterer = OrderClusterer(MockPathFinder(), MockConfig())
    # Same zone, different row/bay should return same zone
    assert clusterer._get_zone("Mech1_R1_B1") == clusterer._get_zone("Mech1_R5_B10")
    assert clusterer._get_zone("Cons1_R2_B3") == clusterer._get_zone("Cons1_R4_B8")
