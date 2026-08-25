import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "evaluate_exactness_gate.py"


def write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def run_gate(
    tmp_path: Path,
    monitoring: dict,
    capture: dict,
    replay: dict,
    lifecycle: dict,
) -> tuple[subprocess.CompletedProcess[str], dict]:
    output = tmp_path / "gate.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--monitoring-check",
            str(write_json(tmp_path / "monitoring.json", monitoring)),
            "--capture-summary",
            str(write_json(tmp_path / "capture.json", capture)),
            "--deployment-replay",
            str(write_json(tmp_path / "replay.json", replay)),
            "--lifecycle-comparison",
            str(write_json(tmp_path / "lifecycle.json", lifecycle)),
            "--minimum-comparisons",
            "1",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    payload = (
        json.loads(output.read_text(encoding="utf-8"))
        if output.exists()
        else {}
    )
    return completed, payload


def test_gate_separates_deterministic_parity_from_broker_execution(tmp_path):
    completed, result = run_gate(
        tmp_path,
        monitoring={
            "preserved_non_overlapping_market_open_hours": 48.5,
            "preserved_complete_deployments": 10,
        },
        capture={
            "transaction_sequence_gaps": 0,
            "dropped_transactions": 0,
        },
        replay={
            "deployment": {"deterministic_match": True},
            "live_lifecycle": {"fill": 2, "stop_exit": 1},
            "tester_lifecycle": {"fill": 1, "stop_exit": 1},
            "next_cycle_start_delta_seconds": -20.0,
            "first_fill_differences": [
                {
                    "comment": "STR B1",
                    "price_delta": 0.1,
                    "time_delta_seconds": 0.2,
                }
            ],
        },
        lifecycle={
            "deterministic_match": True,
            "is_match": False,
            "execution_mismatch_count": 2,
        },
    )

    assert completed.returncode == 0, completed.stderr
    assert result["capture"]["pass"] is True
    assert result["deterministic_parity"]["pass"] is True
    assert result["execution_parity"]["pass"] is False
    assert result["ready_for_deterministic_replica"] is True
    assert result["ready_for_100_percent_trade_claim"] is False


def test_gate_blocks_claim_when_capture_or_decision_evidence_is_incomplete(
    tmp_path,
):
    completed, result = run_gate(
        tmp_path,
        monitoring={
            "preserved_non_overlapping_market_open_hours": 22.2,
            "preserved_complete_deployments": 5,
        },
        capture={
            "transaction_sequence_gaps": 1,
            "dropped_transactions": 0,
        },
        replay={
            "deployment": {"deterministic_match": False},
            "live_lifecycle": {},
            "tester_lifecycle": {},
            "next_cycle_start_delta_seconds": 0.0,
            "first_fill_differences": [],
        },
        lifecycle={
            "deterministic_match": False,
            "is_match": False,
            "execution_mismatch_count": 0,
        },
    )

    assert completed.returncode == 1
    assert result["capture"]["pass"] is False
    assert result["deterministic_parity"]["pass"] is False
    assert result["ready_for_deterministic_replica"] is False
    assert result["ready_for_100_percent_trade_claim"] is False
    assert {
        "market_open_hours",
        "complete_cycles",
        "transaction_sequence_gaps",
        "deployment_decisions",
        "lifecycle_decisions",
    }.issubset(result["blocking_reasons"])
