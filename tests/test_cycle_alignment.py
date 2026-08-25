from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from straddle_replica.cycle_alignment import (
    candidate_freeze_ready,
    next_target_restart,
    plan_target_aligned_launch,
    target_restart_delays,
    validate_bound_demo_preset,
)


UTC = timezone.utc
ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "align_local_auxiliary_cycle.py"


def _utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
        UTC
    )


def _boundary(
    *,
    cycle_id: str,
    completed_at: datetime,
    delay_seconds: float | None,
) -> list[dict]:
    events = [
        {
            "cycle_id": cycle_id,
            "kind": "cycle_complete",
            "time_utc": completed_at.isoformat(),
        }
    ]
    if delay_seconds is not None:
        events.append(
            {
                "cycle_id": cycle_id,
                "kind": "cycle_restart",
                "time_utc": (
                    completed_at + timedelta(seconds=delay_seconds)
                ).isoformat(),
            }
        )
    return events


def test_freeze_requires_complete_without_restart() -> None:
    complete = {
        "cycle_id": "cycle-1",
        "kind": "cycle_complete",
        "time_utc": "2026-08-13T17:00:00Z",
    }
    restart = {
        "cycle_id": "cycle-1",
        "kind": "cycle_restart",
        "time_utc": "2026-08-13T17:00:20Z",
    }

    assert candidate_freeze_ready([complete], cycle_id="cycle-1")
    assert not candidate_freeze_ready(
        [complete, restart],
        cycle_id="cycle-1",
    )
    assert not candidate_freeze_ready(
        [complete],
        cycle_id="another-cycle",
    )


def _write_independent_flat_proof(
    path: Path,
    *,
    captured_at: datetime,
    flat: bool = True,
    terminal_trade_allowed: bool = False,
) -> None:
    positions_total = 0 if flat else 1
    path.write_text(
        json.dumps(
            {
                "account": {"login": 901111},
                "read_only_broker_sync": {
                    "sync_time_utc": captured_at.isoformat(),
                    "positions_total": positions_total,
                    "orders_total": 0,
                    "flat": flat,
                    "terminal_trade_allowed": terminal_trade_allowed,
                    "start_config_experts_enabled": False,
                    "start_config_allow_live_trading": False,
                },
                "process_safety": {
                    "read_only_tester_terminal_stopped": True,
                    "exact_auxiliary_trading_terminal_stopped": True,
                    "alignment_controller_process_running": False,
                    "orders_or_positions_modified": False,
                    "trade_methods_invoked": False,
                },
            }
        ),
        encoding="utf-8",
    )


def test_fresh_independent_flat_proof_replaces_missing_completion(
    tmp_path: Path,
) -> None:
    controller = importlib.import_module(
        "tools.align_local_auxiliary_cycle"
    )
    now = _utc("2026-08-17T11:30:00Z")
    proof = tmp_path / "flat-proof.json"
    _write_independent_flat_proof(
        proof,
        captured_at=now - timedelta(seconds=5),
    )

    captured_at = controller._validate_independent_flat_proof(
        proof,
        expected_login=901111,
        maximum_age_seconds=30,
        now_utc=now,
    )
    source = controller._candidate_freeze_source(
        [],
        cycle_id="interrupted-cycle",
        independent_flat_at_utc=captured_at,
    )

    assert captured_at == now - timedelta(seconds=5)
    assert source == "independent_flat_proof"


def test_independent_flat_proof_rejects_nonflat_state(
    tmp_path: Path,
) -> None:
    controller = importlib.import_module(
        "tools.align_local_auxiliary_cycle"
    )
    now = _utc("2026-08-17T11:30:00Z")
    proof = tmp_path / "nonflat-proof.json"
    _write_independent_flat_proof(
        proof,
        captured_at=now,
        flat=False,
    )

    with pytest.raises(RuntimeError, match="zero positions"):
        controller._validate_independent_flat_proof(
            proof,
            expected_login=901111,
            maximum_age_seconds=30,
            now_utc=now,
        )


def test_independent_flat_proof_rejects_missing_counts(
    tmp_path: Path,
) -> None:
    controller = importlib.import_module(
        "tools.align_local_auxiliary_cycle"
    )
    now = _utc("2026-08-17T11:30:00Z")
    proof = tmp_path / "missing-counts-proof.json"
    _write_independent_flat_proof(proof, captured_at=now)
    payload = json.loads(proof.read_text(encoding="utf-8"))
    del payload["read_only_broker_sync"]["positions_total"]
    proof.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(RuntimeError, match="zero positions"):
        controller._validate_independent_flat_proof(
            proof,
            expected_login=901111,
            maximum_age_seconds=30,
            now_utc=now,
        )


def test_independent_flat_proof_rejects_stale_capture(
    tmp_path: Path,
) -> None:
    controller = importlib.import_module(
        "tools.align_local_auxiliary_cycle"
    )
    now = _utc("2026-08-17T11:30:00Z")
    proof = tmp_path / "stale-proof.json"
    _write_independent_flat_proof(
        proof,
        captured_at=now - timedelta(seconds=31),
    )

    with pytest.raises(RuntimeError, match="stale"):
        controller._validate_independent_flat_proof(
            proof,
            expected_login=901111,
            maximum_age_seconds=30,
            now_utc=now,
        )


def test_independent_flat_recovery_requires_terminal_stopped() -> None:
    controller = importlib.import_module(
        "tools.align_local_auxiliary_cycle"
    )

    assert (
        controller._terminal_process_to_stop(
            [],
            freeze_source="independent_flat_proof",
        )
        == 0
    )
    with pytest.raises(RuntimeError, match="must remain stopped"):
        controller._terminal_process_to_stop(
            [{"ProcessId": 123}],
            freeze_source="independent_flat_proof",
        )


def test_restart_delays_ignore_session_gap_and_outliers() -> None:
    start = _utc("2026-08-13T12:00:00Z")
    events = [
        *_boundary(
            cycle_id="cycle-1",
            completed_at=start,
            delay_seconds=20.5,
        ),
        *_boundary(
            cycle_id="cycle-2",
            completed_at=start + timedelta(hours=1),
            delay_seconds=20.9,
        ),
        *_boundary(
            cycle_id="cycle-session-gap",
            completed_at=start + timedelta(hours=2),
            delay_seconds=130.0,
        ),
        *_boundary(
            cycle_id="cycle-too-fast",
            completed_at=start + timedelta(hours=3),
            delay_seconds=2.0,
        ),
    ]

    assert target_restart_delays(events) == pytest.approx(
        [20.5, 20.9]
    )


def test_launch_plan_uses_first_completion_after_freeze() -> None:
    events = [
        *_boundary(
            cycle_id="historical-1",
            completed_at=_utc("2026-08-13T14:00:00Z"),
            delay_seconds=20.5,
        ),
        *_boundary(
            cycle_id="historical-2",
            completed_at=_utc("2026-08-13T15:00:00Z"),
            delay_seconds=20.9,
        ),
        *_boundary(
            cycle_id="before-freeze",
            completed_at=_utc("2026-08-13T17:40:00Z"),
            delay_seconds=20.7,
        ),
        *_boundary(
            cycle_id="next-target",
            completed_at=_utc("2026-08-13T18:00:00Z"),
            delay_seconds=None,
        ),
        *_boundary(
            cycle_id="later-target",
            completed_at=_utc("2026-08-13T19:00:00Z"),
            delay_seconds=None,
        ),
    ]

    plan = plan_target_aligned_launch(
        events,
        frozen_at_utc=_utc("2026-08-13T17:45:00Z"),
        startup_lead_seconds=3.0,
    )

    assert plan is not None
    assert plan.target_cycle_id == "next-target"
    assert plan.target_complete_utc == _utc("2026-08-13T18:00:00Z")
    assert plan.restart_delay_seconds == pytest.approx(20.7)
    assert plan.launch_at_utc == _utc(
        "2026-08-13T18:00:17.700000Z"
    )
    assert plan.restart_delay_sample_count == 3


def test_launch_plan_waits_when_no_new_target_completion_exists() -> None:
    events = _boundary(
        cycle_id="historical",
        completed_at=_utc("2026-08-13T17:40:00Z"),
        delay_seconds=20.5,
    )

    assert (
        plan_target_aligned_launch(
            events,
            frozen_at_utc=_utc("2026-08-13T17:45:00Z"),
            startup_lead_seconds=3.0,
        )
        is None
    )


def test_viable_plan_skips_elapsed_target_window() -> None:
    controller = importlib.import_module(
        "tools.align_local_auxiliary_cycle"
    )
    events = [
        *_boundary(
            cycle_id="historical-1",
            completed_at=_utc("2026-08-13T17:00:00Z"),
            delay_seconds=20.0,
        ),
        *_boundary(
            cycle_id="historical-2",
            completed_at=_utc("2026-08-13T17:30:00Z"),
            delay_seconds=20.0,
        ),
        *_boundary(
            cycle_id="missed-target",
            completed_at=_utc("2026-08-13T18:00:00Z"),
            delay_seconds=20.0,
        ),
        *_boundary(
            cycle_id="next-target",
            completed_at=_utc("2026-08-13T19:00:00Z"),
            delay_seconds=None,
        ),
    ]

    plan, missed = controller._viable_alignment_plan(
        events,
        frozen_at_utc=_utc("2026-08-13T17:45:00Z"),
        startup_lead_seconds=3.0,
        now_utc=_utc("2026-08-13T18:30:00Z"),
    )

    assert plan is not None
    assert plan.target_cycle_id == "next-target"
    assert missed == ["missed-target"]


def test_next_target_restart_selects_first_restart_after_freeze() -> None:
    events = [
        {
            "cycle_id": "before-freeze",
            "kind": "cycle_restart",
            "time_utc": "2026-08-14T00:00:00Z",
        },
        {
            "cycle_id": "first-after-freeze",
            "kind": "cycle_restart",
            "time_utc": "2026-08-14T01:00:03Z",
        },
        {
            "cycle_id": "later",
            "kind": "cycle_restart",
            "time_utc": "2026-08-14T02:00:03Z",
        },
    ]

    restart = next_target_restart(
        events,
        after_utc=_utc("2026-08-14T00:30:00Z"),
    )

    assert restart is not None
    assert restart["cycle_id"] == "first-after-freeze"


def test_preset_must_be_bound_to_the_expected_demo() -> None:
    valid = (
        "RequireDemoAccount=true\n"
        "RequireBoundAccount=true\n"
        "ExpectedAccountLogin=901111\n"
    )

    validate_bound_demo_preset(valid, expected_login=901111)

    with pytest.raises(ValueError, match="RequireDemoAccount"):
        validate_bound_demo_preset(
            valid.replace("RequireDemoAccount=true", "false"),
            expected_login=901111,
        )
    with pytest.raises(ValueError, match="ExpectedAccountLogin"):
        validate_bound_demo_preset(
            valid.replace("901111", "901112"),
            expected_login=901111,
        )


def test_controller_is_terminal_only_and_hash_guarded() -> None:
    source = TOOL.read_text(encoding="utf-8")
    lowered = source.lower()

    assert "metatrader5" not in lowered
    assert "order_send" not in lowered
    assert "positions_get" not in lowered
    assert "orders_get" not in lowered
    assert "executablepath" in lowered
    assert "--expected-active-ex5-sha256" in source
    assert "--staged-ex5-path" in source
    assert "--expected-staged-ex5-sha256" in source
    assert "--qualification-state" in source
    assert "--candidate-cycle-id" in source
    assert "--independent-flat-proof" in source


def test_staged_ex5_install_is_hash_guarded_and_atomic(tmp_path) -> None:
    controller = importlib.import_module(
        "tools.align_local_auxiliary_cycle"
    )
    assert hasattr(controller, "_install_staged_ex5")

    active = tmp_path / "active.ex5"
    staged = tmp_path / "staged.ex5"
    active.write_bytes(b"active-build")
    staged.write_bytes(b"staged-build")
    active_hash = hashlib.sha256(active.read_bytes()).hexdigest()
    staged_hash = hashlib.sha256(staged.read_bytes()).hexdigest()

    deployed_hash = controller._install_staged_ex5(
        active_ex5_path=active,
        expected_active_ex5_sha256=active_hash,
        staged_ex5_path=staged,
        expected_staged_ex5_sha256=staged_hash,
    )

    assert active.read_bytes() == b"staged-build"
    assert deployed_hash == staged_hash.upper()
    assert not active.with_suffix(".ex5.staged.tmp").exists()


def test_staged_ex5_hash_mismatch_preserves_active_binary(
    tmp_path,
) -> None:
    controller = importlib.import_module(
        "tools.align_local_auxiliary_cycle"
    )
    assert hasattr(controller, "_install_staged_ex5")

    active = tmp_path / "active.ex5"
    staged = tmp_path / "staged.ex5"
    active.write_bytes(b"active-build")
    staged.write_bytes(b"staged-build")
    active_hash = hashlib.sha256(active.read_bytes()).hexdigest()

    with pytest.raises(RuntimeError, match="Staged EX5 SHA256 mismatch"):
        controller._install_staged_ex5(
            active_ex5_path=active,
            expected_active_ex5_sha256=active_hash,
            staged_ex5_path=staged,
            expected_staged_ex5_sha256="0" * 64,
        )

    assert active.read_bytes() == b"active-build"


def test_alignment_hold_is_atomic_and_releasable(tmp_path) -> None:
    controller = importlib.import_module(
        "tools.align_local_auxiliary_cycle"
    )
    hold = tmp_path / "alignment-hold.json"

    controller._write_alignment_hold(
        hold,
        candidate_cycle_id="candidate-excluded",
        active_ex5_sha256="a" * 64,
        created_at_utc=_utc("2026-08-14T01:00:00Z"),
    )

    payload = json.loads(hold.read_text(encoding="utf-8"))
    assert payload["status"] == "HOLD"
    assert payload["candidate_cycle_id"] == "candidate-excluded"
    assert payload["active_ex5_sha256"] == "A" * 64
    assert not hold.with_suffix(".json.tmp").exists()

    controller._release_alignment_hold(hold)

    assert not hold.exists()


def test_staged_qualification_requires_alignment_controller(
    tmp_path,
) -> None:
    controller = importlib.import_module(
        "tools.align_local_auxiliary_cycle"
    )
    qualification = tmp_path / "qualification.json"
    qualification.write_text(
        json.dumps({"excluded_candidate_cycle_ids": []}),
        encoding="utf-8",
    )

    controller._activate_staged_qualification(
        path=qualification,
        candidate_cycle_id="candidate-excluded",
        staged_ex5_path=tmp_path / "staged.ex5",
        staged_ex5_sha256="a" * 64,
        staged_package_path=tmp_path / "staged.zip",
        staged_package_sha256="b" * 64,
        deployed_at_utc=_utc("2026-08-14T00:00:00Z"),
    )

    state = json.loads(qualification.read_text(encoding="utf-8"))
    assert state["qualification_start_policy"] == (
        "alignment_controller"
    )
    assert state["qualification_started_utc"] is None
    assert state["active_cycle_eligible"] is False


def test_frozen_deployment_state_is_resumable() -> None:
    controller = importlib.import_module(
        "tools.align_local_auxiliary_cycle"
    )
    staged_hash = "a" * 64
    state = {
        "active_build_id": staged_hash,
        "active_cycle_id": "candidate-excluded",
        "active_cycle_eligible": False,
        "active_deployed_utc": "2026-08-14T00:25:56Z",
        "qualification_start_policy": "alignment_controller",
        "qualification_started_utc": None,
        "staged_status": (
            "DEPLOYED_AT_NATURAL_FLAT_WAITING_FOR_ALIGNED_CYCLE"
        ),
    }

    frozen_at = controller._frozen_deployment_utc(
        state,
        candidate_cycle_id="candidate-excluded",
        active_ex5_sha256=staged_hash.upper(),
        staged_ex5_sha256=staged_hash.upper(),
    )

    assert frozen_at == _utc("2026-08-14T00:25:56Z")


def test_initial_grid_reports_duplicate_accepted_slot() -> None:
    controller = importlib.import_module(
        "tools.align_local_auxiliary_cycle"
    )
    events = []
    sequence = 1
    for level in range(1, 31):
        for side in ("B", "S"):
            events.append(
                {
                    "cycle_id": "cycle-1",
                    "kind": "pending_request",
                    "comment": f"STR {side}{level}",
                    "retcode": 10009,
                    "sequence": sequence,
                    "event_id": f"event-{sequence}",
                    "time_utc": "2026-08-14T00:00:00Z",
                }
            )
            sequence += 1
    events.append(
        {
            **events[0],
            "sequence": sequence,
            "event_id": "event-duplicate-b1",
        }
    )

    slots, duplicate_slots = controller._initial_grid(
        events,
        "cycle-1",
    )

    assert len(slots) == 60
    assert duplicate_slots == ["STR B1"]


def test_initial_grid_allows_rearm_after_stop_exit() -> None:
    controller = importlib.import_module(
        "tools.align_local_auxiliary_cycle"
    )
    events = [
        {
            "cycle_id": "cycle-1",
            "kind": "pending_request",
            "comment": "STR B1",
            "retcode": 10009,
            "sequence": 1,
            "event_id": "event-initial-b1",
            "time_utc": "2026-08-14T00:00:00Z",
        },
        {
            "cycle_id": "cycle-1",
            "kind": "stop_exit",
            "comment": "STR B1",
            "sequence": 2,
            "event_id": "event-stop-b1",
            "time_utc": "2026-08-14T00:01:00Z",
        },
        {
            "cycle_id": "cycle-1",
            "kind": "pending_request",
            "comment": "STR B1",
            "retcode": 10009,
            "sequence": 3,
            "event_id": "event-rearm-b1",
            "time_utc": "2026-08-14T00:01:20Z",
        },
    ]

    slots, duplicate_slots = controller._initial_grid(
        events,
        "cycle-1",
    )

    assert list(slots) == ["STR B1"]
    assert duplicate_slots == []


def test_controller_help_is_runnable() -> None:
    completed = subprocess.run(
        [sys.executable, str(TOOL), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "--candidate-cycle-id" in completed.stdout
    assert "--startup-lead-seconds" in completed.stdout
    assert "--staged-ex5-path" in completed.stdout
    assert "--qualification-state" in completed.stdout
    assert "--alignment-hold-path" in completed.stdout
    assert "--independent-flat-proof" in completed.stdout
