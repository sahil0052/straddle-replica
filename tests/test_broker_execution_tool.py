import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "analyze_broker_stop_serialization.py"
UTC = timezone.utc


def test_tool_writes_broker_stop_serialization_summary(tmp_path):
    start = datetime(2026, 8, 3, 14, 20, 17, tzinfo=UTC)
    analysis_path = tmp_path / "analysis.json"
    analysis_path.write_text(
        json.dumps(
            {
                "stops": {
                    "change_rows": [
                        {
                            "server_time": "2026.08.03 14:20:17",
                            "ticket": ticket,
                            "new_sl": 4050.23,
                            "previous_sl": 4050.26,
                        }
                        for ticket in (101, 102, 103)
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    session = tmp_path / "capture" / "session"
    session.mkdir(parents=True)
    deal_path = session / "history-deals-20260803-14.jsonl"
    deals = []
    for ticket, seconds in ((1, 6), (2, 26), (3, 46)):
        exit_time = start + timedelta(seconds=seconds)
        deals.append(
            {
                "ticket": ticket,
                "position_id": 100 + ticket,
                "symbol": "XAUUSD",
                "entry": 1,
                "reason": 4,
                "comment": "[sl 4050.23]",
                "time_msc": int(exit_time.timestamp() * 1000),
            }
        )
    deal_path.write_text(
        "\n".join(json.dumps(item) for item in deals) + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "result.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--capture-root",
            str(tmp_path / "capture"),
            "--analysis",
            str(analysis_path),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["serialized_run_count"] == 1
    assert result["serialized_position_count"] == 3
    assert result["all_stops_preassigned_run_count"] == 1
    assert result["ascending_ticket_run_count"] == 1
