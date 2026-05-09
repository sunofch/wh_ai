"""AGV调度动画可视化

将仿真轨迹渲染为GIF/MP4动画，复用仓库地图背景。
每帧只更新AGV位置标记（Artist动画），不重绘地图。

用法:
    python main_simulation.py --animate              # 仿真后自动生成动画
    python -m src.warehouse.visualize_animation      # 独立运行
"""

import argparse
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import matplotlib
matplotlib.use("Agg")
matplotlib.rcParams["font.sans-serif"] = ["AR PL UMing CN", "Droid Sans Fallback", "DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False
import matplotlib.pyplot as plt
import matplotlib.animation as animation

from src.warehouse.visualize_map import AGV_COLORS, draw_map_background

if TYPE_CHECKING:
    from src.warehouse.fleet.map_builder import WarehouseMap
    from src.warehouse.models import SimulationResult


# AGV 状态 → marker 形状和边缘颜色
STATE_STYLE = {
    "idle":              {"marker": "o", "edge": "#AAAAAA", "alpha": 0.4},
    "moving_empty":      {"marker": "o", "edge": "white",   "alpha": 0.9},
    "moving_loaded":     {"marker": "s", "edge": "white",   "alpha": 0.95},
    "loading":           {"marker": "^", "edge": "#43A047",  "alpha": 0.95},
    "unloading":         {"marker": "v", "edge": "#FB8C00",  "alpha": 0.95},
    "charging":          {"marker": "D", "edge": "#FFD54F",  "alpha": 0.9},
    "moving_to_charge":  {"marker": "D", "edge": "#AAAAAA",  "alpha": 0.7},
}

# 状态图例文字
STATE_LABELS = {
    "idle": "空闲",
    "moving_empty": "空载移动",
    "moving_loaded": "载货移动",
    "loading": "装货",
    "unloading": "卸货",
    "charging": "充电",
    "moving_to_charge": "前往充电",
}


def _sample_trajectory(trajectories: dict, makespan: int,
                       target_frames: int | None = None) -> list[dict]:
    """采样轨迹，合并固定间隔 + 状态变化帧

    Returns: list[{"t": int, "positions": {agv_id: (x, y, state, task_id)}}]
    """
    if target_frames is None:
        target_frames = min(makespan // 3, 400)
    target_frames = max(target_frames, 20)

    # 固定间隔采样
    interval = max(1, makespan // target_frames)
    regular = set(range(0, makespan, interval))

    # 状态变化帧
    changes = set()
    for agv_id, steps in trajectories.items():
        prev_state = None
        for step in steps:
            if step.state != prev_state:
                changes.add(step.t)
            prev_state = step.state

    # 合并去重排序
    all_frames = sorted(regular | changes)

    # 仍超过目标帧数，均匀抽样
    if len(all_frames) > target_frames * 1.5:
        indices = np.linspace(0, len(all_frames) - 1, target_frames, dtype=int)
        all_frames = [all_frames[i] for i in indices]

    # 构建每帧数据
    step_map: dict[int, dict] = {}
    for agv_id, steps in trajectories.items():
        for step in steps:
            step_map.setdefault(step.t, {})[agv_id] = (step.x, step.y, step.state, step.task_id)

    frames = []
    for t in all_frames:
        positions = step_map.get(t, {})
        frames.append({"t": t, "positions": positions})

    return frames


def create_animation(wh_map: "WarehouseMap", result: "SimulationResult",
                     output: str = "output/animation.gif",
                     fps: int = 10, fmt: str = "gif",
                     target_frames: int | None = None):
    """生成AGV调度动画

    Args:
        wh_map: 仓库地图实例
        result: 仿真结果（含 agv_trajectories）
        output: 输出文件路径
        fps: 帧率
        fmt: "gif" 或 "mp4"
        target_frames: 目标帧数，None则自动计算
    """
    trajectories = result.agv_trajectories
    if not trajectories:
        print("  [动画] 无轨迹数据，跳过")
        return

    agv_ids = sorted(trajectories.keys())
    n_agv = len(agv_ids)

    # 采样
    frames = _sample_trajectory(trajectories, result.makespan, target_frames)
    print(f"  [动画] makespan={result.makespan}, 采样帧数={len(frames)}, fps={fps}")

    # 创建画布
    fig, ax = plt.subplots(figsize=(16, 12))
    draw_map_background(ax, wh_map)

    # 标题 + 时间步文字
    ax.set_title(
        f"AGV调度动画 ({wh_map.config.display_name})",
        fontsize=14, fontweight="bold", pad=12, color="#333333",
    )
    time_text = ax.text(
        0.02, 0.02, "", transform=ax.transAxes,
        fontsize=10, color="#333333", fontfamily="monospace",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8),
    )

    # 状态图例（右下角）
    _draw_state_legend(ax)

    # AGV 标记 Artists
    artists = []
    for i, agv_id in enumerate(agv_ids):
        color = AGV_COLORS[i % len(AGV_COLORS)]
        line, = ax.plot([], [], marker="o", markersize=10,
                        color=color, markeredgecolor="white",
                        markeredgewidth=1.2, linestyle="none", zorder=10)
        # AGV 编号标签
        label = ax.text(0, 0, str(agv_id), fontsize=6, color="white",
                        fontweight="bold", ha="center", va="center", zorder=11)
        artists.append((agv_id, line, label))

    all_artists = [line for _, line, _ in artists] + \
                  [label for _, _, label in artists] + [time_text]

    def init():
        for _, line, label in artists:
            line.set_data([], [])
            label.set_position((0, 0))
            label.set_visible(False)
        time_text.set_text("")
        return all_artists

    def update(frame_idx):
        frame = frames[frame_idx]
        t = frame["t"]
        positions = frame["positions"]

        for agv_id, line, label in artists:
            if agv_id in positions:
                x, y, state, _ = positions[agv_id]
                style = STATE_STYLE.get(state, STATE_STYLE["idle"])

                line.set_data([x], [y])
                line.set_marker(style["marker"])
                line.set_alpha(style["alpha"])
                line.set_markeredgecolor(style["edge"])

                label.set_position((x, y))
                label.set_visible(True)
            else:
                line.set_data([], [])
                label.set_visible(False)

        time_text.set_text(f"  step {t:>5d} / {result.makespan}")
        return all_artists

    anim = animation.FuncAnimation(
        fig, update, init_func=init,
        frames=len(frames), interval=1000 // fps,
        blit=True, repeat=True,
    )

    # 保存
    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "gif":
        writer = animation.PillowWriter(fps=fps)
    elif fmt == "mp4":
        writer = animation.FFMpegWriter(fps=fps, bitrate=2000)
    else:
        writer = animation.PillowWriter(fps=fps)

    print(f"  [动画] 生成中... ", end="", flush=True)
    anim.save(str(out_path), writer=writer)
    plt.close(fig)
    print(f"完成 → {out_path.resolve()}")


def _draw_state_legend(ax):
    """在地图右下角绘制AGV状态图例"""
    legend_items = [
        ("o", "white", "空载移动"),
        ("s", "white", "载货移动"),
        ("^", "#43A047", "装货"),
        ("v", "#FB8C00", "卸货"),
        ("D", "#FFD54F", "充电"),
        ("o", "#AAAAAA", "空闲"),
    ]

    x0, y0 = 0.98, 0.02
    dy = 0.025

    # 背景框
    ax.text(x0, y0 + dy * (len(legend_items) + 0.5), "状态图例",
            transform=ax.transAxes, fontsize=8, fontweight="bold",
            ha="right", va="bottom", color="#333333",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.85))

    for i, (marker, edge, label) in enumerate(legend_items):
        y = y0 + dy * (len(legend_items) - 1 - i)
        ax.plot(x0 - 0.08, y, marker=marker, markersize=7,
                color="#666666", markeredgecolor=edge, markeredgewidth=1,
                transform=ax.transAxes, clip_on=False)
        ax.text(x0 - 0.05, y, label, transform=ax.transAxes,
                fontsize=7, va="center", color="#333333")


def main():
    parser = argparse.ArgumentParser(description="AGV调度动画可视化")
    parser.add_argument("--output", default="output/animation.gif",
                        help="输出文件路径 (默认: output/animation.gif)")
    parser.add_argument("--fps", type=int, default=10, help="帧率 (默认: 10)")
    parser.add_argument("--format", default="gif", choices=["gif", "mp4"],
                        help="输出格式 (默认: gif)")
    parser.add_argument("--orders", type=int, default=40, help="订单数 (默认: 40)")
    parser.add_argument("--target-frames", type=int, default=None,
                        help="目标帧数 (默认: 自动)")
    args = parser.parse_args()

    from src.warehouse.maps.base import MapRegistry
    import src.warehouse.maps.medium_57x47  # noqa: F401
    from src.warehouse.wms.config import WarehouseConfig
    from main_simulation import run_single

    config = WarehouseConfig()
    print("=" * 50)
    print("  AGV 调度动画生成")
    print("=" * 50)

    result, wmap, _ = run_single(config, config.MAP_NAME, args.orders)
    print(f"  Makespan: {result.makespan}")

    create_animation(wmap, result, args.output, args.fps, args.format, args.target_frames)


if __name__ == "__main__":
    main()
