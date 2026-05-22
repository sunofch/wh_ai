from unittest.mock import MagicMock, patch


def test_forecast_warning_agent_name_constant():
    from src.agents.forecast_warning_agent import AGENT_NAME

    assert AGENT_NAME == "forecast_warning_agent"


def test_get_forecast_warning_agent_passes_name_and_tool():
    with patch("src.agents.forecast_warning_agent.ChatOpenAI"), \
         patch("src.agents.forecast_warning_agent.create_react_agent") as mock_create:
        mock_create.return_value = MagicMock()

        from src.agents.forecast_warning_agent import get_forecast_warning_agent

        get_forecast_warning_agent.cache_clear()
        get_forecast_warning_agent()

        args, kwargs = mock_create.call_args
        tools = args[1]
        assert kwargs.get("name") == "forecast_warning_agent"
        assert any(getattr(tool, "name", "") == "analyze_inventory_risk" for tool in tools)


def test_analyze_inventory_risk_tool_returns_report_json():
    from src.agent_tools.forecast_warning_tool import analyze_inventory_risk

    result = analyze_inventory_risk.invoke({
        "part_name": "深沟球轴承",
        "model": "6208-2RS-C3-SKF",
        "current_stock": 5,
        "forecast": [10, 12, 8, 15],
    })

    assert '"risk_level": "critical"' in result
    assert '"recommended_restock_qty":' in result
    assert "深沟球轴承" in result
