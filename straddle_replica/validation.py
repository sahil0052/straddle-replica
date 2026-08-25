from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .compare import (
    AlignedComparisonResult,
    ComparisonTolerance,
    Event,
    align_events,
)
from .report import MT5Report, PositionRecord
from .tester_report import MT5TesterReport


@dataclass(frozen=True)
class TesterLifecycleComparison:
    report_fills: int
    tester_fills: int
    report_stop_exits: int
    tester_stop_exits: int
    report_basket_exits: int
    tester_basket_exits: int
    fill_alignment: AlignedComparisonResult


def _report_fill_events(report: MT5Report) -> list[Event]:
    if not report.deployments:
        return []
    start = min(deployment.start for deployment in report.deployments)
    return [
        Event(
            time=deal.time,
            kind="fill",
            comment=deal.comment or "",
            side=deal.deal_type,
            volume=deal.volume,
            price=deal.price or 0.0,
        )
        for deal in sorted(report.deals, key=lambda item: (item.time, item.deal_id))
        if deal.time >= start
        and deal.symbol is not None
        and deal.direction == "in"
    ]


def _tester_fill_events(report: MT5TesterReport) -> list[Event]:
    return [
        Event(
            time=deal.time,
            kind="fill",
            comment=deal.comment,
            side=deal.deal_type,
            volume=deal.volume,
            price=deal.price,
        )
        for deal in sorted(report.deals, key=lambda item: (item.time, item.deal_id))
        if deal.direction == "in"
    ]


def compare_report_fills_to_tester(
    report: MT5Report,
    tester: MT5TesterReport,
    tolerance: ComparisonTolerance | None = None,
) -> TesterLifecycleComparison:
    tolerance = tolerance or ComparisonTolerance(
        time_seconds=1.0,
        price=0.01,
    )
    report_fills = _report_fill_events(report)
    tester_fills = _tester_fill_events(tester)
    start = (
        min(deployment.start for deployment in report.deployments)
        if report.deployments
        else None
    )
    report_exits = [
        deal
        for deal in report.deals
        if deal.direction == "out"
        and deal.symbol is not None
        and (start is None or deal.time >= start)
    ]
    tester_exits = [
        deal for deal in tester.deals if deal.direction == "out"
    ]
    return TesterLifecycleComparison(
        report_fills=len(report_fills),
        tester_fills=len(tester_fills),
        report_stop_exits=sum(
            (deal.comment or "").startswith("[sl") for deal in report_exits
        ),
        tester_stop_exits=sum(
            deal.comment.startswith(("sl ", "[sl")) for deal in tester_exits
        ),
        report_basket_exits=sum(
            deal.comment == "STR CLOSE" for deal in report_exits
        ),
        tester_basket_exits=sum(
            deal.comment == "STR CLOSE" for deal in tester_exits
        ),
        fill_alignment=align_events(
            report_fills,
            tester_fills,
            tolerance,
        ),
    )


def _report_lifecycle_events(report: MT5Report) -> list[Event]:
    if not report.deployments:
        return []
    start = min(deployment.start for deployment in report.deployments)
    positions_by_close: dict[datetime, list[PositionRecord]] = {}
    for position in report.closed_positions:
        if position.close_time is not None:
            positions_by_close.setdefault(position.close_time, []).append(position)

    events: list[Event] = []
    for deal in sorted(report.deals, key=lambda item: (item.time, item.deal_id)):
        if deal.time < start or deal.symbol is None:
            continue
        if deal.direction == "in":
            events.append(
                Event(
                    time=deal.time,
                    kind="fill",
                    comment=deal.comment or "",
                    side=deal.deal_type,
                    volume=deal.volume,
                    price=deal.price or 0.0,
                )
            )
            continue
        if deal.direction != "out":
            continue

        candidates = positions_by_close.get(deal.time, [])
        position = next(
            (
                item
                for item in candidates
                if abs(item.volume - deal.volume) <= 1e-9
            ),
            candidates[0] if candidates else None,
        )
        if position is not None:
            candidates.remove(position)
        exit_comment = deal.comment or ""
        if exit_comment.startswith("[sl"):
            kind = "stop_exit"
        elif exit_comment == "STR CLOSE":
            kind = "close_fill"
        else:
            kind = "exit"
        events.append(
            Event(
                time=deal.time,
                kind=kind,
                comment=(position.comment or "") if position else "",
                side=(
                    position.side
                    if position
                    else ("sell" if deal.deal_type == "buy" else "buy")
                ),
                volume=deal.volume,
                price=deal.price or 0.0,
            )
        )
    return events


def _telemetry_lifecycle_events(path: Path) -> list[Event]:
    events: list[Event] = []
    with path.open(encoding="utf-8", newline="") as source:
        for row in csv.DictReader(source):
            if row["kind"] not in {"fill", "stop_exit", "close_fill"}:
                continue
            event_time = datetime.fromisoformat(
                row["time"].replace("Z", "+00:00")
            )
            if event_time.tzinfo is not None:
                event_time = event_time.astimezone(timezone.utc).replace(
                    tzinfo=None
                )
            events.append(
                Event(
                    time=event_time,
                    kind=row["kind"],
                    comment=row["comment"] or row.get("level", ""),
                    side=row["side"],
                    volume=float(row["volume"]),
                    price=float(row["price"]),
                )
            )
    return events


def _golden_lifecycle_events(golden_dir: Path) -> list[Event]:
    with (golden_dir / "deployments.csv").open(
        encoding="utf-8",
        newline="",
    ) as source:
        starts = [
            datetime.fromisoformat(row["start"])
            for row in csv.DictReader(source)
        ]
    if not starts:
        return []
    start = min(starts)

    positions_by_close: dict[datetime, list[dict[str, str]]] = {}
    with (golden_dir / "positions.csv").open(
        encoding="utf-8",
        newline="",
    ) as source:
        for row in csv.DictReader(source):
            if not row["close_time"]:
                continue
            close_time = datetime.fromisoformat(row["close_time"])
            positions_by_close.setdefault(close_time, []).append(row)

    with (golden_dir / "deals.csv").open(
        encoding="utf-8",
        newline="",
    ) as source:
        deals = sorted(
            csv.DictReader(source),
            key=lambda row: (
                datetime.fromisoformat(row["time"]),
                int(row["deal_id"]),
            ),
        )

    events: list[Event] = []
    for deal in deals:
        event_time = datetime.fromisoformat(deal["time"])
        if event_time < start or not deal["symbol"]:
            continue
        volume = float(deal["volume"])
        price = float(deal["price"] or 0.0)
        if deal["direction"] == "in":
            events.append(
                Event(
                    time=event_time,
                    kind="fill",
                    comment=deal["comment"].strip(),
                    side=deal["deal_type"],
                    volume=volume,
                    price=price,
                )
            )
            continue
        if deal["direction"] != "out":
            continue

        candidates = positions_by_close.get(event_time, [])
        position = next(
            (
                item
                for item in candidates
                if abs(float(item["volume"]) - volume) <= 1e-9
            ),
            candidates[0] if candidates else None,
        )
        if position is not None:
            candidates.remove(position)
        exit_comment = deal["comment"].strip()
        kind = (
            "stop_exit"
            if exit_comment.startswith("[sl")
            else "close_fill"
            if exit_comment == "STR CLOSE"
            else "exit"
        )
        events.append(
            Event(
                time=event_time,
                kind=kind,
                comment=position["comment"].strip() if position else "",
                side=(
                    position["side"]
                    if position
                    else (
                        "sell"
                        if deal["deal_type"] == "buy"
                        else "buy"
                    )
                ),
                volume=volume,
                price=price,
            )
        )
    return events


def compare_golden_lifecycle_to_telemetry(
    golden_dir: Path,
    telemetry_path: Path,
    tolerance: ComparisonTolerance | None = None,
) -> AlignedComparisonResult:
    return align_events(
        _golden_lifecycle_events(golden_dir),
        _telemetry_lifecycle_events(telemetry_path),
        tolerance
        or ComparisonTolerance(
            time_seconds=1.0,
            price=0.01,
        ),
    )


def compare_report_lifecycle_to_telemetry(
    report: MT5Report,
    telemetry_path: Path,
    tolerance: ComparisonTolerance | None = None,
) -> AlignedComparisonResult:
    return align_events(
        _report_lifecycle_events(report),
        _telemetry_lifecycle_events(telemetry_path),
        tolerance
        or ComparisonTolerance(
            time_seconds=1.0,
            price=0.01,
        ),
    )
