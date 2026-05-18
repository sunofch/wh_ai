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
from src.agents.inventory_agent import get_inventory_agent
from src.common.config import config

_SUPERVISOR_PROMPT = """你是港口备件仓储系统的智能调度员。

根据用户请求，按以下规则路由：
- 领料、出库、入库、需要备件、零件申请、解析指令 → 先调用 instruction_agent 解析，再调用 inventory_agent 处理库存
- 仅查询库存数量/位置，不涉及工单 → 直接调用 inventory_agent
- 补货、创建工单、库存操作 → 直接调用 inventory_agent

注意：涉及出库/入库的完整流程必须先经过 instruction_agent 解析，再由 inventory_agent 执行库存操作。
"""


@lru_cache(maxsize=1)
def _get_supervisor_llm() -> ChatOpenAI:
    port = config.vllm_server.base_port + 1
    host = config.vllm_server.host
    return ChatOpenAI(
        base_url=f"http://{host}:{port}/v1",
        api_key="EMPTY",
        model=config.supervisor.model,
        temperature=0,
        max_tokens=config.supervisor.max_tokens,
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )


@lru_cache(maxsize=1)
def get_supervisor():
    """返回编译好的 Supervisor 多 Agent 图。"""
    builder = create_supervisor(
        agents=[get_instruction_agent(), get_inventory_agent()],
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
