#!/usr/bin/env python3
"""批量多品类调度测试脚本

使用数据库真实零件名称和型号，提交 10 条指令触发批量调度，
等待调度完成后打印结果并下载动画 GIF。

用法:
    python test_api_batch.py
    python test_api_batch.py --base http://localhost:8000
    python test_api_batch.py --output my_schedule.gif
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


def main(base: str, output: str, poll_interval: int = 3):
    print("=== 提交 10 条指令 ===")
    for text in INSTRUCTIONS:
        r = requests.post(f"{base}/instructions", json={"text": text})
        r.raise_for_status()
        d = r.json()
        print(
            f"  [{d['parsed']['part_name']}]"
            f"  位置={d['resolved_location'] or '未命中'}"
            f"  端口={d['target_port'] or '-'}"
        )

    print("\n=== 等待调度完成 ===")
    while True:
        status = requests.get(f"{base}/status").json()
        print(
            f"  队列: {status['queue_size']} 条"
            f" | 调度状态: {status['scheduler_status']}"
        )
        if status["queue_size"] == 0 and status["last_run_id"]:
            run_id = status["last_run_id"]
            break
        time.sleep(poll_interval)

    print("\n=== 调度结果 ===")
    result = requests.get(f"{base}/result/{run_id}").json()
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

    print("\n=== 下载动画 ===")
    gif = requests.get(f"{base}/result/{run_id}/animation")
    gif.raise_for_status()
    with open(output, "wb") as f:
        f.write(gif.content)
    print(f"  动画已保存 → {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="批量多品类调度测试")
    parser.add_argument("--base", default="http://localhost:8000", help="API 地址")
    parser.add_argument("--output", default="schedule.gif", help="动画输出文件名")
    parser.add_argument("--interval", type=int, default=3, help="轮询间隔（秒）")
    args = parser.parse_args()

    main(args.base, args.output, args.interval)
