from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import statistics
from typing import Any, Iterable


UTC = timezone.utc
COMPLETE_KINDS = {"cycle_complete", "shadow_reset_complete"}
RESTART_KINDS = {"cycle_restart", "restart_ready"}


@dataclass(frozen=True)
class AlignmentPlan:
    target_cycle_id: str
    target_complete_utc: datetime
    restart_delay_seconds: float
    restart_delay_sample_count: int
    launch_at_utc: datetime


def parse_utc(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def validate_bound_demo_preset(
    text: str,
    *,
    expected_login: int,
) -> None:
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", ";")) or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    if values.get("RequireDemoAccount", "").lower() != "true":
        raise ValueError("RequireDemoAccount must be true")
    if values.get("RequireBoundAccount", "").lower() != "true":
        raise ValueError("RequireBoundAccount must be true")
    if values.get("ExpectedAccountLogin") != str(expected_login):
        raise ValueError(
            "ExpectedAccountLogin does not match the dedicated demo"
        )


def _event_time(event: dict[str, Any]) -> datetime:
    return parse_utc(event["time_utc"])


def candidate_freeze_ready(
    events: Iterable[dict[str, Any]],
    *,
    cycle_id: str,
) -> bool:
    boundaries = sorted(
        (
            event
            for event in events
            if str(event.get("cycle_id") or "") == cycle_id
            and str(event.get("kind") or "")
            in COMPLETE_KINDS | RESTART_KINDS
            and event.get("time_utc")
        ),
        key=lambda event: (
            _event_time(event),
            int(event.get("sequence") or 0),
        ),
    )
    if not boundaries:
        return False
    return str(boundaries[-1].get("kind") or "") in COMPLETE_KINDS


def next_target_restart(
    events: Iterable[dict[str, Any]],
    *,
    after_utc: datetime,
) -> dict[str, Any] | None:
    cutoff = parse_utc(after_utc)
    return min(
        (
            event
            for event in events
            if str(event.get("kind") or "") in RESTART_KINDS
            and str(event.get("cycle_id") or "")
            and event.get("time_utc")
            and _event_time(event) > cutoff
        ),
        key=_event_time,
        default=None,
    )


def target_restart_delays(
    events: Iterable[dict[str, Any]],
    *,
    minimum: float = 10.0,
    maximum: float = 60.0,
) -> list[float]:
    if minimum < 0 or maximum < minimum:
        raise ValueError("Invalid target restart-delay range")
    by_cycle: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        cycle_id = str(event.get("cycle_id") or "")
        kind = str(event.get("kind") or "")
        if cycle_id and kind in COMPLETE_KINDS | RESTART_KINDS:
            if event.get("time_utc"):
                by_cycle[cycle_id].append(event)

    samples: list[tuple[datetime, float]] = []
    for cycle_events in by_cycle.values():
        ordered = sorted(cycle_events, key=_event_time)
        completes = [
            event
            for event in ordered
            if str(event.get("kind") or "") in COMPLETE_KINDS
        ]
        if not completes:
            continue
        completed = completes[-1]
        completed_at = _event_time(completed)
        restart = next(
            (
                event
                for event in ordered
                if str(event.get("kind") or "") in RESTART_KINDS
                and _event_time(event) >= completed_at
            ),
            None,
        )
        if restart is None:
            continue
        delay = (_event_time(restart) - completed_at).total_seconds()
        if minimum <= delay <= maximum:
            samples.append((completed_at, delay))
    samples.sort(key=lambda item: item[0])
    return [delay for _, delay in samples]


def plan_target_aligned_launch(
    events: Iterable[dict[str, Any]],
    *,
    frozen_at_utc: datetime,
    startup_lead_seconds: float,
) -> AlignmentPlan | None:
    if startup_lead_seconds < 0:
        raise ValueError("startup_lead_seconds must be non-negative")
    frozen_at_utc = parse_utc(frozen_at_utc)
    materialized = list(events)
    completion = min(
        (
            event
            for event in materialized
            if str(event.get("kind") or "") in COMPLETE_KINDS
            and str(event.get("cycle_id") or "")
            and event.get("time_utc")
            and _event_time(event) > frozen_at_utc
        ),
        key=_event_time,
        default=None,
    )
    if completion is None:
        return None
    samples = target_restart_delays(materialized)
    if not samples:
        return None
    restart_delay = float(statistics.median(samples[-5:]))
    completed_at = _event_time(completion)
    launch_at = completed_at + timedelta(
        seconds=restart_delay - startup_lead_seconds
    )
    return AlignmentPlan(
        target_cycle_id=str(completion["cycle_id"]),
        target_complete_utc=completed_at,
        restart_delay_seconds=restart_delay,
        restart_delay_sample_count=min(len(samples), 5),
        launch_at_utc=launch_at,
    )
