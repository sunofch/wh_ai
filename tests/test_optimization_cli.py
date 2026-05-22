import json
import subprocess
import sys


def test_optimization_cli_outputs_prediction_report_json():
    proc = subprocess.run(
        [
            sys.executable,
            "scripts/test_inventory_optimization.py",
            "--part-name",
            "深沟球轴承",
            "--model",
            "6208-2RS-C3-SKF",
            "--current-stock",
            "5",
            "--forecast",
            "10,12,8,15",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    data = json.loads(proc.stdout)
    assert data["risk_level"] == "critical"
    assert data["recommended_restock_qty"] > 0
    assert "深沟球轴承" in data["report"]
