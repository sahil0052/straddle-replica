from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


UTC = timezone.utc
ACTIVE_GAP_THRESHOLD_MS = 300_000
REQUEST_KINDS = {
    "pending_request",
    "stop_request",
    "cancel_request",
    "close_request",
    "deal_request",
    "trade_request",
}


def _parse_time(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _integer(value: object) -> int | None:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return None


def _sessions(root: Path) -> list[Path]:
    sessions = {
        path.parent
        for pattern in (
            "transactions-*.csv",
            "ticks-*.csv",
            "heartbeat-*.csv",
        )
        for path in root.glob(f"**/{pattern}")
    }
    return sorted(sessions, key=lambda path: str(path))


def _rows(
    paths: Iterable[Path],
    *,
    started: datetime,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in sorted(paths):
        with path.open(
            encoding="utf-8",
            errors="ignore",
            newline="",
        ) as handle:
            for row in csv.DictReader(handle):
                value = row.get("utc_time")
                if not value:
                    continue
                try:
                    captured = _parse_time(value)
                except ValueError:
                    continue
                if _integer(row.get("sequence")) is None:
                    continue
                if captured >= started:
                    rows.append(dict(row))
    return rows


def _sequence_health(rows: Iterable[dict[str, str]]) -> tuple[int, int]:
    gaps = 0
    duplicates = 0
    previous: int | None = None
    for row in rows:
        sequence = _integer(row.get("sequence"))
        if sequence is None or sequence <= 0:
            continue
        if previous is not None:
            if sequence > previous + 1:
                gaps += sequence - previous - 1
            elif sequence <= previous:
                duplicates += 1
        previous = sequence
    return gaps, duplicates


def analyze_probe_health(
    root: Path,
    *,
    certification_started_utc: datetime | str,
) -> dict[str, Any]:
    started = (
        _parse_time(certification_started_utc)
        if isinstance(certification_started_utc, str)
        else certification_started_utc.astimezone(UTC)
    )
    sequence_gaps = 0
    duplicate_sequences = 0
    dropped_transactions = 0
    maximum_queue_depth = 0
    request_event_count = 0
    active_market_ms = 0
    active_sessions = 0
    stream_rows = {
        "transactions": 0,
        "ticks": 0,
        "heartbeats": 0,
    }

    for session in _sessions(root):
        transactions = _rows(
            session.glob("transactions-*.csv"),
            started=started,
        )
        ticks = _rows(session.glob("ticks-*.csv"), started=started)
        heartbeats = _rows(
            session.glob("heartbeat-*.csv"),
            started=started,
        )
        if not transactions and not ticks and not heartbeats:
            continue
        active_sessions += 1
        stream_rows["transactions"] += len(transactions)
        stream_rows["ticks"] += len(ticks)
        stream_rows["heartbeats"] += len(heartbeats)

        for rows in (transactions, ticks, heartbeats):
            gaps, duplicates = _sequence_health(rows)
            sequence_gaps += gaps
            duplicate_sequences += duplicates

        request_event_count += sum(
            str(row.get("event_kind") or "") in REQUEST_KINDS
            for row in transactions
        )
        dropped_values = [
            value
            for row in heartbeats
            if (
                value := _integer(row.get("dropped_transactions"))
            ) is not None
        ]
        if dropped_values:
            dropped_transactions += max(
                0,
                max(dropped_values) - dropped_values[0],
            )
        for row in heartbeats:
            queue_depth = _integer(row.get("queue_depth"))
            if queue_depth is None:
                continue
            maximum_queue_depth = max(
                maximum_queue_depth,
                queue_depth,
            )

        tick_times = [
            value
            for row in ticks
            if (
                value := _integer(row.get("time_msc"))
            ) is not None
            and value > 0
        ]
        for left, right in zip(tick_times, tick_times[1:]):
            gap = right - left
            if 0 <= gap <= ACTIVE_GAP_THRESHOLD_MS:
                active_market_ms += gap

    session_restarts = max(0, active_sessions - 1)
    request_evidence = request_event_count > 0
    failures = []
    if sequence_gaps:
        failures.append("sequence_gaps")
    if duplicate_sequences:
        failures.append("duplicate_sequences")
    if dropped_transactions:
        failures.append("dropped_transactions")
    if session_restarts:
        failures.append("session_restarts")
    if not request_evidence:
        failures.append("direct_request_evidence")

    return {
        "certification_started_utc": started.isoformat(),
        "market_open_hours": round(
            active_market_ms / 3_600_000,
            4,
        ),
        "market_active_gap_threshold_ms": ACTIVE_GAP_THRESHOLD_MS,
        "sequence_gaps": sequence_gaps,
        "duplicate_sequences": duplicate_sequences,
        "dropped_transactions": dropped_transactions,
        "session_count": active_sessions,
        "session_restarts": session_restarts,
        "maximum_queue_depth": maximum_queue_depth,
        "direct_request_evidence_available": request_evidence,
        "request_event_count": request_event_count,
        "stream_rows": stream_rows,
        "operational_failures": failures,
    }
