import pytest

from straddle_replica.fidelity_score import score_lifecycle


def event(kind: str, comment: str, *, classification: str = "") -> dict:
    side = "buy" if " B" in comment else "sell"
    level = int(comment[5:]) if comment else 0
    return {
        "kind": kind,
        "comment": comment,
        "side": side if comment else "",
        "level": level,
        "volume": 0.01 if comment else 0.0,
        "requested_price": 4400.0 if "request" in kind else 0.0,
        "sl": 0.0,
        "tp": 0.0,
        "comparison_class": classification,
    }


def test_exact_lifecycle_scores_one_hundred_percent() -> None:
    target = [event("initial_pending_request", "STR B1")]
    candidate = [dict(target[0])]

    score = score_lifecycle(target, candidate)

    assert score["strict"]["f1_percent"] == 100.0
    assert score["conditional"]["f1_percent"] == 100.0
    assert score["conditional"]["coverage_percent"] == 100.0


def test_extra_and_missing_events_reduce_strict_f1() -> None:
    target = [
        event("initial_pending_request", "STR B1"),
        event("initial_pending_request", "STR S1"),
    ]
    candidate = [
        event("initial_pending_request", "STR B1"),
        event("rearm_request", "STR B2"),
    ]

    score = score_lifecycle(target, candidate)

    assert score["strict"]["matched"] == 1
    assert score["strict"]["precision_percent"] == 50.0
    assert score["strict"]["recall_percent"] == 50.0
    assert score["strict"]["f1_percent"] == 50.0


def test_execution_diverged_events_remain_in_strict_score_only() -> None:
    target = [
        event("stop_request", "STR B1"),
        event(
            "rearm_request",
            "STR B1",
            classification="EXECUTION_DIVERGED",
        ),
    ]
    candidate = [
        event("stop_request", "STR B1"),
        event(
            "rearm_request",
            "STR B2",
            classification="EXECUTION_DIVERGED",
        ),
    ]

    score = score_lifecycle(target, candidate)

    assert score["strict"]["f1_percent"] == 50.0
    assert score["conditional"]["f1_percent"] == 100.0
    assert score["conditional"]["coverage_percent"] == 50.0


def trailing_event(
    kind: str,
    *,
    sl: float = 0.0,
    execution_price: float = 0.0,
) -> dict:
    return {
        "kind": kind,
        "comment": "STR B1",
        "side": "buy",
        "level": 1,
        "volume": 0.01,
        "requested_price": sl if kind == "stop_request" else 0.0,
        "sl": sl,
        "tp": 0.0,
        "normalized_execution_price": execution_price,
    }


def test_intermediate_stop_updates_do_not_reduce_causal_fidelity() -> None:
    target = [
        trailing_event("fill", execution_price=1.0),
        trailing_event("stop_request", sl=1.1),
        trailing_event("stop_request", sl=1.2),
        trailing_event("stop_request", sl=2.6),
        trailing_event("stop_exit", execution_price=2.5),
    ]
    candidate = [
        trailing_event("fill", execution_price=1.0),
        trailing_event("stop_request", sl=1.15),
        trailing_event("stop_request", sl=2.7),
        trailing_event("stop_exit", execution_price=2.5),
    ]

    score = score_lifecycle(target, candidate)

    assert score["strict"]["f1_percent"] == 100.0
    assert score["strict"]["target_events"] == 4
    assert score["strict"]["candidate_events"] == 4


def test_missing_tightened_stop_stage_reduces_fidelity() -> None:
    target = [
        trailing_event("fill", execution_price=1.0),
        trailing_event("stop_request", sl=1.1),
        trailing_event("stop_request", sl=2.6),
        trailing_event("stop_exit", execution_price=2.5),
    ]
    candidate = [
        trailing_event("fill", execution_price=1.0),
        trailing_event("stop_request", sl=1.15),
        trailing_event("stop_exit", execution_price=2.5),
    ]

    score = score_lifecycle(target, candidate)

    assert score["strict"]["f1_percent"] < 100.0
