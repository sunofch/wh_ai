# src/warehouse/wes/clustering.py
"""容量约束层次聚类"""

from __future__ import annotations
from collections import defaultdict
from typing import TYPE_CHECKING

import numpy as np
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import pdist

from src.warehouse.models import TransportTask, TaskCluster, OrderPriority

if TYPE_CHECKING:
    from src.warehouse.fleet.pathfinding import PathFinder
    from src.warehouse.wms.config import WarehouseConfig


class OrderClusterer:
    def __init__(self, path_finder: PathFinder, config: WarehouseConfig):
        self.path_finder = path_finder
        self.config = config

    def _get_zone(self, location: str) -> str:
        if "Raw" in location:
            return "Raw"
        if "Finished" in location:
            return "Finished"
        if "Spare" in location:
            return "Spare"
        return "Unknown"

    def cluster(self, tasks: list[TransportTask],
                max_capacity: int,
                zone_pos: dict[str, tuple[int, int]]) -> list[TaskCluster]:
        if not self.config.ablation.enable_clustering:
            return [
                TaskCluster(cluster_id=i + 1, tasks=[t], task_num=1,
                            order_ids=[t.order_id], priority=t.priority)
                for i, t in enumerate(tasks)
            ]

        # 按目标区域分组
        zone_groups: dict[str, list[TransportTask]] = defaultdict(list)
        for task in tasks:
            zone = self._get_zone(task.dest)
            zone_groups[zone].append(task)

        clusters = []
        cluster_id = 0

        for zone, zone_tasks in zone_groups.items():
            if len(zone_tasks) <= 1:
                for t in zone_tasks:
                    cluster_id += 1
                    clusters.append(TaskCluster(
                        cluster_id=cluster_id, tasks=[t], task_num=1,
                        order_ids=[t.order_id], priority=t.priority, zone=zone,
                    ))
                continue

            # 计算中心坐标
            centers = []
            for t in zone_tasks:
                pos = zone_pos.get(t.dest, (0, 0))
                centers.append(pos)

            if len(centers) <= 1:
                cluster_id += 1
                clusters.append(TaskCluster(
                    cluster_id=cluster_id, tasks=zone_tasks,
                    task_num=len(zone_tasks),
                    order_ids=list({t.order_id for t in zone_tasks}),
                    priority=max(t.priority for t in zone_tasks),
                    zone=zone,
                ))
                continue

            # 层次聚类
            center_arr = np.array(centers, dtype=float)
            dist_matrix = pdist(center_arr, metric="euclidean")
            Z = linkage(dist_matrix, method="ward")
            labels = fcluster(Z, t=25, criterion="distance")

            label_groups: dict[int, list[TransportTask]] = defaultdict(list)
            for idx, label in enumerate(labels):
                label_groups[label].append(zone_tasks[idx])

            for group_tasks in label_groups.values():
                total = len(group_tasks)
                if total > max_capacity:
                    # 分割
                    split_n = (total // max_capacity) + 1
                    subgroups = np.array_split(group_tasks, split_n)
                    for sub in subgroups:
                        cluster_id += 1
                        st = list(sub)
                        clusters.append(TaskCluster(
                            cluster_id=cluster_id, tasks=st, task_num=len(st),
                            order_ids=list({t.order_id for t in st}),
                            priority=max(t.priority for t in st), zone=zone,
                        ))
                else:
                    cluster_id += 1
                    clusters.append(TaskCluster(
                        cluster_id=cluster_id, tasks=group_tasks,
                        task_num=len(group_tasks),
                        order_ids=list({t.order_id for t in group_tasks}),
                        priority=max(t.priority for t in group_tasks), zone=zone,
                    ))

        return clusters
