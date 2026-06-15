from __future__ import annotations

import json


def print_agent_messages(messages: list) -> None:
    """将 Agent 消息链格式化输出，便于观测推理过程。"""
    from langchain_core.messages import AIMessage, ToolMessage, HumanMessage

    print(f"\n{'═' * 50}")
    print("  Agent 推理过程")
    print(f"{'═' * 50}")
    for msg in messages:
        if isinstance(msg, HumanMessage):
            continue
        if isinstance(msg, AIMessage):
            tool_calls = getattr(msg, "tool_calls", [])
            if tool_calls:
                print("\n[LLM → 调用工具]")
                for tc in tool_calls:
                    print(f"  工具: {tc['name']}")
                    print(f"  参数: {json.dumps(tc['args'], ensure_ascii=False)}")
            else:
                print("\n[LLM → 最终输出]")
                print(f"  {msg.content}")
        elif isinstance(msg, ToolMessage):
            print(f"\n[工具结果] {getattr(msg, 'name', '')}")
            try:
                parsed = json.loads(msg.content)
                print(f"  {json.dumps(parsed, ensure_ascii=False, indent=2)}")
            except (json.JSONDecodeError, TypeError):
                print(f"  {msg.content}")
    print(f"{'═' * 50}\n")
