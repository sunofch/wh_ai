#!/usr/bin/env python3
"""批量多品类调度测试脚本

流程：
  阶段1  批量提交 10 条指令（立即返回 instruction_id）
  阶段2  轮询 /agent-result/{id}，等待每条 Agent 处理完成
  阶段3  轮询 /status，收集所有批次 run_id（队列清空后确认无新批次才退出）
  阶段4  逐批次打印调度结果；指定 --animation 时额外下载动画 GIF

说明：
  10 条指令可能因 LLM 处理速度分成多个批次调度，阶段3 会收集所有批次结果。
  多批次时动画文件自动加 _batch1/_batch2 后缀。

用法:
    python test_api_batch.py                          # 只打印结果
    python test_api_batch.py --animation              # 打印结果并下载动画
    python test_api_batch.py --base http://localhost:8000
    python test_api_batch.py --animation --output my_schedule.gif
"""
import argparse
import time

import requests

INSTRUCTIONS = [
    "出库2个深沟球轴承，型号6208-2RS-C3-SKF",
    "出库1台三相异步电动机，型号Y160M-4-11kW-ABB",
    "出库1桶抗磨液压油，型号L-HM46-200L-KUNLUN",
    "出库1个ABS工程安全帽，型号VGard-E2-WHT-MSA",
    "出库1把液压力矩扳手，型号HTW-3400Nm-ENERPAC",
    "出库1个弹性爪型联轴器，型号ROTEX-48-98ShA-KTR",
    "出库1台变频调速器，型号ACS580-039A-ABB",
    "出库1个高压液压油滤芯，型号HF-250x20Q-HYDAC",
    "出库1副防冲击护目镜，型号VMaxx-OTG-CLR-UVEX",
    "出库1台数字钳形万用表，型号F325-600V-FLUKE",
]


def submit_instructions(base: str) -> list[dict]:
    """阶段1：批量提交指令，收集 instruction_id。"""
    print("=== 阶段1：提交指令 ===")
    submitted = []
    for text in INSTRUCTIONS:
        r = requests.post(f"{base}/instructions", json={"text": text}, timeout=10)
        r.raise_for_status()
        d = r.json()
        submitted.append({"instruction_id": d["instruction_id"], "text": text})
        print(f"  已入队  id={d['instruction_id'][:8]}...  [{text[:20]}]")
    print(f"\n  共提交 {len(submitted)} 条指令\n")
    return submitted


def wait_for_agents(base: str, submitted: list[dict], poll_interval: int) -> list[dict]:
    """阶段2：轮询 /agent-result/{id}，等待每条 Agent 处理完成。"""
    print("=== 阶段2：等待 Agent 处理 ===")
    completed = {}
    pending = {s["instruction_id"]: s["text"] for s in submitted}

    while pending:
        done_ids = []
        for iid, text in pending.items():
            r = requests.get(f"{base}/agent-result/{iid}", timeout=10)
            r.raise_for_status()
            d = r.json()

            if d["status"] == "completed":
                wo = d.get("work_order") or {}
                items = wo.get("items", [])
                item = items[0] if items else {}
                print(
                    f"  ✓ [{iid[:8]}]"
                    f"  {item.get('part_name', '-')}"
                    f"  型号={item.get('model', '-')}"
                    f"  数量={item.get('quantity', '-')}"
                    f"  取货={item.get('pick', '-')}"
                )
                completed[iid] = d
                done_ids.append(iid)

            elif d["status"] == "failed":
                print(f"  ✗ [{iid[:8]}] 失败: {d.get('error', '未知错误')}")
                done_ids.append(iid)

        for iid in done_ids:
            pending.pop(iid)

        if pending:
            print(f"  等待中... 剩余 {len(pending)} 条")
            time.sleep(poll_interval)

    print(f"\n  Agent 处理完成: {len(completed)}/{len(submitted)} 条成功\n")
    return list(completed.values())


def wait_for_all_schedules(
    base: str, prev_run_id: str | None, poll_interval: int, idle_rounds: int = 3
) -> list[str]:
    """阶段3：收集本次提交触发的所有批次 run_id。

    退出条件：队列为空，且连续 idle_rounds 轮没有出现新的 run_id。
    """
    print("=== 阶段3：等待批量调度（Simulator）===")

    collected: list[str] = []
    seen: set[str] = {prev_run_id} if prev_run_id else set()
    idle = 0

    while True:
        status = requests.get(f"{base}/status", timeout=5).json()
        queue_size = status["queue_size"]
        sched_status = status["scheduler_status"]
        run_id = status.get("last_run_id")

        # 发现新 run_id，记录并重置空闲计数
        if run_id and run_id not in seen:
            seen.add(run_id)
            collected.append(run_id)
            idle = 0
            print(f"  ✓ 新批次完成 run_id={run_id[:8]}... | 队列剩余: {queue_size} 条")
        else:
            print(f"  队列: {queue_size} 条 | 调度状态: {sched_status}")

        # 队列清空后，等待若干轮确认无新批次
        if queue_size == 0 and collected:
            idle += 1
            if idle >= idle_rounds:
                print(f"\n  全部批次完成，共 {len(collected)} 批\n")
                return collected

        time.sleep(poll_interval)


def print_result(base: str, run_id: str, batch_index: int) -> None:
    """打印单批次调度结果。"""
    print(f"\n=== 批次 {batch_index} 结果（run_id={run_id[:8]}...）===")
    result = requests.get(f"{base}/result/{run_id}", timeout=10).json()
    print(f"  run_id      : {result['run_id']}")
    print(f"  工单数       : {result['order_count']}")
    print(f"  makespan    : {result['makespan']} 步")
    print(f"  总移动距离   : {result['total_distance']}")
    print(f"  AGV 利用率  : {result['agv_utilization']:.1%}")
    print(f"  规划耗时     : {result['planning_time']:.2f}s")
    if result.get("instructions"):
        print("  指令列表:")
        for inst in result["instructions"]:
            print(f"    - {inst}")


def download_animation(base: str, run_id: str, output: str, batch_index: int) -> None:
    """下载单批次调度动画。"""
    print(f"\n=== 下载动画（批次 {batch_index}）===")
    gif = requests.get(f"{base}/result/{run_id}/animation", timeout=30)
    gif.raise_for_status()
    with open(output, "wb") as f:
        f.write(gif.content)
    print(f"  动画已保存 → {output}")


def main(base: str, output: str, poll_interval: int, animation: bool) -> None:
    prev_run_id = requests.get(f"{base}/status", timeout=5).json().get("last_run_id")
    submitted = submit_instructions(base)
    wait_for_agents(base, submitted, poll_interval)
    run_ids = wait_for_all_schedules(base, prev_run_id, poll_interval)

    stem, ext = output.rsplit(".", 1) if "." in output else (output, "gif")
    for i, run_id in enumerate(run_ids, start=1):
        print_result(base, run_id, batch_index=i)
        if animation:
            out_path = f"{stem}_batch{i}.{ext}" if len(run_ids) > 1 else output
            download_animation(base, run_id, out_path, batch_index=i)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="批量多品类调度测试")
    parser.add_argument("--base", default="http://localhost:8000", help="API 地址")
    parser.add_argument("--output", default="schedule.gif", help="动画输出文件名")
    parser.add_argument("--interval", type=int, default=3, help="轮询间隔（秒）")
    parser.add_argument("--animation", action="store_true", help="下载调度动画 GIF")
    args = parser.parse_args()

    main(args.base, args.output, args.interval, args.animation)
