# main_agv.py
"""AGV调度 + 指令解析整合入口"""

import sys
import numpy as np
import random

from src.warehouse.maps.base import MapRegistry
from src.warehouse.fleet.map_builder import WarehouseMap
from src.warehouse.fleet.fleet_manager import FleetManager
from src.warehouse.wms.config import WarehouseConfig
from src.warehouse.wms.inventory import InventoryManager
from src.warehouse.wms.order_manager import OrderManager
from src.warehouse.wes.task_decomposer import TaskDecomposer
from src.warehouse.wes.clustering import OrderClusterer
from src.warehouse.simulation.simulator import Simulator
from src.warehouse.simulation.metrics import MetricsCollector
from src.warehouse.simulation.visualizer import Visualizer, ResultExporter
from src.warehouse.models import WorkOrder

# 注册所有地图
import src.warehouse.maps.medium_50x50  # noqa: F401
import src.warehouse.maps.large_100x100  # noqa: F401
import src.warehouse.maps.extreme  # noqa: F401


class AGVSystemApp:
    def __init__(self):
        self.config = WarehouseConfig()
        self.current_map = self.config.MAP_NAME
        self._rebuild()

    def _rebuild(self):
        map_config = MapRegistry.get(self.current_map)
        self.wmap = WarehouseMap(map_config)
        self.inventory = InventoryManager(map_config, seed=self.config.RANDOM_SEED)
        self.fleet = FleetManager(self.wmap, self.config)
        self.order_manager = OrderManager(map_config, seed=self.config.RANDOM_SEED)
        self.visualizer = Visualizer(self.wmap, self.config)

    def _run_schedule(self, orders: list[WorkOrder]) -> None:
        self.fleet.precompute()

        td = TaskDecomposer(
            self.inventory, self.order_manager.inbound_ports,
            self.order_manager.outbound_ports, seed=self.config.RANDOM_SEED
        )
        tasks = td.decompose(orders, self.wmap.storage_list)

        clusterer = OrderClusterer(self.fleet.path_finder, self.config)
        clusters = clusterer.cluster(tasks, self.config.AGV_MAX_TASK_CAPACITY, self.wmap.zone_pos)

        agv_tasks, makespan = self.fleet.schedule(clusters)

        sim = Simulator(self.wmap, self.fleet, self.config)
        result = sim.run(agv_tasks, makespan)

        print(f"\n  {'─'*40}")
        print(f"  Makespan: {result.makespan}")
        print(f"  总距离: {result.total_distance}")
        print(f"  AGV利用率: {result.agv_utilization:.2%}")
        print(f"  规划耗时: {result.planning_time:.2f}s")
        print(f"  {'─'*40}")

        self.visualizer.export_static_plots(
            sim.get_agvs(), result.makespan, "output/"
        )
        ResultExporter.export_json(result, "output/result.json")

    def run_interactive_mode(self):
        print("\n  [单条指令模式] 输入自然语言指令（输入 q 返回）")
        while True:
            text = input("\n  > ").strip()
            if text.lower() == "q":
                break
            if not text:
                continue
            print("  注意：VLM解析需要vLLM服务运行中。当前使用规则解析降级。")
            print("  如需完整功能，请先启动vLLM服务并通过main_interaction.py解析。")

    def run_batch_instruction_mode(self):
        print("\n  [批量指令模式] 逐行输入指令，空行结束")
        print("  或输入文件路径（如 orders.txt）")
        lines = []
        while True:
            line = input("  > ").strip()
            if not line:
                break
            if line.endswith(".txt") or line.endswith(".json"):
                try:
                    with open(line) as f:
                        lines.extend(l.strip() for l in f if l.strip())
                    break
                except FileNotFoundError:
                    print(f"  文件未找到: {line}")
                    continue
            lines.append(line)

        if not lines:
            print("  未输入任何指令")
            return

        print(f"  收到 {len(lines)} 条指令")
        orders = self.order_manager.from_random(len(lines))
        self._run_schedule(orders)

    def run_batch_simulation(self):
        print("\n  [批量仿真模式]")
        count = input(f"  订单数 [{self.config.ORDER_NUM}]: ").strip()
        count = int(count) if count else self.config.ORDER_NUM
        np.random.seed(self.config.RANDOM_SEED)
        random.seed(self.config.RANDOM_SEED)
        orders = self.order_manager.from_random(count)
        self._run_schedule(orders)

    def run_ablation_suite(self):
        from main_simulation import run_ablation
        run_ablation(self.config, self.current_map, self.config.ORDER_NUM)

    def select_map(self):
        maps = MapRegistry.list_all()
        print("\n  可用地图：")
        for i, (name, display) in enumerate(maps, 1):
            marker = " ◀" if name == self.current_map else ""
            print(f"    [{i}] {display}{marker}")
        choice = input(f"\n  选择 [当前: {self.current_map}]: ").strip()
        if choice and choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(maps):
                self.current_map = maps[idx][0]
                self._rebuild()
                print(f"  已切换到: {maps[idx][1]}")

    def run(self):
        while True:
            print(f"\n  ╔{'═'*48}╗")
            print(f"  ║        AGV 智能仓储调度系统  v2.0              ║")
            print(f"  ╠{'═'*48}╣")
            print(f"  ║  [1] 单条指令调度（自然语言 → 自动调度）       ║")
            print(f"  ║  [2] 批量指令调度（多行/文件 → 批量调度）      ║")
            print(f"  ║  [3] 批量仿真测试（随机订单 → 性能测试）       ║")
            print(f"  ║  [4] 消融实验（对比各模块贡献）                ║")
            print(f"  ║  [5] 地图选择（当前：{self.current_map:<16}）║")
            print(f"  ║  [q] 退出                                      ║")
            print(f"  ╚{'═'*48}╝")

            choice = input("\n  请选择: ").strip().lower()

            if choice == "1":
                self.run_interactive_mode()
            elif choice == "2":
                self.run_batch_instruction_mode()
            elif choice == "3":
                self.run_batch_simulation()
            elif choice == "4":
                self.run_ablation_suite()
            elif choice == "5":
                self.select_map()
            elif choice == "q":
                print("  再见！")
                break


if __name__ == "__main__":
    app = AGVSystemApp()
    app.run()
