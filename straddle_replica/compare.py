from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


MAX_ALIGNMENT_CELLS = 5_000_000


@dataclass(frozen=True)
class Event:
    time: datetime
    kind: str
    comment: str
    side: str
    volume: float
    price: float


@dataclass(frozen=True)
class ComparisonTolerance:
    time_seconds: float = 0.0
    price: float = 0.0
    volume: float = 1e-9


@dataclass(frozen=True)
class Mismatch:
    index: int
    field: str
    expected: object
    actual: object


@dataclass(frozen=True)
class ComparisonResult:
    expected_count: int
    actual_count: int
    mismatches: tuple[Mismatch, ...]

    @property
    def is_match(self) -> bool:
        return (
            self.expected_count == self.actual_count
            and not self.mismatches
        )


@dataclass(frozen=True)
class IndexedEvent:
    index: int
    event: Event


@dataclass(frozen=True)
class AlignedComparisonResult:
    expected_count: int
    actual_count: int
    matched_count: int
    missing_expected: tuple[IndexedEvent, ...]
    unexpected_actual: tuple[IndexedEvent, ...]
    execution_mismatches: tuple[Mismatch, ...]

    @property
    def deterministic_match(self) -> bool:
        return not self.missing_expected and not self.unexpected_actual

    @property
    def is_match(self) -> bool:
        return self.deterministic_match and not self.execution_mismatches


def _same_identity(
    expected: Event,
    actual: Event,
    tolerance: ComparisonTolerance,
) -> bool:
    return (
        expected.kind == actual.kind
        and expected.comment == actual.comment
        and expected.side == actual.side
        and abs(expected.volume - actual.volume) <= tolerance.volume
    )


def align_events(
    expected: list[Event],
    actual: list[Event],
    tolerance: ComparisonTolerance,
) -> AlignedComparisonResult:
    rows = len(expected)
    columns = len(actual)
    if rows * columns > MAX_ALIGNMENT_CELLS:
        raise ValueError(
            "Aligned comparison is too large; compare cycle-sized event "
            "windows instead."
        )
    lengths = [[0] * (columns + 1) for _ in range(rows + 1)]
    for expected_index in range(rows):
        for actual_index in range(columns):
            if _same_identity(
                expected[expected_index],
                actual[actual_index],
                tolerance,
            ):
                lengths[expected_index + 1][actual_index + 1] = (
                    lengths[expected_index][actual_index] + 1
                )
            else:
                lengths[expected_index + 1][actual_index + 1] = max(
                    lengths[expected_index][actual_index + 1],
                    lengths[expected_index + 1][actual_index],
                )

    matches: list[tuple[int, int]] = []
    expected_index = rows
    actual_index = columns
    while expected_index > 0 and actual_index > 0:
        if _same_identity(
            expected[expected_index - 1],
            actual[actual_index - 1],
            tolerance,
        ):
            matches.append((expected_index - 1, actual_index - 1))
            expected_index -= 1
            actual_index -= 1
        elif (
            lengths[expected_index - 1][actual_index]
            >= lengths[expected_index][actual_index - 1]
        ):
            expected_index -= 1
        else:
            actual_index -= 1
    matches.reverse()

    matched_expected = {item[0] for item in matches}
    matched_actual = {item[1] for item in matches}
    missing = tuple(
        IndexedEvent(index, event)
        for index, event in enumerate(expected)
        if index not in matched_expected
    )
    unexpected = tuple(
        IndexedEvent(index, event)
        for index, event in enumerate(actual)
        if index not in matched_actual
    )
    execution_mismatches: list[Mismatch] = []
    for expected_index, actual_index in matches:
        expected_event = expected[expected_index]
        actual_event = actual[actual_index]
        if (
            abs(expected_event.price - actual_event.price)
            > tolerance.price + 1e-12
        ):
            execution_mismatches.append(
                Mismatch(
                    expected_index,
                    "price",
                    expected_event.price,
                    actual_event.price,
                )
            )
        elapsed = abs(
            (expected_event.time - actual_event.time).total_seconds()
        )
        if elapsed > tolerance.time_seconds:
            execution_mismatches.append(
                Mismatch(
                    expected_index,
                    "time",
                    expected_event.time,
                    actual_event.time,
                )
            )

    return AlignedComparisonResult(
        expected_count=rows,
        actual_count=columns,
        matched_count=len(matches),
        missing_expected=missing,
        unexpected_actual=unexpected,
        execution_mismatches=tuple(execution_mismatches),
    )


def compare_events(
    expected: list[Event],
    actual: list[Event],
    tolerance: ComparisonTolerance,
) -> ComparisonResult:
    mismatches: list[Mismatch] = []
    for index, (expected_event, actual_event) in enumerate(zip(expected, actual)):
        for field in ("kind", "comment", "side"):
            expected_value = getattr(expected_event, field)
            actual_value = getattr(actual_event, field)
            if expected_value != actual_value:
                mismatches.append(
                    Mismatch(index, field, expected_value, actual_value)
                )
        if abs(expected_event.volume - actual_event.volume) > tolerance.volume:
            mismatches.append(
                Mismatch(
                    index,
                    "volume",
                    expected_event.volume,
                    actual_event.volume,
                )
            )
        if abs(expected_event.price - actual_event.price) > tolerance.price + 1e-12:
            mismatches.append(
                Mismatch(index, "price", expected_event.price, actual_event.price)
            )
        elapsed = abs((expected_event.time - actual_event.time).total_seconds())
        if elapsed > tolerance.time_seconds:
            mismatches.append(
                Mismatch(index, "time", expected_event.time, actual_event.time)
            )
    return ComparisonResult(
        expected_count=len(expected),
        actual_count=len(actual),
        mismatches=tuple(mismatches),
    )
