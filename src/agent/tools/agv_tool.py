"""AGV 调度工具：WorkOrder → TaskDecomposer → Clusterer → FleetManager。"""
import json
from functools import lru_cache

from langchain_core.tools import tool

from src.warehouse.maps.base import MapRegistry
from src.warehouse.fleet.map_builder import WarehouseMap
from src.warehouse.fleet.fleet_manager import FleetManager
from src.warehouse.wms.config import WarehouseConfig
from src.warehouse.wms.inventory import InventoryManager
from src.warehouse.wms.order_manager import OrderManager
from src.warehouse.wes.task_decomposer import TaskDecomposer
from src.warehouse.wes.clustering import OrderClusterer
from src.warehouse.models import WorkOrder, OrderItem, OrderPriority, TaskType

import src.warehouse.maps.medium_57x47  # noqa: F401


@lru_cache(maxsize=1)
def _get_agv_infra():
    """初始化并缓存 AGV 调度所需的基础设施（含路径预计算）。"""
    config = WarehouseConfig()
    map_config = MapRegistry.get(config.MAP_NAME)
    wmap = WarehouseMap(map_config)
    inventory = InventoryManager(map_config, seed=config.RANDOM_SEED)
    fleet = FleetManager(wmap, config)
    fleet.precompute()
    order_manager = OrderManager(map_config, seed=config.RANDOM_SEED)
    return wmap, inventory, fleet, config, order_manager


@tool
def schedule_agv_tasks(work_order_json: str) -> str:
    """接收工单 JSON，执行 AGV 调度规划，返回各 AGV 的任务分配方案。

    work_order_json: inventory_agent 创建的工单 JSON，需包含 order_id、priority、items
    （items 中每项需有 task_type、model、part_name、quantity、pick、dest）。
    """
    try:
        data = json.loads(work_order_json)
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"工单 JSON 解析失败: {e}"}, ensure_ascii=False)

    wmap, inventory, fleet, config, order_manager = _get_agv_infra()

    items = [
        OrderItem(
            item_id=i + 1,
            task_type=TaskType(item["task_type"]),
            model=item.get("model", ""),
            part_name=item.get("part_name", ""),
            quantity=item.get("quantity", 1),
            resolved_pick=item.get("pick", ""),
            resolved_dest=item.get("dest", ""),
        )
        for i, item in enumerate(data.get("items", []))
    ]

    if not items:
        return json.dumps({"error": "工单中无有效任务项"}, ensure_ascii=False)

    work_order = WorkOrder(
        order_id=data.get("order_id", 1),
        source="vlm",
        priority=OrderPriority(data.get("priority", OrderPriority.NORMAL.value)),
        items=items,
    )

    td = TaskDecomposer(
        inventory,
        order_manager.inbound_ports,
        order_manager.outbound_ports,
        seed=config.RANDOM_SEED,
    )
    tasks = td.decompose([work_order], wmap.storage_list)

    clusterer = OrderClusterer(fleet.path_finder, config)
    clusters = clusterer.cluster(tasks, config.AGV_MAX_TASK_CAPACITY, wmap.zone_pos)

    agv_tasks = fleet.schedule(clusters)

    assignments = {
        f"agv_{agv_id}": [
            {
                "task_id": t.task_id,
                "type": t.task_type.value,
                "part": t.model or t.part_name,
                "pick": t.pick,
                "dest": t.dest,
                "qty": t.quantity,
            }
            for t in task_list
        ]
        for agv_id, task_list in agv_tasks.items()
        if task_list
    }

    return json.dumps(
        {
            "status": "scheduled",
            "agv_count": len(assignments),
            "total_tasks": sum(len(v) for v in assignments.values()),
            "assignments": assignments,
        },
        ensure_ascii=False,
    )
