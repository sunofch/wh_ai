def test_pipeline_marks_low_stock_critical_and_recommends_restock():
    from src.optimization.pipeline import analyze_inventory_optimization

    result = analyze_inventory_optimization(
        part_name="深沟球轴承",
        model="6208-2RS-C3-SKF",
        current_stock=5,
        forecast=[10, 12, 8, 15],
    )

    assert result.risk_level == "critical"
    assert result.recommended_restock_qty > 0
    assert result.forecast_total == 45
    assert "深沟球轴承" in result.report
    assert "critical" in result.report


def test_pipeline_marks_sufficient_stock_normal_without_restock():
    from src.optimization.pipeline import analyze_inventory_optimization

    result = analyze_inventory_optimization(
        part_name="深沟球轴承",
        model="6208-2RS-C3-SKF",
        current_stock=100,
        forecast=[5, 5, 5, 5],
    )

    assert result.risk_level == "normal"
    assert result.recommended_restock_qty == 0
