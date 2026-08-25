from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable

from .fidelity_score import (
    STOP_TIGHTENED_LOCK_STEPS,
    canonical_lifecycle_events,
    score_lifecycle,
)


UTC = timezone.utc
EXECUTION_KINDS = {"fill", "stop_exit", "close_fill"}
DECISION_KINDS = {
    "pending_request",
    "stop_request",
    "cancel_request",
    "close_request",
    "basket_trigger",
    "cycle_complete",
    "cycle_restart",
}
LIFECYCLE_KINDS = DECISION_KINDS | EXECUTION_KINDS | {"cycle_start"}
TRAILING_STAGE_PRICE_TOLERANCE_STEPS = 0.03
GLOBAL_EXECUTION_DEPENDENT_DECISION_KINDS = {
    "basket_trigger",
    "cancel_request",
    "close_request",
    "replacement_request",
}


def _parse_time(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _price(event: dict[str, Any]) -> float:
    kind = str(event.get("kind") or "")
    preferred = (
        ("accepted_price", "price", "requested_price")
        if kind in EXECUTION_KINDS
        else ("requested_price", "price", "accepted_price")
    )
    for key in preferred:
        value = event.get(key)
        if value not in (None, ""):
            return float(value)
    return 0.0


def _accepted(event: dict[str, Any]) -> bool:
    return int(event.get("retcode") or 0) in {
        0,
        10008,
        10009,
        10010,
    }


def _is_broker_acceptance_proxy(event: dict[str, Any]) -> bool:
    return (
        event.get("comparison_class") == "BROKER_ACCEPTANCE_PROXY"
        or (
            str(event.get("kind") or "") == "basket_trigger"
            and str(event.get("source") or "") == "observer_inferred"
        )
    )


def _cycle_groups(
    events: Iterable[dict[str, Any]],
) -> list[list[dict[str, Any]]]:
    grouped: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        cycle_id = str(event.get("cycle_id") or "")
        if cycle_id:
            grouped[cycle_id].append(dict(event))
    cycles = [
        sorted(
            rows,
            key=lambda event: (
                _parse_time(event["time_utc"]),
                int(event.get("sequence") or 0),
            ),
        )
        for rows in grouped.values()
    ]
    return sorted(
        cycles,
        key=lambda rows: _parse_time(rows[0]["time_utc"]),
    )


def _complete(cycle: list[dict[str, Any]]) -> bool:
    kinds = {str(event.get("kind") or "") for event in cycle}
    return "cycle_complete" in kinds and "cycle_restart" in kinds


def pair_complete_cycles(
    target_events: list[dict[str, Any]],
    candidate_events: list[dict[str, Any]],
    *,
    pairing: str,
    max_start_gap_seconds: float,
) -> list[tuple[list[dict[str, Any]], list[dict[str, Any]]]]:
    if pairing not in {"nearest", "ordinal"}:
        raise ValueError("pairing must be nearest or ordinal")
    if max_start_gap_seconds < 0:
        raise ValueError("max_start_gap_seconds must be non-negative")
    target = [
        cycle for cycle in _cycle_groups(target_events) if _complete(cycle)
    ]
    candidate = [
        cycle
        for cycle in _cycle_groups(candidate_events)
        if _complete(cycle)
    ]
    if pairing == "ordinal":
        pairs = []
        for target_cycle, candidate_cycle in zip(target, candidate):
            gap = abs(
                (
                    _parse_time(candidate_cycle[0]["time_utc"])
                    - _parse_time(target_cycle[0]["time_utc"])
                ).total_seconds()
            )
            if gap <= max_start_gap_seconds:
                pairs.append((target_cycle, candidate_cycle))
        return pairs

    remaining = list(candidate)
    pairs: list[
        tuple[list[dict[str, Any]], list[dict[str, Any]]]
    ] = []
    for target_cycle in target:
        if not remaining:
            break
        target_start = _parse_time(target_cycle[0]["time_utc"])
        closest = min(
            remaining,
            key=lambda cycle: abs(
                (
                    _parse_time(cycle[0]["time_utc"]) - target_start
                ).total_seconds()
            ),
        )
        gap = abs(
            (
                _parse_time(closest[0]["time_utc"]) - target_start
            ).total_seconds()
        )
        if gap <= max_start_gap_seconds:
            pairs.append((target_cycle, closest))
            remaining.remove(closest)
    return pairs


def _geometry(events: list[dict[str, Any]]) -> tuple[float, float]:
    initial: dict[str, dict[str, Any]] = {}
    for event in events:
        if str(event.get("kind") or "") != "pending_request":
            continue
        comment = str(event.get("comment") or "")
        if comment and comment not in initial and _accepted(event):
            initial[comment] = event
    buy = initial.get("STR B1")
    sell = initial.get("STR S1")
    if buy is None or sell is None:
        raise ValueError("Cycle is missing accepted STR B1/STR S1 geometry")
    buy_price = _price(buy)
    sell_price = _price(sell)
    step = (buy_price - sell_price) / 2.0
    if step <= 0:
        raise ValueError("Cycle step must be positive")
    return (buy_price + sell_price) / 2.0, step


def _normalized_events(
    events: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    anchor, step = _geometry(events)
    expected = [
        f"STR {side}{level}"
        for level in range(1, 31)
        for side in ("B", "S")
    ]
    seen_pending: set[str] = set()
    eligible_replacements: Counter[str] = Counter()
    used_replacements: Counter[str] = Counter()
    eligible_rearms: Counter[str] = Counter()
    used_rearms: Counter[str] = Counter()
    duplicate_slots: list[str] = []
    rejected_requests: list[dict[str, Any]] = []
    normalized: list[dict[str, Any]] = []
    initial_comments: list[str] = []
    for event in events:
        kind = str(event.get("kind") or "")
        if kind not in LIFECYCLE_KINDS:
            continue
        row = dict(event)
        comment = str(row.get("comment") or "")
        if kind.endswith("_request") and not _accepted(row):
            rejected_requests.append(
                {
                    "kind": kind,
                    "comment": comment,
                    "side": str(row.get("side") or ""),
                    "level": int(row.get("level") or 0),
                    "volume": float(row.get("volume") or 0.0),
                    "requested_price": _price(row),
                    "retcode": int(row.get("retcode") or 0),
                    "time_utc": str(row.get("time_utc") or ""),
                }
            )
            continue
        if kind == "stop_exit" and comment:
            eligible_rearms[comment] += 1
        if kind == "cancel_request" and comment and _accepted(row):
            eligible_replacements[comment] += 1
        if kind == "pending_request":
            if len(seen_pending) < len(expected):
                row["kind"] = "initial_pending_request"
                if _accepted(row):
                    if comment in seen_pending:
                        duplicate_slots.append(comment)
                    else:
                        seen_pending.add(comment)
                        initial_comments.append(comment)
            else:
                if (
                    used_replacements[comment]
                    < eligible_replacements[comment]
                ):
                    row["kind"] = "replacement_request"
                    if _accepted(row):
                        used_replacements[comment] += 1
                else:
                    row["kind"] = "rearm_request"
                    if _accepted(row):
                        used_rearms[comment] += 1
        if row["kind"] in {
            "cycle_start",
            "basket_trigger",
            "cycle_complete",
            "cycle_restart",
        }:
            row["comment"] = ""
            row["side"] = ""
            row["level"] = 0

        event_price = _price(row)
        if row["kind"] in {
            "initial_pending_request",
            "replacement_request",
            "rearm_request",
            "stop_request",
        }:
            row["requested_price"] = round(
                (event_price - anchor) / step,
                6,
            )
            raw_stop = float(row.get("sl") or 0.0)
            row["sl"] = (
                round((raw_stop - anchor) / step, 6)
                if raw_stop
                else 0.0
            )
        else:
            row["requested_price"] = 0.0
            row["sl"] = 0.0
        if row["kind"] in EXECUTION_KINDS:
            row["normalized_execution_price"] = round(
                (event_price - anchor) / step,
                6,
            )
        row["tp"] = 0.0
        normalized.append(row)

    deployment = {
        "count": len(initial_comments),
        "missing_slots": sorted(set(expected) - set(initial_comments)),
        "duplicate_slots": sorted(set(duplicate_slots)),
        "sequence_match": initial_comments == expected,
        "anchor": anchor,
        "step": step,
        "rejected_requests": rejected_requests,
    }
    return normalized, deployment


def _rounded_signature(event: dict[str, Any]) -> tuple[Any, ...]:
    kind = str(event.get("kind") or "")
    stop_value = (
        event.get("stage_sl")
        if kind in {"stop_activation", "stop_tightened"}
        else event.get("sl")
    )
    return (
        kind,
        str(event.get("comment") or ""),
        str(event.get("side") or ""),
        int(event.get("level") or 0),
        round(float(event.get("volume") or 0.0), 8),
        round(float(event.get("requested_price") or 0.0), 4),
        round(float(stop_value or 0.0), 4),
        int(_accepted(event)) if kind.endswith("request") else 1,
    )


def _event_identity(event: dict[str, Any]) -> tuple[str, str, int]:
    return (
        str(event.get("comment") or ""),
        str(event.get("side") or ""),
        int(event.get("level") or 0),
    )


def _mark_stage_source_execution_diverged(
    events: list[dict[str, Any]],
    stage_event: dict[str, Any],
) -> None:
    stage_event["comparison_class"] = "EXECUTION_DIVERGED"
    identity = _event_identity(stage_event)
    time_utc = str(stage_event.get("time_utc") or "")
    for event in events:
        if (
            str(event.get("kind") or "") == "stop_request"
            and _event_identity(event) == identity
            and str(event.get("time_utc") or "") == time_utc
        ):
            event["comparison_class"] = "EXECUTION_DIVERGED"
            return


def _best_effort_implied_tightened_count(
    events: list[dict[str, Any]],
    identity: tuple[str, str, int],
) -> int:
    matching = [
        event for event in events if _event_identity(event) == identity
    ]
    if not any(
        str(event.get("evidence_grade") or "") == "BEST_EFFORT"
        for event in matching
    ):
        return 0
    fill_price: float | None = None
    tightened_seen = False
    implied = 0
    side = identity[1]
    for event in matching:
        kind = str(event.get("kind") or "")
        if kind == "fill":
            fill_price = float(
                event.get("normalized_execution_price") or 0.0
            )
            tightened_seen = False
            continue
        if fill_price is None:
            continue
        if kind == "stop_request":
            stop_price = float(event.get("sl") or 0.0)
            locked = (
                stop_price - fill_price
                if side == "buy"
                else fill_price - stop_price
            )
            if locked >= STOP_TIGHTENED_LOCK_STEPS:
                tightened_seen = True
            continue
        if kind == "stop_exit":
            exit_price = float(
                event.get("normalized_execution_price") or 0.0
            )
            locked = (
                exit_price - fill_price
                if side == "buy"
                else fill_price - exit_price
            )
            if (
                not tightened_seen
                and locked >= STOP_TIGHTENED_LOCK_STEPS
            ):
                implied += 1
            fill_price = None
            tightened_seen = False
        elif kind == "close_fill":
            fill_price = None
            tightened_seen = False
    return implied


def _mark_execution_divergence(
    events: list[dict[str, Any]],
    divergence_at: datetime | None,
    identity: tuple[str, str, int] | None,
) -> None:
    if divergence_at is None:
        return
    for event in events:
        time_value = event.get("time_utc")
        event_identity = _event_identity(event)
        if (
            time_value
            and _parse_time(time_value) >= divergence_at
            and (identity is None or event_identity == identity)
            and str(event.get("kind") or "")
            != "initial_pending_request"
        ):
            event["comparison_class"] = "EXECUTION_DIVERGED"


def _mark_global_execution_dependent_decisions(
    events: list[dict[str, Any]],
    divergence_at: datetime | None,
) -> None:
    if divergence_at is None:
        return
    for event in events:
        time_value = event.get("time_utc")
        if (
            time_value
            and _parse_time(time_value) >= divergence_at
            and str(event.get("kind") or "")
            in GLOBAL_EXECUTION_DEPENDENT_DECISION_KINDS
        ):
            event["comparison_class"] = "EXECUTION_DIVERGED"


def _mark_after_counterpart_cycle_complete(
    events: list[dict[str, Any]],
    counterpart_events: list[dict[str, Any]],
    counterpart_divergence_at: datetime | None,
) -> None:
    if counterpart_divergence_at is None:
        return
    start = _parse_time(events[0]["time_utc"])
    counterpart_start = _parse_time(
        counterpart_events[0]["time_utc"]
    )
    complete = min(
        (
            _parse_time(event["time_utc"])
            for event in events
            if str(event.get("kind") or "") == "cycle_complete"
        ),
        default=None,
    )
    counterpart_complete = min(
        (
            _parse_time(event["time_utc"])
            for event in counterpart_events
            if str(event.get("kind") or "") == "cycle_complete"
        ),
        default=None,
    )
    if (
        complete is None
        or
        counterpart_complete is None
        or counterpart_divergence_at > counterpart_complete
    ):
        return
    cutoff_elapsed = counterpart_complete - counterpart_start
    if cutoff_elapsed >= complete - start:
        return
    for event in events:
        time_value = event.get("time_utc")
        if (
            time_value
            and _parse_time(time_value) - start >= cutoff_elapsed
        ):
            event["comparison_class"] = "EXECUTION_DIVERGED"
    for event in counterpart_events:
        if (
            str(event.get("kind") or "")
            in {"cycle_complete", "cycle_restart"}
            and event.get("time_utc")
            and _parse_time(event["time_utc"]) >= counterpart_complete
        ):
            event["comparison_class"] = "EXECUTION_DIVERGED"


def _execution_divergence_markers(
    target_events: list[dict[str, Any]],
    candidate_events: list[dict[str, Any]],
    *,
    normalized_price_tolerance: float,
    execution_time_tolerance_seconds: float,
) -> tuple[
    dict[tuple[str, str, int], datetime],
    dict[tuple[str, str, int], datetime],
    list[dict[str, Any]],
]:
    target_execution: defaultdict[
        tuple[str, str, int], list[dict[str, Any]]
    ] = defaultdict(list)
    candidate_execution: defaultdict[
        tuple[str, str, int], list[dict[str, Any]]
    ] = defaultdict(list)
    for event in target_events:
        if str(event.get("kind") or "") in EXECUTION_KINDS:
            target_execution[_event_identity(event)].append(event)
    for event in candidate_events:
        if str(event.get("kind") or "") in EXECUTION_KINDS:
            candidate_execution[_event_identity(event)].append(event)

    target_start = _parse_time(target_events[0]["time_utc"])
    candidate_start = _parse_time(candidate_events[0]["time_utc"])
    target_markers: dict[tuple[str, str, int], datetime] = {}
    candidate_markers: dict[tuple[str, str, int], datetime] = {}
    price_mismatches: list[dict[str, Any]] = []
    identities = sorted(set(target_execution) | set(candidate_execution))
    for identity in identities:
        target_rows = target_execution.get(identity, [])
        candidate_rows = candidate_execution.get(identity, [])
        for index in range(max(len(target_rows), len(candidate_rows))):
            target = target_rows[index] if index < len(target_rows) else None
            candidate = (
                candidate_rows[index]
                if index < len(candidate_rows)
                else None
            )
            signatures_match = (
                target is not None
                and candidate is not None
                and _rounded_signature(target)
                == _rounded_signature(candidate)
            )
            if signatures_match:
                target_price = float(
                    target.get("normalized_execution_price") or 0.0
                )
                candidate_price = float(
                    candidate.get("normalized_execution_price") or 0.0
                )
                price_delta = abs(target_price - candidate_price)
                target_elapsed = (
                    _parse_time(target["time_utc"]) - target_start
                ).total_seconds()
                candidate_elapsed = (
                    _parse_time(candidate["time_utc"]) - candidate_start
                ).total_seconds()
                timing_delta = abs(target_elapsed - candidate_elapsed)
                if (
                    price_delta <= normalized_price_tolerance
                    and timing_delta <= execution_time_tolerance_seconds
                ):
                    continue
                if price_delta > normalized_price_tolerance:
                    price_mismatches.append(
                        {
                            "category": "execution_price",
                            "index": index,
                            "kind": str(target.get("kind") or ""),
                            "comment": identity[0],
                            "side": identity[1],
                            "level": identity[2],
                            "volume": float(target.get("volume") or 0.0),
                            "target_price": _price(target),
                            "candidate_price": _price(candidate),
                            "target_normalized_price": target_price,
                            "candidate_normalized_price": candidate_price,
                            "normalized_price_delta": price_delta,
                        }
                    )
                if timing_delta > execution_time_tolerance_seconds:
                    price_mismatches.append(
                        {
                            "category": "execution_timing_causal",
                            "index": index,
                            "kind": str(target.get("kind") or ""),
                            "comment": identity[0],
                            "side": identity[1],
                            "level": identity[2],
                            "volume": float(target.get("volume") or 0.0),
                            "target_elapsed_seconds": target_elapsed,
                            "candidate_elapsed_seconds": candidate_elapsed,
                            "absolute_delta_seconds": timing_delta,
                            "tolerance_seconds": (
                                execution_time_tolerance_seconds
                            ),
                        }
                    )
            if target is not None:
                target_marker = _parse_time(target["time_utc"])
            elif candidate is not None:
                candidate_elapsed = (
                    _parse_time(candidate["time_utc"]) - candidate_start
                )
                target_marker = target_start + candidate_elapsed
            else:
                break
            if candidate is not None:
                candidate_marker = _parse_time(candidate["time_utc"])
            else:
                target_elapsed = target_marker - target_start
                candidate_marker = candidate_start + target_elapsed
            target_markers[identity] = target_marker
            candidate_markers[identity] = candidate_marker
            break
    return target_markers, candidate_markers, price_mismatches


def _transition_timing(
    target_events: list[dict[str, Any]],
    candidate_events: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    candidate_by_signature: defaultdict[
        tuple[Any, ...], list[dict[str, Any]]
    ] = defaultdict(list)
    for event in candidate_events:
        candidate_by_signature[_rounded_signature(event)].append(event)

    used: Counter[tuple[Any, ...]] = Counter()
    occurrences: Counter[tuple[str, str]] = Counter()
    target_start = _parse_time(target_events[0]["time_utc"])
    candidate_start = _parse_time(candidate_events[0]["time_utc"])
    timing: list[dict[str, Any]] = []
    for target_event in target_events:
        signature = _rounded_signature(target_event)
        index = used[signature]
        candidates = candidate_by_signature.get(signature, [])
        if index >= len(candidates):
            continue
        used[signature] += 1
        candidate_event = candidates[index]
        kind = str(target_event.get("kind") or "")
        comment = str(target_event.get("comment") or "")
        occurrences[(kind, comment)] += 1
        target_elapsed = (
            _parse_time(target_event["time_utc"]) - target_start
        ).total_seconds()
        candidate_elapsed = (
            _parse_time(candidate_event["time_utc"]) - candidate_start
        ).total_seconds()
        if _is_broker_acceptance_proxy(
            target_event
        ) or _is_broker_acceptance_proxy(candidate_event):
            comparison_class = "BROKER_ACCEPTANCE_PROXY"
        elif (
            target_event.get("comparison_class")
            == "EXECUTION_DIVERGED"
            or candidate_event.get("comparison_class")
            == "EXECUTION_DIVERGED"
        ):
            comparison_class = "EXECUTION_DIVERGED"
        else:
            comparison_class = "PAIRED"
        timing.append(
            {
                "kind": kind,
                "comment": comment,
                "side": str(target_event.get("side") or ""),
                "level": int(target_event.get("level") or 0),
                "occurrence": occurrences[(kind, comment)],
                "target_elapsed_seconds": round(target_elapsed, 6),
                "candidate_elapsed_seconds": round(
                    candidate_elapsed, 6
                ),
                "delta_seconds": round(
                    candidate_elapsed - target_elapsed, 6
                ),
                "comparison_class": comparison_class,
            }
        )

    eligible_timing = [
        event
        for event in timing
        if event["comparison_class"] == "PAIRED"
    ]
    absolute_deltas = sorted(
        abs(float(event["delta_seconds"])) for event in eligible_timing
    )
    p95_index = (
        max(0, (95 * len(absolute_deltas) + 99) // 100 - 1)
        if absolute_deltas
        else 0
    )
    denominator = max(
        len(target_events),
        len(candidate_events),
        1,
    )
    summary = {
        "target_events": len(target_events),
        "candidate_events": len(candidate_events),
        "matched_events": len(timing),
        "eligible_timed_events": len(eligible_timing),
        "excluded_proxy_events": sum(
            event["comparison_class"] == "BROKER_ACCEPTANCE_PROXY"
            for event in timing
        ),
        "excluded_execution_diverged_events": sum(
            event["comparison_class"] == "EXECUTION_DIVERGED"
            for event in timing
        ),
        "coverage_percent": round(
            len(timing) / denominator * 100.0,
            4,
        ),
        "max_absolute_delta_seconds": (
            round(max(absolute_deltas), 6)
            if absolute_deltas
            else 0.0
        ),
        "p95_absolute_delta_seconds": (
            round(absolute_deltas[p95_index], 6)
            if absolute_deltas
            else 0.0
        ),
    }
    return timing, summary


def compare_independent_cycle_pair(
    target_events: list[dict[str, Any]],
    candidate_events: list[dict[str, Any]],
    *,
    start_tolerance_seconds: float,
    normalized_price_tolerance: float,
) -> dict[str, Any]:
    if start_tolerance_seconds < 0 or normalized_price_tolerance < 0:
        raise ValueError("Tolerances must be non-negative")
    if not target_events or not candidate_events:
        raise ValueError("Both cycle event streams are required")

    target_cycle_id = str(target_events[0].get("cycle_id") or "")
    candidate_cycle_id = str(
        candidate_events[0].get("cycle_id") or ""
    )
    target, target_deployment = _normalized_events(target_events)
    candidate, candidate_deployment = _normalized_events(
        candidate_events
    )
    (
        target_divergences,
        candidate_divergences,
        execution_price_mismatches,
    ) = _execution_divergence_markers(
        target,
        candidate,
        normalized_price_tolerance=normalized_price_tolerance,
        execution_time_tolerance_seconds=start_tolerance_seconds,
    )
    for identity, divergence_at in target_divergences.items():
        _mark_execution_divergence(target, divergence_at, identity)
    for identity, divergence_at in candidate_divergences.items():
        _mark_execution_divergence(candidate, divergence_at, identity)
    _mark_global_execution_dependent_decisions(
        target,
        min(target_divergences.values(), default=None),
    )
    _mark_global_execution_dependent_decisions(
        candidate,
        min(candidate_divergences.values(), default=None),
    )
    _mark_after_counterpart_cycle_complete(
        target,
        candidate,
        min(candidate_divergences.values(), default=None),
    )
    _mark_after_counterpart_cycle_complete(
        candidate,
        target,
        min(target_divergences.values(), default=None),
    )
    transition_timing, transition_timing_summary = _transition_timing(
        target,
        candidate,
    )
    deterministic_mismatches: list[dict[str, Any]] = []
    for source, deployment in (
        ("target", target_deployment),
        ("candidate", candidate_deployment),
    ):
        if (
            deployment["count"] != 60
            or deployment["missing_slots"]
            or deployment["duplicate_slots"]
            or not deployment["sequence_match"]
        ):
            deterministic_mismatches.append(
                {
                    "category": "deployment_structure",
                    "source": source,
                    **deployment,
                }
            )

    trailing_stage_kinds = {
        "stop_activation",
        "stop_tightened",
    }
    target_canonical = canonical_lifecycle_events(target)
    candidate_canonical = canonical_lifecycle_events(candidate)
    execution_diverged_stage_identities = {
        _event_identity(event)
        for event in (*target_canonical, *candidate_canonical)
        if str(event.get("kind") or "") in trailing_stage_kinds
        and event.get("comparison_class") == "EXECUTION_DIVERGED"
    }
    target_decisions = [
        event
        for event in target_canonical
        if str(event.get("kind") or "") not in EXECUTION_KINDS
        and event.get("comparison_class") != "EXECUTION_DIVERGED"
    ]
    candidate_decisions = [
        event
        for event in candidate_canonical
        if str(event.get("kind") or "") not in EXECUTION_KINDS
        and event.get("comparison_class") != "EXECUTION_DIVERGED"
    ]
    target_by_identity: defaultdict[
        tuple[str, str, int], list[tuple[Any, ...]]
    ] = defaultdict(list)
    candidate_by_identity: defaultdict[
        tuple[str, str, int], list[tuple[Any, ...]]
    ] = defaultdict(list)
    target_stage_events_by_identity: defaultdict[
        tuple[str, str, int], list[dict[str, Any]]
    ] = defaultdict(list)
    candidate_stage_events_by_identity: defaultdict[
        tuple[str, str, int], list[dict[str, Any]]
    ] = defaultdict(list)
    for event in target_decisions:
        identity = _event_identity(event)
        target_by_identity[identity].append(
            _rounded_signature(event)
        )
        if (
            str(event.get("kind") or "") in trailing_stage_kinds
            and identity not in execution_diverged_stage_identities
        ):
            target_stage_events_by_identity[identity].append(event)
    for event in candidate_decisions:
        identity = _event_identity(event)
        candidate_by_identity[identity].append(
            _rounded_signature(event)
        )
        if (
            str(event.get("kind") or "") in trailing_stage_kinds
            and identity not in execution_diverged_stage_identities
        ):
            candidate_stage_events_by_identity[identity].append(event)
    decision_identities = sorted(
        set(target_by_identity) | set(candidate_by_identity)
    )
    target_start = _parse_time(target[0]["time_utc"])
    candidate_start = _parse_time(candidate[0]["time_utc"])
    for identity in decision_identities:
        target_signatures = target_by_identity.get(identity, [])
        candidate_signatures = candidate_by_identity.get(identity, [])
        target_stage_events = target_stage_events_by_identity.get(
            identity,
            [],
        )
        candidate_stage_events = candidate_stage_events_by_identity.get(
            identity,
            [],
        )
        stage_mismatch: dict[str, Any] | None = None
        if len(target_stage_events) != len(candidate_stage_events):
            target_stage_counts = Counter(
                str(event.get("kind") or "")
                for event in target_stage_events
            )
            candidate_stage_counts = Counter(
                str(event.get("kind") or "")
                for event in candidate_stage_events
            )
            target_missing_tightened = max(
                candidate_stage_counts["stop_tightened"]
                - target_stage_counts["stop_tightened"],
                0,
            )
            candidate_missing_tightened = max(
                target_stage_counts["stop_tightened"]
                - candidate_stage_counts["stop_tightened"],
                0,
            )
            activation_counts_match = (
                target_stage_counts["stop_activation"]
                == candidate_stage_counts["stop_activation"]
            )
            target_omission_proven = (
                activation_counts_match
                and target_missing_tightened > 0
                and _best_effort_implied_tightened_count(
                    target,
                    identity,
                )
                >= target_missing_tightened
            )
            candidate_omission_proven = (
                activation_counts_match
                and candidate_missing_tightened > 0
                and _best_effort_implied_tightened_count(
                    candidate,
                    identity,
                )
                >= candidate_missing_tightened
            )
            if target_omission_proven:
                extra = [
                    event
                    for event in candidate_stage_events
                    if str(event.get("kind") or "")
                    == "stop_tightened"
                ][target_stage_counts["stop_tightened"] :]
                for event in extra:
                    _mark_stage_source_execution_diverged(
                        candidate,
                        event,
                    )
            elif candidate_omission_proven:
                extra = [
                    event
                    for event in target_stage_events
                    if str(event.get("kind") or "")
                    == "stop_tightened"
                ][candidate_stage_counts["stop_tightened"] :]
                for event in extra:
                    _mark_stage_source_execution_diverged(
                        target,
                        event,
                    )
            else:
                stage_mismatch = {
                    "target_count": len(target_stage_events),
                    "candidate_count": len(candidate_stage_events),
                }
        else:
            stage_tolerance = max(
                normalized_price_tolerance,
                TRAILING_STAGE_PRICE_TOLERANCE_STEPS,
            )
            for index, (
                target_stage_event,
                candidate_stage_event,
            ) in enumerate(
                zip(target_stage_events, candidate_stage_events)
            ):
                target_stage = _rounded_signature(target_stage_event)
                candidate_stage = _rounded_signature(
                    candidate_stage_event
                )
                structural_target = (
                    target_stage[:5] + target_stage[7:]
                )
                structural_candidate = (
                    candidate_stage[:5] + candidate_stage[7:]
                )
                stop_delta = abs(
                    target_stage[6] - candidate_stage[6]
                )
                target_elapsed = (
                    _parse_time(target_stage_event["time_utc"])
                    - target_start
                ).total_seconds()
                candidate_elapsed = (
                    _parse_time(candidate_stage_event["time_utc"])
                    - candidate_start
                ).total_seconds()
                timing_delta = abs(target_elapsed - candidate_elapsed)
                observer_inferred = any(
                    str(event.get("source") or "")
                    == "observer_inferred"
                    or str(event.get("capture_limit") or "")
                    == "no_originating_request_payload"
                    or str(event.get("evidence_grade") or "")
                    == "BEST_EFFORT"
                    for event in (
                        target_stage_event,
                        candidate_stage_event,
                    )
                )
                if structural_target != structural_candidate:
                    stage_mismatch = {
                        "index": index,
                        "target": target_stage,
                        "candidate": candidate_stage,
                        "normalized_sl_delta": stop_delta,
                        "normalized_sl_tolerance": stage_tolerance,
                    }
                    break
                if stop_delta > stage_tolerance:
                    if (
                        observer_inferred
                        and timing_delta > start_tolerance_seconds
                    ):
                        _mark_stage_source_execution_diverged(
                            target,
                            target_stage_event,
                        )
                        _mark_stage_source_execution_diverged(
                            candidate,
                            candidate_stage_event,
                        )
                        continue
                    stage_mismatch = {
                        "index": index,
                        "target": target_stage,
                        "candidate": candidate_stage,
                        "normalized_sl_delta": stop_delta,
                        "normalized_sl_tolerance": stage_tolerance,
                        "absolute_timing_delta_seconds": timing_delta,
                    }
                    break
        if stage_mismatch is not None:
            deterministic_mismatches.append(
                {
                    "category": "trailing_stage_sequence",
                    "comment": identity[0],
                    "side": identity[1],
                    "level": identity[2],
                    **stage_mismatch,
                }
            )
        target_signatures = [
            signature
            for signature in target_signatures
            if signature[0] not in trailing_stage_kinds
        ]
        candidate_signatures = [
            signature
            for signature in candidate_signatures
            if signature[0] not in trailing_stage_kinds
        ]
        if len(target_signatures) != len(candidate_signatures):
            deterministic_mismatches.append(
                {
                    "category": "decision_sequence",
                    "comment": identity[0],
                    "side": identity[1],
                    "level": identity[2],
                    "target_count": len(target_signatures),
                    "candidate_count": len(candidate_signatures),
                }
            )
        for index, (target_signature, candidate_signature) in enumerate(
            zip(target_signatures, candidate_signatures)
        ):
            structural_target = (
                target_signature[:5] + target_signature[7:]
            )
            structural_candidate = (
                candidate_signature[:5] + candidate_signature[7:]
            )
            price_delta = abs(
                target_signature[5] - candidate_signature[5]
            )
            stop_delta = abs(
                target_signature[6] - candidate_signature[6]
            )
            if (
                structural_target != structural_candidate
                or price_delta > normalized_price_tolerance
                or stop_delta > normalized_price_tolerance
            ):
                deterministic_mismatches.append(
                    {
                        "category": "normalized_decision",
                        "comment": identity[0],
                        "side": identity[1],
                        "level": identity[2],
                        "index": index,
                        "target": target_signature,
                        "candidate": candidate_signature,
                        "normalized_price_delta": price_delta,
                        "normalized_sl_delta": stop_delta,
                    }
                )
                break

    target_execution_events = [
        event
        for event in target
        if str(event.get("kind") or "") in EXECUTION_KINDS
    ]
    candidate_execution_events = [
        event
        for event in candidate
        if str(event.get("kind") or "") in EXECUTION_KINDS
    ]
    target_execution = [
        _rounded_signature(event) for event in target_execution_events
    ]
    candidate_execution = [
        _rounded_signature(event) for event in candidate_execution_events
    ]
    execution_mismatches: list[dict[str, Any]] = list(
        execution_price_mismatches
    )
    execution_timing: list[dict[str, Any]] = []
    if target_execution != candidate_execution:
        execution_mismatches.append(
            {
                "category": "execution_sequence",
                "target": target_execution,
                "candidate": candidate_execution,
            }
        )
    target_cycle_start = _parse_time(target[0]["time_utc"])
    candidate_cycle_start = _parse_time(candidate[0]["time_utc"])
    for index, (target_event, candidate_event) in enumerate(
        zip(target_execution_events, candidate_execution_events)
    ):
        if _rounded_signature(target_event) != _rounded_signature(
            candidate_event
        ):
            continue
        target_elapsed = (
            _parse_time(target_event["time_utc"]) - target_cycle_start
        ).total_seconds()
        candidate_elapsed = (
            _parse_time(candidate_event["time_utc"])
            - candidate_cycle_start
        ).total_seconds()
        delta = candidate_elapsed - target_elapsed
        timing = {
            "index": index,
            "kind": str(target_event.get("kind") or ""),
            "comment": str(target_event.get("comment") or ""),
            "side": str(target_event.get("side") or ""),
            "level": int(target_event.get("level") or 0),
            "volume": float(target_event.get("volume") or 0.0),
            "target_elapsed_seconds": round(target_elapsed, 6),
            "candidate_elapsed_seconds": round(candidate_elapsed, 6),
            "delta_seconds": round(delta, 6),
        }
        execution_timing.append(timing)
        if abs(delta) > start_tolerance_seconds:
            execution_mismatches.append(
                {
                    "category": "execution_timing",
                    **timing,
                }
            )

    start_delta = abs(
        (
            _parse_time(candidate_events[0]["time_utc"])
            - _parse_time(target_events[0]["time_utc"])
        ).total_seconds()
    )
    if start_delta > start_tolerance_seconds:
        execution_mismatches.append(
            {
                "category": "cycle_start_timing",
                "delta_seconds": start_delta,
            }
        )

    fidelity = score_lifecycle(target, candidate)
    status = "FAIL" if deterministic_mismatches else "PASS"
    return {
        "status": status,
        "logic_status": status,
        "execution_status": (
            "DIFFERENT" if execution_mismatches else "PASS"
        ),
        "target_cycle_id": target_cycle_id,
        "candidate_cycle_id": candidate_cycle_id,
        "cycle_id": f"{target_cycle_id}__{candidate_cycle_id}",
        "deployment": {
            "target_count": target_deployment["count"],
            "candidate_count": candidate_deployment["count"],
            "target_missing_slots": target_deployment[
                "missing_slots"
            ],
            "candidate_missing_slots": candidate_deployment[
                "missing_slots"
            ],
            "target_duplicate_slots": target_deployment[
                "duplicate_slots"
            ],
            "candidate_duplicate_slots": candidate_deployment[
                "duplicate_slots"
            ],
            "target_sequence_match": target_deployment[
                "sequence_match"
            ],
            "candidate_sequence_match": candidate_deployment[
                "sequence_match"
            ],
        },
        "geometry": {
            "target_anchor": target_deployment["anchor"],
            "target_step": target_deployment["step"],
            "candidate_anchor": candidate_deployment["anchor"],
            "candidate_step": candidate_deployment["step"],
        },
        "request_rejections": {
            "classification": "BROKER_REJECTION_DIAGNOSTIC",
            "target_count": len(target_deployment["rejected_requests"]),
            "candidate_count": len(
                candidate_deployment["rejected_requests"]
            ),
            "target": target_deployment["rejected_requests"],
            "candidate": candidate_deployment["rejected_requests"],
        },
        "deterministic_mismatch_count": len(
            deterministic_mismatches
        ),
        "execution_mismatch_count": len(execution_mismatches),
        "deterministic_mismatches": deterministic_mismatches,
        "execution_mismatches": execution_mismatches,
        "execution_timing": execution_timing,
        "transition_timing": transition_timing,
        "transition_timing_summary": transition_timing_summary,
        "fidelity": fidelity,
        "evidence_grade": "BEST_EFFORT",
        "tolerances": {
            "start_seconds": start_tolerance_seconds,
            "normalized_price": normalized_price_tolerance,
        },
    }
