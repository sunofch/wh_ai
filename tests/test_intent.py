"""两层意图识别测试。"""
from unittest.mock import MagicMock, patch

from src.agents.state import AgentState


def test_general_reply_schema_has_kind_and_text():
    from src.agents.schemas import GeneralReply, DomainResult

    reply = GeneralReply(text="你好，我可以帮你查库存")
    assert isinstance(reply, DomainResult)
    assert reply.kind == "general_reply"
    assert reply.text == "你好，我可以帮你查库存"
