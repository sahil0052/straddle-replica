from __future__ import annotations

from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics
from typing import Any, Iterable, Mapping

from .canonical_events import CanonicalizationResult, canonicalize_events
from .fidelity_score import score_lifecycle


UTC = timezone.utc
DECISION_KINDS = {
    "pending_request",
    "rearm_request",
    "stop_request",
    "cancel_request",
    "close_request",
}
EXECUTION_KINDS = {"fill", "stop_exit", "close_fill"}
CYCLE_COMPLETE_KINDS = {
    "cycle_complete",
    "cycle_restart",
    "shadow_reset_complete",
    "restart_ready",
}
TELEMETRY_EXTENSION_FIELDS = (
    "schema_version",
    "event_sequence",
    "event_id",
    "deal_ticket",
    "order_ticket",
    "position_ticket",
    "cycle_realized",
    "floating_profit",
    "cycle_net",
    "basket_target",
    "evidence_grade",
)


def _parse_time(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _number(event: dict[str, Any], key: str) -> float:
    value = event.get(key, 0.0)
    if value in (None, ""):
        return 0.0
    return float(value)


def _event_price(event: dict[str, Any]) -> float:
    if event.get("price") not in (None, ""):
        return _number(event, "price")
    kind = str(event.get("kind") or "")
    return _number(
        event,
        "accepted_price" if kind in EXECUTION_KINDS else "requested_price",
    )


def _expected_comments() -> list[str]:
    return [
        f"STR {side}{level}"
        for level in range(1, 31)
        for side in ("B", "S")
    ]


def _cycle_id(events: Iterable[dict[str, Any]]) -> str | None:
    values = {
        str(event.get("cycle_id") or "")
        for event in events
        if str(event.get("cycle_id") or "")
    }
    return next(iter(values)) if len(values) == 1 else None


def _duplicates(values: Iterable[str]) -> list[str]:
    return sorted(
        value for value, count in Counter(values).items() if count > 1
    )


def _decision_signature(event: dict[str, Any]) -> tuple[Any, ...]:
    return (
        str(event.get("kind") or ""),
        str(event.get("comment") or ""),
        str(event.get("side") or ""),
        _number(event, "volume"),
        _event_price(event),
        _number(event, "sl"),
        _number(event, "tp"),
        int(event.get("retcode") or 0),
    )


def _pair_by_semantic_key(
    events: Iterable[dict[str, Any]],
) -> dict[tuple[str, str, int], dict[str, Any]]:
    occurrences: defaultdict[tuple[str, str], int] = defaultdict(int)
    paired: dict[tuple[str, str, int], dict[str, Any]] = {}
    for event in events:
        kind = str(event.get("kind") or "")
        comment = str(event.get("comment") or "")
        base = (kind, comment)
        occurrences[base] += 1
        paired[(kind, comment, occurrences[base])] = event
    return paired


def _semantic_sequence(
    events: Iterable[dict[str, Any]],
) -> list[tuple[str, str, int]]:
    occurrences: defaultdict[tuple[str, str], int] = defaultdict(int)
    result: list[tuple[str, str, int]] = []
    for event in events:
        kind = str(event.get("kind") or "")
        comment = str(event.get("comment") or "")
        base = (kind, comment)
        occurrences[base] += 1
        result.append((kind, comment, occurrences[base]))
    return result


def _request_accepted(event: dict[str, Any]) -> bool:
    return int(event.get("retcode") or 0) in {
        0,
        10008,
        10009,
        10010,
    }


def _classify_decisions(
    events: Iterable[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    initial_pending: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    seen_pending: set[str] = set()
    eligible_rearms: Counter[str] = Counter()
    used_rearms: Counter[str] = Counter()
    ineligible_rearms: list[str] = []

    for event in events:
        kind = str(event.get("kind") or "")
        comment = str(event.get("comment") or "")
        if kind == "stop_exit" and comment:
            eligible_rearms[comment] += 1
            continue
        if kind == "pending_request":
            canonical = dict(event)
            if comment not in seen_pending:
                canonical["kind"] = "initial_pending_request"
                if _request_accepted(event):
                    seen_pending.add(comment)
                    initial_pending.append(canonical)
            else:
                canonical["kind"] = "rearm_request"
                if _request_accepted(event):
                    if used_rearms[comment] >= eligible_rearms[comment]:
                        ineligible_rearms.append(comment)
                    used_rearms[comment] += 1
            decisions.append(canonical)
        elif kind in DECISION_KINDS:
            decisions.append(dict(event))
    return initial_pending, decisions, sorted(set(ineligible_rearms))


def _classified_lifecycle_events(
    events: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    classified: list[dict[str, Any]] = []
    seen_pending: set[str] = set()
    for event in events:
        canonical = dict(event)
        kind = str(canonical.get("kind") or "")
        comment = str(canonical.get("comment") or "")
        if kind == "pending_request":
            if comment not in seen_pending:
                canonical["kind"] = "initial_pending_request"
                if _request_accepted(canonical):
                    seen_pending.add(comment)
            else:
                canonical["kind"] = "rearm_request"
        elif kind == "shadow_reset_complete":
            canonical["kind"] = "cycle_complete"
        elif kind == "restart_ready":
            canonical["kind"] = "cycle_restart"
        if str(canonical.get("kind") or "").endswith("request"):
            if canonical.get("requested_price") in (None, ""):
                canonical["requested_price"] = _event_price(canonical)
        classified.append(canonical)
    return classified


def _mark_execution_divergence(
    target_events: list[dict[str, Any]],
    candidate_events: list[dict[str, Any]],
    divergence_at: datetime | None,
) -> None:
    if divergence_at is None:
        return
    for event in [*target_events, *candidate_events]:
        time_value = event.get("time_utc")
        if not time_value:
            continue
        if _parse_time(time_value) >= divergence_at:
            event["comparison_class"] = "EXECUTION_DIVERGED"


def _geometry(events: Iterable[dict[str, Any]]) -> dict[str, float] | None:
    by_comment = {
        str(event.get("comment") or ""): event for event in events
    }
    buy = by_comment.get("STR B1")
    sell = by_comment.get("STR S1")
    if buy is None or sell is None:
        return None
    buy_price = _event_price(buy)
    sell_price = _event_price(sell)
    return {
        "anchor": (buy_price + sell_price) / 2.0,
        "step": (buy_price - sell_price) / 2.0,
    }


def _numeric_candidate_summary(
    *,
    target_initial: list[dict[str, Any]],
    demo_initial: list[dict[str, Any]],
    samples: dict[str, list[float]],
) -> dict[str, Any]:
    fields = {}
    for field, values in sorted(samples.items()):
        nonzero = [value for value in values if abs(value) > 1e-12]
        if nonzero:
            fields[field] = {
                "count": len(nonzero),
                "median_target_minus_demo": statistics.median(nonzero),
                "minimum_target_minus_demo": min(nonzero),
                "maximum_target_minus_demo": max(nonzero),
            }
    target_geometry = _geometry(target_initial)
    demo_geometry = _geometry(demo_initial)
    geometry = None
    if target_geometry is not None and demo_geometry is not None:
        geometry = {
            "target": target_geometry,
            "demo": demo_geometry,
            "anchor_adjustment": (
                target_geometry["anchor"] - demo_geometry["anchor"]
            ),
            "step_adjustment": (
                target_geometry["step"] - demo_geometry["step"]
            ),
        }
    return {
        "advisory_only": True,
        "geometry": geometry,
        "field_adjustments": fields,
    }


def _stream_value(
    rows: Iterable[Mapping[str, Any]],
    key: str,
    default: str,
) -> str:
    for row in rows:
        value = str(row.get(key) or "")
        if value:
            return value
    return default


def load_jsonl_event_stream(path: Path) -> CanonicalizationResult:
    rows: list[dict[str, Any]] = []
    invalid_rows = 0
    for line in path.read_text(
        encoding="utf-8",
        errors="ignore",
    ).splitlines():
        if line.strip():
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                invalid_rows += 1
                continue
            if not isinstance(payload, dict):
                invalid_rows += 1
                continue
            rows.append(payload)
    result = canonicalize_events(
        rows,
        source="target",
        evidence_grade=_stream_value(
            rows,
            "evidence_grade",
            "BEST_EFFORT",
        ),
        session_id=_stream_value(rows, "session_id", path.stem),
    )
    return CanonicalizationResult(
        events=result.events,
        duplicate_event_ids=result.duplicate_event_ids,
        invalid_rows=result.invalid_rows + invalid_rows,
    )


def load_jsonl_events(path: Path) -> list[dict[str, Any]]:
    return list(load_jsonl_event_stream(path).events)


def load_demo_telemetry_stream(path: Path) -> CanonicalizationResult:
    rows: list[dict[str, Any]] = []
    invalid_rows = 0
    with path.open(encoding="utf-8", errors="ignore", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader, [])
        extension = [
            field
            for field in TELEMETRY_EXTENSION_FIELDS
            if field not in header
        ]
        for values in reader:
            extra_count = len(values) - len(header)
            if extra_count > len(extension):
                invalid_rows += 1
                continue
            field_names = header + extension[: max(extra_count, 0)]
            row = dict(zip(field_names, values))
            cycle_id = str(row.get("cycle_id") or "")
            if not cycle_id:
                continue
            time_value = row.get("utc_time") or row.get("time")
            if not time_value:
                continue
            rows.append({**row, "time_utc": str(time_value)})
    result = canonicalize_events(
        rows,
        source="candidate",
        evidence_grade=_stream_value(
            rows,
            "evidence_grade",
            "FORMAL_CANDIDATE",
        ),
        session_id=_stream_value(rows, "session_id", path.stem),
    )
    return CanonicalizationResult(
        events=result.events,
        duplicate_event_ids=result.duplicate_event_ids,
        invalid_rows=result.invalid_rows + invalid_rows,
    )


def load_demo_telemetry_events(path: Path) -> list[dict[str, Any]]:
    return list(load_demo_telemetry_stream(path).events)


def compare_paired_cycles(
    target_events: list[dict[str, Any]],
    demo_events: list[dict[str, Any]],
    *,
    tick_size: float,
    time_tolerance_seconds: float,
    tick_value_per_lot: float | None = None,
    target_capture: CanonicalizationResult | None = None,
    demo_capture: CanonicalizationResult | None = None,
) -> dict[str, Any]:
    if tick_size <= 0 or time_tolerance_seconds < 0:
        raise ValueError("Tick size and time tolerance must be valid")

    capture = {
        "target_duplicate_event_ids": list(
            target_capture.duplicate_event_ids if target_capture else ()
        ),
        "demo_duplicate_event_ids": list(
            demo_capture.duplicate_event_ids if demo_capture else ()
        ),
        "target_invalid_rows": (
            target_capture.invalid_rows if target_capture else 0
        ),
        "demo_invalid_rows": demo_capture.invalid_rows if demo_capture else 0,
    }
    if (
        capture["target_duplicate_event_ids"]
        or capture["demo_duplicate_event_ids"]
        or capture["target_invalid_rows"]
        or capture["demo_invalid_rows"]
    ):
        return {
            "status": "INVALID",
            "reason": (
                "Capture contains duplicate event identities or invalid rows"
            ),
            "capture": capture,
            "deterministic_mismatch_count": 0,
            "execution_mismatch_count": 0,
        }

    target_cycle = _cycle_id(target_events)
    demo_cycle = _cycle_id(demo_events)
    if target_cycle is None or demo_cycle is None:
        return {
            "status": "INVALID",
            "reason": "Each event stream must contain exactly one cycle ID",
            "deterministic_mismatch_count": 0,
            "execution_mismatch_count": 0,
        }
    if target_cycle != demo_cycle:
        return {
            "status": "UNPAIRED",
            "target_cycle_id": target_cycle,
            "demo_cycle_id": demo_cycle,
            "deterministic_mismatch_count": 0,
            "execution_mismatch_count": 0,
        }

    target_initial, target_decisions, target_ineligible = (
        _classify_decisions(target_events)
    )
    demo_initial, demo_decisions, demo_ineligible = _classify_decisions(
        demo_events
    )
    expected = _expected_comments()
    target_comments = [
        str(event.get("comment") or "") for event in target_initial
    ]
    demo_comments = [
        str(event.get("comment") or "") for event in demo_initial
    ]
    deployment = {
        "target_count": len(target_initial),
        "demo_count": len(demo_initial),
        "target_missing_slots": sorted(set(expected) - set(target_comments)),
        "demo_missing_slots": sorted(set(expected) - set(demo_comments)),
        "target_duplicate_slots": target_ineligible,
        "demo_duplicate_slots": demo_ineligible,
        "target_rearm_count": sum(
            event.get("kind") == "rearm_request"
            for event in target_decisions
        ),
        "demo_rearm_count": sum(
            event.get("kind") == "rearm_request"
            for event in demo_decisions
        ),
        "target_ineligible_rearms": target_ineligible,
        "demo_ineligible_rearms": demo_ineligible,
        "target_sequence_match": target_comments == expected,
        "demo_sequence_match": demo_comments == expected,
        "sequence_match": (
            target_comments == expected
            and demo_comments == expected
            and target_comments == demo_comments
        ),
    }

    deterministic_mismatches: list[dict[str, Any]] = []
    for event in [*target_events, *demo_events]:
        if str(event.get("kind") or "") == "duplicate_level_identity":
            deterministic_mismatches.append(
                {
                    "category": "duplicate_level_identity",
                    "comment": str(event.get("comment") or ""),
                    "source": str(event.get("source") or ""),
                }
            )
    if (
        deployment["target_count"] != 60
        or deployment["demo_count"] != 60
        or deployment["target_missing_slots"]
        or deployment["demo_missing_slots"]
        or deployment["target_duplicate_slots"]
        or deployment["demo_duplicate_slots"]
        or not deployment["sequence_match"]
    ):
        deterministic_mismatches.append(
            {"category": "deployment_structure", **deployment}
        )

    target_decision_sequence = _semantic_sequence(target_decisions)
    demo_decision_sequence = _semantic_sequence(demo_decisions)
    if target_decision_sequence != demo_decision_sequence:
        deterministic_mismatches.append(
            {
                "category": "decision_sequence",
                "target": target_decision_sequence,
                "demo": demo_decision_sequence,
            }
        )

    target_decision_map = _pair_by_semantic_key(target_decisions)
    demo_decision_map = _pair_by_semantic_key(demo_decisions)
    numeric_samples: dict[str, list[float]] = defaultdict(list)
    for key in sorted(set(target_decision_map) | set(demo_decision_map)):
        target = target_decision_map.get(key)
        demo = demo_decision_map.get(key)
        if target is None or demo is None:
            deterministic_mismatches.append(
                {
                    "category": "decision_missing",
                    "key": key,
                    "target_present": target is not None,
                    "demo_present": demo is not None,
                }
            )
            continue
        target_signature = _decision_signature(target)
        demo_signature = _decision_signature(demo)
        time_delta = abs(
            (_parse_time(demo["time_utc"]) - _parse_time(target["time_utc"]))
            .total_seconds()
        )
        for field in ("volume", "price", "sl", "tp"):
            target_value = (
                _event_price(target)
                if field == "price"
                else _number(target, field)
            )
            demo_value = (
                _event_price(demo)
                if field == "price"
                else _number(demo, field)
            )
            numeric_samples[field].append(
                target_value - demo_value
            )
        numeric_samples["request_time_seconds"].append(
            (
                _parse_time(target["time_utc"])
                - _parse_time(demo["time_utc"])
            ).total_seconds()
        )
        if (
            target_signature != demo_signature
            or time_delta > time_tolerance_seconds
        ):
            deterministic_mismatches.append(
                {
                    "category": "decision",
                    "key": key,
                    "target": target_signature,
                    "demo": demo_signature,
                    "time_delta_seconds": time_delta,
                }
            )

    target_execution = _pair_by_semantic_key(
        event
        for event in target_events
        if str(event.get("kind") or "") in EXECUTION_KINDS
    )
    demo_execution = _pair_by_semantic_key(
        event
        for event in demo_events
        if str(event.get("kind") or "") in EXECUTION_KINDS
    )
    execution_mismatches: list[dict[str, Any]] = []
    divergence_at: datetime | None = None
    for key in sorted(set(target_execution) | set(demo_execution)):
        target = target_execution.get(key)
        demo = demo_execution.get(key)
        if target is None or demo is None:
            execution_mismatches.append(
                {
                    "category": "execution_missing",
                    "key": key,
                    "target_present": target is not None,
                    "demo_present": demo is not None,
                }
            )
            present = target if target is not None else demo
            if present is not None and present.get("time_utc"):
                mismatch_time = _parse_time(present["time_utc"])
                if divergence_at is None or mismatch_time < divergence_at:
                    divergence_at = mismatch_time
            continue
        price_delta = abs(_event_price(demo) - _event_price(target))
        time_delta = abs(
            (_parse_time(demo["time_utc"]) - _parse_time(target["time_utc"]))
            .total_seconds()
        )
        volume_match = abs(
            _number(demo, "volume") - _number(target, "volume")
        ) <= 1e-9
        side_match = str(demo.get("side") or "") == str(
            target.get("side") or ""
        )
        commission_match = abs(
            _number(demo, "commission") - _number(target, "commission")
        ) <= 1e-9
        swap_match = abs(
            _number(demo, "swap") - _number(target, "swap")
        ) <= 1e-9
        profit_tolerance = (
            abs(float(tick_value_per_lot)) * _number(target, "volume")
            if tick_value_per_lot is not None
            else 1e-9
        )
        profit_match = abs(
            _number(demo, "profit") - _number(target, "profit")
        ) <= profit_tolerance + 1e-9
        state_diverged = (
            price_delta > tick_size + 1e-9
            or time_delta > time_tolerance_seconds
            or not volume_match
            or not side_match
        )
        if (
            state_diverged
            or not commission_match
            or not swap_match
            or not profit_match
        ):
            execution_mismatches.append(
                {
                    "category": "execution",
                    "key": key,
                    "price_delta": price_delta,
                    "time_delta_seconds": time_delta,
                    "volume_match": volume_match,
                    "side_match": side_match,
                    "commission_match": commission_match,
                    "swap_match": swap_match,
                    "profit_match": profit_match,
                }
            )
            if state_diverged:
                mismatch_time = min(
                    _parse_time(target["time_utc"]),
                    _parse_time(demo["time_utc"]),
                )
                if divergence_at is None or mismatch_time < divergence_at:
                    divergence_at = mismatch_time

    _mark_execution_divergence(
        target_events,
        demo_events,
        divergence_at,
    )

    lifecycle = {
        "target_complete": any(
            str(event.get("kind") or "") in CYCLE_COMPLETE_KINDS
            for event in target_events
        ),
        "demo_complete": any(
            str(event.get("kind") or "") in CYCLE_COMPLETE_KINDS
            for event in demo_events
        ),
        "target_invalid": any(
            str(event.get("kind") or "") == "cycle_invalid"
            for event in target_events
        ),
        "demo_invalid": any(
            str(event.get("kind") or "") == "cycle_invalid"
            for event in demo_events
        ),
    }
    logic_status = "FAIL" if deterministic_mismatches else "PASS"
    execution_status = "DIFFERENT" if execution_mismatches else "PASS"
    reason = ""
    if lifecycle["target_invalid"] or lifecycle["demo_invalid"]:
        status = "INVALID"
        reason = "Cycle capture contains an operational invalidation"
    elif not lifecycle["target_complete"] or not lifecycle["demo_complete"]:
        status = "INVALID"
        reason = "Cycle lifecycle is not complete"
    else:
        status = logic_status

    target_scoring_events = _classified_lifecycle_events(target_events)
    demo_scoring_events = _classified_lifecycle_events(demo_events)

    report = {
        "status": status,
        "logic_status": logic_status,
        "execution_status": execution_status,
        "cycle_id": target_cycle,
        "deployment": deployment,
        "lifecycle": lifecycle,
        "deterministic_mismatch_count": len(deterministic_mismatches),
        "execution_mismatch_count": len(execution_mismatches),
        "deterministic_mismatches": deterministic_mismatches,
        "execution_mismatches": execution_mismatches,
        "fidelity": score_lifecycle(
            target_scoring_events,
            demo_scoring_events,
        ),
        "evidence_grade": (
            "FORMAL"
            if all(
                event.get("evidence_grade") == "FORMAL"
                for event in target_events
            )
            else "BEST_EFFORT"
        ),
        "numeric_candidates": _numeric_candidate_summary(
            target_initial=target_initial,
            demo_initial=demo_initial,
            samples=numeric_samples,
        ),
        "tolerances": {
            "tick_size": tick_size,
            "time_seconds": time_tolerance_seconds,
            "tick_value_per_lot": tick_value_per_lot,
        },
    }
    if reason:
        report["reason"] = reason
    return report
