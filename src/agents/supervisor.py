"""Supervisor / Router Agent：意图分类 + 路由到专化 Agent。

当前挂载的子 Agent：
  - instruction_agent（Agent 1：领料解析）

后续扩展只需在 _AGENTS 列表中 append 新 Agent，
并在 _SUPERVISOR_PROMPT 中补充对应路由说明。
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from langchain_openai import ChatOpenAI
from langgraph_supervisor import create_supervisor

from src.agents.instruction_agent import get_instruction_agent
from src.common.config import config

_SUPERVISOR_PROMPT = """你是港口备件仓储系统的智能调度员。

根据用户请求，将任务路由到对应的专化 Agent：
- 领料、出库、入库、需要备件、零件申请、解析指令 → instruction_agent

当前可用 Agent 只有 instruction_agent，所有仓储请求均路由给它。
"""


@lru_cache(maxsize=1)
def _get_supervisor_llm() -> ChatOpenAI:
    port = config.vllm_server.base_port + 1
    host = config.vllm_server.host
    return ChatOpenAI(
        base_url=f"http://{host}:{port}/v1",
        api_key="EMPTY",
        model=config.vlm35.model,
        temperature=0,
        max_tokens=512,
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )


@lru_cache(maxsize=1)
def get_supervisor():
    """返回编译好的 Supervisor 多 Agent 图。"""
    builder = create_supervisor(
        agents=[get_instruction_agent()],
        model=_get_supervisor_llm(),
        prompt=_SUPERVISOR_PROMPT,
    )
    return builder.compile()


def run(
    text: str | None = None,
    image: str | None = None,
    verbose: bool = False,
):
    """Supervisor 主入口，统一替代 src.agent.agent.run_agent()。"""
    from src.agent.agent import _assemble_work_order, _print_agent_messages

    content: list[dict[str, Any]] = []
    if image:
        import base64
        from pathlib import Path
        img_b64 = base64.b64encode(Path(image).read_bytes()).decode()
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
        })
    if text:
        content.append({"type": "text", "text": text})
    if not content:
        content = [{"type": "text", "text": "无有效输入"}]

    app = get_supervisor()
    result = app.invoke({"messages": [{"role": "user", "content": content}]})

    if verbose:
        _print_agent_messages(result.get("messages", []))

    return _assemble_work_order(result)
