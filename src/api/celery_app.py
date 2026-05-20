"""Celery 应用：定义异步 Agent 任务。

Worker 进程独立运行，从 Redis Broker 取任务 → supervisor_run() → 结果写回。
"""
from __future__ import annotations

import os

from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
REDIS_RESULT_URL = os.getenv("REDIS_RESULT_URL", "redis://localhost:6379/1")

celery_app = Celery(
    "warehouse",
    broker=REDIS_URL,
    backend=REDIS_RESULT_URL,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    result_expires=3600,
    task_acks_late=True,            # Worker 崩溃后任务重新入队
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,   # 每次只预取 1 个任务，避免 LLM 任务堆积
    task_routes={
        "warehouse.process_order": {"queue": "default"},
        "warehouse.process_order_urgent": {"queue": "urgent"},
    },
)

@celery_app.task(
    name="warehouse.process_order",
    bind=True,
    max_retries=2,
    default_retry_delay=5,
)
def process_order(
    self,
    text: str | None,
    image_base64: str | None,
    instruction_id: str,
) -> dict:
    """在 Worker 进程中执行完整三段式 Agent 流水线。

    返回值存入 Celery result backend（Redis db=1），
    同时将 WorkOrder JSON 推入 Redis List 供 scheduler_loop 批量调度。
    """
    import base64
    import json
    import os
    import tempfile

    import redis as _redis

    from src.agents.supervisor import run as supervisor_run

    redis_client = _redis.from_url(REDIS_URL)
    tmp_path: str | None = None

    try:
        if image_base64:
            img_bytes = base64.b64decode(image_base64)
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
                f.write(img_bytes)
                tmp_path = f.name

        order = supervisor_run(text=text, image=tmp_path)

        order_dict = {
            "order_id": order.order_id,
            "source": order.source,
            "priority": order.priority.value,
            "items": [
                {
                    "item_id": item.item_id,
                    "task_type": item.task_type.value,
                    "model": item.model,
                    "part_name": item.part_name,
                    "quantity": item.quantity,
                    "pick": item.resolved_pick,
                    "dest": item.resolved_dest,
                }
                for item in order.items
            ],
            "metadata": {
                **order.metadata,
                "instruction_id": instruction_id,
                "raw_text": text or "",
            },
        }

        # 推入 Redis List，供 scheduler_loop 批量调度
        from src.api.queue_manager import _dict_to_work_order, _redis_key_for_order
        queue_order = _dict_to_work_order(order_dict)
        key = _redis_key_for_order(queue_order) if queue_order else "warehouse:pending_orders"
        redis_client.rpush(key, json.dumps(order_dict, ensure_ascii=False))

        return {"status": "completed", "work_order": order_dict}

    except Exception as exc:
        raise self.retry(exc=exc, countdown=5) from exc

    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        redis_client.close()


@celery_app.task(
    name="warehouse.process_order_urgent",
    bind=True,
    max_retries=2,
    default_retry_delay=5,
)
def process_order_urgent(
    self,
    text: str | None,
    image_base64: str | None,
    instruction_id: str,
) -> dict:
    """紧急订单专用任务，路由到 urgent 队列，Worker 优先消费。"""
    return process_order.run(text, image_base64, instruction_id)
