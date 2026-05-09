"""仓库地图可视化 — 建筑平面图风格

生成论文质量的仓库布局图，标注货架区、端口、充电站和AGV初始位置。

用法:
    python -m src.warehouse.visualize_map                 # 默认PNG
    python -m src.warehouse.visualize_map --format svg    # SVG矢量图
    python -m src.warehouse.visualize_map --output my.png # 指定输出文件
"""

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
matplotlib.rcParams["font.sans-serif"] = ["AR PL UMing CN", "Droid Sans Fallback", "DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch
import matplotlib.gridspec as gridspec
import numpy as np

from src.warehouse.maps.base import MapRegistry
from src.warehouse.fleet.map_builder import (
    WarehouseMap, MAP_OBSTACLE, MAP_PASSABLE, MAP_STORAGE, MAP_PORT, MAP_CHARGING,
)


# ── 配色方案（低饱和度论文风格） ──
COLORS = {
    "wall": "#3C3C3C",
    "storage": "#B0BEC5",
    "port_in": "#A5D6A7",
    "port_out": "#90CAF9",
    "charging": "#FFD54F",
    "berth": "#555555",
}

# AGV 配色 — 8种可区分颜色
AGV_COLORS = [
    "#E53935",  # 1-红
    "#1E88E5",  # 2-蓝
    "#43A047",  # 3-绿
    "#FB8C00",  # 4-橙
    "#8E24AA",  # 5-紫
    "#00ACC1",  # 6-青
    "#F4511E",  # 7-深橙
    "#3949AB",  # 8-靛蓝
]


def _draw_agv_badge(ax, x, y, idx, scale=1.0):
    """绘制单个 AGV 徽章：圆角矩形 + 编号"""
    c = AGV_COLORS[idx % len(AGV_COLORS)]
    s = 0.38 * scale
    # 阴影
    ax.add_patch(FancyBboxPatch(
        (x - s + 0.06, y - s + 0.06), 2 * s, 2 * s,
        boxstyle="round,pad=0.12",
        facecolor="#00000020", edgecolor="none", zorder=6,
    ))
    # 底色
    ax.add_patch(FancyBboxPatch(
        (x - s, y - s), 2 * s, 2 * s,
        boxstyle="round,pad=0.12",
        facecolor=c, edgecolor="white", linewidth=1.4, zorder=7,
    ))
    # 编号
    ax.text(
        x, y, str(idx + 1),
        ha="center", va="center", fontsize=7 * scale,
        color="white", fontweight="bold", zorder=8,
    )


def draw_map_background(ax, wh_map: WarehouseMap):
    """绘制仓库地图背景（网格、货架区框、端口、充电站）

    可被静态地图和动画复用，只绘制静态元素，不包含AGV标记和图例。
    """
    cfg = wh_map.config
    gw, gh = cfg.grid_size, cfg.grid_height or cfg.grid_size

    ax.set_xlim(-1, gw)
    ax.set_ylim(gh, -1)
    ax.set_aspect("equal")
    ax.axis("off")

    # 1. 绘制网格
    for y in range(gh):
        for x in range(gw):
            cell = wh_map.grid[y, x]
            if cell == MAP_OBSTACLE:
                color = COLORS["wall"]
            elif cell == MAP_STORAGE:
                color = COLORS["storage"]
            elif cell == MAP_PORT:
                color = COLORS["port_in"] if y < gh // 2 else COLORS["port_out"]
            elif cell == MAP_CHARGING:
                color = COLORS["charging"]
            else:
                continue
            ax.add_patch(mpatches.Rectangle(
                (x - 0.5, y - 0.5), 1, 1,
                facecolor=color, edgecolor="none",
            ))

    # 2. 货架区域框
    for zone_name, zcfg in cfg.rack_zones.items():
        sx, sy = zcfg.pos
        w, h = zcfg.width, zcfg.height

        row_pairs = min(h // 2, 5)
        content_top = sy - 0.5
        content_bottom = sy + (row_pairs - 1) * 2 + 0.5
        content_h = content_bottom - content_top

        content_left = sx - 0.5
        content_w = w
        pad = 0.6
        box_x = content_left - pad
        box_y = content_top - pad
        box_w = content_w + 2 * pad
        box_h = content_h + 2 * pad

        ax.add_patch(FancyBboxPatch(
            (box_x, box_y), box_w, box_h,
            boxstyle="round,pad=0.2",
            facecolor="none", edgecolor=zcfg.color,
            linewidth=1.2, linestyle="--", alpha=0.6,
        ))

    # 3. 端口泊位点
    for port_name, pcfg in cfg.ports.items():
        for bx, by in pcfg.get("berths", []):
            ax.plot(bx, by, "s", color=COLORS["berth"], markersize=3, zorder=5)

    # 4. 充电站
    for cx, cy in cfg.charging_points:
        ax.plot(cx, cy, marker="D", markersize=8,
                color="#F57F17", markeredgecolor="white",
                markeredgewidth=1, zorder=6)


def draw_warehouse_map(wh_map: WarehouseMap, output: str, fmt: str = "png"):
    """绘制仓库建筑平面图"""
    cfg = wh_map.config
    gw, gh = cfg.grid_size, cfg.grid_height or cfg.grid_size

    # 地图 + 图例
    fig = plt.figure(figsize=(20, 14))
    gs = gridspec.GridSpec(1, 2, width_ratios=[5, 1], wspace=0.02)
    ax_map = fig.add_subplot(gs[0])
    ax_legend = fig.add_subplot(gs[1])

    # 绘制地图背景
    draw_map_background(ax_map, wh_map)

    # AGV 初始位置 — 圆角徽章
    for i, (ax_pos, ay_pos) in enumerate(cfg.agv_init_positions):
        _draw_agv_badge(ax_map, ax_pos, ay_pos, i)

    # ── 图例面板 ──
    ax_legend.set_xlim(0, 1)
    ax_legend.set_ylim(0, 1)
    ax_legend.axis("off")

    y = 0.96
    dy = 0.032

    # 图例标题
    ax_legend.text(0.5, y, "图 例", ha="center", va="center",
                   fontsize=14, fontweight="bold", color="#333333")
    y -= dy * 1.5

    # 分隔线
    ax_legend.plot([0.05, 0.95], [y + dy * 0.3, y + dy * 0.3],
                   color="#CCCCCC", linewidth=0.8)
    y -= dy * 0.3

    # 地图元素
    ax_legend.text(0.5, y, "地图元素", ha="center", va="center",
                   fontsize=10, fontweight="bold", color="#666666")
    y -= dy

    legend_map_items = [
        (COLORS["wall"], "墙壁"),
        (COLORS["storage"], "货架"),
        (COLORS["port_in"], "入库端口"),
        (COLORS["port_out"], "出库端口"),
        (COLORS["charging"], "充电站"),
    ]
    for color, label in legend_map_items:
        ax_legend.add_patch(mpatches.FancyBboxPatch(
            (0.08, y - 0.01), 0.1, 0.022,
            boxstyle="round,pad=0.005",
            facecolor=color, edgecolor="#AAAAAA", linewidth=0.5,
        ))
        ax_legend.text(0.22, y, label, ha="left", va="center",
                       fontsize=9, color="#333333")
        y -= dy

    y -= dy * 0.5
    ax_legend.plot([0.05, 0.95], [y + dy * 0.3, y + dy * 0.3],
                   color="#CCCCCC", linewidth=0.8)
    y -= dy * 0.3

    # AGV 图例 — 与地图徽章同风格
    ax_legend.text(0.5, y, "AGV 位置", ha="center", va="center",
                   fontsize=10, fontweight="bold", color="#666666")
    y -= dy

    for i in range(cfg.agv_count):
        c = AGV_COLORS[i % len(AGV_COLORS)]
        # 小型徽章
        ax_legend.add_patch(FancyBboxPatch(
            (0.08, y - 0.009), 0.08, 0.018,
            boxstyle="round,pad=0.004",
            facecolor=c, edgecolor="white", linewidth=0.6,
        ))
        ax_legend.text(0.12, y, str(i + 1), ha="center", va="center",
                       fontsize=5.5, color="white", fontweight="bold")
        ax_legend.text(0.22, y, f"AGV {i + 1}", ha="left", va="center",
                       fontsize=8.5, color="#333333")
        y -= dy

    y -= dy * 0.5
    ax_legend.plot([0.05, 0.95], [y + dy * 0.3, y + dy * 0.3],
                   color="#CCCCCC", linewidth=0.8)
    y -= dy * 0.3

    # 货架区域图例
    ax_legend.text(0.5, y, "货架区域", ha="center", va="center",
                   fontsize=10, fontweight="bold", color="#666666")
    y -= dy

    zone_type_labels = {
        "mechanical": "机械类",
        "electrical": "电气类",
        "consumable": "耗材类",
        "safety": "安全类",
        "tool": "工具类",
    }
    seen_types = set()
    for zone_name, zcfg in cfg.rack_zones.items():
        zt = zcfg.zone_type
        if zt in seen_types:
            continue
        seen_types.add(zt)
        ax_legend.add_patch(mpatches.FancyBboxPatch(
            (0.08, y - 0.01), 0.1, 0.022,
            boxstyle="round,pad=0.005",
            facecolor="none", edgecolor=zcfg.color,
            linewidth=1.2, linestyle="--",
        ))
        ax_legend.text(0.22, y, zone_type_labels.get(zt, zt),
                       ha="left", va="center", fontsize=9, color="#333333")
        y -= dy

    # 标题
    ax_map.set_title(
        "仓库布局图 (57×47)",
        fontsize=14, fontweight="bold", pad=12, color="#333333",
    )

    plt.tight_layout()
    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(out_path), format=fmt, dpi=300, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.close(fig)
    print(f"Map saved to: {out_path.resolve()}")


def main():
    parser = argparse.ArgumentParser(description="仓库地图可视化")
    parser.add_argument("--format", default="png", choices=["png", "svg"],
                        help="输出格式 (默认: png)")
    parser.add_argument("--output", default=None,
                        help="输出文件路径")
    args = parser.parse_args()

    output = args.output
    if output is None:
        ext = args.format
        output = str(Path(__file__).parent / "maps" / f"warehouse_map.{ext}")

    map_config = MapRegistry.get("medium_57x47")
    wh_map = WarehouseMap(map_config)
    draw_warehouse_map(wh_map, output, fmt=args.format)


if __name__ == "__main__":
    main()
