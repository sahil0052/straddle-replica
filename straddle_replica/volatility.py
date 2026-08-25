from __future__ import annotations

import statistics
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Sequence

from .profiles import normalize_price
from .ticks import TickSample


@dataclass(frozen=True, order=True)
class ATRModelSpec:
    timeframe_minutes: int
    period: int
    closed_bar: bool


@dataclass(frozen=True)
class StepObservation:
    time: datetime
    profile: str
    step: float


@dataclass(frozen=True)
class StepFeatureRow:
    observation: StepObservation
    values: dict[ATRModelSpec, float]


@dataclass(frozen=True)
class ATRModelCandidate:
    spec: ATRModelSpec
    multiplier: float
    training_mean_tick_error: float
    training_maximum_tick_error: int
    validation_mean_tick_error: float
    validation_maximum_tick_error: int


@dataclass(frozen=True)
class SpacingProfileCalibration:
    profile: str
    spec: ATRModelSpec
    multiplier: float
    training_count: int
    validation_count: int
    training_mean_tick_error: float
    training_maximum_tick_error: int
    validation_mean_tick_error: float
    validation_maximum_tick_error: int
    validation_exact_fraction: float
    baseline_fixed_step: float
    baseline_validation_mean_tick_error: float
    baseline_validation_maximum_tick_error: int
    accepted: bool
    candidates: tuple[ATRModelCandidate, ...]


@dataclass
class _ATRState:
    timeframe_minutes: int
    maximum_period: int
    bucket: datetime | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    previous_close: float | None = None

    def __post_init__(self) -> None:
        self.true_ranges: deque[float] = deque(maxlen=self.maximum_period)

    def _bucket_for(self, value: datetime) -> datetime:
        return value.replace(
            minute=(value.minute // self.timeframe_minutes)
            * self.timeframe_minutes,
            second=0,
            microsecond=0,
        )

    def update(self, time: datetime, price: float) -> None:
        bucket = self._bucket_for(time)
        if self.bucket is None:
            self.bucket = bucket
            self.high = price
            self.low = price
            self.close = price
            return
        if bucket != self.bucket:
            self.true_ranges.append(self.current_true_range())
            self.previous_close = self.close
            self.bucket = bucket
            self.high = price
            self.low = price
            self.close = price
            return
        assert self.high is not None and self.low is not None
        self.high = max(self.high, price)
        self.low = min(self.low, price)
        self.close = price

    def current_true_range(self) -> float:
        if self.high is None or self.low is None:
            raise ValueError("ATR state has no current bar")
        if self.previous_close is None:
            return self.high - self.low
        return max(
            self.high - self.low,
            abs(self.high - self.previous_close),
            abs(self.low - self.previous_close),
        )

    def features(
        self, periods: Sequence[int]
    ) -> dict[ATRModelSpec, float]:
        if self.bucket is None:
            return {}
        completed = list(self.true_ranges)
        current = self.current_true_range()
        result: dict[ATRModelSpec, float] = {}
        for period in periods:
            if len(completed) >= period - 1:
                result[
                    ATRModelSpec(self.timeframe_minutes, period, False)
                ] = statistics.fmean(completed[-(period - 1) :] + [current])
            if len(completed) >= period:
                result[
                    ATRModelSpec(self.timeframe_minutes, period, True)
                ] = statistics.fmean(completed[-period:])
        return result


def extract_atr_features(
    observations: Sequence[StepObservation],
    ticks: Iterable[TickSample],
    timeframes: Sequence[int] = (5, 15, 30),
    periods: Sequence[int] = tuple(range(2, 81)),
) -> list[StepFeatureRow]:
    if not observations:
        raise ValueError("Step observations are required")
    if not timeframes or any(value <= 0 or value > 60 for value in timeframes):
        raise ValueError("Timeframes must be between 1 and 60 minutes")
    if not periods or any(value < 2 for value in periods):
        raise ValueError("ATR periods must be at least two")
    ordered_observations = sorted(observations, key=lambda item: item.time)
    if any(item.time.tzinfo is None for item in ordered_observations):
        raise ValueError("Observation timestamps must be timezone-aware")
    ordered_periods = tuple(sorted(set(periods)))
    states = {
        timeframe: _ATRState(timeframe, max(ordered_periods))
        for timeframe in sorted(set(timeframes))
    }
    rows: list[StepFeatureRow] = []
    observation_index = 0
    last_tick_time: datetime | None = None

    def append_observation() -> None:
        nonlocal observation_index
        observation = ordered_observations[observation_index]
        values: dict[ATRModelSpec, float] = {}
        for state in states.values():
            values.update(state.features(ordered_periods))
        rows.append(StepFeatureRow(observation, values))
        observation_index += 1

    for tick in ticks:
        if tick.time.tzinfo is None:
            raise ValueError("Tick timestamps must be timezone-aware")
        if last_tick_time is not None and tick.time < last_tick_time:
            raise ValueError("Ticks must be in chronological order")
        last_tick_time = tick.time

        while (
            observation_index < len(ordered_observations)
            and ordered_observations[observation_index].time < tick.time
        ):
            append_observation()
        for state in states.values():
            state.update(tick.time, tick.bid)
        while (
            observation_index < len(ordered_observations)
            and ordered_observations[observation_index].time == tick.time
        ):
            append_observation()
        if observation_index == len(ordered_observations):
            break

    while observation_index < len(ordered_observations):
        append_observation()
    return rows


def _weighted_median_multiplier(
    features: Sequence[float], targets: Sequence[float]
) -> float:
    weighted = sorted(
        (target / feature, feature)
        for feature, target in zip(features, targets)
        if feature > 0
    )
    if len(weighted) != len(features) or not weighted:
        raise ValueError("ATR features must be positive")
    threshold = sum(weight for _, weight in weighted) / 2
    cumulative = 0.0
    for ratio, weight in weighted:
        cumulative += weight
        if cumulative >= threshold:
            return ratio
    return weighted[-1][0]


def _tick_errors(
    features: Sequence[float],
    targets: Sequence[float],
    multiplier: float,
    tick_size: float,
) -> list[int]:
    return [
        round(
            abs(normalize_price(feature * multiplier, tick_size) - target)
            / tick_size
        )
        for feature, target in zip(features, targets)
    ]


def _metrics(errors: Sequence[int]) -> tuple[float, int, float]:
    if not errors:
        raise ValueError("Error samples are required")
    return (
        statistics.fmean(errors),
        max(errors),
        sum(error == 0 for error in errors) / len(errors),
    )


def _refine_multiplier(
    features: Sequence[float],
    targets: Sequence[float],
    initial: float,
    tick_size: float,
) -> float:
    from scipy.optimize import minimize_scalar

    lower = max(initial * 0.8, 1e-9)
    upper = initial * 1.2
    result = minimize_scalar(
        lambda multiplier: statistics.fmean(
            abs(feature * multiplier - target)
            for feature, target in zip(features, targets)
        ),
        bounds=(lower, upper),
        method="bounded",
    )
    center = float(result.x if result.success else initial)
    candidates = [
        center * (0.98 + index * 0.04 / 800)
        for index in range(801)
    ]
    return min(
        candidates,
        key=lambda multiplier: (
            statistics.fmean(
                _tick_errors(
                    features, targets, multiplier, tick_size
                )
            ),
            max(_tick_errors(features, targets, multiplier, tick_size)),
            abs(multiplier - center),
        ),
    )


def calibrate_atr_spacing(
    rows: Sequence[StepFeatureRow],
    tick_size: float,
    training_fraction: float = 0.7,
) -> dict[str, SpacingProfileCalibration]:
    if not rows:
        raise ValueError("ATR feature rows are required")
    if tick_size <= 0:
        raise ValueError("Tick size must be positive")
    if not 0 < training_fraction < 1:
        raise ValueError("Training fraction must be between zero and one")

    grouped: dict[str, list[StepFeatureRow]] = {}
    for row in sorted(rows, key=lambda item: item.observation.time):
        grouped.setdefault(row.observation.profile, []).append(row)

    result: dict[str, SpacingProfileCalibration] = {}
    for profile, profile_rows in grouped.items():
        if len(profile_rows) < 2:
            raise ValueError(f"Profile {profile} needs at least two rows")
        split_at = int(len(profile_rows) * training_fraction)
        split_at = max(1, min(len(profile_rows) - 1, split_at))
        training = profile_rows[:split_at]
        validation = profile_rows[split_at:]
        specs = set.intersection(*(set(row.values) for row in profile_rows))
        if not specs:
            raise ValueError(f"Profile {profile} has no common ATR features")

        candidates: list[ATRModelCandidate] = []
        for spec in sorted(specs):
            train_features = [row.values[spec] for row in training]
            train_targets = [row.observation.step for row in training]
            validation_features = [row.values[spec] for row in validation]
            validation_targets = [
                row.observation.step for row in validation
            ]
            multiplier = _weighted_median_multiplier(
                train_features, train_targets
            )
            train_metrics = _metrics(
                _tick_errors(
                    train_features,
                    train_targets,
                    multiplier,
                    tick_size,
                )
            )
            validation_metrics = _metrics(
                _tick_errors(
                    validation_features,
                    validation_targets,
                    multiplier,
                    tick_size,
                )
            )
            candidates.append(
                ATRModelCandidate(
                    spec=spec,
                    multiplier=multiplier,
                    training_mean_tick_error=train_metrics[0],
                    training_maximum_tick_error=train_metrics[1],
                    validation_mean_tick_error=validation_metrics[0],
                    validation_maximum_tick_error=validation_metrics[1],
                )
            )

        selected = min(
            candidates,
            key=lambda candidate: (
                candidate.training_mean_tick_error,
                candidate.training_maximum_tick_error,
                candidate.spec,
            ),
        )
        train_features = [row.values[selected.spec] for row in training]
        train_targets = [row.observation.step for row in training]
        validation_features = [
            row.values[selected.spec] for row in validation
        ]
        validation_targets = [
            row.observation.step for row in validation
        ]
        multiplier = _refine_multiplier(
            train_features,
            train_targets,
            selected.multiplier,
            tick_size,
        )
        training_metrics = _metrics(
            _tick_errors(
                train_features, train_targets, multiplier, tick_size
            )
        )
        validation_metrics = _metrics(
            _tick_errors(
                validation_features,
                validation_targets,
                multiplier,
                tick_size,
            )
        )

        baseline = normalize_price(
            statistics.median(train_targets), tick_size
        )
        baseline_errors = [
            round(abs(baseline - target) / tick_size)
            for target in validation_targets
        ]
        baseline_metrics = _metrics(baseline_errors)
        accepted = (
            validation_metrics[0] < baseline_metrics[0]
            and validation_metrics[1] <= baseline_metrics[1]
        )
        result[profile] = SpacingProfileCalibration(
            profile=profile,
            spec=selected.spec,
            multiplier=multiplier,
            training_count=len(training),
            validation_count=len(validation),
            training_mean_tick_error=training_metrics[0],
            training_maximum_tick_error=training_metrics[1],
            validation_mean_tick_error=validation_metrics[0],
            validation_maximum_tick_error=validation_metrics[1],
            validation_exact_fraction=validation_metrics[2],
            baseline_fixed_step=baseline,
            baseline_validation_mean_tick_error=baseline_metrics[0],
            baseline_validation_maximum_tick_error=baseline_metrics[1],
            accepted=accepted,
            candidates=tuple(
                sorted(
                    candidates,
                    key=lambda candidate: (
                        candidate.training_mean_tick_error,
                        candidate.training_maximum_tick_error,
                        candidate.spec,
                    ),
                )
            ),
        )
    return result
