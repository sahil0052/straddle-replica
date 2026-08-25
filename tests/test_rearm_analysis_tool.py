import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "analyze_live_rearms.py"


def test_tool_excludes_deployments_and_checks_minimum_rearm_delay(tmp_path):
    session = tmp_path / "capture" / "session"
    session.mkdir(parents=True)
    orders = []
    for level in range(1, 31):
        for side in ("B", "S"):
            orders.append(
                {
                    "ticket": 1_000 + len(orders),
                    "state": 0,
                    "type": 4 if side == "B" else 5,
                    "time_setup_msc": 2_000 + len(orders) * 100,
                    "time_done_msc": 0,
                    "volume_initial": (
                        0.01 if level <= 10
                        else 0.06 if level <= 20
                        else 0.15
                    ),
                    "price_open": 100 + level if side == "B" else 100 - level,
                    "comment": f"STR {side}{level}",
                }
            )
    orders.append(
        {
            "ticket": 2_000,
            "state": 0,
            "type": 4,
            "time_setup_msc": 21_113,
            "time_done_msc": 0,
            "volume_initial": 0.01,
            "price_open": 101.0,
            "comment": "STR B1",
        }
    )
    deals = [
        {
            "ticket": 10,
            "time_msc": 500,
            "entry": 0,
            "reason": 3,
            "position_id": 9,
            "comment": "STR B1",
        },
        {
            "ticket": 11,
            "time_msc": 1_000,
            "entry": 1,
            "reason": 4,
            "position_id": 9,
            "comment": "[sl 101.20]",
        },
    ]
    (session / "history-orders-1.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in orders),
        encoding="utf-8",
    )
    (session / "history-deals-1.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in deals),
        encoding="utf-8",
    )
    output = tmp_path / "rearms.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--capture-root",
            str(tmp_path / "capture"),
            "--minimum-delay-ms",
            "20000",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["complete_deployment_count"] == 1
    assert result["rearm_count"] == 1
    assert result["rearm_delay_ms"]["min"] == 20_113
    assert result["minimum_delay_gate"] == {
        "minimum_delay_ms": 20_000,
        "events_below_minimum": 0,
        "pass": True,
    }
