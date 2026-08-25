from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class StopChange:
    position_id: int
    time: datetime
    stop_price: float


@dataclass(frozen=True)
class StopExit:
    position_id: int
    time: datetime
    stop_price: float


@dataclass(frozen=True)
class SerializedStopRun:
    stop_price: float
    first_exit_time: datetime
    position_ids: tuple[int, ...]
    exit_gaps_seconds: tuple[float, ...]
    ticket_order: str
    assigned_before_first_exit: int
    all_stops_set_before_first_exit: bool
    latest_assignment_lead_seconds: float | None


def detect_serialized_stop_runs(
    exits: list[StopExit],
    changes: list[StopChange],
    *,
    minimum_gap_seconds: float = 18.0,
    maximum_gap_seconds: float = 22.0,
    price_tolerance: float = 0.02,
) -> tuple[SerializedStopRun, ...]:
    ordered_exits = sorted(exits, key=lambda item: item.time)
    grouped_exits: list[list[StopExit]] = []
    current: list[StopExit] = []
    for item in ordered_exits:
        if not current:
            current = [item]
            continue
        gap = (item.time - current[-1].time).total_seconds()
        same_stop = (
            abs(item.stop_price - current[-1].stop_price)
            <= price_tolerance
        )
        if same_stop and minimum_gap_seconds <= gap <= maximum_gap_seconds:
            current.append(item)
            continue
        if len(current) >= 2:
            grouped_exits.append(current)
        current = [item]
    if len(current) >= 2:
        grouped_exits.append(current)

    changes_by_position: dict[int, list[StopChange]] = defaultdict(list)
    for change in changes:
        changes_by_position[change.position_id].append(change)
    for position_changes in changes_by_position.values():
        position_changes.sort(key=lambda item: item.time)

    runs: list[SerializedStopRun] = []
    for group in grouped_exits:
        first_exit = group[0].time
        target_stop = group[0].stop_price
        qualifying_assignments: list[StopChange] = []
        for item in group:
            prior_changes = [
                change
                for change in changes_by_position.get(item.position_id, [])
                if change.time <= first_exit
            ]
            if not prior_changes:
                continue
            latest = prior_changes[-1]
            if abs(latest.stop_price - target_stop) <= price_tolerance:
                qualifying_assignments.append(latest)

        position_ids = tuple(item.position_id for item in group)
        ticket_order = "mixed"
        if position_ids == tuple(sorted(position_ids)):
            ticket_order = "ascending"
        elif position_ids == tuple(sorted(position_ids, reverse=True)):
            ticket_order = "descending"
        latest_assignment_lead = (
            (
                first_exit
                - max(item.time for item in qualifying_assignments)
            ).total_seconds()
            if qualifying_assignments
            else None
        )
        runs.append(
            SerializedStopRun(
                stop_price=target_stop,
                first_exit_time=first_exit,
                position_ids=position_ids,
                exit_gaps_seconds=tuple(
                    (right.time - left.time).total_seconds()
                    for left, right in zip(group, group[1:])
                ),
                ticket_order=ticket_order,
                assigned_before_first_exit=len(qualifying_assignments),
                all_stops_set_before_first_exit=(
                    len(qualifying_assignments) == len(group)
                ),
                latest_assignment_lead_seconds=latest_assignment_lead,
            )
        )
    return tuple(runs)
