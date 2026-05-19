#!/usr/bin/env python3
"""Celery Worker 启动入口。

启动方式：
    python main_worker.py              # 默认并发数（CELERY_WORKER_CONCURRENCY）
    python main_worker.py --concurrency 4
    python main_worker.py --queues urgent,default

多实例（提高吞吐）：
    python main_worker.py &
    python main_worker.py &
"""
import argparse
import logging
import os

# 强制 HuggingFace 离线模式，使用本地缓存，不尝试连接外网
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_DATASETS_OFFLINE", "1")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="AGV Warehouse Celery Worker")
    parser.add_argument(
        "--concurrency",
        type=int,
        default=int(os.getenv("CELERY_WORKER_CONCURRENCY", "2")),
        help="同时处理的任务数（默认 2，受 GPU 显存限制）",
    )
    parser.add_argument(
        "--queues",
        default="urgent,default",
        help="监听的队列，逗号分隔，靠前的优先级更高",
    )
    parser.add_argument(
        "--loglevel",
        default="info",
        choices=["debug", "info", "warning", "error"],
    )
    args = parser.parse_args()

    from src.api.celery_app import celery_app

    logger.info(
        "启动 Celery Worker: concurrency=%d, queues=%s",
        args.concurrency, args.queues,
    )

    celery_app.worker_main(
        argv=[
            "worker",
            f"--concurrency={args.concurrency}",
            f"--queues={args.queues}",
            f"--loglevel={args.loglevel}",
            "--without-heartbeat",   # 减少 Redis 连接数
            "--without-gossip",
        ]
    )


if __name__ == "__main__":
    main()
