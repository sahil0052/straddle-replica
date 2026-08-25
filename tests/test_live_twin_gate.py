from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys

from straddle_replica.live_twin_gate import evaluate_live_twin_gate


UTC = timezone.utc
ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "evaluate_live_twin_gate.py"


def reports(
    statuses: list[str],
    *,
    build_id: str = "build-1",
    certification_started_utc: datetime | None = None,
) -> list[dict]:
    start = datetime(2026, 8, 4, 0, 0, tzinfo=UTC)
    certification_start = certification_started_utc or (
        start - timedelta(hours=60)
    )
    return [
        {
            "status": status,
            "cycle_id": f"cycle-{index}",
            "build_id": build_id,
            "certification_started_utc": certification_start.isoformat(),
            "generated_utc": (
                start + timedelta(hours=index)
            ).isoformat(),
        }
        for index, status in enumerate(statuses, start=1)
    ]


def test_gate_passes_twenty_consecutive_cycles_and_48_hours() -> None:
    result = evaluate_live_twin_gate(
        reports=reports(["PASS"] * 20),
        market_open_hours=48.0,
        sequence_gaps=0,
        dropped_transactions=0,
        account_terms_match=True,
        request_evidence_available=True,
    )

    assert result["qualification_status"] == "FORMAL_PASS"
    assert result["ready_for_formal_fidelity"] is True
    assert result["required_clean_cycles"] == 20
    assert result["consecutive_clean_cycles"] == 20
    assert result["blocking_reasons"] == []


def test_observer_evidence_can_pass_best_effort_but_not_formal() -> None:
    result = evaluate_live_twin_gate(
        reports=reports(["PASS"] * 20),
        market_open_hours=48.0,
        sequence_gaps=0,
        dropped_transactions=0,
        account_terms_match=False,
        request_evidence_available=False,
    )

    assert result["qualification_status"] == "BEST_EFFORT_PASS"
    assert result["ready_for_best_effort_candidate"] is True
    assert result["ready_for_formal_fidelity"] is False


def test_gate_counts_only_passes_after_latest_failure() -> None:
    result = evaluate_live_twin_gate(
        reports=reports(["PASS"] * 7 + ["FAIL"] + ["PASS"] * 3),
        market_open_hours=60.0,
        sequence_gaps=0,
        dropped_transactions=0,
        account_terms_match=True,
    )

    assert result["qualification_status"] == "BLOCKED"
    assert result["ready_for_formal_fidelity"] is False
    assert result["consecutive_clean_cycles"] == 3
    assert "consecutive_clean_cycles" in result["blocking_reasons"]
    assert result["reset_required"] is True
    assert "cycle_mismatch" in result["reset_reasons"]


def test_gate_fails_closed_for_account_or_capture_mismatch() -> None:
    result = evaluate_live_twin_gate(
        reports=reports(["PASS"] * 20),
        market_open_hours=47.9,
        sequence_gaps=1,
        dropped_transactions=2,
        account_terms_match=False,
    )

    assert result["qualification_status"] == "BLOCKED"
    assert {
        "market_open_hours",
        "sequence_gaps",
        "dropped_transactions",
    }.issubset(result["blocking_reasons"])
    assert "account_terms" in result["formal_blocking_reasons"]


def test_gate_resets_when_build_changes() -> None:
    prior = reports(["PASS"] * 20, build_id="build-1")
    current = reports(["PASS"] * 2, build_id="build-2")

    result = evaluate_live_twin_gate(
        reports=[*prior, *current],
        market_open_hours=48.0,
        sequence_gaps=0,
        dropped_transactions=0,
        account_terms_match=True,
    )

    assert result["active_build_id"] == "build-2"
    assert result["consecutive_clean_cycles"] == 2
    assert result["qualification_status"] == "BLOCKED"


def test_gate_counts_repeated_reports_for_one_cycle_only_once() -> None:
    cycle = reports(["PASS"])[0]
    repeated = [
        {
            **cycle,
            "generated_utc": (
                datetime.fromisoformat(cycle["generated_utc"])
                + timedelta(minutes=index)
            ).isoformat(),
        }
        for index in range(10)
    ]

    result = evaluate_live_twin_gate(
        reports=repeated,
        market_open_hours=48.0,
        sequence_gaps=0,
        dropped_transactions=0,
        account_terms_match=True,
    )

    assert result["consecutive_clean_cycles"] == 1
    assert result["qualification_status"] == "BLOCKED"


def test_gate_reverted_build_still_starts_a_new_certification_run() -> None:
    first_start = datetime(2026, 8, 1, tzinfo=UTC)
    second_start = datetime(2026, 8, 3, tzinfo=UTC)
    reverted_start = datetime(2026, 8, 4, tzinfo=UTC)
    prior = reports(
        ["PASS"] * 20,
        build_id="build-1",
        certification_started_utc=first_start,
    )
    changed = reports(
        ["PASS"],
        build_id="build-2",
        certification_started_utc=second_start,
    )
    reverted = reports(
        ["PASS"],
        build_id="build-1",
        certification_started_utc=reverted_start,
    )
    reverted[0]["generated_utc"] = datetime(
        2026, 8, 4, 12, tzinfo=UTC
    ).isoformat()

    result = evaluate_live_twin_gate(
        reports=[*prior, *changed, *reverted],
        market_open_hours=48.0,
        sequence_gaps=0,
        dropped_transactions=0,
        account_terms_match=True,
        evaluated_utc=datetime(2026, 8, 4, 13, tzinfo=UTC),
    )

    assert result["consecutive_clean_cycles"] == 1
    assert result["active_build_id"] == "build-1"
    assert result["certification_started_utc"] == reverted_start.isoformat()


def test_gate_cannot_reuse_hours_from_before_certification_start() -> None:
    certification_start = datetime(2026, 8, 4, 10, tzinfo=UTC)
    current = reports(
        ["PASS"] * 20,
        certification_started_utc=certification_start,
    )

    result = evaluate_live_twin_gate(
        reports=current,
        market_open_hours=48.0,
        sequence_gaps=0,
        dropped_transactions=0,
        account_terms_match=True,
        evaluated_utc=datetime(2026, 8, 4, 12, tzinfo=UTC),
    )

    assert result["market_open_hours"]["effective"] == 2.0
    assert "market_open_hours" in result["blocking_reasons"]


def test_gate_blocks_operational_capture_failures() -> None:
    result = evaluate_live_twin_gate(
        reports=reports(["PASS"] * 20),
        market_open_hours=48.0,
        sequence_gaps=0,
        duplicate_sequences=1,
        dropped_transactions=0,
        session_restarts=1,
        operational_guard_failures=1,
        request_evidence_available=False,
        account_terms_match=True,
    )

    assert {
        "duplicate_sequences",
        "session_restarts",
        "operational_guard_failures",
    }.issubset(result["blocking_reasons"])
    assert (
        "direct_request_evidence"
        in result["formal_blocking_reasons"]
    )
    assert result["reset_required"] is True


def test_incomplete_active_cycle_does_not_request_gate_reset() -> None:
    incomplete = reports(["INVALID"])
    incomplete[0]["reason"] = "Cycle lifecycle is not complete"

    result = evaluate_live_twin_gate(
        reports=incomplete,
        market_open_hours=0.0,
        sequence_gaps=0,
        dropped_transactions=0,
        account_terms_match=True,
    )

    assert result["reset_required"] is False
    assert result["reset_reasons"] == []


def test_incomplete_older_cycle_requests_reset_after_newer_cycle() -> None:
    current = reports(["INVALID", *(["PASS"] * 20)])
    current[0]["reason"] = "Cycle lifecycle is not complete"

    result = evaluate_live_twin_gate(
        reports=current,
        market_open_hours=48.0,
        sequence_gaps=0,
        dropped_transactions=0,
        account_terms_match=True,
    )

    assert result["reset_required"] is True
    assert result["qualification_status"] == "BLOCKED"
    assert "cycle_invalid" in result["reset_reasons"]


def test_gate_cli_writes_machine_readable_result(tmp_path: Path) -> None:
    comparison_paths = []
    for index, report in enumerate(reports(["PASS"] * 20), start=1):
        path = tmp_path / f"comparison-{index}.json"
        path.write_text(json.dumps(report), encoding="utf-8")
        comparison_paths.extend(["--comparison", str(path)])
    output = tmp_path / "gate.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            *comparison_paths,
            "--market-open-hours",
            "48",
            "--sequence-gaps",
            "0",
            "--dropped-transactions",
            "0",
            "--account-terms-match",
            "--certification-started-utc",
            "2026-08-01T00:00:00+00:00",
            "--output",
            str(output),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(output.read_text(encoding="utf-8"))[
        "qualification_status"
    ] == "FORMAL_PASS"


def test_gate_cli_reads_probe_health_and_account_term_reports(
    tmp_path: Path,
) -> None:
    comparison_paths = []
    for index, report in enumerate(reports(["PASS"] * 20), start=1):
        path = tmp_path / f"comparison-{index}.json"
        path.write_text(json.dumps(report), encoding="utf-8")
        comparison_paths.extend(["--comparison", str(path)])
    health = tmp_path / "health.json"
    health.write_text(
        json.dumps(
            {
                "market_open_hours": 48.0,
                "sequence_gaps": 0,
                "duplicate_sequences": 0,
                "dropped_transactions": 0,
                "session_restarts": 0,
                "direct_request_evidence_available": True,
            }
        ),
        encoding="utf-8",
    )
    terms = tmp_path / "terms.json"
    terms.write_text(json.dumps({"match": True}), encoding="utf-8")
    output = tmp_path / "gate.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            *comparison_paths,
            "--probe-health",
            str(health),
            "--account-terms-report",
            str(terms),
            "--output",
            str(output),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(output.read_text(encoding="utf-8"))[
        "qualification_status"
    ] == "FORMAL_PASS"
