from datetime import datetime, timedelta, timezone

import pytest

from straddle_replica.broker_execution import (
    StopChange,
    StopExit,
    detect_serialized_stop_runs,
)


UTC = timezone.utc


def test_detects_serialized_exits_after_all_identical_stops_were_set():
    start = datetime(2026, 8, 3, 14, 20, 17, tzinfo=UTC)
    changes = [
        StopChange(101, start, 4050.23),
        StopChange(102, start + timedelta(milliseconds=100), 4050.23),
        StopChange(103, start + timedelta(milliseconds=200), 4050.23),
    ]
    exits = [
        StopExit(101, start + timedelta(seconds=6), 4050.23),
        StopExit(102, start + timedelta(seconds=26.1), 4050.23),
        StopExit(103, start + timedelta(seconds=46.0), 4050.23),
    ]

    runs = detect_serialized_stop_runs(exits, changes)

    assert len(runs) == 1
    run = runs[0]
    assert run.stop_price == pytest.approx(4050.23)
    assert run.first_exit_time == start + timedelta(seconds=6)
    assert run.position_ids == (101, 102, 103)
    assert run.exit_gaps_seconds == pytest.approx((20.1, 19.9))
    assert run.ticket_order == "ascending"
    assert run.assigned_before_first_exit == 3
    assert run.all_stops_set_before_first_exit is True
    assert run.latest_assignment_lead_seconds == pytest.approx(5.8)


def test_does_not_group_different_prices_or_non_serialized_gaps():
    start = datetime(2026, 8, 3, 14, 20, tzinfo=UTC)
    exits = [
        StopExit(101, start, 4050.23),
        StopExit(102, start + timedelta(seconds=5), 4050.23),
        StopExit(103, start + timedelta(seconds=25), 4050.30),
    ]

    assert detect_serialized_stop_runs(exits, []) == ()


def test_reports_incomplete_stop_assignment_evidence():
    start = datetime(2026, 8, 3, 14, 20, tzinfo=UTC)
    changes = [StopChange(201, start, 4043.23)]
    exits = [
        StopExit(201, start + timedelta(seconds=3), 4043.23),
        StopExit(202, start + timedelta(seconds=23), 4043.23),
    ]

    run = detect_serialized_stop_runs(exits, changes)[0]

    assert run.assigned_before_first_exit == 1
    assert run.all_stops_set_before_first_exit is False
    assert run.ticket_order == "ascending"
