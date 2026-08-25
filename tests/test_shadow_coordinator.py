from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import time

from straddle_replica.shadow_coordinator import (
    ShadowCoordinator,
    ShadowCoordinatorConfig,
    load_probe_events,
    read_shadow_command,
)


UTC = timezone.utc
ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "run_shadow_coordinator.py"


def write_ack(path: Path, *, status: str, command_seq: int = 0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("schema_version", "command_seq", "status", "cycle_id"),
        )
        writer.writeheader()
        writer.writerow(
            {
                "schema_version": 1,
                "command_seq": command_seq,
                "status": status,
                "cycle_id": "",
            }
        )


def wait_for_json_status(
    path: Path,
    expected_status: str,
    timeout: float = 3.0,
) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = {}
            if payload.get("status") == expected_status:
                return payload
        time.sleep(0.02)
    raise AssertionError(
        f"Timed out waiting for {path} status={expected_status}"
    )


def build_stale_observer(tmp_path: Path) -> Path:
    root = tmp_path / "observer"
    session = root / "session"
    session.mkdir(parents=True)
    (root / "current-session.json").write_text(
        json.dumps({"session_id": "session"}),
        encoding="utf-8",
    )
    (session / "manifest.json").write_text(
        json.dumps(
            {"time_domains": {"history_server_offset_seconds": 0}}
        ),
        encoding="utf-8",
    )
    stale = datetime.now(tz=UTC) - timedelta(minutes=1)
    (session / "heartbeat.json").write_text(
        json.dumps(
            {
                "capture_time_utc": stale.isoformat(),
                "healthy": True,
                "stopped": False,
            }
        ),
        encoding="utf-8",
    )
    (session / "snapshots-20260810-05.jsonl").write_text(
        json.dumps(
            {
                "capture_time_utc": stale.isoformat(),
                "sequence": 1,
                "orders": [{"ticket": 1, "comment": "STR B1"}],
                "positions": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return root


def request_event(
    *,
    sequence: int,
    time: datetime,
    action: str,
    comment: str = "",
    price: float = 0.0,
    session_id: str = "session-1",
    retcode: int = 10008,
) -> dict:
    return {
        "session_id": session_id,
        "sequence": sequence,
        "time_utc": time.isoformat(),
        "kind": action,
        "comment": comment,
        "price": price,
        "volume": 0.01,
        "request_id": sequence,
        "retcode": retcode,
    }


def coordinator(tmp_path: Path, *, observe_only: bool = False):
    command_path = tmp_path / "command.csv"
    ack_path = tmp_path / "ack.csv"
    state_path = tmp_path / "state.json"
    write_ack(ack_path, status="FLAT")
    return (
        ShadowCoordinator(
            ShadowCoordinatorConfig(
                command_path=command_path,
                ack_path=ack_path,
                state_path=state_path,
                target_archive_path=tmp_path / "target-cycles.jsonl",
                observe_only=observe_only,
                command_ttl_ms=2_000,
                pair_window_ms=1_000,
            )
        ),
        command_path,
        state_path,
    )


def test_coordinator_uses_injected_transport_and_ack_sequence(
    tmp_path: Path,
) -> None:
    class MemoryTransport:
        def __init__(self) -> None:
            self.commands: list[dict] = []

        def read_ack(self) -> dict:
            return {
                "status": "FLAT",
                "command_seq": 7,
                "cycle_id": "",
            }

        def write_command(self, payload: dict) -> None:
            self.commands.append(payload)

    transport = MemoryTransport()
    service = ShadowCoordinator(
        ShadowCoordinatorConfig(
            command_path=tmp_path / "unused-command.csv",
            ack_path=tmp_path / "unused-ack.csv",
            state_path=tmp_path / "state.json",
            target_archive_path=tmp_path / "target.jsonl",
            observe_only=False,
        ),
        transport=transport,
    )
    now = datetime(2026, 8, 4, 14, 0, tzinfo=UTC)

    result = service.process_events(
        [
            request_event(
                sequence=1,
                time=now,
                action="cancel_request",
                comment="STR S30",
            )
        ],
        now=now,
    )

    assert result["commands_written"] == 1
    assert transport.commands[0]["command"] == "RESET"
    assert transport.commands[0]["command_seq"] == 8


def test_close_request_emits_demo_reset_command(tmp_path: Path) -> None:
    service, command_path, _ = coordinator(tmp_path)
    now = datetime(2026, 8, 4, 14, 0, tzinfo=UTC)

    result = service.process_events(
        [
            request_event(
                sequence=1,
                time=now,
                action="cancel_request",
                comment="STR S30",
            )
        ],
        now=now,
    )

    command = read_shadow_command(command_path)
    assert result["commands_written"] == 1
    assert command.command == "RESET"
    assert command.command_seq == 1


def test_b1_s1_pair_emits_exact_start_command(tmp_path: Path) -> None:
    service, command_path, _ = coordinator(tmp_path)
    now = datetime(2026, 8, 4, 14, 0, tzinfo=UTC)

    result = service.process_events(
        [
            request_event(
                sequence=1,
                time=now,
                action="pending_request",
                comment="STR B1",
                price=4081.36,
            ),
            request_event(
                sequence=2,
                time=now + timedelta(milliseconds=100),
                action="pending_request",
                comment="STR S1",
                price=4078.64,
            ),
        ],
        now=now + timedelta(milliseconds=200),
    )

    command = read_shadow_command(command_path)
    assert result["commands_written"] == 1
    assert command.command == "START"
    assert command.profile == "LATEST_30"
    assert command.anchor == 4080.0
    assert command.step == 1.36
    assert command.cycle_id
    archived = [
        json.loads(line)
        for line in (tmp_path / "target-cycles.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert [event["comment"] for event in archived] == ["STR B1", "STR S1"]
    assert {event["cycle_id"] for event in archived} == {command.cycle_id}


def test_stale_pair_is_skipped_and_does_not_write_command(
    tmp_path: Path,
) -> None:
    service, command_path, _ = coordinator(tmp_path)
    now = datetime(2026, 8, 4, 14, 0, tzinfo=UTC)

    result = service.process_events(
        [
            request_event(
                sequence=1,
                time=now,
                action="pending_request",
                comment="STR B1",
                price=4081.36,
            ),
            request_event(
                sequence=2,
                time=now + timedelta(seconds=2),
                action="pending_request",
                comment="STR S1",
                price=4078.64,
            ),
        ],
        now=now + timedelta(seconds=2),
    )

    assert result["commands_written"] == 0
    assert result["skipped_cycles"] == 1
    assert not command_path.exists()


def test_stale_in_cycle_b1_s1_rearms_do_not_skip_cycle(
    tmp_path: Path,
) -> None:
    service, command_path, _ = coordinator(tmp_path)
    now = datetime(2026, 8, 4, 14, 0, tzinfo=UTC)
    service.process_events(
        [
            request_event(
                sequence=1,
                time=now,
                action="pending_request",
                comment="STR B1",
                price=4081.36,
            ),
            request_event(
                sequence=2,
                time=now + timedelta(milliseconds=100),
                action="pending_request",
                comment="STR S1",
                price=4078.64,
            ),
        ],
        now=now + timedelta(milliseconds=200),
    )
    first_command = read_shadow_command(command_path)

    result = service.process_events(
        [
            request_event(
                sequence=3,
                time=now + timedelta(minutes=5),
                action="pending_request",
                comment="STR S1",
                price=4078.64,
            ),
            request_event(
                sequence=4,
                time=now + timedelta(minutes=12),
                action="pending_request",
                comment="STR B1",
                price=4081.36,
            ),
        ],
        now=now + timedelta(minutes=12),
    )

    command = read_shadow_command(command_path)
    assert result["commands_written"] == 0
    assert result["skipped_cycles"] == 0
    assert command.command_seq == first_command.command_seq
    state = json.loads(
        (tmp_path / "state.json").read_text(encoding="utf-8")
    )
    assert state["skipped_cycles"] == 0
    assert state["b1"] is None
    assert state["s1"] is None


def test_close_timed_in_cycle_b1_s1_rearms_do_not_emit_start(
    tmp_path: Path,
) -> None:
    service, command_path, _ = coordinator(tmp_path)
    now = datetime(2026, 8, 4, 14, 0, tzinfo=UTC)
    service.process_events(
        [
            request_event(
                sequence=1,
                time=now,
                action="pending_request",
                comment="STR B1",
                price=4081.36,
            ),
            request_event(
                sequence=2,
                time=now + timedelta(milliseconds=100),
                action="pending_request",
                comment="STR S1",
                price=4078.64,
            ),
        ],
        now=now + timedelta(milliseconds=200),
    )
    first_command = read_shadow_command(command_path)

    result = service.process_events(
        [
            request_event(
                sequence=3,
                time=now + timedelta(minutes=5),
                action="pending_request",
                comment="STR B1",
                price=4081.36,
            ),
            request_event(
                sequence=4,
                time=now
                + timedelta(minutes=5, milliseconds=100),
                action="pending_request",
                comment="STR S1",
                price=4078.64,
            ),
        ],
        now=now + timedelta(minutes=5, milliseconds=200),
    )

    command = read_shadow_command(command_path)
    assert result["commands_written"] == 0
    assert result["skipped_cycles"] == 0
    assert command.command_seq == first_command.command_seq


def test_rejected_b1_is_archived_but_cannot_start_cycle(
    tmp_path: Path,
) -> None:
    service, command_path, _ = coordinator(tmp_path)
    now = datetime(2026, 8, 4, 14, 0, tzinfo=UTC)

    result = service.process_events(
        [
            request_event(
                sequence=1,
                time=now,
                action="pending_request",
                comment="STR B1",
                price=4099.0,
                retcode=10016,
            ),
            request_event(
                sequence=2,
                time=now + timedelta(milliseconds=100),
                action="pending_request",
                comment="STR S1",
                price=4078.64,
            ),
            request_event(
                sequence=3,
                time=now + timedelta(milliseconds=200),
                action="pending_request",
                comment="STR B1",
                price=4081.36,
            ),
        ],
        now=now + timedelta(milliseconds=300),
    )

    command = read_shadow_command(command_path)
    assert result["commands_written"] == 1
    assert command.anchor == 4080.0
    assert command.step == 1.36
    archived = [
        json.loads(line)
        for line in (tmp_path / "target-cycles.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert [event["sequence"] for event in archived] == [1, 2, 3]
    assert archived[0]["retcode"] == 10016


def test_restart_does_not_reprocess_target_sequence(tmp_path: Path) -> None:
    service, command_path, state_path = coordinator(tmp_path)
    now = datetime(2026, 8, 4, 14, 0, tzinfo=UTC)
    event = request_event(
        sequence=1,
        time=now,
        action="cancel_request",
        comment="STR S30",
    )
    service.process_events([event], now=now)

    restarted = ShadowCoordinator(service.config)
    result = restarted.process_events([event], now=now)

    assert state_path.exists()
    assert read_shadow_command(command_path).command_seq == 1
    assert result["commands_written"] == 0


def test_new_coordinator_continues_after_existing_ea_ack_sequence(
    tmp_path: Path,
) -> None:
    ack_path = tmp_path / "ack.csv"
    write_ack(ack_path, status="ADOPTED", command_seq=41)
    service = ShadowCoordinator(
        ShadowCoordinatorConfig(
            command_path=tmp_path / "command.csv",
            ack_path=ack_path,
            state_path=tmp_path / "missing-state.json",
            observe_only=False,
        )
    )
    now = datetime(2026, 8, 10, 5, 0, tzinfo=UTC)

    service.process_events(
        [
            request_event(
                sequence=1,
                time=now,
                action="cancel_request",
            )
        ],
        now=now,
    )

    assert read_shadow_command(
        tmp_path / "command.csv"
    ).command_seq == 42


def test_observation_only_mode_never_writes_demo_command(
    tmp_path: Path,
) -> None:
    service, command_path, _ = coordinator(tmp_path, observe_only=True)
    now = datetime(2026, 8, 4, 14, 0, tzinfo=UTC)

    result = service.process_events(
        [
            request_event(
                sequence=1,
                time=now,
                action="cancel_request",
                comment="STR S30",
            )
        ],
        now=now,
    )

    assert result["commands_written"] == 0
    assert result["commands_observed"] == 1
    assert not command_path.exists()


def test_load_probe_events_normalizes_request_fields(tmp_path: Path) -> None:
    root = tmp_path / "probe"
    session = root / "session"
    session.mkdir(parents=True)
    path = session / "transactions-20260804-14.csv"
    fields = (
        "utc_time",
        "sequence",
        "event_kind",
        "entity_comment",
        "request_comment",
        "request_volume",
        "request_price",
        "request_sl",
        "request_tp",
        "result_request_id",
        "result_retcode",
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerow(
            {
                "utc_time": "2026-08-04T14:00:00Z",
                "sequence": 7,
                "event_kind": "pending_request",
                "entity_comment": "STR B1",
                "request_comment": "STR B1",
                "request_volume": 0.01,
                "request_price": 4081.36,
                "request_sl": 0,
                "request_tp": 0,
                "result_request_id": 99,
                "result_retcode": 10008,
            }
        )

    events = load_probe_events(root, minimum_sequence=0)

    assert events == [
        {
            "session_id": "session",
            "sequence": 7,
            "time_utc": "2026-08-04T14:00:00Z",
            "kind": "pending_request",
            "comment": "STR B1",
            "side": "buy",
            "volume": 0.01,
            "price": 4081.36,
            "sl": 0.0,
            "tp": 0.0,
            "request_id": 99,
            "retcode": 10008,
            "evidence_grade": "FORMAL",
            "order_ticket": 0,
            "position_ticket": 0,
            "deal_ticket": 0,
        }
    ]


def test_load_probe_events_uses_deal_fields_for_execution_rows(
    tmp_path: Path,
) -> None:
    root = tmp_path / "probe"
    session = root / "session"
    session.mkdir(parents=True)
    path = session / "transactions-20260804-14.csv"
    fields = (
        "utc_time",
        "sequence",
        "event_kind",
        "entity_comment",
        "trans_deal",
        "trans_position",
        "trans_volume",
        "trans_price",
        "deal_commission",
        "deal_swap",
        "deal_profit",
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerow(
            {
                "utc_time": "2026-08-04T14:00:01Z",
                "sequence": 8,
                "event_kind": "fill",
                "entity_comment": "STR B1",
                "trans_deal": 501,
                "trans_position": 401,
                "trans_volume": 0.01,
                "trans_price": 4081.37,
                "deal_commission": -0.04,
                "deal_swap": 0,
                "deal_profit": 0,
            }
        )

    events = load_probe_events(root)

    assert events == [
        {
            "session_id": "session",
            "sequence": 8,
            "time_utc": "2026-08-04T14:00:01Z",
            "kind": "fill",
            "comment": "STR B1",
            "side": "buy",
            "volume": 0.01,
            "price": 4081.37,
            "sl": 0.0,
            "tp": 0.0,
            "request_id": 0,
            "retcode": 0,
            "ticket": 401,
            "deal": 501,
            "commission": -0.04,
            "swap": 0.0,
            "profit": 0.0,
            "evidence_grade": "FORMAL",
            "order_ticket": 0,
            "position_ticket": 401,
            "deal_ticket": 501,
        }
    ]


def test_load_probe_events_ignores_partially_written_numeric_row(
    tmp_path: Path,
) -> None:
    root = tmp_path / "probe"
    session = root / "session"
    session.mkdir(parents=True)
    path = session / "transactions-20260804-14.csv"
    path.write_text(
        "utc_time,sequence,event_kind,entity_comment,request_volume,"
        "request_price\n"
        "2026-08-04T14:00:00Z,1,pending_request,STR B1,0.01,4081.36\n"
        "2026-08-04T14:00:01Z,partial,pending_request,STR S1,0.01,",
        encoding="utf-8",
    )

    events = load_probe_events(root)

    assert [event["sequence"] for event in events] == [1]


def test_out_of_order_pair_preserves_target_sequence_in_archive(
    tmp_path: Path,
) -> None:
    service, _, _ = coordinator(tmp_path)
    now = datetime(2026, 8, 4, 14, 0, tzinfo=UTC)

    service.process_events(
        [
            request_event(
                sequence=1,
                time=now,
                action="pending_request",
                comment="STR S1",
                price=4078.64,
            ),
            request_event(
                sequence=2,
                time=now + timedelta(milliseconds=100),
                action="pending_request",
                comment="STR B1",
                price=4081.36,
            ),
        ],
        now=now + timedelta(milliseconds=200),
    )

    archived = [
        json.loads(line)
        for line in (tmp_path / "target-cycles.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert [event["comment"] for event in archived] == ["STR S1", "STR B1"]


def test_probe_session_restart_resets_cursor_and_records_failure(
    tmp_path: Path,
) -> None:
    service, _, _ = coordinator(tmp_path)
    now = datetime(2026, 8, 4, 14, 0, tzinfo=UTC)
    service.process_events(
        [
            request_event(
                sequence=1,
                time=now,
                action="transaction",
                session_id="session-a",
            )
        ],
        now=now,
    )

    result = service.process_events(
        [
            request_event(
                sequence=1,
                time=now + timedelta(seconds=1),
                action="transaction",
                session_id="session-b",
            )
        ],
        now=now + timedelta(seconds=1),
    )

    assert result["session_restarts"] == 1
    assert service.target_session_id == "session-b"
    assert service.last_target_sequence == 1


def test_next_deployment_marks_previous_target_cycle_complete(
    tmp_path: Path,
) -> None:
    service, _, _ = coordinator(tmp_path)
    now = datetime(2026, 8, 4, 14, 0, tzinfo=UTC)
    service.process_events(
        [
            request_event(
                sequence=1,
                time=now,
                action="pending_request",
                comment="STR B1",
                price=4081.36,
            ),
            request_event(
                sequence=2,
                time=now + timedelta(milliseconds=100),
                action="pending_request",
                comment="STR S1",
                price=4078.64,
            ),
        ],
        now=now + timedelta(milliseconds=200),
    )
    first_cycle_id = read_shadow_command(
        tmp_path / "command.csv"
    ).cycle_id
    service.process_events(
        [
            request_event(
                sequence=3,
                time=now + timedelta(seconds=10),
                action="cancel_request",
                comment="STR S30",
            )
        ],
        now=now + timedelta(seconds=10),
    )
    write_ack(tmp_path / "ack.csv", status="FLAT", command_seq=2)
    service.process_events(
        [
            request_event(
                sequence=4,
                time=now + timedelta(seconds=30),
                action="pending_request",
                comment="STR B1",
                price=4082.36,
            ),
            request_event(
                sequence=5,
                time=now + timedelta(seconds=30, milliseconds=100),
                action="pending_request",
                comment="STR S1",
                price=4079.64,
            ),
        ],
        now=now + timedelta(seconds=30, milliseconds=200),
    )

    archived = [
        json.loads(line)
        for line in (tmp_path / "target-cycles.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert any(
        event["cycle_id"] == first_cycle_id
        and event["kind"] == "cycle_complete"
        for event in archived
    )


def test_stale_flat_ack_cannot_overwrite_unprocessed_reset(
    tmp_path: Path,
) -> None:
    service, command_path, _ = coordinator(tmp_path)
    now = datetime(2026, 8, 4, 14, 0, tzinfo=UTC)
    service.process_events(
        [
            request_event(
                sequence=1,
                time=now,
                action="pending_request",
                comment="STR B1",
                price=4081.36,
            ),
            request_event(
                sequence=2,
                time=now + timedelta(milliseconds=100),
                action="pending_request",
                comment="STR S1",
                price=4078.64,
            ),
        ],
        now=now + timedelta(milliseconds=200),
    )
    service.process_events(
        [
            request_event(
                sequence=3,
                time=now + timedelta(seconds=10),
                action="cancel_request",
                comment="STR S30",
            )
        ],
        now=now + timedelta(seconds=10),
    )
    assert read_shadow_command(command_path).command == "RESET"
    write_ack(tmp_path / "ack.csv", status="FLAT", command_seq=1)

    result = service.process_events(
        [
            request_event(
                sequence=4,
                time=now + timedelta(seconds=30),
                action="pending_request",
                comment="STR B1",
                price=4082.36,
            ),
            request_event(
                sequence=5,
                time=now + timedelta(seconds=30, milliseconds=100),
                action="pending_request",
                comment="STR S1",
                price=4079.64,
            ),
        ],
        now=now + timedelta(seconds=30, milliseconds=200),
    )

    assert result["commands_written"] == 0
    assert result["skipped_cycles"] == 1
    assert read_shadow_command(command_path).command == "RESET"


def test_shadow_coordinator_cli_processes_existing_probe_once(
    tmp_path: Path,
) -> None:
    now = datetime.now(tz=UTC)
    probe_root = tmp_path / "probe"
    session = probe_root / "session"
    session.mkdir(parents=True)
    transaction_path = session / "transactions-20260804-14.csv"
    fields = (
        "utc_time",
        "sequence",
        "event_kind",
        "entity_comment",
        "request_comment",
        "request_volume",
        "request_price",
        "request_sl",
        "request_tp",
        "result_request_id",
        "result_retcode",
    )
    with transaction_path.open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for sequence, comment, price in (
            (1, "STR B1", 4081.36),
            (2, "STR S1", 4078.64),
        ):
            writer.writerow(
                {
                    "utc_time": (
                        now.isoformat().replace("+00:00", "Z")
                        if sequence == 1
                        else (now + timedelta(milliseconds=100))
                        .isoformat()
                        .replace("+00:00", "Z")
                    ),
                    "sequence": sequence,
                    "event_kind": "pending_request",
                    "entity_comment": comment,
                    "request_comment": comment,
                    "request_volume": 0.01,
                    "request_price": price,
                    "request_sl": 0,
                    "request_tp": 0,
                    "result_request_id": sequence,
                    "result_retcode": 10008,
                }
            )

    ack_path = tmp_path / "ack.csv"
    write_ack(ack_path, status="FLAT")
    command_path = tmp_path / "command.csv"
    completed = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--target-probe-root",
            str(probe_root),
            "--command-path",
            str(command_path),
            "--ack-path",
            str(ack_path),
            "--state-path",
            str(tmp_path / "state.json"),
            "--target-archive-path",
            str(tmp_path / "target.jsonl"),
            "--active",
            "--once",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert read_shadow_command(command_path).command == "START"


def test_shadow_coordinator_cli_rejects_non_candidate_remote_root(
    tmp_path: Path,
) -> None:
    probe_root = tmp_path / "probe"
    probe_root.mkdir()
    completed = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--target-probe-root",
            str(probe_root),
            "--state-path",
            str(tmp_path / "state.json"),
            "--target-archive-path",
            str(tmp_path / "target.jsonl"),
            "--remote-ssh-alias",
            "candidate-vps",
            "--remote-root",
            "/opt/straddle-replica-demo",
            "--remote-command-path",
            "/opt/straddle-replica-demo/command.csv",
            "--remote-ack-path",
            "/opt/straddle-replica-demo/ack.csv",
            "--once",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode != 0
    assert "candidate root" in completed.stderr.lower()


def test_shadow_coordinator_cli_uses_observer_after_clean_boundary(
    tmp_path: Path,
) -> None:
    now = datetime.now(tz=UTC)
    observer_root = tmp_path / "observer"
    session_id = "session-observer"
    session = observer_root / session_id
    session.mkdir(parents=True)
    (observer_root / "current-session.json").write_text(
        json.dumps({"session_id": session_id}),
        encoding="utf-8",
    )
    (session / "manifest.json").write_text("{}", encoding="utf-8")
    heartbeat_path = session / "heartbeat.json"
    snapshot_path = session / "snapshots-20260804-20.jsonl"

    def write_heartbeat(at: datetime) -> None:
        heartbeat_path.write_text(
            json.dumps(
                {
                    "capture_time_utc": at.isoformat(),
                    "healthy": True,
                    "stopped": False,
                }
            ),
            encoding="utf-8",
        )

    def append_snapshot(
        *,
        at: datetime,
        sequence: int,
        orders: list[dict],
    ) -> None:
        with snapshot_path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "capture_time_utc": at.isoformat(),
                        "sequence": sequence,
                        "orders": orders,
                        "positions": [],
                    }
                )
                + "\n"
            )
        write_heartbeat(at)

    def order(
        ticket: int,
        comment: str,
        price: float,
        at: datetime,
    ) -> dict:
        return {
            "ticket": ticket,
            "comment": comment,
            "price_open": price,
            "volume_initial": 0.01,
            "time_setup_msc": int(at.timestamp() * 1000),
        }

    initial_orders = [
        order(101, "STR B1", 4081.36, now),
        order(
            102,
            "STR S1",
            4078.64,
            now + timedelta(milliseconds=100),
        ),
    ]
    append_snapshot(at=now, sequence=1, orders=initial_orders)

    ack_path = tmp_path / "ack.csv"
    command_path = tmp_path / "command.csv"
    coordinator_state = tmp_path / "coordinator.json"
    adapter_state = tmp_path / "adapter.json"
    archive_path = tmp_path / "target.jsonl"
    write_ack(ack_path, status="FLAT")
    base_arguments = [
        sys.executable,
        str(TOOL),
        "--target-observer-root",
        str(observer_root),
        "--observer-state-path",
        str(adapter_state),
        "--command-path",
        str(command_path),
        "--ack-path",
        str(ack_path),
        "--state-path",
        str(coordinator_state),
        "--target-archive-path",
        str(archive_path),
        "--active",
        "--once",
    ]

    seeded = subprocess.run(
        base_arguments,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert seeded.returncode == 0, seeded.stderr
    assert not command_path.exists()

    flat_time = datetime.now(tz=UTC) - timedelta(seconds=2)
    append_snapshot(at=flat_time, sequence=2, orders=[])
    settling = subprocess.run(
        base_arguments,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert settling.returncode == 0, settling.stderr
    assert not command_path.exists()

    confirmed_flat_time = datetime.now(tz=UTC)
    append_snapshot(
        at=confirmed_flat_time,
        sequence=3,
        orders=[],
    )
    reset = subprocess.run(
        base_arguments,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert reset.returncode == 0, reset.stderr
    assert read_shadow_command(command_path).command == "RESET"

    write_ack(ack_path, status="FLAT", command_seq=1)
    start_time = datetime.now(tz=UTC)
    next_orders = [
        order(201, "STR B1", 4082.36, start_time),
        order(
            202,
            "STR S1",
            4079.64,
            start_time + timedelta(milliseconds=100),
        ),
    ]
    append_snapshot(at=start_time, sequence=4, orders=next_orders)
    started = subprocess.run(
        base_arguments,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert started.returncode == 0, started.stderr
    command = read_shadow_command(command_path)
    assert command.command == "START"
    assert command.command_seq == 2
    assert command.anchor == 4081.0
    assert command.step == 1.36


def test_continuous_coordinator_waits_on_stale_observer_heartbeat(
    tmp_path: Path,
) -> None:
    observer_root = build_stale_observer(tmp_path)
    health_path = tmp_path / "coordinator-health.json"
    process = subprocess.Popen(
        [
            sys.executable,
            str(TOOL),
            "--target-observer-root",
            str(observer_root),
            "--observer-state-path",
            str(tmp_path / "adapter.json"),
            "--command-path",
            str(tmp_path / "command.csv"),
            "--ack-path",
            str(tmp_path / "ack.csv"),
            "--state-path",
            str(tmp_path / "state.json"),
            "--target-archive-path",
            str(tmp_path / "target.jsonl"),
            "--health-path",
            str(health_path),
            "--retry-ms",
            "50",
        ],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        health = wait_for_json_status(
            health_path,
            "WAITING_FOR_TARGET",
        )
        assert process.poll() is None
        assert health["error_type"] == "RuntimeError"
        assert "heartbeat is stale" in health["error"]
    finally:
        process.terminate()
        process.communicate(timeout=5)
