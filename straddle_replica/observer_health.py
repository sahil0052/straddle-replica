from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


UTC = timezone.utc


def _parse_time(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _complete_jsonl_rows(paths: list[Path]) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    invalid_rows = 0
    for path in sorted(paths):
        with path.open(encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                if not line.endswith("\n") or not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    invalid_rows += 1
                    continue
                if not isinstance(row, dict):
                    invalid_rows += 1
                    continue
                rows.append(row)
    return rows, invalid_rows


def analyze_observer_health(
    session: Path,
    *,
    certification_started_utc: datetime | str,
) -> dict[str, Any]:
    started = _parse_time(certification_started_utc)
    started_msc = int(started.timestamp() * 1000)
    rows, invalid_tick_rows = _complete_jsonl_rows(
        list(session.glob("ticks-*.jsonl"))
    )
    tick_rows: list[dict[str, Any]] = []
    for row in rows:
        try:
            time_msc = int(row.get("time_msc") or 0)
            if time_msc <= 0 and row.get("capture_time_utc"):
                time_msc = int(
                    _parse_time(str(row["capture_time_utc"])).timestamp()
                    * 1000
                )
            int(row.get("sequence") or 0)
        except (TypeError, ValueError):
            invalid_tick_rows += 1
            continue
        if time_msc < started_msc:
            continue
        tick_rows.append({**row, "time_msc": time_msc})

    tick_rows.sort(key=lambda row: int(row["time_msc"]))
    times = [int(row["time_msc"]) for row in tick_rows]
    active_ms = sum(
        right - left
        for left, right in zip(times, times[1:])
        if 0 <= right - left <= 300_000
    )
    previous = None
    sequence_gaps = 0
    duplicate_sequences = 0
    for row in tick_rows:
        sequence = int(row.get("sequence") or 0)
        if previous is not None:
            if sequence > previous + 1:
                sequence_gaps += sequence - previous - 1
            elif sequence <= previous:
                duplicate_sequences += 1
        previous = sequence

    heartbeat_path = session / "heartbeat.json"
    heartbeat: dict[str, Any] = {}
    operational_failures: list[str] = []
    if heartbeat_path.exists():
        try:
            payload = json.loads(heartbeat_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                heartbeat = payload
            else:
                operational_failures.append("heartbeat_invalid")
        except (OSError, json.JSONDecodeError):
            operational_failures.append("heartbeat_invalid")
    else:
        operational_failures.append("heartbeat_missing")

    read_only_verified = bool(heartbeat.get("read_only_verified"))
    heartbeat_healthy = bool(heartbeat.get("healthy"))
    collector_stopped = bool(heartbeat.get("stopped"))
    dropped_transactions = int(
        heartbeat.get("dropped_transactions") or 0
    )
    if not read_only_verified:
        operational_failures.append("read_only_not_verified")
    if not heartbeat_healthy:
        operational_failures.append("heartbeat_unhealthy")
    if collector_stopped:
        operational_failures.append("collector_stopped")
    if dropped_transactions:
        operational_failures.append("dropped_transactions")
    if invalid_tick_rows:
        operational_failures.append("invalid_tick_rows")

    return {
        "session_id": session.name,
        "certification_started_utc": started.isoformat(),
        "tick_count": len(tick_rows),
        "market_open_hours": round(active_ms / 3_600_000.0, 4),
        "sequence_gaps": sequence_gaps,
        "duplicate_sequences": duplicate_sequences,
        "dropped_transactions": dropped_transactions,
        "session_restarts": 0,
        "read_only_verified": read_only_verified,
        "heartbeat_healthy": heartbeat_healthy,
        "collector_stopped": collector_stopped,
        "invalid_tick_rows": invalid_tick_rows,
        "direct_request_evidence_available": False,
        "operational_failures": sorted(set(operational_failures)),
    }
