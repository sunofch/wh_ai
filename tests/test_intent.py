"""两层意图识别测试。"""
from unittest.mock import MagicMock, patch

from src.agents.state import AgentState


def test_general_reply_schema_has_kind_and_text():
    from src.agents.schemas import GeneralReply, DomainResult

    reply = GeneralReply(text="你好，我可以帮你查库存")
    assert isinstance(reply, DomainResult)
    assert reply.kind == "general_reply"
    assert reply.text == "你好，我可以帮你查库存"


def test_agent_state_has_category_and_reply_defaults():
    from src.agents.state import AgentState

    state = AgentState()
    assert state.category == ""
    assert state.reply == ""

    updated = state.with_updates(category="business", reply="hi")
    assert updated.category == "business"
    assert updated.reply == "hi"
    # 不可变：原对象不被改动
    assert state.category == ""


def _mock_intent_llm(category: str):
    """构造一个 .with_structured_output(...).invoke(...) 返回指定 category 的 LLM。"""
    from src.agents.intent import IntentDecision

    structured = MagicMock()
    structured.invoke.return_value = IntentDecision(category=category)
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    return llm


def test_classify_intent_returns_business():
    with patch("src.agents.intent._get_intent_llm", return_value=_mock_intent_llm("business")):
        from src.agents.intent import classify_intent
        assert classify_intent(AgentState(user_input="出库3个轴承")) == "business"


def test_classify_intent_returns_general():
    with patch("src.agents.intent._get_intent_llm", return_value=_mock_intent_llm("general")):
        from src.agents.intent import classify_intent
        assert classify_intent(AgentState(user_input="今天天气真好")) == "general"


def test_classify_intent_falls_back_to_business_on_error():
    broken = MagicMock()
    broken.with_structured_output.side_effect = RuntimeError("llm down")
    with patch("src.agents.intent._get_intent_llm", return_value=broken):
        from src.agents.intent import classify_intent
        assert classify_intent(AgentState(user_input="出库3个轴承")) == "business"


def test_classify_intent_image_only_is_business():
    # 纯图片输入默认 business，不调 LLM
    from src.agents.intent import classify_intent
    assert classify_intent(AgentState(image="/tmp/order.jpg")) == "business"
