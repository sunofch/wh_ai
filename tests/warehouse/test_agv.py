# tests/warehouse/test_agv.py
from src.warehouse.simulation.agv import AGV


def test_agv_init():
    agv = AGV(1, (8, 6))
    assert agv.battery == 100
    assert agv.current_pos == (8, 6)
    assert len(agv.trajectory) == 15000


def test_record_path():
    agv = AGV(1, (8, 6), max_steps=100)
    path = [(8, 6), (8, 7), (8, 8)]
    end_t = agv.record_path(path, 0, "moving_empty", 1)
    assert end_t == 3
    assert agv.trajectory[0] == (8, 6, "moving_empty", 1)
    assert agv.trajectory[2] == (8, 8, "moving_empty", 1)


def test_record_wait():
    agv = AGV(1, (8, 6), max_steps=100)
    end_t = agv.record_wait((8, 6), 5, 8, "loading", 1)
    assert end_t == 13
    assert agv.trajectory[5] == (8, 6, "loading", 1)


def test_consume_battery():
    agv = AGV(1, (8, 6))
    agv.consume_battery(20)
    assert agv.battery == 80


def test_charge_full():
    agv = AGV(1, (8, 6))
    agv.consume_battery(50)
    agv.charge_full()
    assert agv.battery == 100
