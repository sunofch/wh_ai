# src/warehouse/simulation/visualizer.py
"""可视化 + 动画 + 导出"""

from __future__ import annotations
import json
import csv
from pathlib import Path
from typing import TYPE_CHECKING

import matplotlib
matplotlib.use("Agg")  # 非交互式后端
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np

from src.warehouse.models import SimulationResult
from src.warehouse.simulation.agv import AGV

if TYPE_CHECKING:
    from src.warehouse.fleet.map_builder import WarehouseMap
    from src.warehouse.wms.config import WarehouseConfig


# ── 视觉风格 ──

class VisualStyle:
    # 货架区域 — 按类型分色
    ZONE_COLORS = {
        "Mech1": "#FF9800", "Mech2": "#FFB74D",
        "Elec1": "#2196F3", "Elec2": "#64B5F6",
        "Cons1": "#4CAF50", "Cons2": "#66BB6A", "Cons3": "#81C784",
        "Safety": "#9C27B0", "Tool": "#795548",
    }
    ZONE_TYPE_COLORS = {
        "mechanical": "#FF9800",
        "electrical": "#2196F3",
        "consumable": "#4CAF50",
        "safety": "#9C27B0",
        "tool": "#795548",
    }
    PORT_COLORS = {
        "INBOUND": {"fill": "#BBDEFB", "edge": "#2196F3", "label": "#0D47A1"},
        "OUTBOUND": {"fill": "#FFCDD2", "edge": "#F44336", "label": "#B71C1C"},
    }
    AGV_COLORS = [
        "#E74C3C", "#3498DB", "#2ECC71", "#F39C12",
        "#9B59B6", "#1ABC9C", "#E91E63", "#8BC34A",
    ]
    # 格子类型颜色
    CELL_COLORS = {
        1: "#F5F5F5",   # PASSABLE
        2: "#FFF9C4",   # STORAGE
        3: "#BBDEFB",   # PORT
        4: "#80CBC4",   # YIELD_POINT
        5: "#FFF176",   # CHARGING
        6: "#B2DFDB",   # AISLE_DOWN
        7: "#B3E5FC",   # AISLE_UP
        8: "#D7CCC8",   # SUB_AISLE
    }
    OBSTACLE_COLOR = "#FAFAFA"
    CHARGE_FILL = "#FFF176"
    CHARGE_EDGE = "#FBC02D"
    # 字体
    TITLE_FONT = {"family": ["DejaVu Sans"], "size": 16, "weight": "bold"}
    SUBTITLE_FONT = {"family": ["DejaVu Sans"], "size": 11}
    LABEL_FONT = {"family": ["DejaVu Sans"], "size": 9}
    LEGEND_FONT = {"family": ["DejaVu Sans"], "size": 8}
    LEGEND_TITLE_FONT = {"family": ["DejaVu Sans"], "size": 9, "weight": "bold"}
    # 端口标签
    PORT_LABELS = {
        "IN-L": "In-L", "IN-C": "In-C", "IN-R": "In-R",
        "OUT-L": "Out-L", "OUT-C": "Out-C", "OUT-R": "Out-R",
    }
    # AGV
    AGV_SIZE = 120
    AGV_EDGE_WIDTH = 1.5
    # 布局常量
    LEGEND_WIDTH_INCHES = 2.2
    LEGEND_PADDING = 0.15
    LEGEND_LINE_HEIGHT = 0.028


class ExportConfig:
    def __init__(self, fmt: str = "gif", path: str = "output/",
                 fps: int = 15, dpi: int = 150):
        self.format = fmt
        self.path = path
        self.fps = fps
        self.dpi = dpi


class ResultExporter:
    @staticmethod
    def export_json(result: SimulationResult, path: str) -> None:
        data = result.model_dump(exclude={"agv_trajectories"})
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @staticmethod
    def export_summary(result: SimulationResult, path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"Makespan: {result.makespan}\n")
            f.write(f"Total Distance: {result.total_distance}\n")
            f.write(f"AGV Utilization: {result.agv_utilization:.2%}\n")
            f.write(f"Planning Time: {result.planning_time:.2f}s\n")
            f.write(f"Conflict Count: {result.conflict_count}\n")
            f.write(f"Yield Count: {result.yield_count}\n")

    @staticmethod
    def export_trajectory(result: SimulationResult, path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["agv_id", "t", "x", "y", "state", "task_id"])
            for agv_id, steps in result.agv_trajectories.items():
                for s in steps:
                    writer.writerow([agv_id, s.t, s.x, s.y, s.state, s.task_id])


class Visualizer:
    def __init__(self, warehouse_map, config):
        self.wmap = warehouse_map
        self.config = config
        plt.rcParams["font.sans-serif"] = ["DejaVu Sans"]
        plt.rcParams["axes.unicode_minus"] = False

    def plot_base_map(self) -> plt.Figure:
        fig, ax = plt.subplots(1, 1, figsize=self.config.FIG_SIZE, dpi=self.config.FIG_DPI)
        grid = self.wmap.grid
        gs = self.wmap.config.grid_size

        # 画网格（按格子类型着色）
        CELL_COLORS = {
            1: VisualStyle.ROAD_COLOR,        # PASSABLE
            2: VisualStyle.STORAGE_COLOR,     # STORAGE
            3: "#BBDEFB",                     # PORT
            4: "#80CBC4",                     # YIELD_POINT
            5: "#FFF176",                     # CHARGING
            6: VisualStyle.AISLE_DOWN_COLOR,  # AISLE_DOWN
            7: VisualStyle.AISLE_UP_COLOR,    # AISLE_UP
            8: VisualStyle.SUB_AISLE_COLOR,   # SUB_AISLE
        }
        for y in range(gs):
            for x in range(gs):
                cell = grid[y, x]
                color = CELL_COLORS.get(cell, VisualStyle.OBSTACLE_COLOR)
                ax.add_patch(patches.Rectangle((x - 0.5, y - 0.5), 1, 1,
                                               facecolor=color, edgecolor="none"))

        # 画货架区域
        for name, zcfg in self.wmap.config.rack_zones.items():
            sx, sy = zcfg.pos
            w, h = zcfg.height, zcfg.width
            color = VisualStyle.ZONE_COLORS.get(name, "#E0E0E0")
            ax.add_patch(patches.Rectangle((sx - 0.5, sy - 0.5), w, h,
                                           facecolor=color, edgecolor="#555",
                                           linewidth=1.5, alpha=0.4))
            ax.text(sx + w / 2, sy + h / 2, name, ha="center", va="center",
                    color="#333", **{k: v for k, v in VisualStyle.LABEL_FONT.items() if k != "size"})

        # 画端口
        for name, pcfg in self.wmap.port_info.items():
            x1, x2, y1, y2 = pcfg["area"]
            colors = VisualStyle.PORT_COLORS.get(pcfg["type"],
                                                  {"fill": "#E0E0E0", "edge": "#757575", "label": "#333"})
            ax.add_patch(patches.Rectangle((x1 - 0.5, y1 - 0.5), x2 - x1, y2 - y1,
                                           facecolor=colors["fill"], edgecolor=colors["edge"],
                                           linewidth=2, alpha=0.7))
            ax.text((x1 + x2) / 2, (y1 + y2) / 2,
                    VisualStyle.PORT_LABELS.get(name, name),
                    ha="center", va="center",
                    color=colors["label"], **VisualStyle.LABEL_FONT)

        # 画充电桩
        for pos in self.wmap.charging_points:
            ax.plot(pos[0], pos[1], "s", color=VisualStyle.CHARGE_COLOR,
                    markersize=10, markeredgecolor="#F9A825", markeredgewidth=1.5)

        ax.set_xlim(-1, gs)
        ax.set_ylim(gs, -1)
        ax.set_aspect("equal")
        ax.set_title("AGV Warehouse Map", **VisualStyle.TITLE_FONT)
        return fig

    def plot_snapshot(self, agvs: list[AGV], step: int) -> plt.Figure:
        fig = self.plot_base_map()
        ax = fig.axes[0]
        for agv in agvs:
            if step < len(agv.trajectory):
                x, y, state, _ = agv.trajectory[step]
                color = VisualStyle.AGV_COLORS[agv.agv_id % len(VisualStyle.AGV_COLORS)]
                ax.plot(x, y, "o", color=color, markersize=12,
                        markeredgecolor="white", markeredgewidth=1.5)
                ax.text(x, y - 1.5, f"AGV{agv.agv_id}", ha="center",
                        fontsize=8, color=color)
        return fig

    def _render_frames(self, agvs: list[AGV], makespan: int,
                       max_frames: int = 300) -> list[np.ndarray]:
        frames = []
        step = 0
        while step < makespan:
            fig = self.plot_snapshot(agvs, step)
            fig.canvas.draw()
            buf = np.asarray(fig.canvas.buffer_rgba())
            frames.append(buf[:, :, :3].copy())  # RGBA → RGB
            plt.close(fig)
            step += max(1, makespan // max_frames)
        return frames

    def export_gif(self, agvs: list[AGV], makespan: int,
                   path: str = "output/animation.gif", fps: int = 15, dpi: int = 100) -> str:
        frames = self._render_frames(agvs, makespan)
        if frames:
            from PIL import Image
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            imgs = [Image.fromarray(f) for f in frames]
            imgs[0].save(path, save_all=True, append_images=imgs[1:],
                         duration=1000 // fps, loop=0)
        return path

    def export_mp4(self, agvs: list[AGV], makespan: int,
                   path: str = "output/animation.mp4", fps: int = 15, dpi: int = 100) -> str:
        frames = self._render_frames(agvs, makespan)
        if not frames:
            return path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        import subprocess
        h, w = frames[0].shape[:2]
        cmd = [
            "ffmpeg", "-y",
            "-f", "rawvideo", "-vcodec", "rawvideo",
            "-s", f"{w}x{h}", "-pix_fmt", "rgb24",
            "-r", str(fps),
            "-i", "-",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-crf", "23", path,
        ]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
        for f in frames:
            proc.stdin.write(f.tobytes())
        proc.stdin.close()
        proc.wait()
        return path

    def export_static_plots(self, agvs: list[AGV], makespan: int,
                            output_dir: str = "output/",
                            formats: list[str] | None = None) -> list[str]:
        if formats is None:
            formats = ["png"]
        saved = []
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        fig = self.plot_snapshot(agvs, makespan - 1)
        for fmt in formats:
            p = f"{output_dir}/final_state.{fmt}"
            fig.savefig(p, dpi=self.config.FIG_DPI, bbox_inches="tight")
            saved.append(p)
        plt.close(fig)
        return saved
