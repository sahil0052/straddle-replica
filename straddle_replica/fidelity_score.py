from __future__ import annotations

from typing import Any, Iterable


SCORABLE_KINDS = {
    "cycle_start",
    "initial_pending_request",
    "fill",
    "stop_activation",
    "stop_tightened",
    "stop_exit",
    "rearm_eligible",
    "rearm_request",
    "basket_trigger",
    "cancel_request",
    "close_request",
    "close_fill",
    "cycle_complete",
    "cycle_restart",
}
STOP_TIGHTENED_LOCK_STEPS = 1.5


def _identity(event: dict[str, Any]) -> tuple[str, str, int]:
    return (
        str(event.get("comment") or ""),
        str(event.get("side") or ""),
        int(event.get("level") or 0),
    )


def _stage_event(
    event: dict[str, Any],
    *,
    kind: str,
) -> dict[str, Any]:
    return {
        **event,
        "kind": kind,
        "stage_sl": float(event.get("sl") or 0.0),
        "requested_price": 0.0,
        "sl": 0.0,
        "tp": 0.0,
    }


def canonical_lifecycle_events(
    events: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    canonical: list[dict[str, Any]] = []
    episodes: dict[tuple[str, str, int], int] = {}
    fill_prices: dict[
        tuple[tuple[str, str, int], int], float
    ] = {}
    stages: dict[
        tuple[tuple[str, str, int], int], set[str]
    ] = {}
    stage_indices: dict[
        tuple[tuple[str, str, int], int], dict[str, int]
    ] = {}
    for source in events:
        event = dict(source)
        kind = str(event.get("kind") or "")
        identity = _identity(event)
        if kind == "fill":
            episode = episodes.get(identity, 0) + 1
            episodes[identity] = episode
            key = (identity, episode)
            fill_prices[key] = float(
                event.get("normalized_execution_price")
                or event.get("accepted_price")
                or event.get("price")
                or 0.0
            )
            stages[key] = set()
            stage_indices[key] = {}
            canonical.append(event)
            continue
        if kind != "stop_request":
            canonical.append(event)
            continue

        episode = episodes.get(identity, 0)
        key = (identity, episode)
        seen = stages.setdefault(key, set())
        indices = stage_indices.setdefault(key, {})
        if "activation" not in seen:
            canonical.append(
                _stage_event(event, kind="stop_activation")
            )
            seen.add("activation")
            indices["activation"] = len(canonical) - 1

        fill_price = fill_prices.get(key)
        stop_price = float(event.get("sl") or 0.0)
        if fill_price is None or stop_price == 0.0:
            canonical[indices["activation"]] = _stage_event(
                event,
                kind="stop_activation",
            )
            continue
        side = identity[1]
        locked_steps = (
            stop_price - fill_price
            if side == "buy"
            else fill_price - stop_price
        )
        if (
            locked_steps >= STOP_TIGHTENED_LOCK_STEPS
        ):
            tightened = _stage_event(
                event,
                kind="stop_tightened",
            )
            if "tightened" not in seen:
                canonical.append(tightened)
                seen.add("tightened")
                indices["tightened"] = len(canonical) - 1
            else:
                canonical[indices["tightened"]] = tightened
        elif "tightened" not in seen:
            canonical[indices["activation"]] = _stage_event(
                event,
                kind="stop_activation",
            )
    return canonical


def _signature(event: dict[str, Any]) -> tuple[Any, ...]:
    decision = str(event.get("kind") or "").endswith("request")
    return (
        str(event.get("kind") or ""),
        str(event.get("comment") or ""),
        str(event.get("side") or ""),
        int(event.get("level") or 0),
        round(float(event.get("volume") or 0.0), 8),
        round(float(event.get("requested_price") or 0.0), 8)
        if decision
        else 0.0,
        round(float(event.get("sl") or 0.0), 8)
        if str(event.get("kind") or "") == "stop_request"
        else 0.0,
        round(float(event.get("tp") or 0.0), 8),
    )


def _sequence(events: Iterable[dict[str, Any]]) -> list[tuple[Any, ...]]:
    return [
        _signature(event)
        for event in canonical_lifecycle_events(events)
        if str(event.get("kind") or "") in SCORABLE_KINDS
    ]


def _lcs_count(
    left: list[tuple[Any, ...]],
    right: list[tuple[Any, ...]],
) -> int:
    previous = [0] * (len(right) + 1)
    for left_item in left:
        current = [0]
        for index, right_item in enumerate(right, start=1):
            if left_item == right_item:
                current.append(previous[index - 1] + 1)
            else:
                current.append(max(previous[index], current[-1]))
        previous = current
    return previous[-1]


def _score(
    target: list[tuple[Any, ...]],
    candidate: list[tuple[Any, ...]],
) -> dict[str, float | int]:
    matched = _lcs_count(target, candidate)
    precision = matched / len(candidate) if candidate else 0.0
    recall = matched / len(target) if target else 0.0
    f1 = (
        2.0 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )
    return {
        "target_events": len(target),
        "candidate_events": len(candidate),
        "matched": matched,
        "precision_percent": round(precision * 100.0, 4),
        "recall_percent": round(recall * 100.0, 4),
        "f1_percent": round(f1 * 100.0, 4),
    }


def score_lifecycle(
    target_events: list[dict[str, Any]],
    candidate_events: list[dict[str, Any]],
) -> dict[str, Any]:
    strict_target = _sequence(target_events)
    strict_candidate = _sequence(candidate_events)
    conditional_target = _sequence(
        event
        for event in target_events
        if event.get("comparison_class") != "EXECUTION_DIVERGED"
    )
    conditional_candidate = _sequence(
        event
        for event in candidate_events
        if event.get("comparison_class") != "EXECUTION_DIVERGED"
    )
    conditional = _score(conditional_target, conditional_candidate)
    denominator = max(len(strict_target), len(strict_candidate), 1)
    conditional["coverage_percent"] = round(
        max(len(conditional_target), len(conditional_candidate))
        / denominator
        * 100.0,
        4,
    )
    return {
        "strict": _score(strict_target, strict_candidate),
        "conditional": conditional,
    }
