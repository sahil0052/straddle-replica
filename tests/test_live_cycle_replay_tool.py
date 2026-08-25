import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "compare_live_cycle_replay.py"


def test_tool_separates_deployment_decisions_from_lifecycle_execution(tmp_path):
    analysis = tmp_path / "analysis.json"
    analysis.write_text(
        json.dumps(
            {
                "deployments": {
                    "complete": [
                        {
                            "start_server_time": "2026.08.03 10:00:00",
                            "order_count": 2,
                            "sequence_exact": True,
                            "grid": {
                                "anchor": 100.0,
                                "normalized_step": 1.0,
                            },
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    session = tmp_path / "capture" / "session"
    session.mkdir(parents=True)
    (session / "history-deals.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "ticket": 1,
                        "position_id": 10,
                        "symbol": "XAUUSD",
                        "entry": 0,
                        "reason": 3,
                        "comment": "STR B1",
                        "time_msc": 1785751201000,
                        "price": 101.1,
                        "volume": 0.01,
                    }
                ),
                json.dumps(
                    {
                        "ticket": 2,
                        "position_id": 10,
                        "symbol": "XAUUSD",
                        "entry": 1,
                        "reason": 4,
                        "comment": "[sl 101.20]",
                        "time_msc": 1785751202000,
                        "price": 101.2,
                        "volume": 0.01,
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    telemetry = tmp_path / "telemetry.csv"
    telemetry.write_text(
        "time,kind,comment,side,volume,price,state,level,ticket\n"
        "2026-08-03T10:00:00Z,cycle_start,,,0,100.00,CYCLE_DEPLOYING,,0\n"
        "2026-08-03T10:00:00Z,pending,STR B1,buy,0.01,101.00,"
        "CYCLE_DEPLOYING,STR B1,2\n"
        "2026-08-03T10:00:00Z,pending,STR S1,sell,0.01,99.00,"
        "CYCLE_DEPLOYING,STR S1,3\n"
        "2026-08-03T10:00:01Z,fill,STR B1,buy,0.01,101.00,"
        "CYCLE_RUNNING,STR B1,2\n"
        "2026-08-03T10:00:03Z,cycle_start,,,0,102.00,CYCLE_DEPLOYING,,0\n",
        encoding="utf-8",
    )
    output = tmp_path / "comparison.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--analysis",
            str(analysis),
            "--capture-root",
            str(tmp_path / "capture"),
            "--telemetry",
            str(telemetry),
            "--live-start",
            "2026-08-03T10:00:00+00:00",
            "--live-next-start",
            "2026-08-03T10:00:03+00:00",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["deployment"]["deterministic_match"] is True
    assert result["deployment"]["pending_count"] == {
        "expected": 2,
        "actual": 2,
    }
    assert result["live_lifecycle"]["fill"] == 1
    assert result["live_lifecycle"]["stop_exit"] == 1
    assert result["tester_lifecycle"]["fill"] == 1
    assert result["next_cycle_start_delta_seconds"] == 0.0
