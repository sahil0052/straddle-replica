from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from straddle_replica.independent_cycle_archive import (
    IndependentCycleArchive,
    IndependentCycleArchiveConfig,
)


UTC = timezone.utc


def event(
    sequence: int,
    time: datetime,
    kind: str,
    comment: str = "",
    price: float = 0.0,
) -> dict:
    return {
        "session_id": "target-session",
        "sequence": sequence,
        "time_utc": time.isoformat(),
        "kind": kind,
        "comment": comment,
        "side": (
            "buy"
            if " B" in comment
            else "sell"
            if " S" in comment
            else ""
        ),
        "volume": 0.01 if comment else 0.0,
        "price": price,
        "sl": price if kind == "stop_request" else 0.0,
        "retcode": 10008 if kind == "pending_request" else 0,
        "evidence_grade": "BEST_EFFORT",
    }


def read_rows(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_archives_cycle_without_writing_shadow_commands(
    tmp_path: Path,
) -> None:
    archive_path = tmp_path / "target-cycles.jsonl"
    service = IndependentCycleArchive(
        IndependentCycleArchiveConfig(
            state_path=tmp_path / "state.json",
            archive_path=archive_path,
        )
    )
    started = datetime(2026, 8, 12, 0, 0, tzinfo=UTC)

    service.process_events(
        [
            event(1, started, "pending_request", "STR B1", 4081.36),
            event(
                2,
                started + timedelta(milliseconds=100),
                "pending_request",
                "STR S1",
                4078.64,
            ),
            event(
                3,
                started + timedelta(seconds=1),
                "stop_request",
                "STR B1",
                4081.56,
            ),
            event(
                4,
                started + timedelta(seconds=2),
                "cancel_request",
                "STR S30",
            ),
            event(
                5,
                started + timedelta(seconds=3),
                "cancel_request",
                "",
            ),
        ]
    )

    rows = read_rows(archive_path)
    assert rows[0]["kind"] == "cycle_start"
    assert [
        row["comment"]
        for row in rows
        if row["kind"] == "pending_request"
    ] == ["STR B1", "STR S1"]
    basket_trigger = next(
        row for row in rows if row["kind"] == "basket_trigger"
    )
    assert (
        basket_trigger["comparison_class"]
        == "BROKER_ACCEPTANCE_PROXY"
    )
    assert basket_trigger["capture_limit"] == (
        "basket_trigger_inferred_from_first_broker_close_or_cancel"
    )
    assert any(row["kind"] == "stop_request" for row in rows)
    assert rows[-1]["kind"] == "cycle_complete"
    assert not (tmp_path / "command.csv").exists()
    assert not (tmp_path / "ack.csv").exists()


def test_next_cycle_adds_restart_to_the_completed_cycle(
    tmp_path: Path,
) -> None:
    archive_path = tmp_path / "target-cycles.jsonl"
    service = IndependentCycleArchive(
        IndependentCycleArchiveConfig(
            state_path=tmp_path / "state.json",
            archive_path=archive_path,
        )
    )
    started = datetime(2026, 8, 12, 0, 0, tzinfo=UTC)
    service.process_events(
        [
            event(1, started, "pending_request", "STR B1", 4081.36),
            event(2, started, "pending_request", "STR S1", 4078.64),
            event(3, started + timedelta(seconds=1), "cancel_request"),
        ]
    )
    service.process_events(
        [
            event(
                4,
                started + timedelta(seconds=5),
                "pending_request",
                "STR B1",
                4082.36,
            ),
            event(
                5,
                started + timedelta(seconds=5, milliseconds=100),
                "pending_request",
                "STR S1",
                4079.64,
            ),
        ]
    )

    rows = read_rows(archive_path)
    cycle_ids = []
    for row in rows:
        if row["cycle_id"] not in cycle_ids:
            cycle_ids.append(row["cycle_id"])
    assert len(cycle_ids) == 2
    assert any(
        row["cycle_id"] == cycle_ids[0]
        and row["kind"] == "cycle_restart"
        for row in rows
    )
