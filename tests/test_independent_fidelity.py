from datetime import datetime, timedelta, timezone

from straddle_replica.independent_fidelity import (
    compare_independent_cycle_pair,
    pair_complete_cycles,
)


UTC = timezone.utc


def deployment(
    cycle_id: str,
    started: datetime,
    anchor: float,
    step: float,
) -> list[dict]:
    events = [
        {
            "cycle_id": cycle_id,
            "time_utc": started.isoformat(),
            "kind": "cycle_start",
            "comment": "",
            "side": "",
            "level": 0,
            "volume": 0.0,
            "requested_price": 0.0,
            "accepted_price": 0.0,
            "sl": 0.0,
            "retcode": 0,
        }
    ]
    for level in range(1, 31):
        volume = 0.01 if level <= 10 else 0.06 if level <= 20 else 0.15
        for side in ("B", "S"):
            index = (level - 1) * 2 + (0 if side == "B" else 1)
            events.append(
                {
                    "cycle_id": cycle_id,
                    "time_utc": (
                        started + timedelta(milliseconds=index * 100)
                    ).isoformat(),
                    "kind": "pending_request",
                    "comment": f"STR {side}{level}",
                    "side": "buy" if side == "B" else "sell",
                    "level": level,
                    "volume": volume,
                    "requested_price": anchor
                    + (1 if side == "B" else -1) * level * step,
                    "accepted_price": 0.0,
                    "sl": 0.0,
                    "retcode": 10008,
                }
            )
    return events


def complete(events: list[dict], at: datetime) -> None:
    cycle_id = events[0]["cycle_id"]
    for kind in ("basket_trigger", "cycle_complete", "cycle_restart"):
        events.append(
            {
                "cycle_id": cycle_id,
                "time_utc": at.isoformat(),
                "kind": kind,
                "comment": (
                    "threshold_reached"
                    if kind == "basket_trigger"
                    else "flat"
                    if kind == "cycle_complete"
                    else "new_cycle"
                ),
                "side": "",
                "level": 0,
                "volume": 0.0,
                "requested_price": 0.0,
                "accepted_price": 0.0,
                "sl": 0.0,
                "retcode": 0,
            }
        )


def test_different_ids_and_anchors_can_have_exact_logic_parity() -> None:
    started = datetime(2026, 8, 12, tzinfo=UTC)
    target = deployment("target-1", started, 4380.0, 1.46)
    candidate = deployment(
        "candidate-9",
        started + timedelta(milliseconds=400),
        4395.0,
        1.465,
    )
    complete(target, started + timedelta(minutes=1))
    complete(
        candidate,
        started + timedelta(minutes=1, milliseconds=400),
    )

    report = compare_independent_cycle_pair(
        target,
        candidate,
        start_tolerance_seconds=2.0,
        normalized_price_tolerance=0.02,
    )

    assert report["status"] == "PASS"
    assert report["target_cycle_id"] == "target-1"
    assert report["candidate_cycle_id"] == "candidate-9"
    assert report["fidelity"]["strict"]["f1_percent"] == 100.0
    assert report["deterministic_mismatch_count"] == 0


def test_missing_level_fails_independent_logic() -> None:
    started = datetime(2026, 8, 12, tzinfo=UTC)
    target = deployment("target-1", started, 4380.0, 1.46)
    candidate = deployment("candidate-1", started, 4380.0, 1.46)
    candidate = [
        event for event in candidate if event["comment"] != "STR B7"
    ]
    complete(target, started + timedelta(minutes=1))
    complete(candidate, started + timedelta(minutes=1))

    report = compare_independent_cycle_pair(
        target,
        candidate,
        start_tolerance_seconds=2.0,
        normalized_price_tolerance=0.02,
    )

    assert report["status"] == "FAIL"
    assert "STR B7" in report["deployment"]["candidate_missing_slots"]


def test_different_stop_transition_fails_deterministic_logic() -> None:
    started = datetime(2026, 8, 12, tzinfo=UTC)
    target = deployment("target-1", started, 4380.0, 1.46)
    candidate = deployment("candidate-1", started, 4380.0, 1.46)
    stop = {
        "cycle_id": "target-1",
        "time_utc": (started + timedelta(seconds=30)).isoformat(),
        "kind": "stop_request",
        "comment": "STR B1",
        "side": "buy",
        "level": 1,
        "volume": 0.01,
        "requested_price": 4381.66,
        "accepted_price": 0.0,
        "sl": 4381.66,
        "retcode": 10009,
    }
    target.append(stop)
    candidate.append(
        {
            **stop,
            "cycle_id": "candidate-1",
            "requested_price": 4381.86,
            "sl": 4381.86,
        }
    )
    complete(target, started + timedelta(minutes=1))
    complete(candidate, started + timedelta(minutes=1))

    report = compare_independent_cycle_pair(
        target,
        candidate,
        start_tolerance_seconds=2.0,
        normalized_price_tolerance=0.02,
    )

    assert report["status"] == "FAIL"
    assert any(
        mismatch["category"] == "trailing_stage_sequence"
        for mismatch in report["deterministic_mismatches"]
    )


def test_pairing_uses_nearest_start_without_requiring_equal_ids() -> None:
    started = datetime(2026, 8, 12, tzinfo=UTC)
    target_one = deployment("target-1", started, 4380.0, 1.46)
    target_two = deployment(
        "target-2",
        started + timedelta(hours=1),
        4390.0,
        1.463,
    )
    candidate_one = deployment(
        "candidate-a",
        started + timedelta(seconds=1),
        4381.0,
        1.4603,
    )
    candidate_two = deployment(
        "candidate-b",
        started + timedelta(hours=1, seconds=1),
        4391.0,
        1.4636,
    )
    for events in (
        target_one,
        target_two,
        candidate_one,
        candidate_two,
    ):
        complete(
            events,
            datetime.fromisoformat(events[0]["time_utc"])
            + timedelta(minutes=1),
        )

    pairs = pair_complete_cycles(
        [*target_one, *target_two],
        [*candidate_one, *candidate_two],
        pairing="nearest",
        max_start_gap_seconds=5.0,
    )

    assert [
        (pair[0][0]["cycle_id"], pair[1][0]["cycle_id"])
        for pair in pairs
    ] == [
        ("target-1", "candidate-a"),
        ("target-2", "candidate-b"),
    ]


def test_ordinal_pairing_rejects_cycles_outside_start_gap() -> None:
    started = datetime(2026, 8, 12, tzinfo=UTC)
    target = deployment("target-1", started, 4380.0, 1.46)
    candidate = deployment(
        "candidate-1",
        started + timedelta(seconds=3),
        4380.0,
        1.46,
    )
    complete(target, started + timedelta(minutes=1))
    complete(
        candidate,
        started + timedelta(minutes=1, seconds=3),
    )

    pairs = pair_complete_cycles(
        target,
        candidate,
        pairing="ordinal",
        max_start_gap_seconds=2.0,
    )

    assert pairs == []


def test_broker_fill_divergence_does_not_become_logic_mismatch() -> None:
    started = datetime(2026, 8, 12, tzinfo=UTC)
    target = deployment("target-1", started, 4380.0, 1.46)
    candidate = deployment("candidate-1", started, 4380.0, 1.46)
    target.extend(
        [
            {
                "cycle_id": "target-1",
                "time_utc": (started + timedelta(seconds=30)).isoformat(),
                "kind": "fill",
                "comment": "STR B1",
                "side": "buy",
                "level": 1,
                "volume": 0.01,
                "accepted_price": 4381.46,
                "requested_price": 4381.46,
                "sl": 0.0,
                "retcode": 0,
            },
            {
                "cycle_id": "target-1",
                "time_utc": (started + timedelta(seconds=31)).isoformat(),
                "kind": "stop_request",
                "comment": "STR B1",
                "side": "buy",
                "level": 1,
                "volume": 0.01,
                "requested_price": 4381.70,
                "accepted_price": 0.0,
                "sl": 4381.70,
                "retcode": 10009,
            },
        ]
    )
    candidate.extend(
        [
            {
                "cycle_id": "candidate-1",
                "time_utc": (started + timedelta(seconds=30)).isoformat(),
                "kind": "fill",
                "comment": "STR S1",
                "side": "sell",
                "level": 1,
                "volume": 0.01,
                "accepted_price": 4378.54,
                "requested_price": 4378.54,
                "sl": 0.0,
                "retcode": 0,
            },
            {
                "cycle_id": "candidate-1",
                "time_utc": (started + timedelta(seconds=31)).isoformat(),
                "kind": "stop_request",
                "comment": "STR S1",
                "side": "sell",
                "level": 1,
                "volume": 0.01,
                "requested_price": 4378.30,
                "accepted_price": 0.0,
                "sl": 4378.30,
                "retcode": 10009,
            },
        ]
    )
    complete(target, started + timedelta(minutes=1))
    complete(candidate, started + timedelta(minutes=1))

    report = compare_independent_cycle_pair(
        target,
        candidate,
        start_tolerance_seconds=2.0,
        normalized_price_tolerance=0.02,
    )

    assert report["logic_status"] == "PASS"
    assert report["deterministic_mismatch_count"] == 0
    assert report["execution_status"] == "DIFFERENT"
    assert report["fidelity"]["conditional"]["f1_percent"] == 100.0
    assert report["fidelity"]["conditional"]["coverage_percent"] < 100.0


def test_same_fill_identity_price_divergence_excludes_dependent_stops() -> None:
    started = datetime(2026, 8, 12, tzinfo=UTC)
    target = deployment("target-1", started, 4380.0, 1.46)
    candidate = deployment("candidate-1", started, 4380.0, 1.46)
    target.extend(
        [
            {
                "cycle_id": "target-1",
                "time_utc": (started + timedelta(seconds=30)).isoformat(),
                "kind": "fill",
                "comment": "STR B1",
                "side": "buy",
                "level": 1,
                "volume": 0.01,
                "accepted_price": 4381.46,
                "requested_price": 4381.46,
                "sl": 0.0,
                "retcode": 0,
            },
            {
                "cycle_id": "target-1",
                "time_utc": (started + timedelta(seconds=31)).isoformat(),
                "kind": "stop_request",
                "comment": "STR B1",
                "side": "buy",
                "level": 1,
                "volume": 0.01,
                "requested_price": 4381.66,
                "accepted_price": 0.0,
                "sl": 4381.66,
                "retcode": 10009,
            },
        ]
    )
    candidate.extend(
        [
            {
                "cycle_id": "candidate-1",
                "time_utc": (started + timedelta(seconds=30)).isoformat(),
                "kind": "fill",
                "comment": "STR B1",
                "side": "buy",
                "level": 1,
                "volume": 0.01,
                "accepted_price": 4381.54,
                "requested_price": 4381.54,
                "sl": 0.0,
                "retcode": 0,
            },
            {
                "cycle_id": "candidate-1",
                "time_utc": (started + timedelta(seconds=31)).isoformat(),
                "kind": "stop_request",
                "comment": "STR B1",
                "side": "buy",
                "level": 1,
                "volume": 0.01,
                "requested_price": 4381.74,
                "accepted_price": 0.0,
                "sl": 4381.74,
                "retcode": 10009,
            },
        ]
    )
    complete(target, started + timedelta(minutes=1))
    complete(candidate, started + timedelta(minutes=1))

    report = compare_independent_cycle_pair(
        target,
        candidate,
        start_tolerance_seconds=2.0,
        normalized_price_tolerance=0.02,
    )

    assert report["logic_status"] == "PASS"
    assert report["deterministic_mismatch_count"] == 0
    assert report["execution_status"] == "DIFFERENT"
    assert any(
        mismatch["category"] == "execution_price"
        for mismatch in report["execution_mismatches"]
    )


def test_fill_price_divergence_only_excludes_the_affected_level() -> None:
    started = datetime(2026, 8, 12, tzinfo=UTC)
    target = deployment("target-1", started, 4380.0, 1.46)
    candidate = deployment("candidate-1", started, 4380.0, 1.46)
    target.extend(
        [
            {
                "cycle_id": "target-1",
                "time_utc": (started + timedelta(seconds=30)).isoformat(),
                "kind": "fill",
                "comment": "STR B1",
                "side": "buy",
                "level": 1,
                "volume": 0.01,
                "accepted_price": 4381.46,
                "requested_price": 4381.46,
                "sl": 0.0,
                "retcode": 0,
            },
            {
                "cycle_id": "target-1",
                "time_utc": (started + timedelta(seconds=31)).isoformat(),
                "kind": "stop_request",
                "comment": "STR B1",
                "side": "buy",
                "level": 1,
                "volume": 0.01,
                "requested_price": 4381.66,
                "accepted_price": 0.0,
                "sl": 4381.66,
                "retcode": 10009,
            },
            {
                "cycle_id": "target-1",
                "time_utc": (started + timedelta(seconds=32)).isoformat(),
                "kind": "stop_request",
                "comment": "STR B2",
                "side": "buy",
                "level": 2,
                "volume": 0.01,
                "requested_price": 4383.12,
                "accepted_price": 0.0,
                "sl": 4383.12,
                "retcode": 10009,
            },
        ]
    )
    candidate.extend(
        [
            {
                "cycle_id": "candidate-1",
                "time_utc": (started + timedelta(seconds=30)).isoformat(),
                "kind": "fill",
                "comment": "STR B1",
                "side": "buy",
                "level": 1,
                "volume": 0.01,
                "accepted_price": 4381.54,
                "requested_price": 4381.54,
                "sl": 0.0,
                "retcode": 0,
            },
            {
                "cycle_id": "candidate-1",
                "time_utc": (started + timedelta(seconds=31)).isoformat(),
                "kind": "stop_request",
                "comment": "STR B1",
                "side": "buy",
                "level": 1,
                "volume": 0.01,
                "requested_price": 4381.74,
                "accepted_price": 0.0,
                "sl": 4381.74,
                "retcode": 10009,
            },
            {
                "cycle_id": "candidate-1",
                "time_utc": (started + timedelta(seconds=32)).isoformat(),
                "kind": "stop_request",
                "comment": "STR B2",
                "side": "buy",
                "level": 2,
                "volume": 0.01,
                "requested_price": 4383.12,
                "accepted_price": 0.0,
                "sl": 4383.12,
                "retcode": 10009,
            },
        ]
    )
    complete(target, started + timedelta(minutes=1))
    complete(candidate, started + timedelta(minutes=1))

    report = compare_independent_cycle_pair(
        target,
        candidate,
        start_tolerance_seconds=2.0,
        normalized_price_tolerance=0.02,
    )

    b2_stop = next(
        event
        for event in report["transition_timing"]
        if event["kind"] == "stop_request"
        and event["comment"] == "STR B2"
    )
    assert report["logic_status"] == "PASS"
    assert report["deterministic_mismatch_count"] == 0
    assert b2_stop["comparison_class"] == "PAIRED"
    assert report["fidelity"]["conditional"]["coverage_percent"] >= 95.0


def test_execution_divergence_excludes_global_basket_decisions() -> None:
    started = datetime(2026, 8, 12, tzinfo=UTC)
    target = deployment("target-1", started, 4380.0, 1.46)
    candidate = deployment("candidate-1", started, 4380.0, 1.46)
    target.extend(
        [
            {
                "cycle_id": "target-1",
                "time_utc": (started + timedelta(seconds=30)).isoformat(),
                "kind": "fill",
                "comment": "STR B1",
                "side": "buy",
                "level": 1,
                "volume": 0.01,
                "accepted_price": 4381.46,
                "requested_price": 4381.46,
                "sl": 0.0,
                "retcode": 0,
            },
            {
                "cycle_id": "target-1",
                "time_utc": (started + timedelta(seconds=40)).isoformat(),
                "kind": "cancel_request",
                "comment": "STR B11",
                "side": "buy",
                "level": 11,
                "volume": 0.06,
                "requested_price": 0.0,
                "accepted_price": 0.0,
                "sl": 0.0,
                "retcode": 10009,
            },
        ]
    )
    candidate.extend(
        [
            {
                "cycle_id": "candidate-1",
                "time_utc": (started + timedelta(seconds=30)).isoformat(),
                "kind": "fill",
                "comment": "STR B1",
                "side": "buy",
                "level": 1,
                "volume": 0.01,
                "accepted_price": 4381.54,
                "requested_price": 4381.54,
                "sl": 0.0,
                "retcode": 0,
            },
            {
                "cycle_id": "candidate-1",
                "time_utc": (started + timedelta(seconds=50)).isoformat(),
                "kind": "fill",
                "comment": "STR B11",
                "side": "buy",
                "level": 11,
                "volume": 0.06,
                "accepted_price": 4396.06,
                "requested_price": 4396.06,
                "sl": 0.0,
                "retcode": 0,
            },
            {
                "cycle_id": "candidate-1",
                "time_utc": (started + timedelta(seconds=60)).isoformat(),
                "kind": "close_request",
                "comment": "STR B11",
                "side": "buy",
                "level": 11,
                "volume": 0.06,
                "requested_price": 0.0,
                "accepted_price": 0.0,
                "sl": 0.0,
                "retcode": 10009,
            },
        ]
    )
    complete(target, started + timedelta(minutes=2))
    complete(candidate, started + timedelta(minutes=2))

    report = compare_independent_cycle_pair(
        target,
        candidate,
        start_tolerance_seconds=2.0,
        normalized_price_tolerance=0.02,
    )

    assert report["logic_status"] == "PASS"
    assert report["deterministic_mismatch_count"] == 0
    assert report["execution_status"] == "DIFFERENT"


def test_execution_divergence_excludes_recovery_replacements() -> None:
    started = datetime(2026, 8, 12, tzinfo=UTC)
    target = deployment("target-1", started, 4380.0, 1.46)
    candidate = deployment("candidate-1", started, 4380.0, 1.46)
    target.extend(
        [
            {
                "cycle_id": "target-1",
                "time_utc": (started + timedelta(seconds=30)).isoformat(),
                "kind": "fill",
                "comment": "STR B1",
                "side": "buy",
                "level": 1,
                "volume": 0.01,
                "accepted_price": 4381.46,
                "requested_price": 4381.46,
                "sl": 0.0,
                "retcode": 0,
            },
            {
                "cycle_id": "target-1",
                "time_utc": (started + timedelta(seconds=40)).isoformat(),
                "kind": "cancel_request",
                "comment": "STR S15",
                "side": "sell",
                "level": 15,
                "volume": 0.06,
                "requested_price": 0.0,
                "accepted_price": 0.0,
                "sl": 0.0,
                "retcode": 10009,
            },
            {
                "cycle_id": "target-1",
                "time_utc": (started + timedelta(seconds=41)).isoformat(),
                "kind": "pending_request",
                "comment": "STR S15",
                "side": "sell",
                "level": 15,
                "volume": 0.12,
                "requested_price": 4358.1,
                "accepted_price": 0.0,
                "sl": 0.0,
                "retcode": 10009,
            },
        ]
    )
    candidate.append(
        {
            "cycle_id": "candidate-1",
            "time_utc": (started + timedelta(seconds=30)).isoformat(),
            "kind": "fill",
            "comment": "STR B1",
            "side": "buy",
            "level": 1,
            "volume": 0.01,
            "accepted_price": 4381.54,
            "requested_price": 4381.54,
            "sl": 0.0,
            "retcode": 0,
        }
    )
    complete(target, started + timedelta(minutes=2))
    complete(candidate, started + timedelta(minutes=2))

    report = compare_independent_cycle_pair(
        target,
        candidate,
        start_tolerance_seconds=2.0,
        normalized_price_tolerance=0.02,
    )

    assert report["logic_status"] == "PASS"
    assert report["deterministic_mismatch_count"] == 0
    assert report["execution_status"] == "DIFFERENT"


def test_execution_time_divergence_excludes_downstream_trailing() -> None:
    started = datetime(2026, 8, 12, tzinfo=UTC)
    target = deployment("target-1", started, 4380.0, 1.46)
    candidate = deployment("candidate-1", started, 4380.0, 1.46)
    for events, cycle_id, fill_seconds, stop_seconds, stop_price in (
        (target, "target-1", 30, 31, 4381.66),
        (candidate, "candidate-1", 40, 41, 4382.10),
    ):
        events.extend(
            [
                {
                    "cycle_id": cycle_id,
                    "time_utc": (
                        started + timedelta(seconds=fill_seconds)
                    ).isoformat(),
                    "kind": "fill",
                    "comment": "STR B1",
                    "side": "buy",
                    "level": 1,
                    "volume": 0.01,
                    "accepted_price": 4381.46,
                    "requested_price": 4381.46,
                    "sl": 0.0,
                    "retcode": 0,
                },
                {
                    "cycle_id": cycle_id,
                    "time_utc": (
                        started + timedelta(seconds=stop_seconds)
                    ).isoformat(),
                    "kind": "stop_request",
                    "comment": "STR B1",
                    "side": "buy",
                    "level": 1,
                    "volume": 0.01,
                    "requested_price": stop_price,
                    "accepted_price": 0.0,
                    "sl": stop_price,
                    "retcode": 10009,
                },
            ]
        )
    complete(target, started + timedelta(minutes=2))
    complete(candidate, started + timedelta(minutes=2))

    report = compare_independent_cycle_pair(
        target,
        candidate,
        start_tolerance_seconds=2.0,
        normalized_price_tolerance=0.02,
    )

    assert report["logic_status"] == "PASS"
    assert report["deterministic_mismatch_count"] == 0
    assert report["execution_status"] == "DIFFERENT"


def test_decisions_after_diverged_counterpart_completion_are_excluded() -> None:
    started = datetime(2026, 8, 12, tzinfo=UTC)
    target = deployment("target-1", started, 4380.0, 1.46)
    candidate = deployment("candidate-1", started, 4380.0, 1.46)
    for events, cycle_id in (
        (target, "target-1"),
        (candidate, "candidate-1"),
    ):
        events.append(
            {
                "cycle_id": cycle_id,
                "time_utc": (started + timedelta(seconds=20)).isoformat(),
                "kind": "fill",
                "comment": "STR S1",
                "side": "sell",
                "level": 1,
                "volume": 0.01,
                "accepted_price": 4378.54,
                "requested_price": 4378.54,
                "sl": 0.0,
                "retcode": 0,
            }
        )
    target.append(
        {
            "cycle_id": "target-1",
            "time_utc": (started + timedelta(seconds=30)).isoformat(),
            "kind": "fill",
            "comment": "STR B1",
            "side": "buy",
            "level": 1,
            "volume": 0.01,
            "accepted_price": 4381.46,
            "requested_price": 4381.46,
            "sl": 0.0,
            "retcode": 0,
        }
    )
    candidate.append(
        {
            "cycle_id": "candidate-1",
            "time_utc": (started + timedelta(seconds=30)).isoformat(),
            "kind": "fill",
            "comment": "STR B1",
            "side": "buy",
            "level": 1,
            "volume": 0.01,
            "accepted_price": 4381.54,
            "requested_price": 4381.54,
            "sl": 0.0,
            "retcode": 0,
        }
    )
    target.append(
        {
            "cycle_id": "target-1",
            "time_utc": (started + timedelta(seconds=60)).isoformat(),
            "kind": "stop_request",
            "comment": "STR S1",
            "side": "sell",
            "level": 1,
            "volume": 0.01,
            "requested_price": 4378.34,
            "accepted_price": 0.0,
            "sl": 4378.34,
            "retcode": 10009,
        }
    )
    complete(candidate, started + timedelta(seconds=40))
    complete(target, started + timedelta(minutes=2))

    report = compare_independent_cycle_pair(
        target,
        candidate,
        start_tolerance_seconds=2.0,
        normalized_price_tolerance=0.02,
    )

    assert report["logic_status"] == "PASS"
    assert report["deterministic_mismatch_count"] == 0
    assert report["execution_status"] == "DIFFERENT"


def test_delayed_observer_stop_stage_price_is_execution_dependent() -> None:
    started = datetime(2026, 8, 12, tzinfo=UTC)
    target = deployment("target-1", started, 4380.0, 1.46)
    candidate = deployment("candidate-1", started, 4380.0, 1.46)
    for events, cycle_id in (
        (target, "target-1"),
        (candidate, "candidate-1"),
    ):
        events.append(
            {
                "cycle_id": cycle_id,
                "time_utc": (started + timedelta(seconds=30)).isoformat(),
                "kind": "fill",
                "comment": "STR B1",
                "side": "buy",
                "level": 1,
                "volume": 0.01,
                "accepted_price": 4381.46,
                "requested_price": 4381.46,
                "sl": 0.0,
                "retcode": 0,
            }
        )
    target.append(
        {
            "cycle_id": "target-1",
            "time_utc": (started + timedelta(seconds=60)).isoformat(),
            "kind": "stop_request",
            "comment": "STR B1",
            "side": "buy",
            "level": 1,
            "volume": 0.01,
            "requested_price": 4381.66,
            "accepted_price": 0.0,
            "sl": 4381.66,
            "retcode": 0,
            "source": "target",
            "evidence_grade": "BEST_EFFORT",
        }
    )
    candidate.append(
        {
            "cycle_id": "candidate-1",
            "time_utc": (started + timedelta(seconds=40)).isoformat(),
            "kind": "stop_request",
            "comment": "STR B1",
            "side": "buy",
            "level": 1,
            "volume": 0.01,
            "requested_price": 4382.10,
            "accepted_price": 0.0,
            "sl": 4382.10,
            "retcode": 10009,
            "source": "ea_telemetry",
        }
    )
    complete(target, started + timedelta(minutes=2))
    complete(candidate, started + timedelta(minutes=2))

    report = compare_independent_cycle_pair(
        target,
        candidate,
        start_tolerance_seconds=2.0,
        normalized_price_tolerance=0.02,
    )

    assert report["logic_status"] == "PASS"
    assert report["deterministic_mismatch_count"] == 0


def test_best_effort_stop_exit_can_prove_omitted_tightened_stage() -> None:
    started = datetime(2026, 8, 12, tzinfo=UTC)
    target = deployment("target-1", started, 4380.0, 1.46)
    candidate = deployment("candidate-1", started, 4380.0, 1.46)
    for events, cycle_id in (
        (target, "target-1"),
        (candidate, "candidate-1"),
    ):
        events.extend(
            [
                {
                    "cycle_id": cycle_id,
                    "time_utc": (
                        started + timedelta(seconds=30)
                    ).isoformat(),
                    "kind": "fill",
                    "comment": "STR B1",
                    "side": "buy",
                    "level": 1,
                    "volume": 0.01,
                    "accepted_price": 4381.46,
                    "requested_price": 4381.46,
                    "sl": 0.0,
                    "retcode": 0,
                },
                {
                    "cycle_id": cycle_id,
                    "time_utc": (
                        started + timedelta(seconds=40)
                    ).isoformat(),
                    "kind": "stop_request",
                    "comment": "STR B1",
                    "side": "buy",
                    "level": 1,
                    "volume": 0.01,
                    "requested_price": 4381.66,
                    "accepted_price": 0.0,
                    "sl": 4381.66,
                    "retcode": 10009,
                    "source": (
                        "target"
                        if cycle_id == "target-1"
                        else "candidate"
                    ),
                    "evidence_grade": (
                        "BEST_EFFORT"
                        if cycle_id == "target-1"
                        else "FORMAL_CANDIDATE"
                    ),
                },
            ]
        )
    candidate.append(
        {
            "cycle_id": "candidate-1",
            "time_utc": (started + timedelta(seconds=50)).isoformat(),
            "kind": "stop_request",
            "comment": "STR B1",
            "side": "buy",
            "level": 1,
            "volume": 0.01,
            "requested_price": 4383.70,
            "accepted_price": 0.0,
            "sl": 4383.70,
            "retcode": 10009,
            "source": "candidate",
            "evidence_grade": "FORMAL_CANDIDATE",
        }
    )
    target.append(
        {
            "cycle_id": "target-1",
            "time_utc": (started + timedelta(seconds=60)).isoformat(),
            "kind": "stop_exit",
            "comment": "STR B1",
            "side": "buy",
            "level": 1,
            "volume": 0.01,
            "accepted_price": 4384.50,
            "requested_price": 0.0,
            "sl": 0.0,
            "retcode": 0,
            "source": "target",
            "evidence_grade": "BEST_EFFORT",
        }
    )
    candidate.append(
        {
            "cycle_id": "candidate-1",
            "time_utc": (started + timedelta(seconds=55)).isoformat(),
            "kind": "stop_exit",
            "comment": "STR B1",
            "side": "buy",
            "level": 1,
            "volume": 0.01,
            "accepted_price": 4383.70,
            "requested_price": 0.0,
            "sl": 0.0,
            "retcode": 0,
            "source": "candidate",
            "evidence_grade": "FORMAL_CANDIDATE",
        }
    )
    complete(target, started + timedelta(minutes=2))
    complete(candidate, started + timedelta(minutes=2))

    report = compare_independent_cycle_pair(
        target,
        candidate,
        start_tolerance_seconds=2.0,
        normalized_price_tolerance=0.02,
    )

    assert report["logic_status"] == "PASS"
    assert report["deterministic_mismatch_count"] == 0
    assert report["execution_status"] == "DIFFERENT"


def test_execution_divergence_is_tracked_for_each_affected_level() -> None:
    started = datetime(2026, 8, 12, tzinfo=UTC)
    target = deployment("target-1", started, 4380.0, 1.46)
    candidate = deployment("candidate-1", started, 4380.0, 1.46)
    for events, cycle_id, fill_delta in (
        (target, "target-1", 0.0),
        (candidate, "candidate-1", 0.08),
    ):
        events.extend(
            [
                {
                    "cycle_id": cycle_id,
                    "time_utc": (
                        started + timedelta(seconds=30)
                    ).isoformat(),
                    "kind": "fill",
                    "comment": "STR B1",
                    "side": "buy",
                    "level": 1,
                    "volume": 0.01,
                    "accepted_price": 4381.46 + fill_delta,
                    "requested_price": 4381.46 + fill_delta,
                    "sl": 0.0,
                    "retcode": 0,
                },
                {
                    "cycle_id": cycle_id,
                    "time_utc": (
                        started + timedelta(seconds=31)
                    ).isoformat(),
                    "kind": "stop_request",
                    "comment": "STR B1",
                    "side": "buy",
                    "level": 1,
                    "volume": 0.01,
                    "requested_price": 4381.66 + fill_delta,
                    "accepted_price": 0.0,
                    "sl": 4381.66 + fill_delta,
                    "retcode": 10009,
                },
                {
                    "cycle_id": cycle_id,
                    "time_utc": (
                        started + timedelta(seconds=32)
                    ).isoformat(),
                    "kind": "fill",
                    "comment": "STR B2",
                    "side": "buy",
                    "level": 2,
                    "volume": 0.01,
                    "accepted_price": 4382.92 + fill_delta,
                    "requested_price": 4382.92 + fill_delta,
                    "sl": 0.0,
                    "retcode": 0,
                },
                {
                    "cycle_id": cycle_id,
                    "time_utc": (
                        started + timedelta(seconds=33)
                    ).isoformat(),
                    "kind": "stop_request",
                    "comment": "STR B2",
                    "side": "buy",
                    "level": 2,
                    "volume": 0.01,
                    "requested_price": 4383.12 + fill_delta,
                    "accepted_price": 0.0,
                    "sl": 4383.12 + fill_delta,
                    "retcode": 10009,
                },
                {
                    "cycle_id": cycle_id,
                    "time_utc": (
                        started + timedelta(seconds=34)
                    ).isoformat(),
                    "kind": "stop_request",
                    "comment": "STR B3",
                    "side": "buy",
                    "level": 3,
                    "volume": 0.01,
                    "requested_price": 4384.38,
                    "accepted_price": 0.0,
                    "sl": 4384.38,
                    "retcode": 10009,
                },
            ]
        )
        complete(events, started + timedelta(minutes=1))

    report = compare_independent_cycle_pair(
        target,
        candidate,
        start_tolerance_seconds=2.0,
        normalized_price_tolerance=0.02,
    )

    b3_stop = next(
        event
        for event in report["transition_timing"]
        if event["kind"] == "stop_request"
        and event["comment"] == "STR B3"
    )
    assert report["logic_status"] == "PASS"
    assert report["deterministic_mismatch_count"] == 0
    assert b3_stop["comparison_class"] == "PAIRED"
    assert sum(
        mismatch["category"] == "execution_price"
        for mismatch in report["execution_mismatches"]
    ) == 2


def test_cross_level_decision_interleaving_is_not_logic_mismatch() -> None:
    started = datetime(2026, 8, 12, tzinfo=UTC)
    target = deployment("target-1", started, 4380.0, 1.46)
    candidate = deployment("candidate-1", started, 4380.0, 1.46)
    b1_stop = {
        "time_utc": (started + timedelta(seconds=30)).isoformat(),
        "kind": "stop_request",
        "comment": "STR B1",
        "side": "buy",
        "level": 1,
        "volume": 0.01,
        "requested_price": 4381.66,
        "accepted_price": 0.0,
        "sl": 4381.66,
        "retcode": 10009,
    }
    s1_stop = {
        "time_utc": (started + timedelta(seconds=31)).isoformat(),
        "kind": "stop_request",
        "comment": "STR S1",
        "side": "sell",
        "level": 1,
        "volume": 0.01,
        "requested_price": 4378.34,
        "accepted_price": 0.0,
        "sl": 4378.34,
        "retcode": 10009,
    }
    target.extend(
        [
            {**b1_stop, "cycle_id": "target-1"},
            {**s1_stop, "cycle_id": "target-1"},
        ]
    )
    candidate.extend(
        [
            {
                **s1_stop,
                "cycle_id": "candidate-1",
                "time_utc": (
                    started + timedelta(seconds=30)
                ).isoformat(),
            },
            {
                **b1_stop,
                "cycle_id": "candidate-1",
                "time_utc": (
                    started + timedelta(seconds=31)
                ).isoformat(),
            },
        ]
    )
    complete(target, started + timedelta(minutes=1))
    complete(candidate, started + timedelta(minutes=1))

    report = compare_independent_cycle_pair(
        target,
        candidate,
        start_tolerance_seconds=2.0,
        normalized_price_tolerance=0.02,
    )

    assert report["logic_status"] == "PASS"
    assert report["deterministic_mismatch_count"] == 0


def test_execution_diverged_transitions_are_excluded_from_timing_summary() -> None:
    started = datetime(2026, 8, 12, tzinfo=UTC)
    target = deployment("target-1", started, 4380.0, 1.46)
    candidate = deployment("candidate-1", started, 4380.0, 1.46)
    target.extend(
        [
            {
                "cycle_id": "target-1",
                "time_utc": (started + timedelta(seconds=30)).isoformat(),
                "kind": "fill",
                "comment": "STR B1",
                "side": "buy",
                "level": 1,
                "volume": 0.01,
                "accepted_price": 4381.46,
                "requested_price": 4381.46,
                "sl": 0.0,
                "retcode": 0,
            },
            {
                "cycle_id": "target-1",
                "time_utc": (started + timedelta(seconds=31)).isoformat(),
                "kind": "stop_request",
                "comment": "STR B1",
                "side": "buy",
                "level": 1,
                "volume": 0.01,
                "requested_price": 4381.66,
                "accepted_price": 0.0,
                "sl": 4381.66,
                "retcode": 10009,
            },
        ]
    )
    candidate.extend(
        [
            {
                "cycle_id": "candidate-1",
                "time_utc": (started + timedelta(seconds=30)).isoformat(),
                "kind": "fill",
                "comment": "STR B1",
                "side": "buy",
                "level": 1,
                "volume": 0.01,
                "accepted_price": 4381.54,
                "requested_price": 4381.54,
                "sl": 0.0,
                "retcode": 0,
            },
            {
                "cycle_id": "candidate-1",
                "time_utc": (started + timedelta(seconds=51)).isoformat(),
                "kind": "stop_request",
                "comment": "STR B1",
                "side": "buy",
                "level": 1,
                "volume": 0.01,
                "requested_price": 4381.66,
                "accepted_price": 0.0,
                "sl": 4381.66,
                "retcode": 10009,
            },
        ]
    )
    complete(target, started + timedelta(minutes=1))
    complete(candidate, started + timedelta(minutes=1))

    report = compare_independent_cycle_pair(
        target,
        candidate,
        start_tolerance_seconds=2.0,
        normalized_price_tolerance=0.02,
    )

    summary = report["transition_timing_summary"]
    assert report["logic_status"] == "PASS"
    basket_trigger = next(
        event
        for event in report["transition_timing"]
        if event["kind"] == "basket_trigger"
    )
    assert summary["excluded_execution_diverged_events"] == 3
    assert basket_trigger["comparison_class"] == "EXECUTION_DIVERGED"
    assert summary["max_absolute_delta_seconds"] == 0.0
    assert summary["p95_absolute_delta_seconds"] == 0.0


def test_initial_pending_request_survives_earlier_missing_fill_divergence() -> None:
    started = datetime(2026, 8, 12, tzinfo=UTC)
    target = deployment("target-1", started, 4380.0, 1.46)
    candidate = deployment("candidate-1", started, 4380.0, 1.46)
    for event in candidate:
        if (
            event["kind"] == "pending_request"
            and event["comment"] == "STR S1"
        ):
            event["time_utc"] = (
                started + timedelta(seconds=2)
            ).isoformat()
            break
    target.append(
        {
            "cycle_id": "target-1",
            "time_utc": (started + timedelta(seconds=1)).isoformat(),
            "kind": "fill",
            "comment": "STR S1",
            "side": "sell",
            "level": 1,
            "volume": 0.01,
            "accepted_price": 4378.54,
            "requested_price": 4378.54,
            "sl": 0.0,
            "retcode": 0,
        }
    )
    complete(target, started + timedelta(seconds=10))
    complete(candidate, started + timedelta(seconds=10))

    report = compare_independent_cycle_pair(
        target,
        candidate,
        start_tolerance_seconds=0.5,
        normalized_price_tolerance=0.02,
    )

    assert report["logic_status"] == "PASS"
    assert not any(
        mismatch["category"] == "decision_sequence"
        and mismatch["comment"] == "STR S1"
        for mismatch in report["deterministic_mismatches"]
    )


def test_counterpart_completion_excludes_both_trailing_stage_sequences() -> None:
    started = datetime(2026, 8, 12, tzinfo=UTC)
    target = deployment("target-1", started, 4380.0, 1.46)
    candidate = deployment("candidate-1", started, 4380.0, 1.46)
    fill = {
        "time_utc": (started + timedelta(seconds=30)).isoformat(),
        "kind": "fill",
        "comment": "STR B3",
        "side": "buy",
        "level": 3,
        "volume": 0.01,
        "accepted_price": 4384.38,
        "requested_price": 4384.38,
        "sl": 0.0,
        "retcode": 0,
    }

    def stop_request(seconds: int, price: float) -> dict:
        return {
            **fill,
            "time_utc": (
                started + timedelta(seconds=seconds)
            ).isoformat(),
            "kind": "stop_request",
            "accepted_price": 0.0,
            "requested_price": price,
            "sl": price,
            "retcode": 10009,
        }

    def stop_exit(seconds: int) -> dict:
        return {
            **fill,
            "time_utc": (
                started + timedelta(seconds=seconds)
            ).isoformat(),
            "kind": "stop_exit",
            "accepted_price": 4386.72,
            "requested_price": 0.0,
        }

    target.extend(
        [
            {**fill, "cycle_id": "target-1"},
            {
                **stop_request(110, 4384.58),
                "cycle_id": "target-1",
            },
            {
                **stop_request(111, 4386.72),
                "cycle_id": "target-1",
            },
            {**stop_exit(120), "cycle_id": "target-1"},
        ]
    )
    candidate.extend(
        [
            {**fill, "cycle_id": "candidate-1"},
            {
                **stop_request(35, 4384.58),
                "cycle_id": "candidate-1",
            },
            {
                **stop_request(36, 4386.72),
                "cycle_id": "candidate-1",
            },
            {**stop_exit(40), "cycle_id": "candidate-1"},
        ]
    )
    complete(candidate, started + timedelta(seconds=60))
    complete(target, started + timedelta(seconds=130))

    report = compare_independent_cycle_pair(
        target,
        candidate,
        start_tolerance_seconds=5.0,
        normalized_price_tolerance=0.02,
    )

    assert report["logic_status"] == "PASS"
    assert not any(
        mismatch["category"] == "trailing_stage_sequence"
        and mismatch["comment"] == "STR B3"
        for mismatch in report["deterministic_mismatches"]
    )


def test_intermediate_trailing_updates_compare_by_causal_stage() -> None:
    started = datetime(2026, 8, 12, tzinfo=UTC)
    target = deployment("target-1", started, 4380.0, 1.46)
    candidate = deployment("candidate-1", started, 4380.0, 1.46)
    fill = {
        "time_utc": (started + timedelta(seconds=30)).isoformat(),
        "kind": "fill",
        "comment": "STR B1",
        "side": "buy",
        "level": 1,
        "volume": 0.01,
        "accepted_price": 4381.46,
        "requested_price": 4381.46,
        "sl": 0.0,
        "retcode": 0,
    }
    target.extend(
        [
            {**fill, "cycle_id": "target-1"},
            {
                **fill,
                "cycle_id": "target-1",
                "time_utc": (
                    started + timedelta(seconds=31)
                ).isoformat(),
                "kind": "stop_request",
                "requested_price": 4381.66,
                "accepted_price": 0.0,
                "sl": 4381.66,
                "retcode": 10009,
            },
            {
                **fill,
                "cycle_id": "target-1",
                "time_utc": (
                    started + timedelta(seconds=32)
                ).isoformat(),
                "kind": "stop_request",
                "requested_price": 4381.68,
                "accepted_price": 0.0,
                "sl": 4381.68,
                "retcode": 10009,
            },
            {
                **fill,
                "cycle_id": "target-1",
                "time_utc": (
                    started + timedelta(seconds=33)
                ).isoformat(),
                "kind": "stop_request",
                "requested_price": 4383.80,
                "accepted_price": 0.0,
                "sl": 4383.80,
                "retcode": 10009,
            },
        ]
    )
    candidate.extend(
        [
            {**fill, "cycle_id": "candidate-1"},
            {
                **fill,
                "cycle_id": "candidate-1",
                "time_utc": (
                    started + timedelta(seconds=31)
                ).isoformat(),
                "kind": "stop_request",
                "requested_price": 4381.70,
                "accepted_price": 0.0,
                "sl": 4381.70,
                "retcode": 10009,
            },
            {
                **fill,
                "cycle_id": "candidate-1",
                "time_utc": (
                    started + timedelta(seconds=33)
                ).isoformat(),
                "kind": "stop_request",
                "requested_price": 4383.84,
                "accepted_price": 0.0,
                "sl": 4383.84,
                "retcode": 10009,
            },
        ]
    )
    complete(target, started + timedelta(minutes=1))
    complete(candidate, started + timedelta(minutes=1))

    report = compare_independent_cycle_pair(
        target,
        candidate,
        start_tolerance_seconds=2.0,
        normalized_price_tolerance=0.02,
    )

    assert report["logic_status"] == "PASS"
    assert report["deterministic_mismatch_count"] == 0
    assert report["fidelity"]["strict"]["f1_percent"] == 100.0


def test_missing_tightened_trailing_stage_is_deterministic() -> None:
    started = datetime(2026, 8, 12, tzinfo=UTC)
    target = deployment("target-1", started, 4380.0, 1.46)
    candidate = deployment("candidate-1", started, 4380.0, 1.46)
    fill = {
        "time_utc": (started + timedelta(seconds=30)).isoformat(),
        "kind": "fill",
        "comment": "STR B1",
        "side": "buy",
        "level": 1,
        "volume": 0.01,
        "accepted_price": 4381.46,
        "requested_price": 4381.46,
        "sl": 0.0,
        "retcode": 0,
    }
    activation = {
        **fill,
        "time_utc": (started + timedelta(seconds=31)).isoformat(),
        "kind": "stop_request",
        "requested_price": 4381.66,
        "accepted_price": 0.0,
        "sl": 4381.66,
        "retcode": 10009,
    }
    tightened = {
        **activation,
        "time_utc": (started + timedelta(seconds=32)).isoformat(),
        "requested_price": 4383.80,
        "sl": 4383.80,
    }
    target.extend(
        [
            {**fill, "cycle_id": "target-1"},
            {**activation, "cycle_id": "target-1"},
            {**tightened, "cycle_id": "target-1"},
        ]
    )
    candidate.extend(
        [
            {**fill, "cycle_id": "candidate-1"},
            {**activation, "cycle_id": "candidate-1"},
        ]
    )
    complete(target, started + timedelta(minutes=1))
    complete(candidate, started + timedelta(minutes=1))

    report = compare_independent_cycle_pair(
        target,
        candidate,
        start_tolerance_seconds=2.0,
        normalized_price_tolerance=0.02,
    )

    assert report["logic_status"] == "FAIL"
    assert any(
        mismatch["category"] == "trailing_stage_sequence"
        for mismatch in report["deterministic_mismatches"]
    )


def test_matching_fill_identity_reports_relative_timing_difference() -> None:
    started = datetime(2026, 8, 12, tzinfo=UTC)
    target = deployment("target-1", started, 4380.0, 1.46)
    candidate = deployment("candidate-1", started, 4380.0, 1.46)
    fill = {
        "cycle_id": "target-1",
        "time_utc": (started + timedelta(seconds=30)).isoformat(),
        "kind": "fill",
        "comment": "STR B1",
        "side": "buy",
        "level": 1,
        "volume": 0.01,
        "accepted_price": 4381.46,
        "requested_price": 4381.46,
        "sl": 0.0,
        "retcode": 0,
    }
    target.append(fill)
    candidate.append(
        {
            **fill,
            "cycle_id": "candidate-1",
            "time_utc": (
                started + timedelta(seconds=34)
            ).isoformat(),
        }
    )
    complete(target, started + timedelta(minutes=1))
    complete(candidate, started + timedelta(minutes=1))

    report = compare_independent_cycle_pair(
        target,
        candidate,
        start_tolerance_seconds=2.0,
        normalized_price_tolerance=0.02,
    )

    assert report["logic_status"] == "PASS"
    assert report["execution_status"] == "DIFFERENT"
    assert report["execution_timing"][0]["comment"] == "STR B1"
    assert report["execution_timing"][0]["delta_seconds"] == 4.0
    assert any(
        mismatch["category"] == "execution_timing"
        for mismatch in report["execution_mismatches"]
    )


def test_matching_lifecycle_transitions_report_non_gating_timing() -> None:
    started = datetime(2026, 8, 12, tzinfo=UTC)
    target = deployment("target-1", started, 4380.0, 1.46)
    candidate = deployment("candidate-1", started, 4380.0, 1.46)
    stop = {
        "cycle_id": "target-1",
        "time_utc": (started + timedelta(seconds=30)).isoformat(),
        "kind": "stop_request",
        "comment": "STR B1",
        "side": "buy",
        "level": 1,
        "volume": 0.01,
        "requested_price": 4381.66,
        "accepted_price": 0.0,
        "sl": 4381.66,
        "retcode": 10009,
    }
    target.append(stop)
    candidate.append(
        {
            **stop,
            "cycle_id": "candidate-1",
            "time_utc": (started + timedelta(seconds=34)).isoformat(),
        }
    )
    complete(target, started + timedelta(minutes=1))
    complete(candidate, started + timedelta(minutes=1))

    report = compare_independent_cycle_pair(
        target,
        candidate,
        start_tolerance_seconds=2.0,
        normalized_price_tolerance=0.02,
    )

    timing = next(
        event
        for event in report["transition_timing"]
        if event["kind"] == "stop_request"
        and event["comment"] == "STR B1"
    )
    assert report["logic_status"] == "PASS"
    assert timing["delta_seconds"] == 4.0
    assert report["transition_timing_summary"]["matched_events"] == len(
        report["transition_timing"]
    )


def test_inferred_basket_trigger_is_excluded_from_timing_percentiles() -> None:
    started = datetime(2026, 8, 12, tzinfo=UTC)
    target = deployment("target-1", started, 4380.0, 1.46)
    candidate = deployment("candidate-1", started, 4380.0, 1.46)
    completed = started + timedelta(minutes=1)
    complete(target, completed)
    complete(candidate, completed)

    target_trigger = next(
        event for event in target if event["kind"] == "basket_trigger"
    )
    target_trigger.update(
        {
            "time_utc": (started + timedelta(seconds=50)).isoformat(),
            "source": "observer_inferred",
            "capture_limit": (
                "basket_trigger_inferred_from_first_broker_close_or_cancel"
            ),
        }
    )
    candidate_trigger = next(
        event
        for event in candidate
        if event["kind"] == "basket_trigger"
    )
    candidate_trigger["time_utc"] = (
        started + timedelta(seconds=10)
    ).isoformat()

    report = compare_independent_cycle_pair(
        target,
        candidate,
        start_tolerance_seconds=2.0,
        normalized_price_tolerance=0.02,
    )

    trigger_timing = next(
        event
        for event in report["transition_timing"]
        if event["kind"] == "basket_trigger"
    )
    summary = report["transition_timing_summary"]
    assert report["logic_status"] == "PASS"
    assert (
        trigger_timing["comparison_class"]
        == "BROKER_ACCEPTANCE_PROXY"
    )
    assert trigger_timing["delta_seconds"] == -40.0
    assert summary["excluded_proxy_events"] == 1
    assert summary["eligible_timed_events"] == summary["matched_events"] - 1
    assert summary["max_absolute_delta_seconds"] == 0.0
    assert summary["p95_absolute_delta_seconds"] == 0.0


def test_cancel_then_pending_is_a_recovery_replacement_not_duplicate_rearm() -> None:
    started = datetime(2026, 8, 13, tzinfo=UTC)
    target = deployment("target-1", started, 4380.0, 1.46)
    candidate = deployment("candidate-1", started, 4390.0, 1.465)

    for events, cycle_id, anchor, step in (
        (target, "target-1", 4380.0, 1.46),
        (candidate, "candidate-1", 4390.0, 1.465),
    ):
        events.extend(
            [
                {
                    "cycle_id": cycle_id,
                    "time_utc": (started + timedelta(seconds=10)).isoformat(),
                    "kind": "cancel_request",
                    "comment": "STR S15",
                    "side": "sell",
                    "level": 15,
                    "volume": 0.06,
                    "requested_price": anchor - 15 * step,
                    "accepted_price": 0.0,
                    "sl": 0.0,
                    "retcode": 10009,
                },
                {
                    "cycle_id": cycle_id,
                    "time_utc": (
                        started + timedelta(seconds=10, milliseconds=100)
                    ).isoformat(),
                    "kind": "pending_request",
                    "comment": "STR S15",
                    "side": "sell",
                    "level": 15,
                    "volume": 0.12,
                    "requested_price": anchor - 15 * step,
                    "accepted_price": 0.0,
                    "sl": 0.0,
                    "retcode": 10008,
                },
            ]
        )
        complete(events, started + timedelta(minutes=1))

    report = compare_independent_cycle_pair(
        target,
        candidate,
        start_tolerance_seconds=2.0,
        normalized_price_tolerance=0.02,
    )

    assert report["logic_status"] == "PASS"
    assert report["deterministic_mismatch_count"] == 0
    assert report["deployment"]["target_duplicate_slots"] == []
    assert report["deployment"]["candidate_duplicate_slots"] == []
    assert any(
        event["kind"] == "replacement_request"
        and event["comment"] == "STR S15"
        for event in report["transition_timing"]
    )


def test_post_deployment_pending_without_observed_stop_is_not_duplicate() -> None:
    started = datetime(2026, 8, 13, tzinfo=UTC)
    target = deployment("target-1", started, 4380.0, 1.46)
    candidate = deployment("candidate-1", started, 4390.0, 1.465)

    for events, cycle_id, anchor, step in (
        (target, "target-1", 4380.0, 1.46),
        (candidate, "candidate-1", 4390.0, 1.465),
    ):
        events.extend(
            [
                {
                    "cycle_id": cycle_id,
                    "time_utc": (started + timedelta(seconds=10)).isoformat(),
                    "kind": "fill",
                    "comment": "STR B6",
                    "side": "buy",
                    "level": 6,
                    "volume": 0.01,
                    "requested_price": anchor + 6 * step,
                    "accepted_price": anchor + 6 * step,
                    "sl": 0.0,
                    "retcode": 0,
                },
                {
                    "cycle_id": cycle_id,
                    "time_utc": (started + timedelta(seconds=20)).isoformat(),
                    "kind": "pending_request",
                    "comment": "STR B6",
                    "side": "buy",
                    "level": 6,
                    "volume": 0.01,
                    "requested_price": anchor + 6 * step,
                    "accepted_price": 0.0,
                    "sl": 0.0,
                    "retcode": 10008,
                },
            ]
        )
        complete(events, started + timedelta(minutes=1))

    report = compare_independent_cycle_pair(
        target,
        candidate,
        start_tolerance_seconds=2.0,
        normalized_price_tolerance=0.02,
    )

    assert report["logic_status"] == "PASS"
    assert report["deterministic_mismatch_count"] == 0
    assert report["deployment"]["target_duplicate_slots"] == []
    assert report["deployment"]["candidate_duplicate_slots"] == []


def test_candidate_only_rejected_rearm_attempt_is_diagnostic() -> None:
    started = datetime(2026, 8, 13, tzinfo=UTC)
    target = deployment("target-1", started, 4380.0, 1.46)
    candidate = deployment("candidate-1", started, 4380.0, 1.46)
    stopped = started + timedelta(seconds=30)
    accepted = stopped + timedelta(seconds=21)

    target_stop = {
        "cycle_id": "target-1",
        "time_utc": stopped.isoformat(),
        "kind": "stop_exit",
        "comment": "STR S10",
        "side": "sell",
        "level": 10,
        "volume": 0.01,
        "requested_price": 4365.4,
        "accepted_price": 4365.4,
        "sl": 0.0,
        "retcode": 0,
    }
    target_rearm = {
        "cycle_id": "target-1",
        "time_utc": accepted.isoformat(),
        "kind": "pending_request",
        "comment": "STR S10",
        "side": "sell",
        "level": 10,
        "volume": 0.01,
        "requested_price": 4365.4,
        "accepted_price": 0.0,
        "sl": 0.0,
        "retcode": 10009,
    }
    target.extend([target_stop, target_rearm])
    candidate.extend(
        [
            {**target_stop, "cycle_id": "candidate-1"},
            {
                **target_rearm,
                "cycle_id": "candidate-1",
                "time_utc": (
                    stopped + timedelta(seconds=20, milliseconds=100)
                ).isoformat(),
                "retcode": 10015,
            },
            {**target_rearm, "cycle_id": "candidate-1"},
        ]
    )
    complete(target, started + timedelta(minutes=1))
    complete(candidate, started + timedelta(minutes=1))

    report = compare_independent_cycle_pair(
        target,
        candidate,
        start_tolerance_seconds=2.0,
        normalized_price_tolerance=0.02,
    )

    assert report["logic_status"] == "PASS"
    assert report["fidelity"]["strict"]["f1_percent"] == 100.0
    assert report["request_rejections"]["target_count"] == 0
    assert report["request_rejections"]["candidate_count"] == 1
