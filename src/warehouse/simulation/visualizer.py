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
        cfg = self.config
        fig = plt.figure(figsize=cfg.FIG_SIZE, dpi=cfg.FIG_DPI)

        # Title
        fig.text(0.42, 0.96, "AGV Warehouse Simulation Map",
                 ha="center", va="center", **VisualStyle.TITLE_FONT, color="#212121")
        subtitle = (f"{self.wmap.config.grid_size}x{self.wmap.config.grid_size} Grid | "
                    f"9 Zones | {self.wmap.config.agv_count} AGVs")
        fig.text(0.42, 0.935, subtitle,
                 ha="center", va="center", **VisualStyle.SUBTITLE_FONT, color="#757575")

        # GridSpec: 地图主区域(左) + 图例区域(右)
        gridspec = fig.add_gridspec(1, 2, width_ratios=[1, 0.12],
                                    left=0.04, right=0.98, top=0.91, bottom=0.04,
                                    wspace=0.02)
        ax = fig.add_subplot(gridspec[0, 0])
        ax_legend = fig.add_subplot(gridspec[0, 1])
        ax_legend.set_axis_off()

        grid = self.wmap.grid
        gsize = self.wmap.config.grid_size

        # 画格子（按类型着色）
        for y in range(gsize):
            for x in range(gsize):
                cell = grid[y, x]
                color = VisualStyle.CELL_COLORS.get(cell, VisualStyle.OBSTACLE_COLOR)
                ax.add_patch(patches.Rectangle(
                    (x - 0.5, y - 0.5), 1, 1,
                    facecolor=color, edgecolor="none"))

        # 画货架区域（边框 + 纹理 + 标签）
        self._draw_rack_zones(ax)

        # 画端口
        for name, pcfg in self.wmap.port_info.items():
            x1, x2, y1, y2 = pcfg["area"]
            colors = VisualStyle.PORT_COLORS.get(
                pcfg["type"], {"fill": "#E0E0E0", "edge": "#757575", "label": "#333"})
            ax.add_patch(patches.Rectangle(
                (x1 - 0.5, y1 - 0.5), x2 - x1, y2 - y1,
                facecolor=colors["fill"], edgecolor=colors["edge"],
                linewidth=2, alpha=0.7))
            ax.text((x1 + x2) / 2, (y1 + y2) / 2,
                    VisualStyle.PORT_LABELS.get(name, name),
                    ha="center", va="center",
                    color=colors["label"], **VisualStyle.LABEL_FONT)

        # 画充电桩（方形标记）
        for pos in self.wmap.charging_points:
            ax.add_patch(patches.Rectangle(
                (pos[0] - 0.6, pos[1] - 0.6), 1.2, 1.2,
                facecolor=VisualStyle.CHARGE_FILL,
                edgecolor=VisualStyle.CHARGE_EDGE,
                linewidth=1.5, zorder=4))

        # 方位标识 N（右上角）
        ax.plot(gsize - 2, 1.5, "o", markersize=14,
                markerfacecolor="white", markeredgecolor="#9E9E9E",
                markeredgewidth=1.5, zorder=6)
        ax.text(gsize - 2, 1.5, "N", ha="center", va="center",
                fontsize=8, fontweight="bold", color="#757575", zorder=7)

        # 比例尺（底部居中）
        scale_x = gsize / 2 - 5
        scale_y = gsize - 1.5
        ax.plot([scale_x, scale_x + 10], [scale_y, scale_y],
                color="#757575", linewidth=2, zorder=6)
        ax.plot([scale_x, scale_x], [scale_y - 0.5, scale_y + 0.5],
                color="#757575", linewidth=1.5, zorder=6)
        ax.plot([scale_x + 10, scale_x + 10], [scale_y - 0.5, scale_y + 0.5],
                color="#757575", linewidth=1.5, zorder=6)
        ax.text(scale_x + 5, scale_y + 1.2, "10 cells",
                ha="center", va="center", fontsize=7, color="#9E9E9E", zorder=6)

        # 坐标轴精简
        ax.set_xlim(-1, gsize)
        ax.set_ylim(gsize, -1)
        ax.set_aspect("equal")
        ax.set_xticks(range(0, gsize + 1, 10))
        ax.set_yticks(range(0, gsize + 1, 10))
        ax.tick_params(colors="#9E9E9E", labelsize=7)
        ax.set_facecolor("#FAFAFA")
        for spine in ax.spines.values():
            spine.set_color("#E0E0E0")

        # 画图例
        self._draw_legend(ax_legend)

        return fig

    def _draw_rack_zones(self, ax: plt.Axes) -> None:
        for name, zcfg in self.wmap.config.rack_zones.items():
            sx, sy = zcfg.pos
            w, h = zcfg.height, zcfg.width
            zone_color = VisualStyle.ZONE_COLORS.get(name, "#E0E0E0")

            # 区域半透明填充 + 边框
            ax.add_patch(patches.Rectangle(
                (sx - 0.5, sy - 0.5), w, h,
                facecolor=zone_color, edgecolor=zone_color,
                linewidth=1.5, alpha=0.2))

            # 储位格子纹理
            num_rows = zcfg.num_rows
            bays = zcfg.bays_per_row
            sub_aisle_cols = zcfg.sub_aisle_cols

            total_cols = bays
            storage_cols = [c for c in range(total_cols) if c not in sub_aisle_cols]
            cell_w = w / total_cols
            cell_h = h / num_rows

            for row_i in range(num_rows):
                for col_i in storage_cols:
                    cx = sx + col_i * cell_w
                    cy = sy + row_i * cell_h
                    ax.add_patch(patches.Rectangle(
                        (cx - 0.5, cy - 0.5), cell_w, cell_h,
                        facecolor=zone_color, edgecolor="none", alpha=0.4))

            # 区域名称标签（白色半透明背景）
            ax.text(sx + w / 2, sy + h / 2, name,
                    ha="center", va="center",
                    fontsize=8, fontweight="bold", color="#424242",
                    bbox=dict(boxstyle="round,pad=0.2",
                              facecolor="white", alpha=0.8, edgecolor="none"))

    def _draw_legend(self, ax: plt.Axes) -> None:
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)

        y = 0.96
        dy = VisualStyle.LEGEND_LINE_HEIGHT

        def section(title: str):
            nonlocal y
            y -= dy * 0.5
            ax.text(0.5, y, title, ha="center", va="top",
                    **VisualStyle.LEGEND_TITLE_FONT, color="#424242")
            y -= dy * 1.2
            ax.plot([0.05, 0.95], [y + dy * 0.3, y + dy * 0.3],
                    color="#E0E0E0", linewidth=0.5)

        def color_box(label: str, facecolor: str, edgecolor: str = "none",
                      box_h: float = 0.018):
            nonlocal y
            ax.add_patch(patches.FancyBboxPatch(
                (0.05, y - box_h / 2), 0.15, box_h,
                boxstyle="round,pad=0.002",
                facecolor=facecolor, edgecolor=edgecolor,
                linewidth=1.0 if edgecolor != "none" else 0))
            ax.text(0.25, y, label, va="center",
                    **VisualStyle.LEGEND_FONT, color="#424242")
            y -= dy

        def circle_dot(label: str, color: str):
            nonlocal y
            ax.plot(0.12, y, "o", markersize=6, color=color,
                    markeredgecolor="white", markeredgewidth=0.8)
            ax.text(0.25, y, label, va="center",
                    **VisualStyle.LEGEND_FONT, color="#424242")
            y -= dy

        # Legend title
        ax.text(0.5, y, "LEGEND", ha="center", va="top",
                fontsize=11, fontweight="bold", color="#424242",
                family="DejaVu Sans")
        y -= dy * 1.5
        ax.plot([0.05, 0.95], [y + dy * 0.3, y + dy * 0.3],
                color="#E0E0E0", linewidth=0.8)

        # Rack zones
        section("Rack Zones")
        type_labels = {
            "mechanical": "Mech",
            "electrical": "Elec",
            "consumable": "Cons",
            "safety": "Safety",
            "tool": "Tool",
        }
        seen_types = set()
        for name, zcfg in self.wmap.config.rack_zones.items():
            zt = zcfg.zone_type
            if zt in seen_types:
                continue
            seen_types.add(zt)
            color = VisualStyle.ZONE_TYPE_COLORS.get(zt, "#E0E0E0")
            color_box(type_labels.get(zt, zt), color)

        # Ports
        section("Ports")
        color_box("Inbound", "#BBDEFB", edgecolor="#2196F3")
        color_box("Outbound", "#FFCDD2", edgecolor="#F44336")

        # Aisles
        section("Aisles")
        color_box("Main Aisle", "#F5F5F5", edgecolor="#BDBDBD")
        color_box("Aisle Down", "#B2DFDB")
        color_box("Aisle Up", "#B3E5FC")

        # Facilities
        section("Facilities")
        color_box("Charging", "#FFF176", edgecolor="#FBC02D")

        # AGVs
        section("AGVs")
        for i, color in enumerate(VisualStyle.AGV_COLORS):
            circle_dot(f"AGV {i + 1}", color)

    def plot_snapshot(self, agvs: list[AGV], step: int) -> plt.Figure:
        fig = self.plot_base_map()
        ax = fig.axes[0]
        for agv in agvs:
            if step < len(agv.trajectory):
                x, y, state, _ = agv.trajectory[step]
                color = VisualStyle.AGV_COLORS[agv.agv_id % len(VisualStyle.AGV_COLORS)]
                ax.plot(x, y, "o", color=color, markersize=11,
                        markeredgecolor="white", markeredgewidth=1.8,
                        zorder=8)
                ax.text(x, y - 1.8, f"AGV{agv.agv_id}", ha="center",
                        fontsize=7, color=color, fontweight="bold", zorder=8)
        return fig

    def _render_base_image(self) -> np.ndarray:
        """Render base map once and cache as RGB array."""
        fig = self.plot_base_map()
        fig.canvas.draw()
        buf = np.asarray(fig.canvas.buffer_rgba())
        base = buf[:, :, :3].copy()
        plt.close(fig)
        return base

    def _render_frames(self, agvs: list[AGV], makespan: int,
                       max_frames: int = 300) -> list[np.ndarray]:
        # Render base map once
        base_img = self._render_base_image()
        h, w = base_img.shape[:2]

        frames = []
        step = 0
        while step < makespan:
            # Use base image as background, overlay AGV markers
            fig, ax = plt.subplots(figsize=self.config.FIG_SIZE, dpi=self.config.FIG_DPI)
            ax.imshow(base_img, extent=[0, w, h, 0], aspect="auto")
            ax.set_axis_off()

            gsize = self.wmap.config.grid_size
            for agv in agvs:
                if step < len(agv.trajectory):
                    ax_x, ax_y, _, _ = agv.trajectory[step]
                    color = VisualStyle.AGV_COLORS[agv.agv_id % len(VisualStyle.AGV_COLORS)]
                    # Map grid coords to pixel coords
                    px = (ax_x + 0.5) / gsize * w
                    py = (ax_y + 0.5) / gsize * h
                    ax.plot(px, py, "o", color=color, markersize=11,
                            markeredgecolor="white", markeredgewidth=1.8, zorder=8)
                    ax.text(px, py - h * 0.02, f"AGV{agv.agv_id}", ha="center",
                            fontsize=7, color=color, fontweight="bold", zorder=8)

            fig.canvas.draw()
            buf = np.asarray(fig.canvas.buffer_rgba())
            frames.append(buf[:, :, :3].copy())
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
