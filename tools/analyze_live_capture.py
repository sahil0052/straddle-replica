from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import json
import math
import re
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence


UTC = timezone.utc
COMMENT_RE = re.compile(r"^STR ([BS])(\d+)$")
PHASE_LOCK_THRESHOLD_STEPS = 1.5


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def quantile(values: Sequence[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * fraction
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return ordered[lower]
    weight = index - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def distribution(values: Sequence[float], digits: int = 3) -> dict[str, Any]:
    if not values:
        return {"count": 0}
    return {
        "count": len(values),
        "min": round(min(values), digits),
        "p10": round(quantile(values, 0.10) or 0.0, digits),
        "median": round(statistics.median(values), digits),
        "mean": round(statistics.fmean(values), digits),
        "p90": round(quantile(values, 0.90) or 0.0, digits),
        "max": round(max(values), digits),
    }


def top_rounded(
    values: Sequence[float],
    digits: int = 2,
    limit: int = 10,
) -> list[dict[str, Any]]:
    counts = Counter(round(value, digits) for value in values)
    return [
        {"value": value, "count": count}
        for value, count in counts.most_common(limit)
    ]


def parse_mt5_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y.%m.%d %H:%M:%S").replace(tzinfo=UTC)
    except ValueError:
        return None


def epoch_iso(time_msc: int) -> str | None:
    if time_msc <= 0:
        return None
    return datetime.fromtimestamp(time_msc / 1000, tz=UTC).isoformat()


def broker_epoch_iso(
    time_msc: int,
    server_offset_ms: int,
) -> str | None:
    return epoch_iso(time_msc - server_offset_ms)


def parse_iso_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def iter_csv(paths: Iterable[Path]) -> Iterator[dict[str, str]]:
    for path in sorted(paths):
        with path.open("r", encoding="utf-8", newline="") as handle:
            yield from csv.DictReader(handle)


def iter_jsonl(paths: Iterable[Path]) -> Iterator[dict[str, Any]]:
    for path in sorted(paths):
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue


def latest_directory(root: Path) -> Path:
    directories = sorted(path for path in root.iterdir() if path.is_dir())
    if not directories:
        raise FileNotFoundError(f"No session directories below {root}")
    return directories[-1]


def current_python_session(root: Path) -> Path:
    pointer = json.loads((root / "current-session.json").read_text(encoding="utf-8"))
    session = root / pointer["session_id"]
    if not session.is_dir():
        raise FileNotFoundError(f"Current Python session is missing: {session}")
    return session


def python_sessions(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.iterdir()
        if path.is_dir() and (path / "manifest.json").is_file()
    )


def file_inventory(session: Path) -> dict[str, Any]:
    files = sorted(path for path in session.iterdir() if path.is_file())
    return {
        "session": session.name,
        "file_count": len(files),
        "bytes": sum(path.stat().st_size for path in files),
        "files": [
            {
                "name": path.name,
                "bytes": path.stat().st_size,
                "modified_utc": datetime.fromtimestamp(
                    path.stat().st_mtime,
                    tz=UTC,
                ).isoformat(),
            }
            for path in files
        ],
    }


@dataclass
class StateEvent:
    capture_micros: int
    server_time: str
    ticket: int
    record: dict[str, Any]


def normalized_snapshot_row(row: dict[str, str]) -> dict[str, Any]:
    integer_fields = {
        "snapshot_sequence",
        "ticket",
        "time_msc",
        "time_update_msc",
        "type",
        "state",
        "magic",
        "identifier",
        "position_id",
        "position_by_id",
        "reason_code",
    }
    float_fields = {
        "volume_initial",
        "volume_current",
        "price_open",
        "sl",
        "tp",
        "price_current",
        "price_stoplimit",
        "swap",
        "profit",
    }
    result: dict[str, Any] = dict(row)
    result["capture_micros"] = as_int(row.get("capture_micros"))
    for field in integer_fields:
        result[field] = as_int(row.get(field))
    for field in float_fields:
        result[field] = as_float(row.get(field))
    return result


def load_snapshot_evidence(
    session: Path,
) -> tuple[
    dict[int, dict[str, Any]],
    dict[int, dict[str, Any]],
    list[StateEvent],
    list[StateEvent],
    list[StateEvent],
    list[StateEvent],
    list[dict[str, Any]],
    dict[int, float],
]:
    order_metadata: dict[int, dict[str, Any]] = {}
    position_metadata: dict[int, dict[str, Any]] = {}
    added_orders: list[StateEvent] = []
    removed_orders: list[StateEvent] = []
    added_positions: list[StateEvent] = []
    removed_positions: list[StateEvent] = []
    summaries: list[dict[str, Any]] = []
    initial_sl: dict[int, float] = {}

    previous_orders: dict[int, dict[str, Any]] | None = None
    previous_positions: dict[int, dict[str, Any]] | None = None
    group: list[dict[str, Any]] = []
    group_sequence: int | None = None

    def process(rows: list[dict[str, Any]]) -> None:
        nonlocal previous_orders, previous_positions
        if not rows:
            return
        orders = {
            row["ticket"]: row
            for row in rows
            if row["record_type"] == "order"
        }
        positions = {
            row["ticket"]: row
            for row in rows
            if row["record_type"] == "position"
        }
        capture_micros = min(row["capture_micros"] for row in rows)
        server_time = rows[0]["server_time"]
        reason = rows[0]["reason"]
        for ticket, row in orders.items():
            order_metadata.setdefault(ticket, row)
        for ticket, row in positions.items():
            position_metadata.setdefault(ticket, row)

        if previous_orders is None or previous_positions is None:
            initial_sl.update(
                {
                    ticket: row["sl"]
                    for ticket, row in positions.items()
                }
            )
        else:
            for ticket in orders.keys() - previous_orders.keys():
                added_orders.append(
                    StateEvent(capture_micros, server_time, ticket, orders[ticket])
                )
            for ticket in previous_orders.keys() - orders.keys():
                removed_orders.append(
                    StateEvent(
                        capture_micros,
                        server_time,
                        ticket,
                        previous_orders[ticket],
                    )
                )
            for ticket in positions.keys() - previous_positions.keys():
                added_positions.append(
                    StateEvent(
                        capture_micros,
                        server_time,
                        ticket,
                        positions[ticket],
                    )
                )
                initial_sl[ticket] = 0.0
            for ticket in previous_positions.keys() - positions.keys():
                removed_positions.append(
                    StateEvent(
                        capture_micros,
                        server_time,
                        ticket,
                        previous_positions[ticket],
                    )
                )

        summaries.append(
            {
                "capture_micros": capture_micros,
                "snapshot_sequence": rows[0]["snapshot_sequence"],
                "server_time": server_time,
                "reason": reason,
                "position_count": len(positions),
                "order_count": len(orders),
                "floating_profit": sum(
                    row["profit"] + row["swap"] for row in positions.values()
                ),
            }
        )
        previous_orders = orders
        previous_positions = positions

    for raw in iter_csv(session.glob("snapshots-*.csv")):
        row = normalized_snapshot_row(raw)
        sequence = row["snapshot_sequence"]
        if group_sequence is not None and sequence != group_sequence:
            process(group)
            group = []
        group_sequence = sequence
        group.append(row)
    process(group)
    return (
        order_metadata,
        position_metadata,
        added_orders,
        removed_orders,
        added_positions,
        removed_positions,
        summaries,
        initial_sl,
    )


def load_transactions(session: Path) -> list[dict[str, Any]]:
    integer_fields = {
        "capture_micros",
        "sequence",
        "trans_type",
        "trans_deal",
        "trans_order",
        "trans_order_type",
        "trans_order_state",
        "trans_deal_type",
        "trans_time_type",
        "trans_position",
        "trans_position_by",
        "request_action",
        "request_magic",
        "request_order",
        "request_deviation",
        "request_type",
        "request_type_filling",
        "request_type_time",
        "request_position",
        "request_position_by",
        "result_retcode",
        "result_deal",
        "result_order",
        "result_request_id",
        "result_retcode_external",
    }
    float_fields = {
        "trans_price",
        "trans_price_trigger",
        "trans_price_sl",
        "trans_price_tp",
        "trans_volume",
        "request_volume",
        "request_price",
        "request_stoplimit",
        "request_sl",
        "request_tp",
        "result_volume",
        "result_price",
        "result_bid",
        "result_ask",
    }
    transactions: list[dict[str, Any]] = []
    for raw in iter_csv(session.glob("transactions-*.csv")):
        row: dict[str, Any] = dict(raw)
        for field in integer_fields:
            row[field] = as_int(raw.get(field))
        for field in float_fields:
            row[field] = as_float(raw.get(field))
        transactions.append(row)
    return transactions


def is_trade_request_event(row: dict[str, Any]) -> bool:
    result_fields = (
        "result_retcode",
        "result_deal",
        "result_order",
        "result_volume",
        "result_price",
        "result_bid",
        "result_ask",
        "result_request_id",
        "result_retcode_external",
    )
    if any(as_float(row.get(field)) != 0 for field in result_fields):
        return True
    if str(row.get("result_comment") or ""):
        return True

    request_numeric_fields = (
        "request_action",
        "request_magic",
        "request_order",
        "request_volume",
        "request_price",
        "request_stoplimit",
        "request_sl",
        "request_tp",
        "request_deviation",
        "request_type",
        "request_type_filling",
        "request_type_time",
        "request_position",
        "request_position_by",
    )
    return (
        any(as_float(row.get(field)) != 0 for field in request_numeric_fields)
        or bool(str(row.get("request_symbol") or ""))
        or bool(str(row.get("request_comment") or ""))
    )


def analyze_trade_requests(
    transactions: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    integer_fields = {
        "capture_micros",
        "sequence",
        "trans_type",
        "trans_deal",
        "trans_order",
        "trans_position",
        "request_action",
        "request_magic",
        "request_order",
        "request_deviation",
        "request_type",
        "request_type_filling",
        "request_type_time",
        "request_position",
        "request_position_by",
        "result_retcode",
        "result_deal",
        "result_order",
        "result_request_id",
        "result_retcode_external",
    }
    float_fields = {
        "trans_price",
        "trans_price_sl",
        "trans_volume",
        "request_volume",
        "request_price",
        "request_stoplimit",
        "request_sl",
        "request_tp",
        "result_volume",
        "result_price",
        "result_bid",
        "result_ask",
    }
    text_fields = {
        "server_time",
        "local_time",
        "trans_symbol",
        "request_symbol",
        "request_expiration",
        "request_comment",
        "result_comment",
    }
    event_fields = (
        "server_time",
        "local_time",
        "capture_micros",
        "sequence",
        "trans_type",
        "trans_deal",
        "trans_order",
        "trans_symbol",
        "trans_price",
        "trans_price_sl",
        "trans_volume",
        "trans_position",
        "request_action",
        "request_magic",
        "request_order",
        "request_symbol",
        "request_volume",
        "request_price",
        "request_stoplimit",
        "request_sl",
        "request_tp",
        "request_deviation",
        "request_type",
        "request_type_filling",
        "request_type_time",
        "request_expiration",
        "request_comment",
        "request_position",
        "request_position_by",
        "result_retcode",
        "result_deal",
        "result_order",
        "result_volume",
        "result_price",
        "result_bid",
        "result_ask",
        "result_comment",
        "result_request_id",
        "result_retcode_external",
    )

    events: list[dict[str, Any]] = []
    for row in transactions:
        if not is_trade_request_event(row):
            continue
        event: dict[str, Any] = {}
        for field in event_fields:
            if field in integer_fields:
                event[field] = as_int(row.get(field))
            elif field in float_fields:
                event[field] = as_float(row.get(field))
            elif field in text_fields:
                event[field] = str(row.get(field) or "")
        events.append(event)

    transaction_type_counts = Counter(
        event["trans_type"] for event in events
    )
    action_counts = Counter(event["request_action"] for event in events)
    retcode_counts = Counter(event["result_retcode"] for event in events)
    return {
        "count": len(events),
        "direct_request_evidence_available": bool(events),
        "interpretation": (
            "Request/result payload is present for direct request-sequence "
            "comparison."
            if events
            else
            "No request/result payload was observed; use accepted broker "
            "transactions and state changes for strategy inference."
        ),
        "sequence_numbers": [event["sequence"] for event in events],
        "request_id_sequence": [
            event["result_request_id"] for event in events
        ],
        "transaction_type_counts": {
            str(key): value
            for key, value in sorted(transaction_type_counts.items())
        },
        "action_counts": {
            str(key): value for key, value in sorted(action_counts.items())
        },
        "retcode_counts": {
            str(key): value for key, value in sorted(retcode_counts.items())
        },
        "nonzero_sl_count": sum(
            event["request_sl"] != 0 for event in events
        ),
        "events": events,
    }


def load_heartbeats(session: Path) -> list[dict[str, Any]]:
    integer_fields = {
        "capture_micros",
        "sequence",
        "connected",
        "trade_allowed",
        "positions_total",
        "orders_total",
        "queue_depth",
        "dropped_transactions",
        "last_tick_msc",
        "transaction_sequence",
        "tick_sequence",
        "snapshot_sequence",
    }
    heartbeats: list[dict[str, Any]] = []
    for raw in iter_csv(session.glob("heartbeat-*.csv")):
        row: dict[str, Any] = dict(raw)
        for field in integer_fields:
            row[field] = as_int(raw.get(field))
        heartbeats.append(row)
    return heartbeats


def load_ticks(session: Path) -> list[dict[str, Any]]:
    ticks: list[dict[str, Any]] = []
    for raw in iter_csv(session.glob("ticks-*.csv")):
        ticks.append(
            {
                "server_time": raw.get("server_time", ""),
                "local_time": raw.get("local_time", ""),
                "capture_micros": as_int(raw.get("capture_micros")),
                "sequence": as_int(raw.get("sequence")),
                "time_msc": as_int(raw.get("time_msc")),
                "bid": as_float(raw.get("bid")),
                "ask": as_float(raw.get("ask")),
                "flags": as_int(raw.get("flags")),
            }
        )
    return ticks


def load_history(
    sessions: Path | Sequence[Path],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    session_list = [sessions] if isinstance(sessions, Path) else list(sessions)

    def merge(prefix: str) -> list[dict[str, Any]]:
        by_ticket: dict[int, dict[str, Any]] = {}
        for session in sorted(session_list):
            for row in iter_jsonl(session.glob(f"{prefix}-*.jsonl")):
                ticket = as_int(row.get("ticket"))
                if ticket <= 0:
                    continue
                current = by_ticket.get(ticket)
                if current is None or str(
                    row.get("capture_time_utc") or ""
                ) < str(current.get("capture_time_utc") or ""):
                    by_ticket[ticket] = row
        return [by_ticket[ticket] for ticket in sorted(by_ticket)]

    return merge("history-orders"), merge("history-deals")


def ticket_digest(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    tickets = sorted({as_int(row.get("ticket")) for row in rows if row.get("ticket")})
    encoded = ",".join(map(str, tickets)).encode("ascii")
    return {
        "count": len(tickets),
        "minimum": tickets[0] if tickets else None,
        "maximum": tickets[-1] if tickets else None,
        "sha256": hashlib.sha256(encoded).hexdigest(),
    }


def nearest_tick(
    ticks: Sequence[dict[str, Any]],
    capture_values: Sequence[int],
    capture_micros: int,
) -> dict[str, Any] | None:
    if not ticks:
        return None
    index = bisect.bisect_left(capture_values, capture_micros)
    candidates = [
        ticks[candidate]
        for candidate in {max(0, index - 1), min(len(ticks) - 1, index)}
    ]
    return min(
        candidates,
        key=lambda row: abs(row["capture_micros"] - capture_micros),
    )


def latest_tick_at_or_before(
    ticks: Sequence[dict[str, Any]],
    capture_values: Sequence[int],
    capture_micros: int,
) -> dict[str, Any] | None:
    if not ticks:
        return None
    index = bisect.bisect_right(capture_values, capture_micros) - 1
    return ticks[index] if index >= 0 else None


def comment_parts(comment: str) -> tuple[str, int] | None:
    match = COMMENT_RE.match(comment)
    if not match:
        return None
    return match.group(1), int(match.group(2))


def latest_profile_grid_step(
    comment: str,
    order_price: float,
) -> float | None:
    parsed = comment_parts(comment)
    if not parsed or order_price <= 0:
        return None
    side, level = parsed
    divisor = 3000 + level if side == "B" else 3000 - level
    if divisor <= 0:
        return None
    return round(order_price / divisor, 2)


def history_position_steps(
    orders: Sequence[dict[str, Any]],
) -> dict[int, float]:
    steps: dict[int, float] = {}
    for row in orders:
        position_id = as_int(row.get("position_id"))
        if position_id <= 0:
            continue
        step = latest_profile_grid_step(
            str(row.get("comment") or ""),
            as_float(row.get("price_open")),
        )
        if step is not None:
            steps.setdefault(position_id, step)
    return steps


def fit_grid(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    points: list[tuple[int, float]] = []
    for row in records:
        parsed = comment_parts(str(row.get("comment") or ""))
        if not parsed:
            continue
        side, level = parsed
        points.append((level if side == "B" else -level, row["price_open"]))
    if len(points) < 2:
        return {}
    x_mean = statistics.fmean(point[0] for point in points)
    y_mean = statistics.fmean(point[1] for point in points)
    denominator = sum((x - x_mean) ** 2 for x, _ in points)
    step = sum((x - x_mean) * (y - y_mean) for x, y in points) / denominator
    anchor = y_mean - step * x_mean
    normalized_step = round(step, 2)
    errors = [
        abs(y - (anchor + x * normalized_step))
        for x, y in points
    ]
    return {
        "anchor": round(anchor, 6),
        "fitted_step": round(step, 6),
        "normalized_step": normalized_step,
        "anchor_divisor": round(anchor / normalized_step, 6)
        if normalized_step
        else None,
        "maximum_geometry_error_ticks": round(max(errors) / 0.01)
        if errors
        else None,
    }


def group_by_gap(
    rows: Sequence[dict[str, Any]],
    *,
    time_field: str,
    maximum_gap: int,
) -> list[list[dict[str, Any]]]:
    if not rows:
        return []
    ordered = sorted(rows, key=lambda row: as_int(row.get(time_field)))
    groups: list[list[dict[str, Any]]] = [[ordered[0]]]
    for row in ordered[1:]:
        if (
            as_int(row.get(time_field))
            - as_int(groups[-1][-1].get(time_field))
            > maximum_gap
        ):
            groups.append([])
        groups[-1].append(row)
    return groups


def stop_distance_band(distance: float | None) -> str:
    if distance is None:
        return "unknown"
    if 1.15 <= distance <= 1.75:
        return "one_step"
    if 2.45 <= distance <= 3.15:
        return "two_step"
    return "other"


def annotate_stop_sequence(
    changes: Sequence[dict[str, Any]],
    *,
    maximum_gap: int = 500_000,
) -> list[dict[str, Any]]:
    update_counts: Counter[int] = Counter()
    previous_bands: dict[int, str] = {}
    maximum_favorable_moves: dict[int, float] = {}
    maximum_favorable_move_steps: dict[int, float] = {}
    annotated: list[dict[str, Any]] = []
    for burst_index, burst in enumerate(
        group_by_gap(
            changes,
            time_field="capture_micros",
            maximum_gap=maximum_gap,
        ),
        start=1,
    ):
        for burst_position, change in enumerate(burst, start=1):
            result = dict(change)
            ticket = as_int(change.get("ticket"))
            observed_band = stop_distance_band(
                change.get("trailing_distance")
            )
            lock_offset_steps = change.get("lock_offset_steps")
            if change.get("activation"):
                band = "activation"
            elif lock_offset_steps is not None:
                band = (
                    "one_step"
                    if float(lock_offset_steps)
                    >= PHASE_LOCK_THRESHOLD_STEPS
                    else "two_step"
                )
            else:
                band = observed_band
            previous_band = previous_bands.get(ticket)
            previous_max_move = maximum_favorable_moves.get(ticket)
            current_move = change.get("favorable_move")
            if current_move is not None:
                maximum_favorable_moves[ticket] = max(
                    previous_max_move
                    if previous_max_move is not None
                    else float("-inf"),
                    float(current_move),
                )
            previous_max_move_steps = maximum_favorable_move_steps.get(ticket)
            current_move_steps = change.get("favorable_move_steps")
            if current_move_steps is not None:
                maximum_favorable_move_steps[ticket] = max(
                    previous_max_move_steps
                    if previous_max_move_steps is not None
                    else float("-inf"),
                    float(current_move_steps),
                )
            update_counts[ticket] += 1
            result.update(
                {
                    "distance_band": band,
                    "observed_distance_band": observed_band,
                    "previous_distance_band": previous_band,
                    "distance_band_transition": (
                        f"{previous_band or 'start'}->{band}"
                    ),
                    "ticket_update_index": update_counts[ticket],
                    "burst_index": burst_index,
                    "burst_position": burst_position,
                    "burst_size": len(burst),
                    "previous_max_favorable_move": previous_max_move,
                    "max_favorable_move": maximum_favorable_moves.get(ticket),
                    "previous_max_favorable_move_steps": (
                        previous_max_move_steps
                    ),
                    "max_favorable_move_steps": (
                        maximum_favorable_move_steps.get(ticket)
                    ),
                }
            )
            previous_bands[ticket] = band
            annotated.append(result)
    return annotated


def evaluate_categorical_band_predictor(
    rows: Sequence[dict[str, Any]],
    feature: str,
    *,
    train_fraction: float = 0.7,
) -> dict[str, Any]:
    eligible = [
        row
        for row in rows
        if row.get("distance_band") in {"one_step", "two_step"}
        and row.get(feature) is not None
    ]
    if len(eligible) < 2:
        return {
            "feature": feature,
            "eligible_count": len(eligible),
            "train_count": len(eligible),
            "holdout_count": 0,
            "seen_holdout_count": 0,
            "holdout_coverage": 0.0,
            "holdout_accuracy": None,
            "holdout_baseline_accuracy": None,
            "exact_holdout": False,
            "mapping": {},
        }

    split = max(1, min(len(eligible) - 1, int(len(eligible) * train_fraction)))
    train = eligible[:split]
    holdout = eligible[split:]
    labels_by_value: dict[Any, Counter[str]] = defaultdict(Counter)
    train_labels: Counter[str] = Counter()
    for row in train:
        band = str(row["distance_band"])
        labels_by_value[row[feature]][band] += 1
        train_labels[band] += 1
    mapping = {
        value: counts.most_common(1)[0][0]
        for value, counts in labels_by_value.items()
    }
    baseline = train_labels.most_common(1)[0][0]
    seen = [row for row in holdout if row[feature] in mapping]
    correct = sum(
        mapping[row[feature]] == row["distance_band"] for row in seen
    )
    baseline_correct = sum(
        baseline == row["distance_band"] for row in holdout
    )
    coverage = len(seen) / len(holdout)
    accuracy = correct / len(seen) if seen else None
    baseline_accuracy = baseline_correct / len(holdout)
    return {
        "feature": feature,
        "eligible_count": len(eligible),
        "train_count": len(train),
        "holdout_count": len(holdout),
        "seen_holdout_count": len(seen),
        "holdout_coverage": round(coverage, 4),
        "holdout_accuracy": round(accuracy, 4)
        if accuracy is not None
        else None,
        "holdout_baseline_accuracy": round(baseline_accuracy, 4),
        "exact_holdout": coverage == 1.0 and accuracy == 1.0,
        "mapping": {
            str(value): band
            for value, band in sorted(
                mapping.items(),
                key=lambda item: str(item[0]),
            )
        },
    }


def evaluate_numeric_threshold_predictor(
    rows: Sequence[dict[str, Any]],
    feature: str,
    *,
    train_fraction: float = 0.7,
) -> dict[str, Any]:
    eligible: list[tuple[dict[str, Any], float]] = []
    for row in rows:
        if row.get("distance_band") not in {"one_step", "two_step"}:
            continue
        try:
            value = float(row[feature])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(value):
            eligible.append((row, value))
    if len(eligible) < 2:
        return {
            "feature": feature,
            "eligible_count": len(eligible),
            "train_count": len(eligible),
            "holdout_count": 0,
            "direction": None,
            "threshold": None,
            "train_accuracy": None,
            "holdout_accuracy": None,
            "holdout_baseline_accuracy": None,
            "exact_holdout": False,
            "train_mismatches": [],
            "holdout_mismatches": [],
        }

    split = max(1, min(len(eligible) - 1, int(len(eligible) * train_fraction)))
    train = eligible[:split]
    holdout = eligible[split:]
    unique_values = sorted({value for _, value in train})
    epsilon = max(1.0, unique_values[-1] - unique_values[0]) * 1e-9
    thresholds = [
        unique_values[0] - epsilon,
        *[
            (left + right) / 2
            for left, right in zip(unique_values, unique_values[1:])
        ],
        unique_values[-1] + epsilon,
    ]

    best_accuracy = -1.0
    best_direction = ""
    best_threshold = 0.0
    for direction in ("greater_or_equal", "less_or_equal"):
        for threshold in thresholds:
            correct = 0
            for row, value in train:
                positive = (
                    value >= threshold
                    if direction == "greater_or_equal"
                    else value <= threshold
                )
                prediction = "one_step" if positive else "two_step"
                correct += prediction == row["distance_band"]
            accuracy = correct / len(train)
            if accuracy > best_accuracy:
                best_accuracy = accuracy
                best_direction = direction
                best_threshold = threshold

    def predict(value: float) -> str:
        positive = (
            value >= best_threshold
            if best_direction == "greater_or_equal"
            else value <= best_threshold
        )
        return "one_step" if positive else "two_step"

    holdout_correct = sum(
        predict(value) == row["distance_band"] for row, value in holdout
    )
    holdout_accuracy = holdout_correct / len(holdout)
    train_labels = Counter(str(row["distance_band"]) for row, _ in train)
    baseline = train_labels.most_common(1)[0][0]
    baseline_correct = sum(
        baseline == row["distance_band"] for row, _ in holdout
    )
    baseline_accuracy = baseline_correct / len(holdout)

    def mismatch_details(
        values: Sequence[tuple[dict[str, Any], float]],
    ) -> list[dict[str, Any]]:
        mismatches: list[dict[str, Any]] = []
        for row, value in values:
            prediction = predict(value)
            if prediction == row["distance_band"]:
                continue
            mismatches.append(
                {
                    "server_time": row.get("server_time"),
                    "ticket": row.get("ticket"),
                    "comment": row.get("comment"),
                    "feature_value": round(value, 6),
                    "actual_band": row["distance_band"],
                    "predicted_band": prediction,
                    "previous_distance_band": row.get(
                        "previous_distance_band"
                    ),
                    "ticket_update_index": row.get("ticket_update_index"),
                    "level": row.get("level"),
                    "level_gap_from_highest_open": row.get(
                        "level_gap_from_highest_open"
                    ),
                    "favorable_move": row.get("favorable_move"),
                    "lock_offset": row.get("lock_offset"),
                    "trailing_distance": row.get("trailing_distance"),
                }
            )
            if len(mismatches) >= 50:
                break
        return mismatches

    return {
        "feature": feature,
        "eligible_count": len(eligible),
        "train_count": len(train),
        "holdout_count": len(holdout),
        "direction": best_direction,
        "threshold": round(best_threshold, 6),
        "train_accuracy": round(best_accuracy, 4),
        "holdout_accuracy": round(holdout_accuracy, 4),
        "holdout_baseline_accuracy": round(baseline_accuracy, 4),
        "exact_holdout": holdout_accuracy == 1.0,
        "train_mismatches": mismatch_details(train),
        "holdout_mismatches": mismatch_details(holdout),
    }


def phase_transition_evidence(
    changes: Sequence[dict[str, Any]],
    *,
    threshold_steps: float = 3.0,
) -> dict[str, Any]:
    previous_by_ticket: dict[int, dict[str, Any]] = {}
    previous_implied: list[float] = []
    switch_implied: list[float] = []
    for row in changes:
        ticket = as_int(row.get("ticket"))
        previous = previous_by_ticket.get(ticket)
        if (
            previous is not None
            and previous.get("distance_band") == "two_step"
            and row.get("distance_band") == "one_step"
            and previous.get("lock_offset_steps") is not None
            and row.get("lock_offset_steps") is not None
        ):
            previous_implied.append(
                float(previous["lock_offset_steps"]) + 2.0
            )
            switch_implied.append(float(row["lock_offset_steps"]) + 1.0)
        previous_by_ticket[ticket] = row

    transition_count = len(previous_implied)
    previous_below = sum(
        value < threshold_steps for value in previous_implied
    )
    switch_at_or_above = sum(
        value >= threshold_steps for value in switch_implied
    )
    return {
        "threshold_steps": threshold_steps,
        "transition_count": transition_count,
        "previous_implied_decision_steps": distribution(
            previous_implied,
            digits=4,
        ),
        "switch_implied_decision_steps": distribution(
            switch_implied,
            digits=4,
        ),
        "previous_below_threshold_count": previous_below,
        "switch_at_or_above_threshold_count": switch_at_or_above,
        "boundary_accuracy": round(
            (previous_below + switch_at_or_above)
            / (2 * transition_count),
            4,
        )
        if transition_count
        else None,
    }


def annotate_level_context(
    changes: Sequence[dict[str, Any]],
    position_metadata: dict[int, dict[str, Any]],
    added_positions: Sequence[StateEvent],
    removed_positions: Sequence[StateEvent],
    *,
    tolerance_micros: int = 500_000,
) -> list[dict[str, Any]]:
    added_at = {
        event.ticket: event.capture_micros for event in added_positions
    }
    removed_at = {
        event.ticket: event.capture_micros for event in removed_positions
    }
    annotated: list[dict[str, Any]] = []
    for change in changes:
        ticket = as_int(change.get("ticket"))
        metadata = position_metadata.get(ticket, {})
        parsed = comment_parts(str(metadata.get("comment") or ""))
        side = str(change.get("side") or "")
        position_type = 0 if side == "buy" else 1
        capture_micros = as_int(change.get("capture_micros"))
        active_levels: list[int] = []
        for candidate, candidate_metadata in position_metadata.items():
            if as_int(candidate_metadata.get("type"), -1) != position_type:
                continue
            candidate_parts = comment_parts(
                str(candidate_metadata.get("comment") or "")
            )
            if not candidate_parts:
                continue
            start = added_at.get(candidate, 0)
            end = removed_at.get(candidate)
            if start > capture_micros + tolerance_micros:
                continue
            if end is not None and end < capture_micros - tolerance_micros:
                continue
            active_levels.append(candidate_parts[1])
        result = dict(change)
        if parsed and active_levels:
            result["level"] = parsed[1]
            result["same_side_open_count"] = len(active_levels)
            result["highest_open_level"] = max(active_levels)
            result["level_gap_from_highest_open"] = (
                max(active_levels) - parsed[1]
            )
        else:
            result["level"] = parsed[1] if parsed else None
            result["same_side_open_count"] = None
            result["highest_open_level"] = None
            result["level_gap_from_highest_open"] = None
        annotated.append(result)
    return annotated


def detect_history_deployments(
    rows: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    additions = sorted(
        [
            row
            for row in rows
            if comment_parts(str(row.get("comment") or ""))
            and as_int(row.get("time_setup_msc")) > 0
        ],
        key=lambda row: as_int(row.get("time_setup_msc")),
    )
    deployments: list[dict[str, Any]] = []
    for group in group_by_gap(
        additions,
        time_field="time_setup_msc",
        maximum_gap=1_000,
    ):
        parsed = [
            comment_parts(str(row.get("comment") or ""))
            for row in group
        ]
        valid = [value for value in parsed if value]
        maximum_level = max((level for _, level in valid), default=0)
        expected = [
            item
            for level in range(1, maximum_level + 1)
            for item in (f"STR B{level}", f"STR S{level}")
        ]
        actual = [str(row.get("comment") or "") for row in group]
        if (
            maximum_level < 25
            or len(group) != maximum_level * 2
            or actual != expected
        ):
            continue
        start = as_int(group[0].get("time_setup_msc"))
        end = as_int(group[-1].get("time_setup_msc"))
        deployments.append(
            {
                "start_broker_time_msc": start,
                "end_broker_time_msc": end,
                "duration_ms": end - start,
                "order_count": len(group),
                "maximum_level": maximum_level,
                "sequence_exact": True,
                "first_order_ticket": as_int(group[0].get("ticket")),
                "last_order_ticket": as_int(group[-1].get("ticket")),
                "grid": fit_grid(
                    [
                        {
                            **row,
                            "price_open": as_float(row.get("price_open")),
                        }
                        for row in group
                    ]
                ),
            }
        )
    return deployments


def sequence_continuity(
    rows: Sequence[dict[str, Any]],
    field: str,
) -> dict[str, Any]:
    values = [as_int(row.get(field)) for row in rows]
    values = [value for value in values if value > 0]
    if not values:
        return {
            "count": 0,
            "first": None,
            "last": None,
            "duplicate_steps": 0,
            "regressions": 0,
            "gap_steps": 0,
            "missing_values": 0,
        }
    differences = [
        right - left for left, right in zip(values, values[1:])
    ]
    return {
        "count": len(values),
        "first": values[0],
        "last": values[-1],
        "duplicate_steps": sum(value == 0 for value in differences),
        "regressions": sum(value < 0 for value in differences),
        "gap_steps": sum(value > 1 for value in differences),
        "missing_values": sum(
            max(0, value - 1) for value in differences
        ),
    }


def counter_monotonicity(
    rows: Sequence[dict[str, Any]],
    field: str,
) -> dict[str, Any]:
    values = [as_int(row.get(field)) for row in rows]
    if not values:
        return {
            "count": 0,
            "first": None,
            "last": None,
            "unchanged_steps": 0,
            "increasing_steps": 0,
            "regressions": 0,
            "maximum_increase": None,
        }
    differences = [
        right - left for left, right in zip(values, values[1:])
    ]
    return {
        "count": len(values),
        "first": values[0],
        "last": values[-1],
        "unchanged_steps": sum(value == 0 for value in differences),
        "increasing_steps": sum(value > 0 for value in differences),
        "regressions": sum(value < 0 for value in differences),
        "maximum_increase": max(differences) if differences else 0,
    }


def derive_server_offset_ms(
    rows: Sequence[dict[str, Any]],
) -> int:
    offsets: list[float] = []
    for row in rows:
        server_time = parse_mt5_time(str(row.get("server_time") or ""))
        local_time = parse_mt5_time(str(row.get("local_time") or ""))
        if server_time is None or local_time is None:
            continue
        offsets.append((server_time - local_time).total_seconds() * 1000)
    if not offsets:
        return 0
    return round(statistics.median(offsets))


def analyze_heartbeats(
    heartbeats: Sequence[dict[str, Any]],
    *,
    transaction_count: int,
    maximum_transaction_sequence: int,
    tick_count: int,
    maximum_tick_sequence: int,
    maximum_snapshot_sequence: int,
) -> dict[str, Any]:
    if not heartbeats:
        return {"count": 0}
    capture_values = [row["capture_micros"] for row in heartbeats]
    capture_gaps_ms = [
        (right - left) / 1000
        for left, right in zip(capture_values, capture_values[1:])
        if right >= left
    ]
    server_offsets = [
        (
            server_time - local_time
        ).total_seconds()
        for row in heartbeats
        if (
            (server_time := parse_mt5_time(
                str(row.get("server_time") or "")
            ))
            is not None
            and (
                local_time := parse_mt5_time(
                    str(row.get("local_time") or "")
                )
            )
            is not None
        )
    ]
    final = heartbeats[-1]
    return {
        "count": len(heartbeats),
        "first_server_time": heartbeats[0].get("server_time"),
        "last_server_time": final.get("server_time"),
        "first_local_time": heartbeats[0].get("local_time"),
        "last_local_time": final.get("local_time"),
        "duration_hours": round(
            (capture_values[-1] - capture_values[0]) / 3_600_000_000,
            4,
        ),
        "capture_gap_ms": distribution(capture_gaps_ms, digits=3),
        "maximum_capture_gap_ms": round(max(capture_gaps_ms), 3)
        if capture_gaps_ms
        else None,
        "heartbeat_sequence": sequence_continuity(
            heartbeats,
            "sequence",
        ),
        "transaction_counter": counter_monotonicity(
            heartbeats,
            "transaction_sequence",
        ),
        "tick_counter": counter_monotonicity(
            heartbeats,
            "tick_sequence",
        ),
        "snapshot_counter": counter_monotonicity(
            heartbeats,
            "snapshot_sequence",
        ),
        "connected_false_count": sum(
            row["connected"] != 1 for row in heartbeats
        ),
        "trade_allowed_true_count": sum(
            row["trade_allowed"] != 0 for row in heartbeats
        ),
        "maximum_queue_depth": max(
            row["queue_depth"] for row in heartbeats
        ),
        "maximum_dropped_transactions": max(
            row["dropped_transactions"] for row in heartbeats
        ),
        "server_utc_offset_seconds": distribution(
            server_offsets,
            digits=1,
        ),
        "final": {
            "connected": final["connected"],
            "trade_allowed": final["trade_allowed"],
            "positions_total": final["positions_total"],
            "orders_total": final["orders_total"],
            "queue_depth": final["queue_depth"],
            "dropped_transactions": final["dropped_transactions"],
            "transaction_sequence": final["transaction_sequence"],
            "tick_sequence": final["tick_sequence"],
            "snapshot_sequence": final["snapshot_sequence"],
        },
        "loaded_streams": {
            "transaction_rows": transaction_count,
            "maximum_transaction_sequence": maximum_transaction_sequence,
            "tick_rows": tick_count,
            "maximum_tick_sequence": maximum_tick_sequence,
            "maximum_snapshot_sequence": maximum_snapshot_sequence,
        },
    }


def analyze_deployments(
    transactions: Sequence[dict[str, Any]],
    order_metadata: dict[int, dict[str, Any]],
    ticks: Sequence[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    tick_captures = [row["capture_micros"] for row in ticks]
    additions: list[dict[str, Any]] = []
    for transaction in transactions:
        if transaction["trans_type"] != 0:
            continue
        ticket = transaction["trans_order"]
        metadata = order_metadata.get(ticket)
        if not metadata or not comment_parts(str(metadata.get("comment") or "")):
            continue
        additions.append(
            {
                **transaction,
                "ticket": ticket,
                "comment": metadata["comment"],
                "volume": metadata["volume_initial"],
                "price_open": metadata["price_open"],
            }
        )
    bursts = group_by_gap(
        additions,
        time_field="capture_micros",
        maximum_gap=2_000_000,
    )
    full_deployments: list[dict[str, Any]] = []
    rearm_bursts: list[dict[str, Any]] = []
    for burst in bursts:
        parsed = [
            comment_parts(str(row.get("comment") or ""))
            for row in burst
        ]
        valid = [value for value in parsed if value]
        sides = {side for side, _ in valid}
        maximum_level = max((level for _, level in valid), default=0)
        delays = [
            (right["capture_micros"] - left["capture_micros"]) / 1000
            for left, right in zip(burst, burst[1:])
        ]
        if len(burst) >= 50 and sides == {"B", "S"} and maximum_level >= 25:
            grid = fit_grid(burst)
            first = burst[0]
            tick = nearest_tick(ticks, tick_captures, first["capture_micros"])
            expected = [
                item
                for level in range(1, maximum_level + 1)
                for item in (f"STR B{level}", f"STR S{level}")
            ]
            actual = [str(row["comment"]) for row in burst]
            lot_tiers = Counter(
                (
                    comment_parts(str(row["comment"]))[1],
                    round(row["volume"], 2),
                )
                for row in burst
            )
            full_deployments.append(
                {
                    "start_server_time": first["server_time"],
                    "start_local_time": first.get("local_time"),
                    "start_capture_micros": first["capture_micros"],
                    "end_capture_micros": burst[-1]["capture_micros"],
                    "duration_ms": round(
                        (
                            burst[-1]["capture_micros"]
                            - first["capture_micros"]
                        )
                        / 1000,
                        3,
                    ),
                    "order_count": len(burst),
                    "maximum_level": maximum_level,
                    "sequence_exact": actual == expected,
                    "inter_order_delay_ms": distribution(delays),
                    "grid": grid,
                    "nearest_tick_midpoint": round(
                        (tick["bid"] + tick["ask"]) / 2,
                        6,
                    )
                    if tick
                    else None,
                    "anchor_midpoint_error_ticks": round(
                        abs(
                            grid.get("anchor", 0.0)
                            - (tick["bid"] + tick["ask"]) / 2
                        )
                        / 0.01
                    )
                    if tick and grid
                    else None,
                    "first_order_ticket": first["ticket"],
                    "last_order_ticket": burst[-1]["ticket"],
                    "lot_pairs": [
                        {"level": level, "volume": volume, "count": count}
                        for (level, volume), count in sorted(lot_tiers.items())
                    ],
                }
            )
        else:
            rearm_bursts.append(
                {
                    "start_server_time": burst[0]["server_time"],
                    "count": len(burst),
                    "comments": [str(row["comment"]) for row in burst],
                    "duration_ms": round(
                        (
                            burst[-1]["capture_micros"]
                            - burst[0]["capture_micros"]
                        )
                        / 1000,
                        3,
                    ),
                }
            )
    return full_deployments, rearm_bursts


def analyze_stops(
    transactions: Sequence[dict[str, Any]],
    position_metadata: dict[int, dict[str, Any]],
    initial_sl: dict[int, float],
    ticks: Sequence[dict[str, Any]],
    added_positions: Sequence[StateEvent],
    removed_positions: Sequence[StateEvent],
    *,
    position_steps: dict[int, float] | None = None,
) -> dict[str, Any]:
    tick_captures = [row["capture_micros"] for row in ticks]
    current_sl = dict(initial_sl)
    changes: list[dict[str, Any]] = []
    for row in transactions:
        if row["trans_type"] != 9 or row["trans_price_sl"] <= 0:
            continue
        ticket = row["trans_position"]
        metadata = position_metadata.get(ticket)
        if not metadata:
            continue
        new_sl = row["trans_price_sl"]
        previous_sl = current_sl.get(ticket, 0.0)
        if abs(new_sl - previous_sl) < 0.005:
            continue
        tick = latest_tick_at_or_before(
            ticks,
            tick_captures,
            row["capture_micros"],
        )
        position_type = metadata["type"]
        entry = metadata["price_open"]
        executable = (
            tick["bid"] if position_type == 0 else tick["ask"]
        ) if tick else None
        lock_offset = (
            new_sl - entry
            if position_type == 0
            else entry - new_sl
        )
        favorable_move = (
            executable - entry
            if position_type == 0 and executable is not None
            else entry - executable
            if executable is not None
            else None
        )
        trailing_distance = (
            executable - new_sl
            if position_type == 0 and executable is not None
            else new_sl - executable
            if executable is not None
            else None
        )
        grid_step = (position_steps or {}).get(ticket)
        changes.append(
            {
                "capture_micros": row["capture_micros"],
                "server_time": row["server_time"],
                "ticket": ticket,
                "comment": metadata["comment"],
                "side": "buy" if position_type == 0 else "sell",
                "entry": entry,
                "previous_sl": previous_sl,
                "new_sl": new_sl,
                "increment": abs(new_sl - previous_sl)
                if previous_sl > 0
                else None,
                "activation": previous_sl <= 0,
                "lock_offset": lock_offset,
                "favorable_move": favorable_move,
                "trailing_distance": trailing_distance,
                "grid_step": grid_step,
                "favorable_move_steps": favorable_move / grid_step
                if favorable_move is not None and grid_step
                else None,
                "lock_offset_steps": lock_offset / grid_step
                if grid_step
                else None,
                "trailing_distance_steps": trailing_distance / grid_step
                if trailing_distance is not None and grid_step
                else None,
            }
        )
        current_sl[ticket] = new_sl

    changes = annotate_level_context(
        changes,
        position_metadata,
        added_positions,
        removed_positions,
    )
    changes = annotate_stop_sequence(changes)
    activations = [row for row in changes if row["activation"]]
    increments = [
        row["increment"]
        for row in changes
        if row["increment"] is not None
    ]
    global_gaps = [
        (right["capture_micros"] - left["capture_micros"]) / 1_000_000
        for left, right in zip(changes, changes[1:])
    ]
    per_ticket_gaps: list[float] = []
    by_ticket: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in changes:
        by_ticket[row["ticket"]].append(row)
    for rows in by_ticket.values():
        per_ticket_gaps.extend(
            (
                right["capture_micros"] - left["capture_micros"]
            )
            / 1_000_000
            for left, right in zip(rows, rows[1:])
        )
    activation_locks = [row["lock_offset"] for row in activations]
    activation_moves = [
        row["favorable_move"]
        for row in activations
        if row["favorable_move"] is not None
    ]
    activation_move_steps = [
        row["favorable_move_steps"]
        for row in activations
        if row.get("favorable_move_steps") is not None
    ]
    trailing_distances = [
        row["trailing_distance"]
        for row in changes
        if not row["activation"] and row["trailing_distance"] is not None
    ]
    trailing_distance_steps = [
        row["trailing_distance_steps"]
        for row in changes
        if not row["activation"]
        and row.get("trailing_distance_steps") is not None
    ]
    comment_sequence = [row["comment"] for row in changes]
    consecutive_same_ticket = sum(
        left["ticket"] == right["ticket"]
        for left, right in zip(changes, changes[1:])
    )
    different_ticket_transitions = [
        right["ticket"] - left["ticket"]
        for left, right in zip(changes, changes[1:])
        if right["ticket"] != left["ticket"]
    ]
    same_side_level_transitions: list[int] = []
    for left, right in zip(changes, changes[1:]):
        if left["side"] != right["side"]:
            continue
        left_parts = comment_parts(str(left.get("comment") or ""))
        right_parts = comment_parts(str(right.get("comment") or ""))
        if not left_parts or not right_parts:
            continue
        difference = right_parts[1] - left_parts[1]
        if difference:
            same_side_level_transitions.append(difference)

    def stop_rows_summary(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
        distances = [
            row["trailing_distance"]
            for row in rows
            if not row["activation"]
            and row.get("trailing_distance") is not None
        ]
        locks = [
            row["lock_offset"]
            for row in rows
            if row.get("activation")
        ]
        bands = Counter(
            row["distance_band"]
            for row in rows
            if not row["activation"]
            and row.get("trailing_distance") is not None
        )
        return {
            "count": len(rows),
            "position_count": len(
                {as_int(row.get("ticket")) for row in rows}
            ),
            "trailing_distance": distribution(distances, digits=4),
            "trailing_distance_modes": top_rounded(
                distances,
                digits=2,
            ),
            "distance_band_counts": dict(bands),
            "activation_count": len(locks),
            "activation_lock_offset": distribution(locks, digits=4),
        }

    by_side = {
        side: stop_rows_summary(
            [row for row in changes if row["side"] == side]
        )
        for side in ("buy", "sell")
    }
    level_gap_groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in changes:
        gap = row.get("level_gap_from_highest_open")
        if gap is not None:
            level_gap_groups[as_int(gap)].append(row)
    by_level_gap = {
        str(gap): stop_rows_summary(rows)
        for gap, rows in sorted(level_gap_groups.items())
    }

    per_ticket = []
    for ticket, rows in sorted(by_ticket.items()):
        annotated_rows = [
            row for row in changes if row["ticket"] == ticket
        ]
        per_ticket.append(
            {
                "ticket": ticket,
                "comment": rows[0]["comment"],
                "side": rows[0]["side"],
                "update_count": len(rows),
                "first_server_time": rows[0]["server_time"],
                "last_server_time": rows[-1]["server_time"],
                **stop_rows_summary(annotated_rows),
            }
        )

    stop_bursts = group_by_gap(
        changes,
        time_field="capture_micros",
        maximum_gap=500_000,
    )
    burst_sizes = [len(group) for group in stop_bursts]
    burst_unique_tickets = [
        len({row["ticket"] for row in group})
        for group in stop_bursts
    ]
    distance_band_transitions = Counter(
        row["distance_band_transition"] for row in changes
    )
    distance_band_switches = [
        {
            "server_time": row["server_time"],
            "ticket": row["ticket"],
            "comment": row["comment"],
            "side": row["side"],
            "level": row.get("level"),
            "same_side_open_count": row.get("same_side_open_count"),
            "highest_open_level": row.get("highest_open_level"),
            "level_gap_from_highest_open": row.get(
                "level_gap_from_highest_open"
            ),
            "from_band": row["previous_distance_band"],
            "to_band": row["distance_band"],
            "ticket_update_index": row["ticket_update_index"],
            "burst_index": row["burst_index"],
            "burst_position": row["burst_position"],
            "burst_size": row["burst_size"],
            "trailing_distance": round(row["trailing_distance"], 4)
            if row.get("trailing_distance") is not None
            else None,
            "favorable_move": round(row["favorable_move"], 4)
            if row.get("favorable_move") is not None
            else None,
            "lock_offset": round(row["lock_offset"], 4),
            "increment": round(row["increment"], 4)
            if row.get("increment") is not None
            else None,
            "previous_sl": round(row["previous_sl"], 4),
            "new_sl": round(row["new_sl"], 4),
            "grid_step": row.get("grid_step"),
            "favorable_move_steps": round(
                row["favorable_move_steps"],
                4,
            )
            if row.get("favorable_move_steps") is not None
            else None,
            "lock_offset_steps": round(row["lock_offset_steps"], 4)
            if row.get("lock_offset_steps") is not None
            else None,
            "trailing_distance_steps": round(
                row["trailing_distance_steps"],
                4,
            )
            if row.get("trailing_distance_steps") is not None
            else None,
        }
        for row in changes
        if row.get("previous_distance_band") in {"one_step", "two_step"}
        and row["distance_band"] in {"one_step", "two_step"}
        and row["previous_distance_band"] != row["distance_band"]
    ]
    predictor_features = (
        "burst_position",
        "level",
        "level_gap_from_highest_open",
        "previous_distance_band",
        "same_side_open_count",
        "side",
        "ticket_update_index",
    )
    numeric_predictor_features = (
        "favorable_move",
        "favorable_move_steps",
        "increment",
        "level_gap_from_highest_open",
        "lock_offset",
        "max_favorable_move_steps",
        "ticket_update_index",
    )
    return {
        "change_count": len(changes),
        "change_rows": changes,
        "phase_lock_threshold_steps": PHASE_LOCK_THRESHOLD_STEPS,
        "position_count": len(by_ticket),
        "activation_count": len(activations),
        "activation_lock_offset": distribution(activation_locks, digits=4),
        "activation_lock_offset_modes": top_rounded(
            activation_locks,
            digits=2,
        ),
        "activation_favorable_move": distribution(
            activation_moves,
            digits=4,
        ),
        "activation_favorable_move_modes": top_rounded(
            activation_moves,
            digits=2,
        ),
        "activation_favorable_move_steps": distribution(
            activation_move_steps,
            digits=4,
        ),
        "trailing_distance": distribution(trailing_distances, digits=4),
        "trailing_distance_steps": distribution(
            trailing_distance_steps,
            digits=4,
        ),
        "trailing_distance_modes": top_rounded(
            trailing_distances,
            digits=2,
        ),
        "increment": distribution(increments, digits=4),
        "increment_modes": top_rounded(
            increments,
            digits=2,
            limit=30,
        ),
        "global_update_gap_seconds": distribution(global_gaps, digits=4),
        "per_position_update_gap_seconds": distribution(
            per_ticket_gaps,
            digits=4,
        ),
        "consecutive_same_ticket_ratio": round(
            consecutive_same_ticket / max(1, len(changes) - 1),
            4,
        ),
        "different_ticket_transition_direction": {
            "ascending": sum(
                value > 0 for value in different_ticket_transitions
            ),
            "descending": sum(
                value < 0 for value in different_ticket_transitions
            ),
        },
        "same_side_level_transition_direction": {
            "ascending": sum(
                value > 0 for value in same_side_level_transitions
            ),
            "descending": sum(
                value < 0 for value in same_side_level_transitions
            ),
            "adjacent_ascending": sum(
                value == 1 for value in same_side_level_transitions
            ),
            "adjacent_descending": sum(
                value == -1 for value in same_side_level_transitions
            ),
        },
        "distance_band_transitions": dict(distance_band_transitions),
        "distance_band_switches": distance_band_switches,
        "phase_transition_evidence": phase_transition_evidence(changes),
        "categorical_predictor_holdout": {
            feature: evaluate_categorical_band_predictor(changes, feature)
            for feature in predictor_features
        },
        "numeric_threshold_holdout": {
            feature: evaluate_numeric_threshold_predictor(changes, feature)
            for feature in numeric_predictor_features
        },
        "updates_by_comment": dict(Counter(comment_sequence).most_common()),
        "by_side": by_side,
        "by_level_gap_from_highest_open": by_level_gap,
        "per_ticket": per_ticket,
        "update_bursts": {
            "count": len(stop_bursts),
            "size": distribution(burst_sizes),
            "unique_tickets": distribution(burst_unique_tickets),
            "first_20": [
                {
                    "start_server_time": group[0]["server_time"],
                    "duration_ms": round(
                        (
                            group[-1]["capture_micros"]
                            - group[0]["capture_micros"]
                        )
                        / 1000,
                        3,
                    ),
                    "update_count": len(group),
                    "unique_ticket_count": len(
                        {row["ticket"] for row in group}
                    ),
                    "comments": [row["comment"] for row in group],
                    "tickets": [row["ticket"] for row in group],
                    "level_gaps": [
                        row.get("level_gap_from_highest_open")
                        for row in group
                    ],
                }
                for group in stop_bursts[:20]
            ],
        },
        "first_20_updates": changes[:20],
    }


def nearest_summary(
    summaries: Sequence[dict[str, Any]],
    ticks: Sequence[dict[str, Any]],
    time_msc: int,
) -> dict[str, Any] | None:
    if not summaries or not ticks:
        return None
    target_time_msc = time_msc
    tick_times = [row["time_msc"] for row in ticks]
    index = bisect.bisect_left(tick_times, target_time_msc)
    tick_candidates = [
        ticks[candidate]
        for candidate in {max(0, index - 1), min(len(ticks) - 1, index)}
    ]
    tick = min(
        tick_candidates,
        key=lambda row: abs(row["time_msc"] - target_time_msc),
    )
    summary_captures = [row["capture_micros"] for row in summaries]
    summary_index = bisect.bisect_right(
        summary_captures,
        tick["capture_micros"],
    ) - 1
    if summary_index < 0:
        return None
    return summaries[summary_index]


def analyze_lifecycle(
    orders: Sequence[dict[str, Any]],
    deals: Sequence[dict[str, Any]],
    deployments: Sequence[dict[str, Any]],
    summaries: Sequence[dict[str, Any]],
    ticks: Sequence[dict[str, Any]],
    server_offset_ms: int,
) -> dict[str, Any]:
    historical_orders = [
        {
            **row,
            "ticket": as_int(row.get("ticket")),
            "state": as_int(row.get("state")),
            "type": as_int(row.get("type")),
            "time_setup_msc": as_int(row.get("time_setup_msc")),
            "time_done_msc": as_int(row.get("time_done_msc")),
            "volume_initial": as_float(row.get("volume_initial")),
            "price_open": as_float(row.get("price_open")),
        }
        for row in orders
    ]
    historical_deals = [
        {
            **row,
            "ticket": as_int(row.get("ticket")),
            "order": as_int(row.get("order")),
            "time_msc": as_int(row.get("time_msc")),
            "entry": as_int(row.get("entry")),
            "reason": as_int(row.get("reason")),
            "position_id": as_int(row.get("position_id")),
            "volume": as_float(row.get("volume")),
            "price": as_float(row.get("price")),
            "profit": as_float(row.get("profit")),
            "swap": as_float(row.get("swap")),
            "commission": as_float(row.get("commission")),
            "fee": as_float(row.get("fee")),
        }
        for row in deals
    ]
    canceled = [
        row
        for row in historical_orders
        if row["state"] == 2
        and comment_parts(str(row.get("comment") or ""))
        and row["time_done_msc"] > 0
    ]
    cancellation_groups = [
        group
        for group in group_by_gap(
            canceled,
            time_field="time_done_msc",
            maximum_gap=1_000,
        )
        if len(group) >= 10
    ]
    cancellations: list[dict[str, Any]] = []
    for group in cancellation_groups:
        gaps = [
            right["time_done_msc"] - left["time_done_msc"]
            for left, right in zip(group, group[1:])
        ]
        first_time = group[0]["time_done_msc"]
        summary = nearest_summary(
            summaries,
            ticks,
            first_time,
        )
        cancellations.append(
            {
                "start_broker_time_msc": first_time,
                "start_utc": broker_epoch_iso(
                    first_time,
                    server_offset_ms,
                ),
                "end_utc": broker_epoch_iso(
                    group[-1]["time_done_msc"],
                    server_offset_ms,
                ),
                "count": len(group),
                "duration_ms": group[-1]["time_done_msc"] - first_time,
                "inter_cancel_ms": distribution(gaps),
                "floating_profit_near_start": round(
                    summary["floating_profit"],
                    2,
                )
                if summary
                else None,
                "positions_near_start": summary["position_count"]
                if summary
                else None,
                "orders_near_start": summary["order_count"]
                if summary
                else None,
            }
        )

    exits = [row for row in historical_deals if row["entry"] in {1, 3}]
    stop_exits = [row for row in exits if row["reason"] == 4]
    close_exits = [
        row
        for row in exits
        if str(row.get("comment") or "") == "STR CLOSE"
    ]
    close_groups = group_by_gap(
        close_exits,
        time_field="time_msc",
        maximum_gap=25_000,
    )
    residual_closes = []
    for group in close_groups:
        gaps = [
            right["time_msc"] - left["time_msc"]
            for left, right in zip(group, group[1:])
        ]
        residual_closes.append(
            {
                "start_utc": broker_epoch_iso(
                    group[0]["time_msc"],
                    server_offset_ms,
                ),
                "end_utc": broker_epoch_iso(
                    group[-1]["time_msc"],
                    server_offset_ms,
                ),
                "count": len(group),
                "duration_ms": group[-1]["time_msc"] - group[0]["time_msc"],
                "inter_close_ms": distribution(gaps),
            }
        )

    order_additions = sorted(
        [
            row
            for row in historical_orders
            if comment_parts(str(row.get("comment") or ""))
            and row["time_setup_msc"] > 0
        ],
        key=lambda row: row["time_setup_msc"],
    )
    history_deployments = detect_history_deployments(order_additions)
    deployment_order_tickets = {
        row["ticket"]
        for row in order_additions
        if any(
            deployment["start_broker_time_msc"]
            <= row["time_setup_msc"]
            <= deployment["end_broker_time_msc"]
            for deployment in history_deployments
        )
    }
    rearm_delays: list[int] = []
    rearm_pairs: list[dict[str, Any]] = []
    used_rearm_order_tickets: set[int] = set()
    entry_comment_by_position: dict[int, str] = {}
    for deal in historical_deals:
        comment = str(deal.get("comment") or "")
        if (
            deal["entry"] in {0, 2}
            and deal["position_id"] > 0
            and comment_parts(comment)
        ):
            entry_comment_by_position.setdefault(
                deal["position_id"],
                comment,
            )
    unmatched_rearm_exits = 0
    for deal in stop_exits:
        original_comment = entry_comment_by_position.get(
            deal["position_id"],
            "",
        )
        if not comment_parts(original_comment):
            unmatched_rearm_exits += 1
            continue
        candidates = [
            row
            for row in order_additions
            if row["time_setup_msc"] > deal["time_msc"]
            and row.get("comment") == original_comment
            and row["ticket"] not in deployment_order_tickets
            and row["ticket"] not in used_rearm_order_tickets
        ]
        if not candidates:
            unmatched_rearm_exits += 1
            continue
        candidate = candidates[0]
        delay = candidate["time_setup_msc"] - deal["time_msc"]
        if delay > 120_000:
            continue
        used_rearm_order_tickets.add(candidate["ticket"])
        rearm_delays.append(delay)
        rearm_pairs.append(
            {
                "stop_deal": deal["ticket"],
                "comment": original_comment,
                "delay_ms": delay,
                "new_order": candidate["ticket"],
            }
        )

    deployment_times = [
        deployment["start_broker_time_msc"]
        for deployment in history_deployments
    ]
    for deployment in deployments:
        ticket = deployment["first_order_ticket"]
        matching = [
            row
            for row in order_additions
            if row["ticket"] == ticket
        ]
        if matching:
            deployment_times.append(matching[0]["time_setup_msc"])
            continue
        server_time = parse_mt5_time(
            str(deployment.get("start_server_time") or "")
        )
        if server_time is not None:
            deployment_times.append(
                round(server_time.timestamp() * 1000)
            )
    unique_deployment_times: list[int] = []
    for value in sorted(deployment_times):
        if (
            not unique_deployment_times
            or value - unique_deployment_times[-1] > 2_000
        ):
            unique_deployment_times.append(value)
    deployment_times = unique_deployment_times
    restart_delays: list[int] = []
    for deployment_time in deployment_times[1:]:
        earlier_closes = [
            row["time_msc"]
            for row in close_exits
            if row["time_msc"] < deployment_time
        ]
        if earlier_closes:
            delay = deployment_time - max(earlier_closes)
            if 0 <= delay <= 300_000:
                restart_delays.append(delay)

    cycle_net_estimates: list[dict[str, Any]] = []
    for cancellation in cancellations:
        cancel_time = cancellation["start_broker_time_msc"]
        prior_deployments = [
            value for value in deployment_times if value < cancel_time
        ]
        if not prior_deployments:
            continue
        cycle_start = max(prior_deployments)
        realized = sum(
            row["profit"] + row["swap"] + row["commission"] + row["fee"]
            for row in exits
            if cycle_start <= row["time_msc"] <= cancel_time
        )
        floating = cancellation["floating_profit_near_start"]
        cycle_net_estimates.append(
            {
                "cancel_start_utc": cancellation["start_utc"],
                "realized": round(realized, 2),
                "floating": floating,
                "estimated_cycle_net": round(realized + floating, 2)
                if floating is not None
                else None,
            }
        )

    history_capture_lags: list[float] = []
    latest_history_event_utc_msc = 0
    for row in [*historical_orders, *historical_deals]:
        event_msc = as_int(
            row.get("time_done_msc")
            or row.get("time_msc")
            or row.get("time_setup_msc")
        )
        captured = parse_iso_time(str(row.get("capture_time_utc") or ""))
        if event_msc <= 0 or captured is None:
            continue
        event_utc_msc = event_msc - server_offset_ms
        latest_history_event_utc_msc = max(
            latest_history_event_utc_msc,
            event_utc_msc,
        )
        history_capture_lags.append(
            captured.timestamp() - event_utc_msc / 1000
        )

    return {
        "historical_order_count": len(historical_orders),
        "historical_deal_count": len(historical_deals),
        "exit_deal_count": len(exits),
        "stop_exit_count": len(stop_exits),
        "str_close_exit_count": len(close_exits),
        "exit_reason_counts": {
            str(reason): count
            for reason, count in sorted(
                Counter(row["reason"] for row in exits).items()
            )
        },
        "cancellation_bursts": cancellations,
        "residual_close_groups": residual_closes,
        "rearm_count": len(rearm_delays),
        "unmatched_rearm_stop_exits": unmatched_rearm_exits,
        "rearm_delay_ms": distribution(rearm_delays),
        "rearm_delays_ms": rearm_delays,
        "first_20_rearms": rearm_pairs[:20],
        "restart_delay_after_final_close_ms": distribution(restart_delays),
        "cycle_net_at_cancellation": cycle_net_estimates,
        "history_deployments": [
            {
                **deployment,
                "start_utc": broker_epoch_iso(
                    deployment["start_broker_time_msc"],
                    server_offset_ms,
                ),
                "end_utc": broker_epoch_iso(
                    deployment["end_broker_time_msc"],
                    server_offset_ms,
                ),
            }
            for deployment in history_deployments
        ],
        "history_capture_lag_seconds": distribution(
            history_capture_lags,
            digits=3,
        ),
        "latest_history_event_utc": epoch_iso(
            latest_history_event_utc_msc
        ),
        "order_ticket_digest": ticket_digest(historical_orders),
        "deal_ticket_digest": ticket_digest(historical_deals),
    }


def analyze_ticks(
    ticks: Sequence[dict[str, Any]],
    server_offset_ms: int,
) -> dict[str, Any]:
    times = [row["time_msc"] for row in ticks if row["time_msc"] > 0]
    gaps = [
        right - left
        for left, right in zip(times, times[1:])
        if right >= left
    ]
    active_gap_threshold_ms = 300_000
    active_gaps = [
        gap for gap in gaps if gap <= active_gap_threshold_ms
    ]
    pause_gaps = [
        gap for gap in gaps if gap > active_gap_threshold_ms
    ]
    return {
        "count": len(ticks),
        "start_utc": epoch_iso(min(times) - server_offset_ms)
        if times
        else None,
        "end_utc": epoch_iso(max(times) - server_offset_ms)
        if times
        else None,
        "first_server_time": ticks[0].get("server_time") if ticks else None,
        "last_server_time": ticks[-1].get("server_time") if ticks else None,
        "first_local_time": ticks[0].get("local_time") if ticks else None,
        "last_local_time": ticks[-1].get("local_time") if ticks else None,
        "maximum_gap_ms": max(gaps) if gaps else None,
        "gap_ms": distribution(gaps),
        "market_active_gap_threshold_ms": active_gap_threshold_ms,
        "market_active_hours": round(
            sum(active_gaps) / 3_600_000,
            4,
        ),
        "market_pause_count": len(pause_gaps),
        "market_pause_hours": round(
            sum(pause_gaps) / 3_600_000,
            4,
        ),
        "sequence": sequence_continuity(ticks, "sequence"),
    }


def build_report(
    mql_root: Path,
    python_root: Path,
) -> dict[str, Any]:
    mql_session = (
        mql_root
        if any(mql_root.glob("heartbeat-*.csv"))
        else latest_directory(mql_root)
    )
    python_session = current_python_session(python_root)
    all_python_sessions = python_sessions(python_root)
    transactions = load_transactions(mql_session)
    heartbeats = load_heartbeats(mql_session)
    ticks = load_ticks(mql_session)
    (
        order_metadata,
        position_metadata,
        added_orders,
        removed_orders,
        added_positions,
        removed_positions,
        summaries,
        initial_sl,
    ) = load_snapshot_evidence(mql_session)
    server_offset_ms = derive_server_offset_ms(heartbeats)
    history_orders, history_deals = load_history(
        all_python_sessions or [python_session]
    )
    position_steps = history_position_steps(history_orders)
    observed_steps: list[float] = list(position_steps.values())
    for ticket, order in order_metadata.items():
        step = latest_profile_grid_step(
            str(order.get("comment") or ""),
            as_float(order.get("price_open")),
        )
        if step is None:
            continue
        observed_steps.append(step)
        if ticket in position_metadata:
            position_steps.setdefault(ticket, step)
    if observed_steps:
        fallback_step = Counter(observed_steps).most_common(1)[0][0]
        for ticket, position in position_metadata.items():
            if comment_parts(str(position.get("comment") or "")):
                position_steps.setdefault(ticket, fallback_step)
    deployments, rearm_bursts = analyze_deployments(
        transactions,
        order_metadata,
        ticks,
    )
    transaction_counts = Counter(
        row["trans_type"] for row in transactions
    )
    heartbeat = json.loads(
        (python_session / "heartbeat.json").read_text(encoding="utf-8")
    )
    return {
        "generated_utc": datetime.now(tz=UTC).isoformat(),
        "sessions": {
            "mql": file_inventory(mql_session),
            "python": file_inventory(python_session),
            "python_all": {
                "session_count": len(all_python_sessions),
                "sessions": [
                    {
                        "session": session.name,
                        "bytes": sum(
                            path.stat().st_size
                            for path in session.iterdir()
                            if path.is_file()
                        ),
                    }
                    for session in all_python_sessions
                ],
            },
        },
        "python_heartbeat": heartbeat,
        "mql_heartbeat": analyze_heartbeats(
            heartbeats,
            transaction_count=len(transactions),
            maximum_transaction_sequence=max(
                (
                    row["sequence"]
                    for row in transactions
                ),
                default=0,
            ),
            tick_count=len(ticks),
            maximum_tick_sequence=max(
                (row["sequence"] for row in ticks),
                default=0,
            ),
            maximum_snapshot_sequence=max(
                (
                    row["snapshot_sequence"]
                    for row in summaries
                ),
                default=0,
            ),
        ),
        "time_domains": {
            "broker_server_minus_observer_utc_ms": server_offset_ms,
            "mql_tick_epoch": "broker_server",
            "python_history_epoch": "broker_server",
            "python_tick_epoch": "utc",
        },
        "ticks": analyze_ticks(ticks, server_offset_ms),
        "transactions": {
            "count": len(transactions),
            "sequence": sequence_continuity(
                transactions,
                "sequence",
            ),
            "type_counts": {
                str(key): value for key, value in sorted(transaction_counts.items())
            },
            "first_server_time": transactions[0]["server_time"]
            if transactions
            else None,
            "last_server_time": transactions[-1]["server_time"]
            if transactions
            else None,
        },
        "requests": analyze_trade_requests(transactions),
        "state_changes": {
            "order_additions": len(added_orders),
            "order_removals": len(removed_orders),
            "position_additions": len(added_positions),
            "position_removals": len(removed_positions),
            "snapshot_count": len(summaries),
        },
        "deployments": {
            "complete_count": len(deployments),
            "complete": deployments,
            "non_deployment_add_burst_count": len(rearm_bursts),
            "non_deployment_add_bursts": rearm_bursts[:50],
        },
        "stops": analyze_stops(
            transactions,
            position_metadata,
            initial_sl,
            ticks,
            added_positions,
            removed_positions,
            position_steps=position_steps,
        ),
        "lifecycle": analyze_lifecycle(
            history_orders,
            history_deals,
            deployments,
            summaries,
            ticks,
            server_offset_ms,
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mql-root", required=True, type=Path)
    parser.add_argument("--python-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = build_report(args.mql_root, args.python_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps(
        {
            "output": str(args.output),
            "deployments": report["deployments"]["complete_count"],
            "transactions": report["transactions"]["count"],
            "requests": report["requests"]["count"],
            "ticks": report["ticks"]["count"],
            "stop_changes": report["stops"]["change_count"],
            "history_orders": report["lifecycle"]["historical_order_count"],
            "history_deals": report["lifecycle"]["historical_deal_count"],
        },
        sort_keys=True,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
