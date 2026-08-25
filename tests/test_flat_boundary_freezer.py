from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from straddle_replica.flat_boundary import (
    evaluate_freeze_readiness,
    freeze_remote_candidate,
    read_last_two_jsonl,
)
from tools.freeze_candidate_at_flat_boundary import (
    _post_stop_flat_confirmation,
)


NOW = datetime(2026, 8, 13, 9, 0, 2, tzinfo=timezone.utc)
ACTIVE_BUILD = (
    "98f3269cf233c7732c1a8a9493ea17d352c76202a018424c36dd964775feec72"
)
STAGED_BUILD = (
    "98cf4f67be9432ca2b033b7e1c6ef0999e0f57a05b504fffeb1a750ee00cb071"
)
EXCLUDED_CYCLE = "local-110971967-20260812T113748Z"


def _heartbeat(*, positions: int = 0, orders: int = 0) -> dict:
    return {
        "capture_time_utc": "2026-08-13T09:00:01.800000+00:00",
        "healthy": True,
        "orders_total": orders,
        "positions_total": positions,
        "read_only_verified": True,
        "sequence": 200,
        "session_id": "candidate-session",
        "stopped": False,
    }


def _manifest() -> dict:
    return {
        "account": {
            "login": 110971967,
            "server": "MetaQuotes-Demo",
            "trade_allowed": False,
        },
        "safety": {
            "account_trade_allowed": False,
            "collector_has_trading_api": False,
            "require_read_only": True,
        },
        "session_id": "candidate-session",
        "terminal": {
            "connected": True,
            "trade_allowed": False,
        },
    }


def _snapshot(sequence: int, timestamp: str, *, flat: bool = True) -> dict:
    return {
        "capture_time_utc": timestamp,
        "orders": [] if flat else [{"ticket": 1}],
        "positions": [] if flat else [{"ticket": 2}],
        "sequence": sequence,
    }


def _observer_state() -> dict:
    return {
        "armed_for_next_cycle": False,
        "session_id": "candidate-session",
        "suppress_current_cycle": True,
        "waiting_for_flat": True,
    }


def _archive_state() -> dict:
    return {
        "current_cycle_id": "",
        "sequence_gaps": 0,
        "session_id": "candidate-session-observer",
    }


def _qualification_state() -> dict:
    return {
        "active_build_id": ACTIVE_BUILD,
        "active_cycle_eligible": False,
        "active_cycle_id": EXCLUDED_CYCLE,
        "complete_paired_cycles": 0,
        "evidence_based_fidelity_percent": None,
        "excluded_candidate_cycle_ids": [EXCLUDED_CYCLE],
        "staged_build_id": STAGED_BUILD,
        "staged_status": "LOCAL_VERIFIED_AWAITING_NATURAL_FLAT_BOUNDARY",
    }


def _evaluate(
    *,
    heartbeat: dict | None = None,
    previous_snapshot: dict | None = None,
    latest_snapshot: dict | None = None,
    qualification_state: dict | None = None,
) -> dict:
    return evaluate_freeze_readiness(
        heartbeat=heartbeat or _heartbeat(),
        manifest=_manifest(),
        previous_snapshot=previous_snapshot
        or _snapshot(
            198,
            "2026-08-13T09:00:00.500000+00:00",
        ),
        latest_snapshot=latest_snapshot
        or _snapshot(
            199,
            "2026-08-13T09:00:01.500000+00:00",
        ),
        observer_state=_observer_state(),
        archive_state=_archive_state(),
        qualification_state=qualification_state
        or _qualification_state(),
        now_utc=NOW,
        expected_login=110971967,
        expected_server="MetaQuotes-Demo",
        expected_active_build_id=ACTIVE_BUILD,
        expected_staged_build_id=STAGED_BUILD,
        max_heartbeat_age_seconds=5.0,
        minimum_flat_confirmation_seconds=0.25,
    )


def test_accepts_two_fresh_consecutive_flat_snapshots():
    result = _evaluate()

    assert result["ready"] is True
    assert result["reasons"] == []
    assert result["flat_confirmation_seconds"] == 1.0


def test_rejects_non_flat_or_single_snapshot_transition():
    result = _evaluate(
        heartbeat=_heartbeat(positions=1),
        previous_snapshot=_snapshot(
            198,
            "2026-08-13T09:00:00.500000+00:00",
            flat=False,
        ),
    )

    assert result["ready"] is False
    assert "heartbeat_not_flat" in result["reasons"]
    assert "previous_snapshot_not_flat" in result["reasons"]


def test_rejects_stale_or_unqualified_evidence():
    heartbeat = _heartbeat()
    heartbeat["capture_time_utc"] = "2026-08-13T08:59:50+00:00"
    qualification = _qualification_state()
    qualification["active_cycle_eligible"] = True

    result = _evaluate(
        heartbeat=heartbeat,
        qualification_state=qualification,
    )

    assert result["ready"] is False
    assert "heartbeat_stale" in result["reasons"]
    assert "active_cycle_not_excluded" in result["reasons"]


def test_remote_freeze_checks_and_stops_only_exact_candidate():
    commands: list[str] = []

    def run_ssh(command: str) -> str:
        commands.append(command)
        if "grep '^MT5_START='" in command:
            return "MT5_START=1"
        if command.startswith("docker inspect --format"):
            return "container-id|running|0|false"
        if command.startswith("docker port"):
            return "127.0.0.1:15925"
        if command.startswith("sha256sum"):
            return f"{ACTIVE_BUILD}  /exact/StraddleReplica.ex5"
        if command.startswith("docker stop"):
            return "straddle-fidelity-independent-demo"
        raise AssertionError(f"unexpected command: {command}")

    result = freeze_remote_candidate(
        run_ssh=run_ssh,
        expected_active_ex5_sha256=ACTIVE_BUILD,
    )

    assert result["container_id"] == "container-id"
    assert result["stopped"] is True
    assert commands[-1] == (
        "docker stop --time 1 straddle-fidelity-independent-demo"
    )
    assert all(
        "straddle-fidelity-independent-demo" in command
        or command.startswith("sha256sum ")
        for command in commands
    )
    assert not any("docker ps" in command for command in commands)


def test_remote_freeze_rejects_wrong_active_build_without_stop():
    commands: list[str] = []

    def run_ssh(command: str) -> str:
        commands.append(command)
        if "grep '^MT5_START='" in command:
            return "MT5_START=1"
        if command.startswith("docker inspect --format"):
            return "container-id|running|0|false"
        if command.startswith("docker port"):
            return "127.0.0.1:15925"
        if command.startswith("sha256sum"):
            return "wrong-hash  /exact/StraddleReplica.ex5"
        raise AssertionError(f"unexpected command: {command}")

    try:
        freeze_remote_candidate(
            run_ssh=run_ssh,
            expected_active_ex5_sha256=ACTIVE_BUILD,
        )
    except RuntimeError as error:
        assert "active EX5 hash mismatch" in str(error)
    else:
        raise AssertionError("wrong active build was accepted")

    assert not any(command.startswith("docker stop") for command in commands)


def test_reads_last_two_nonempty_jsonl_records(tmp_path):
    path = tmp_path / "snapshots.jsonl"
    path.write_text(
        '{"sequence": 1}\n'
        '{"sequence": 2}\n'
        '\n'
        '{"sequence": 3}\n',
        encoding="utf-8",
    )

    previous, latest = read_last_two_jsonl(path)

    assert previous["sequence"] == 2
    assert latest["sequence"] == 3


def test_post_stop_confirmation_retries_transient_evidence_error():
    attempts = 0

    def load_evidence(**_: object) -> dict:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError("atomic snapshot transition")
        return {
            "heartbeat": {
                "positions_total": 0,
                "orders_total": 0,
            },
            "previous_snapshot": {
                "capture_time_utc": "2026-08-13T09:00:02+00:00",
                "positions": [],
                "orders": [],
            },
            "latest_snapshot": {
                "capture_time_utc": "2026-08-13T09:00:03+00:00",
                "positions": [],
                "orders": [],
            },
        }

    confirmed, evidence = _post_stop_flat_confirmation(
        stopped_at_utc=datetime(
            2026,
            8,
            13,
            9,
            0,
            1,
            tzinfo=timezone.utc,
        ),
        candidate_root=Path("."),
        observer_state_path=Path("observer.json"),
        archive_state_path=Path("archive.json"),
        qualification_state_path=Path("qualification.json"),
        timeout_seconds=0.5,
        load_evidence=load_evidence,
        sleep=lambda _: None,
    )

    assert confirmed is True
    assert attempts == 2
    assert evidence["latest_snapshot"]["positions"] == []
