from __future__ import annotations

import csv
import json
import re
import statistics
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


UTC = timezone.utc
COMMENT_RE = re.compile(r"^STR ([BS])(\d+)$")
PRICE_TOLERANCE = 0.011


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _comment_parts(comment: str) -> tuple[str, int] | None:
    match = COMMENT_RE.fullmatch(comment)
    if match is None:
        return None
    return match.group(1), int(match.group(2))


def _lot_for_level(level: int) -> float:
    if level <= 10:
        return 0.01
    if level <= 20:
        return 0.06
    return 0.15


def _expected_comments() -> list[str]:
    return [
        f"STR {side}{level}"
        for level in range(1, 31)
        for side in ("B", "S")
    ]


def _current_target_session(root: Path) -> Path:
    pointer_path = root / "current-session.json"
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    session = root / str(pointer["session_id"])
    if not session.is_dir():
        raise FileNotFoundError(f"Current target session is missing: {session}")
    return session


def _latest_jsonl_record(paths: Iterable[Path]) -> dict[str, Any]:
    for path in reversed(sorted(paths)):
        latest = ""
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                if line.strip():
                    latest = line
        if latest:
            return json.loads(latest)
    raise FileNotFoundError("No target snapshot record was found")


def _grid_estimate(records: Iterable[dict[str, Any]]) -> tuple[float, float]:
    prices: dict[str, float] = {}
    for record in records:
        comment = str(record.get("comment") or "")
        if _comment_parts(comment) is None:
            continue
        prices[comment] = float(record.get("price_open") or 0.0)

    anchors: list[float] = []
    steps: list[float] = []
    for level in range(1, 31):
        buy = prices.get(f"STR B{level}")
        sell = prices.get(f"STR S{level}")
        if buy is None or sell is None:
            continue
        anchors.append((buy + sell) / 2)
        steps.append((buy - sell) / (2 * level))
    if not anchors:
        raise ValueError("No paired buy/sell grid levels were available")
    return statistics.median(anchors), statistics.median(steps)


def _volume_matches(records: Iterable[dict[str, Any]]) -> bool:
    observed = False
    for record in records:
        parts = _comment_parts(str(record.get("comment") or ""))
        if parts is None:
            continue
        observed = True
        level = parts[1]
        volume = float(
            record.get("volume_initial")
            if record.get("volume_initial") is not None
            else record.get("volume") or 0.0
        )
        if abs(volume - _lot_for_level(level)) > 1e-9:
            return False
    return observed


def _target_summary(target_python_root: Path) -> dict[str, Any]:
    session = _current_target_session(target_python_root)
    snapshot = _latest_jsonl_record(session.glob("snapshots-*.jsonl"))
    orders = [
        row
        for row in snapshot.get("orders", [])
        if _comment_parts(str(row.get("comment") or "")) is not None
    ]
    positions = [
        row
        for row in snapshot.get("positions", [])
        if _comment_parts(str(row.get("comment") or "")) is not None
    ]
    records = [*orders, *positions]
    comments = {str(row["comment"]) for row in records}
    anchor, step = _grid_estimate(orders)

    ordered_comments = [
        str(row["comment"])
        for row in sorted(
            orders,
            key=lambda row: (
                int(row.get("time_setup_msc") or 0),
                str(row.get("comment") or ""),
            ),
        )
    ]
    expected = _expected_comments()
    sequence_match = (
        ordered_comments == expected if len(ordered_comments) == len(expected) else None
    )

    placement_rows = orders
    if len(orders) < len(expected):
        high_level_rows = [
            row
            for row in orders
            if (_comment_parts(str(row.get("comment") or "")) or ("", 0))[1]
            >= 21
        ]
        if high_level_rows:
            placement_rows = high_level_rows
    setup_times = [
        int(row.get("time_setup_msc") or 0)
        for row in placement_rows
        if int(row.get("time_setup_msc") or 0) > 0
    ]
    deployment_span = (
        (max(setup_times) - min(setup_times)) / 1000 if setup_times else None
    )

    return {
        "session": session.name,
        "snapshot_capture_utc": snapshot.get("capture_time_utc"),
        "snapshot_sequence": snapshot.get("sequence"),
        "order_count": len(orders),
        "position_count": len(positions),
        "observed_slots": len(comments),
        "missing_slots": sorted(set(expected) - comments),
        "duplicate_slots": sorted(
            comment
            for comment, count in Counter(
                str(row["comment"]) for row in records
            ).items()
            if count > 1
        ),
        "anchor": anchor,
        "step": step,
        "step_formula_error": step - anchor / 3000,
        "step_formula_match": abs(step - anchor / 3000) <= PRICE_TOLERANCE,
        "volume_match": _volume_matches(records),
        "sequence_match": sequence_match,
        "deployment_span_seconds": deployment_span,
    }


def _load_demo_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _latest_complete_demo_cycle(
    rows: list[dict[str, str]],
) -> tuple[list[dict[str, str]], bool]:
    starts = [index for index, row in enumerate(rows) if row["kind"] == "cycle_start"]
    if not starts:
        raise ValueError("Demo telemetry does not contain a cycle_start event")

    latest_rows: list[dict[str, str]] = []
    for position, start in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(rows)
        cycle = rows[start:end]
        latest_rows = cycle
        if any(row["kind"] == "deployment_complete" for row in cycle):
            complete_cycle = cycle
    if "complete_cycle" in locals():
        return complete_cycle, True
    return latest_rows, False


def _demo_summary(demo_telemetry: Path) -> dict[str, Any]:
    cycle, complete = _latest_complete_demo_cycle(
        _load_demo_rows(demo_telemetry)
    )
    cycle_start = cycle[0]
    pending: list[dict[str, str]] = []
    deployment_complete: dict[str, str] | None = None
    for row in cycle[1:]:
        if row["kind"] == "deployment_complete":
            deployment_complete = row
            break
        if row["kind"] == "pending":
            pending.append(row)

    anchor = float(cycle_start["price"])
    _, step = _grid_estimate(
        {
            "comment": row["comment"],
            "price_open": row["price"],
        }
        for row in pending
    )
    start_time = _parse_time(cycle_start["time"])
    duration = (
        (_parse_time(deployment_complete["time"]) - start_time).total_seconds()
        if deployment_complete is not None
        else None
    )
    comments = [row["comment"] for row in pending]
    return {
        "telemetry": str(demo_telemetry),
        "cycle_start_utc": start_time.isoformat(),
        "deployment_complete": complete,
        "deployment_duration_seconds": duration,
        "pending_count": len(pending),
        "sequence_match": comments == _expected_comments(),
        "volume_match": _volume_matches(pending),
        "anchor": anchor,
        "step": step,
        "step_formula_error": step - anchor / 3000,
        "step_formula_match": abs(step - anchor / 3000) <= PRICE_TOLERANCE,
        "event_counts": dict(Counter(row["kind"] for row in cycle)),
    }


def build_live_target_demo_comparison(
    *,
    target_python_root: Path,
    demo_telemetry: Path,
) -> dict[str, Any]:
    target = _target_summary(target_python_root)
    demo = _demo_summary(demo_telemetry)
    target_duration = target["deployment_span_seconds"]
    demo_duration = demo["deployment_duration_seconds"]
    profile_match = (
        target["observed_slots"] == 60
        and not target["missing_slots"]
        and not target["duplicate_slots"]
        and target["sequence_match"] is True
        and target["volume_match"]
        and target["step_formula_match"]
        and demo["pending_count"] == 60
        and demo["sequence_match"]
        and demo["volume_match"]
        and demo["step_formula_match"]
    )
    return {
        "generated_utc": datetime.now(tz=UTC).isoformat(),
        "target": target,
        "demo": demo,
        "comparison": {
            "status": "PASS" if profile_match else "FAIL",
            "profile_match": profile_match,
            "step_match": abs(target["step"] - demo["step"])
            <= PRICE_TOLERANCE,
            "step_delta": demo["step"] - target["step"],
            "deployment_duration_delta_seconds": (
                demo_duration - target_duration
                if demo_duration is not None and target_duration is not None
                else None
            ),
        },
    }
