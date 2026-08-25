from datetime import datetime, timezone

import pytest

from straddle_replica.compare import (
    ComparisonTolerance,
    Event,
    align_events,
    compare_events,
)


UTC = timezone.utc


def test_comparator_requires_exact_deterministic_fields():
    expected = Event(
        time=datetime(2026, 7, 30, 12, 0, tzinfo=UTC),
        kind="pending",
        comment="STR B1",
        side="buy",
        volume=0.01,
        price=4101.37,
    )
    actual = Event(
        time=datetime(2026, 7, 30, 12, 0, tzinfo=UTC),
        kind="pending",
        comment="STR B1",
        side="buy",
        volume=0.02,
        price=4101.37,
    )

    result = compare_events([expected], [actual], ComparisonTolerance())

    assert not result.is_match
    assert result.mismatches[0].field == "volume"


def test_comparator_allows_configured_execution_tolerance():
    expected = Event(
        time=datetime(2026, 7, 30, 12, 0, 0, tzinfo=UTC),
        kind="fill",
        comment="STR B1",
        side="buy",
        volume=0.01,
        price=4101.37,
    )
    actual = Event(
        time=datetime(2026, 7, 30, 12, 0, 0, 600_000, tzinfo=UTC),
        kind="fill",
        comment="STR B1",
        side="buy",
        volume=0.01,
        price=4101.38,
    )

    result = compare_events(
        [expected],
        [actual],
        ComparisonTolerance(time_seconds=1.0, price=0.01),
    )

    assert result.is_match


def test_aligned_comparator_does_not_cascade_after_extra_event():
    start = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)

    def event(second: int, comment: str) -> Event:
        return Event(
            time=start.replace(second=second),
            kind="fill",
            comment=comment,
            side="buy",
            volume=0.01,
            price=4100.0 + second,
        )

    expected = [event(1, "STR B1"), event(2, "STR B2"), event(3, "STR B3")]
    actual = [
        event(1, "STR B1"),
        event(9, "STR B9"),
        event(2, "STR B2"),
        event(3, "STR B3"),
    ]

    result = align_events(expected, actual, ComparisonTolerance())

    assert result.matched_count == 3
    assert result.missing_expected == ()
    assert [item.event.comment for item in result.unexpected_actual] == ["STR B9"]
    assert result.execution_mismatches == ()


def test_aligned_comparator_rejects_unbounded_quadratic_comparison():
    event = Event(
        time=datetime(2026, 7, 30, 12, 0, tzinfo=UTC),
        kind="fill",
        comment="STR B1",
        side="buy",
        volume=0.01,
        price=4100.0,
    )

    with pytest.raises(ValueError, match="cycle-sized"):
        align_events(
            [event] * 2_237,
            [event] * 2_237,
            ComparisonTolerance(),
        )
