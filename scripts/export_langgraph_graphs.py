# 用法：
#   1. 导出全部当前 LangGraph 图为 Mermaid 文件：
#      python scripts/export_langgraph_graphs.py
#
#   2. 查看可导出的图名称：
#      python scripts/export_langgraph_graphs.py --list
#
#   3. 只导出某一个图：
#      python scripts/export_langgraph_graphs.py --graph inventory_agent
#
#   4. 导出到指定目录：
#      python scripts/export_langgraph_graphs.py --output-dir outputs/langgraph
#
#   5. 同时尝试导出 PNG：
#      python scripts/export_langgraph_graphs.py --png
#
#   6. 导出 LangGraph 展开后的 xray 图（如果当前版本支持）：
#      python scripts/export_langgraph_graphs.py --xray
#
#   7. 指定图方向（默认 TD 竖向；LR 为横向）：
#      python scripts/export_langgraph_graphs.py --direction LR --png
#
# 默认输出目录：outputs/langgraph/
# 默认导出的图：instruction_agent、inventory_agent
from __future__ import annotations

import argparse
import sys
import types
from collections.abc import Callable
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _install_lightweight_package(name: str, path: Path) -> None:
    """Let submodules import without executing heavyweight package __init__ files."""
    if name in sys.modules:
        return

    module = types.ModuleType(name)
    module.__path__ = [str(path)]  # type: ignore[attr-defined]
    module.__package__ = name
    sys.modules[name] = module


def _avoid_package_import_side_effects() -> None:
    _install_lightweight_package("src", PROJECT_ROOT / "src")
    _install_lightweight_package("src.agents", PROJECT_ROOT / "src" / "agents")
    _install_lightweight_package("src.common", PROJECT_ROOT / "src" / "common")
    _install_lightweight_package("src.warehouse", PROJECT_ROOT / "src" / "warehouse")


GraphFactory = Callable[[], Any]


def _get_instruction_graph() -> Any:
    _avoid_package_import_side_effects()
    from src.agents.instruction.agent import get_instruction_agent

    return get_instruction_agent()


def _get_inventory_graph() -> Any:
    _avoid_package_import_side_effects()
    from src.agents.inventory.agent import get_inventory_agent

    pipeline = get_inventory_agent()
    graph = getattr(pipeline, "_graph", None)
    if graph is None:
        raise RuntimeError("inventory_agent pipeline does not expose a compiled _graph")
    return graph


GRAPH_FACTORIES: dict[str, GraphFactory] = {
    "instruction_agent": _get_instruction_graph,
    "inventory_agent": _get_inventory_graph,
}


def _drawable_graph(compiled_graph: Any, *, xray: bool) -> Any:
    if not hasattr(compiled_graph, "get_graph"):
        raise TypeError(f"{type(compiled_graph).__name__} does not provide get_graph()")

    try:
        return compiled_graph.get_graph(xray=xray)
    except TypeError:
        return compiled_graph.get_graph()


def _set_mermaid_direction(mermaid: str, direction: str) -> str:
    return mermaid.replace("graph TD;", f"graph {direction};", 1)


def export_graph(
    name: str,
    factory: GraphFactory,
    output_dir: Path,
    *,
    write_png: bool,
    xray: bool,
    direction: str,
) -> list[Path]:
    compiled_graph = factory()
    drawable_graph = _drawable_graph(compiled_graph, xray=xray)

    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    mermaid = _set_mermaid_direction(drawable_graph.draw_mermaid(), direction)

    mermaid_path = output_dir / f"{name}.mmd"
    mermaid_path.write_text(mermaid, encoding="utf-8")
    written.append(mermaid_path)

    if write_png:
        from langchain_core.runnables.graph_mermaid import draw_mermaid_png

        png_path = output_dir / f"{name}.png"
        try:
            png_path.write_bytes(draw_mermaid_png(mermaid))
        except Exception as exc:  # noqa: BLE001 - keep Mermaid export usable if PNG deps fail.
            print(f"[warn] failed to export PNG for {name}: {exc}", file=sys.stderr)
        else:
            written.append(png_path)

    return written


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export current LangGraph graphs to Mermaid .mmd files.",
    )
    parser.add_argument(
        "--graph",
        choices=sorted(GRAPH_FACTORIES),
        action="append",
        help="Graph name to export. Repeat to export multiple graphs. Defaults to all.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "langgraph",
        help="Directory for exported graph files.",
    )
    parser.add_argument(
        "--png",
        action="store_true",
        help="Also try to export Mermaid-rendered PNG files.",
    )
    parser.add_argument(
        "--xray",
        action="store_true",
        help="Ask LangGraph for the expanded xray graph where supported.",
    )
    parser.add_argument(
        "--direction",
        choices=("TD", "LR", "BT", "RL"),
        default="TD",
        help="Mermaid graph direction. Defaults to TD for top-down output.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available graph names and exit.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.list:
        for graph_name in sorted(GRAPH_FACTORIES):
            print(graph_name)
        return 0

    graph_names = args.graph or sorted(GRAPH_FACTORIES)
    for graph_name in graph_names:
        try:
            written = export_graph(
                graph_name,
                GRAPH_FACTORIES[graph_name],
                args.output_dir,
                write_png=args.png,
                xray=args.xray,
                direction=args.direction,
            )
        except ModuleNotFoundError as exc:
            print(
                f"[error] missing dependency while exporting {graph_name}: {exc.name}. "
                "Install the project requirements first.",
                file=sys.stderr,
            )
            return 1
        for path in written:
            print(path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
