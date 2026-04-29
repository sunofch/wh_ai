# src/warehouse/wes/clustering.py
"""方向感知层次聚类：OUTBOUND按dest区域聚类，INBOUND按pick区域聚类"""

from __future__ import annotations
from collections import defaultdict
from typing import TYPE_CHECKING

import numpy as np
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import pdist

from src.warehouse.models import TransportTask, TaskCluster, TaskType, OrderPriority

if TYPE_CHECKING:
    from src.warehouse.fleet.pathfinding import PathFinder
    from src.warehouse.wms.config import WarehouseConfig


class OrderClusterer:
    def __init__(self, path_finder: PathFinder, config: WarehouseConfig):
        self.path_finder = path_finder
        self.config = config

    def _get_zone(self, location: str) -> str:
        parts = location.split("_")
        if parts:
            return parts[0]
        return "Unknown"

    def _group_by_order(self, tasks: list[TransportTask]) -> list[list[TransportTask]]:
        """将任务按 order_id 分组"""
        order_map: dict[int, list[TransportTask]] = defaultdict(list)
        for t in tasks:
            order_map[t.order_id].append(t)
        return list(order_map.values())

    def _get_order_zone(self, order_tasks: list[TransportTask],
                        direction: str = "outbound") -> str:
        """确定订单所属区域。OUTBOUND用dest，INBOUND用pick"""
        if direction == "outbound":
            zones = [self._get_zone(t.dest) for t in order_tasks]
        else:
            zones = [self._get_zone(t.pick) for t in order_tasks]
        return max(set(zones), key=zones.count) if zones else "Unknown"

    def _get_order_center(self, order_tasks: list[TransportTask],
                          zone_pos: dict[str, tuple[int, int]],
                          direction: str = "outbound") -> tuple[float, float]:
        """计算订单中心。OUTBOUND用dest坐标，INBOUND用pick坐标"""
        xs, ys = [], []
        for t in order_tasks:
            loc = t.dest if direction == "outbound" else t.pick
            pos = zone_pos.get(loc, (0, 0))
            xs.append(pos[0])
            ys.append(pos[1])
        return (np.mean(xs), np.mean(ys))

    def _make_cluster(self, cluster_id: int, tasks: list[TransportTask],
                      zone: str = "") -> TaskCluster:
        return TaskCluster(
            cluster_id=cluster_id,
            tasks=tasks,
            task_num=len(tasks),
            order_ids=list({t.order_id for t in tasks}),
            priority=max(t.priority for t in tasks),
            zone=zone,
        )

    def cluster(self, tasks: list[TransportTask],
                max_capacity: int,
                zone_pos: dict[str, tuple[int, int]]) -> list[TaskCluster]:

        if not self.config.ablation.enable_clustering:
            order_groups = self._group_by_order(tasks)
            return [
                self._make_cluster(i + 1, group)
                for i, group in enumerate(order_groups)
            ]

        # 方向感知：分离 OUTBOUND/TRANSFER 和 INBOUND
        ob_tasks = [t for t in tasks if t.task_type != TaskType.INBOUND]
        ib_tasks = [t for t in tasks if t.task_type == TaskType.INBOUND]

        clusters = []
        cluster_id = 0

        # OUTBOUND/TRANSFER: 按 dest 区域聚类
        if ob_tasks:
            for c in self._cluster_direction(ob_tasks, max_capacity, zone_pos, "outbound"):
                cluster_id += 1
                c.cluster_id = cluster_id
                clusters.append(c)

        # INBOUND: 按 pick 区域聚类
        if ib_tasks:
            for c in self._cluster_direction(ib_tasks, max_capacity, zone_pos, "inbound"):
                cluster_id += 1
                c.cluster_id = cluster_id
                clusters.append(c)

        return clusters

    def _cluster_direction(self, tasks: list[TransportTask],
                           max_capacity: int,
                           zone_pos: dict[str, tuple[int, int]],
                           direction: str) -> list[TaskCluster]:
        """对单方向任务进行层次聚类"""
        order_groups = self._group_by_order(tasks)

        # 按区域分组
        zone_orders: dict[str, list[list[TransportTask]]] = defaultdict(list)
        for group in order_groups:
            zone = self._get_order_zone(group, direction)
            zone_orders[zone].append(group)

        clusters = []

        for zone, order_list in zone_orders.items():
            if len(order_list) <= 1:
                for group in order_list:
                    clusters.append(self._make_cluster(0, group, zone))
                continue

            # 计算订单中心
            centers = [self._get_order_center(g, zone_pos, direction) for g in order_list]

            # 层次聚类
            center_arr = np.array(centers, dtype=float)
            dist_matrix = pdist(center_arr, metric="euclidean")
            Z = linkage(dist_matrix, method="ward")
            labels = fcluster(Z, t=25, criterion="distance")

            label_groups: dict[int, list[list[TransportTask]]] = defaultdict(list)
            for idx, label in enumerate(labels):
                label_groups[label].append(order_list[idx])

            for order_subgroups in label_groups.values():
                all_tasks = []
                for g in order_subgroups:
                    all_tasks.extend(g)

                if len(all_tasks) > max_capacity:
                    split_n = (len(all_tasks) // max_capacity) + 1
                    subgroups = np.array_split(all_tasks, split_n)
                    for sub in subgroups:
                        clusters.append(self._make_cluster(0, list(sub), zone))
                else:
                    clusters.append(self._make_cluster(0, all_tasks, zone))

        return clusters
