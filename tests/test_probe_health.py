from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys

from straddle_replica.probe_health import analyze_probe_health


UTC = timezone.utc
ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "analyze_probe_health.py"


def write_csv(
    path: Path,
    *,
    fields: tuple[str, ...],
    rows: list[dict],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def build_healthy_session(root: Path, start: datetime) -> None:
    session = root / "session-1"
    write_csv(
        session / "transactions-1.csv",
        fields=("utc_time", "sequence", "event_kind"),
        rows=[
            {
                "utc_time": start.isoformat(),
                "sequence": 1,
                "event_kind": "pending_request",
            },
            {
                "utc_time": (start + timedelta(seconds=1)).isoformat(),
                "sequence": 2,
                "event_kind": "order_add",
            },
        ],
    )
    write_csv(
        session / "ticks-1.csv",
        fields=("utc_time", "sequence", "time_msc"),
        rows=[
            {
                "utc_time": start.isoformat(),
                "sequence": 1,
                "time_msc": 1_000,
            },
            {
                "utc_time": (start + timedelta(seconds=60)).isoformat(),
                "sequence": 2,
                "time_msc": 61_000,
            },
        ],
    )
    write_csv(
        session / "heartbeat-1.csv",
        fields=(
            "utc_time",
            "sequence",
            "queue_depth",
            "dropped_transactions",
        ),
        rows=[
            {
                "utc_time": start.isoformat(),
                "sequence": 1,
                "queue_depth": 0,
                "dropped_transactions": 0,
            },
            {
                "utc_time": (start + timedelta(seconds=1)).isoformat(),
                "sequence": 2,
                "queue_depth": 2,
                "dropped_transactions": 0,
            },
        ],
    )


def test_probe_health_derives_clean_capture_metrics(tmp_path: Path) -> None:
    start = datetime(2026, 8, 4, 14, 0, tzinfo=UTC)
    build_healthy_session(tmp_path, start)

    result = analyze_probe_health(
        tmp_path,
        certification_started_utc=start,
    )

    assert result["market_open_hours"] == 0.0167
    assert result["sequence_gaps"] == 0
    assert result["duplicate_sequences"] == 0
    assert result["dropped_transactions"] == 0
    assert result["session_restarts"] == 0
    assert result["direct_request_evidence_available"] is True
    assert result["operational_failures"] == []


def test_probe_health_fails_closed_for_gaps_drops_and_session_restart(
    tmp_path: Path,
) -> None:
    start = datetime(2026, 8, 4, 14, 0, tzinfo=UTC)
    build_healthy_session(tmp_path / "old", start)
    build_healthy_session(tmp_path / "new", start + timedelta(minutes=1))
    newest = tmp_path / "new" / "session-1"
    write_csv(
        newest / "transactions-1.csv",
        fields=("utc_time", "sequence", "event_kind"),
        rows=[
            {
                "utc_time": (start + timedelta(minutes=1)).isoformat(),
                "sequence": 1,
                "event_kind": "order_add",
            },
            {
                "utc_time": (start + timedelta(minutes=1, seconds=1))
                .isoformat(),
                "sequence": 3,
                "event_kind": "order_add",
            },
            {
                "utc_time": (start + timedelta(minutes=1, seconds=2))
                .isoformat(),
                "sequence": 3,
                "event_kind": "order_add",
            },
        ],
    )
    write_csv(
        newest / "heartbeat-1.csv",
        fields=(
            "utc_time",
            "sequence",
            "queue_depth",
            "dropped_transactions",
        ),
        rows=[
            {
                "utc_time": (start + timedelta(minutes=1)).isoformat(),
                "sequence": 1,
                "queue_depth": 100,
                "dropped_transactions": 0,
            },
            {
                "utc_time": (
                    start + timedelta(minutes=1, seconds=1)
                ).isoformat(),
                "sequence": 2,
                "queue_depth": 8192,
                "dropped_transactions": 2,
            }
        ],
    )

    result = analyze_probe_health(
        tmp_path,
        certification_started_utc=start,
    )

    assert result["sequence_gaps"] == 1
    assert result["duplicate_sequences"] == 1
    assert result["dropped_transactions"] == 2
    assert result["session_restarts"] == 1
    assert result["direct_request_evidence_available"] is True
    assert {
        "sequence_gaps",
        "duplicate_sequences",
        "dropped_transactions",
        "session_restarts",
    }.issubset(result["operational_failures"])


def test_probe_health_excludes_closed_market_tick_gap(
    tmp_path: Path,
) -> None:
    start = datetime(2026, 8, 4, 14, 0, tzinfo=UTC)
    session = tmp_path / "session-1"
    write_csv(
        session / "ticks-1.csv",
        fields=("utc_time", "sequence", "time_msc"),
        rows=[
            {
                "utc_time": start.isoformat(),
                "sequence": 1,
                "time_msc": 1_000,
            },
            {
                "utc_time": (start + timedelta(seconds=60)).isoformat(),
                "sequence": 2,
                "time_msc": 61_000,
            },
            {
                "utc_time": (start + timedelta(hours=10)).isoformat(),
                "sequence": 3,
                "time_msc": 36_001_000,
            },
        ],
    )

    result = analyze_probe_health(
        tmp_path,
        certification_started_utc=start,
    )

    assert result["market_open_hours"] == 0.0167


def test_probe_health_uses_dropped_counter_delta_after_run_start(
    tmp_path: Path,
) -> None:
    start = datetime(2026, 8, 4, 14, 0, tzinfo=UTC)
    session = tmp_path / "session-1"
    write_csv(
        session / "heartbeat-1.csv",
        fields=(
            "utc_time",
            "sequence",
            "queue_depth",
            "dropped_transactions",
        ),
        rows=[
            {
                "utc_time": start.isoformat(),
                "sequence": 100,
                "queue_depth": 0,
                "dropped_transactions": 3,
            },
            {
                "utc_time": (start + timedelta(seconds=1)).isoformat(),
                "sequence": 101,
                "queue_depth": 0,
                "dropped_transactions": 3,
            },
        ],
    )

    result = analyze_probe_health(
        tmp_path,
        certification_started_utc=start,
    )

    assert result["dropped_transactions"] == 0
    assert "dropped_transactions" not in result["operational_failures"]


def test_probe_health_ignores_partially_written_numeric_row(
    tmp_path: Path,
) -> None:
    start = datetime(2026, 8, 4, 14, 0, tzinfo=UTC)
    session = tmp_path / "session-1"
    write_csv(
        session / "transactions-1.csv",
        fields=("utc_time", "sequence", "event_kind"),
        rows=[
            {
                "utc_time": start.isoformat(),
                "sequence": 1,
                "event_kind": "pending_request",
            },
            {
                "utc_time": (start + timedelta(seconds=1)).isoformat(),
                "sequence": "partial",
                "event_kind": "pending_request",
            },
        ],
    )

    result = analyze_probe_health(
        tmp_path,
        certification_started_utc=start,
    )

    assert result["sequence_gaps"] == 0
    assert result["request_event_count"] == 1


def test_probe_health_cli_writes_json(tmp_path: Path) -> None:
    start = datetime(2026, 8, 4, 14, 0, tzinfo=UTC)
    build_healthy_session(tmp_path / "probe", start)
    output = tmp_path / "health.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--probe-root",
            str(tmp_path / "probe"),
            "--certification-started-utc",
            start.isoformat(),
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
        "direct_request_evidence_available"
    ]
