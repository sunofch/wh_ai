from src.warehouse.models import OrderItem, WorkOrder, TaskType, OrderPriority
from src.warehouse.wes.task_decomposer import TaskDecomposer


def _make_order(pick: str, dest: str, task_type=TaskType.OUTBOUND) -> WorkOrder:
    item = OrderItem(
        item_id=1, task_type=task_type,
        resolved_pick=pick, resolved_dest=dest, quantity=1
    )
    return WorkOrder(order_id=1, source="vlm", items=[item])


def test_resolved_pick_dest_used_directly():
    td = TaskDecomposer(None, ["IN-L"], ["OUT-L"], seed=42)
    order = _make_order(pick="Mech1_R1_B1", dest="OUT-L")
    tasks = td.decompose([order], storage_names=["Mech1_R1_B1", "Mech1_R1_B2"])
    assert tasks[0].pick == "Mech1_R1_B1"
    assert tasks[0].dest == "OUT-L"


def test_empty_resolved_falls_back_to_random():
    td = TaskDecomposer(None, ["IN-L"], ["OUT-L"], seed=42)
    item = OrderItem(item_id=1, task_type=TaskType.OUTBOUND, quantity=1)
    order = WorkOrder(order_id=1, source="random", items=[item])
    tasks = td.decompose([order], storage_names=["Mech1_R1_B1", "Mech1_R1_B2"])
    # 随机分配，结果不为空即可
    assert tasks[0].pick != ""
    assert tasks[0].dest != ""
