# src/warehouse/wes/clustering.py
"""路线A聚类：按精确batch键分组 → 空间合并 → 容量拆分（保持batch组完整性）"""

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

        if ob_tasks:
            for c in self._cluster_direction(ob_tasks, max_capacity, zone_pos, "outbound"):
                cluster_id += 1
                c.cluster_id = cluster_id
                clusters.append(c)

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
        """按精确batch键分组 → 空间合并 → 容量拆分"""

        # Step 1: 按精确 batch 键分组（OUTBOUND按dest, INBOUND按pick）
        batch_map: dict[str, list[TransportTask]] = defaultdict(list)
        for t in tasks:
            key = t.dest if direction == "outbound" else t.pick
            batch_map[key].append(t)

        batch_groups = list(batch_map.values())

        if not batch_groups:
            return []

        if len(batch_groups) == 1:
            all_tasks = batch_groups[0]
            if len(all_tasks) <= max_capacity:
                zone = self._get_zone_from_tasks(all_tasks, direction)
                return [self._make_cluster(0, all_tasks, zone)]
            return self._split_preserving_batches([batch_groups], max_capacity)

        # Step 2: 计算每个 batch 组的中心位置
        centers = []
        for group in batch_groups:
            loc = group[0].dest if direction == "outbound" else group[0].pick
            centers.append(zone_pos.get(loc, (0, 0)))

        # Step 3: 空间合并（层次聚类）
        center_arr = np.array(centers, dtype=float)
        dist_matrix = pdist(center_arr, metric="euclidean")
        Z = linkage(dist_matrix, method="ward")
        labels = fcluster(Z, t=25, criterion="distance")

        # 按聚类标签合并 batch 组
        merged: dict[int, list[list[TransportTask]]] = defaultdict(list)
        for idx, label in enumerate(labels):
            merged[label].append(batch_groups[idx])

        # Step 4: 容量拆分（保持 batch 组完整性）
        clusters = []
        for subgroups in merged.values():
            total = sum(len(g) for g in subgroups)
            if total <= max_capacity:
                all_tasks = []
                for g in subgroups:
                    all_tasks.extend(g)
                zone = self._get_zone_from_tasks(all_tasks, direction)
                clusters.append(self._make_cluster(0, all_tasks, zone))
            else:
                clusters.extend(self._split_preserving_batches(subgroups, max_capacity))

        return clusters

    def _get_zone_from_tasks(self, tasks: list[TransportTask], direction: str) -> str:
        """从任务列表推断主要区域"""
        if not tasks:
            return ""
        locs = [t.dest if direction == "outbound" else t.pick for t in tasks]
        zones = [self._get_zone(loc) for loc in locs]
        return max(set(zones), key=zones.count)

    def _split_preserving_batches(self, groups: list[list[TransportTask]],
                                   max_capacity: int) -> list[TaskCluster]:
        """贪心装箱：保持 batch 组完整性，单组超限则均分"""
        sorted_groups = sorted(groups, key=lambda g: len(g), reverse=True)

        clusters = []
        current: list[TransportTask] = []

        for group in sorted_groups:
            if len(group) > max_capacity:
                # 单组超限：均分（同 batch 键的任务拆开影响较小）
                if current:
                    clusters.append(self._make_cluster(0, current))
                    current = []
                split_n = (len(group) // max_capacity) + 1
                for sub in np.array_split(group, split_n):
                    clusters.append(self._make_cluster(0, list(sub)))
                continue

            if current and len(current) + len(group) > max_capacity:
                clusters.append(self._make_cluster(0, current))
                current = list(group)
            else:
                current.extend(group)

        if current:
            clusters.append(self._make_cluster(0, current))

        return clusters
