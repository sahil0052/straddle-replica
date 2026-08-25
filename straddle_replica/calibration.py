from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta
from math import inf
from typing import Iterable, Sequence, TypeVar

from .profiles import normalize_price
from .report import DeploymentRecord
from .ticks import TickSample, server_time_to_utc


T = TypeVar("T")


@dataclass(frozen=True)
class DivisorFit:
    divisor: float
    maximum_tick_error: int
    mean_tick_error: float


@dataclass(frozen=True)
class ProfileCalibration:
    profile: str
    count: int
    median_step: float
    minimum_step: float
    maximum_step: float
    anchor_divisor: float | None
    maximum_tick_error: int | None


@dataclass(frozen=True)
class AnchorObservation:
    server_time: datetime
    anchor: float
    label: str = ""


@dataclass(frozen=True)
class AnchorCandidateScore:
    offset_hours: int
    source: str
    training_missing: int
    validation_missing: int
    training_mean_tick_error: float | None
    validation_mean_tick_error: float | None
    training_maximum_tick_error: int | None
    validation_maximum_tick_error: int | None


@dataclass(frozen=True)
class AnchorResidual:
    observation_index: int
    server_time: datetime
    label: str
    anchor: float
    matched_tick_time: datetime | None
    matched_price: float | None
    price_error: float | None
    tick_error: int | None
    is_training: bool


@dataclass(frozen=True)
class AnchorCalibration:
    selected_offset_hours: int
    selected_source: str
    training_count: int
    validation_count: int
    training_missing: int
    validation_missing: int
    training_mean_tick_error: float | None
    validation_mean_tick_error: float | None
    training_maximum_tick_error: int | None
    validation_maximum_tick_error: int | None
    candidates: tuple[AnchorCandidateScore, ...]
    residuals: tuple[AnchorResidual, ...]


@dataclass
class _AnchorQuery:
    observation_index: int
    offset_hours: int
    start: datetime
    end: datetime
    anchor: float
    best_errors: dict[str, float]
    best_matches: dict[str, tuple[datetime, float] | None]


def split_train_validation(
    values: Sequence[T], training_fraction: float = 0.7
) -> tuple[list[T], list[T]]:
    if not 0 < training_fraction < 1:
        raise ValueError("Training fraction must be between zero and one")
    split_at = int(len(values) * training_fraction)
    return list(values[:split_at]), list(values[split_at:])


def _error_metrics(
    values: Sequence[float], tick_size: float
) -> tuple[int, float | None, int | None]:
    finite = [value for value in values if value != inf]
    missing = len(values) - len(finite)
    if not finite:
        return missing, None, None
    tick_errors = [value / tick_size for value in finite]
    return (
        missing,
        statistics.fmean(tick_errors),
        round(max(tick_errors)),
    )


def select_anchor_deployments(
    deployments: Sequence[DeploymentRecord],
    minimum_order_coverage: float = 0.9,
) -> list[DeploymentRecord]:
    if not 0 < minimum_order_coverage <= 1:
        raise ValueError("Minimum order coverage must be in (0, 1]")
    return [
        deployment
        for deployment in deployments
        if deployment.initial_order_count
        >= minimum_order_coverage * deployment.levels_per_side * 2
    ]


def calibrate_anchor_model(
    observations: Sequence[AnchorObservation],
    ticks: Iterable[TickSample],
    tick_size: float,
    offset_hours: Sequence[int] = tuple(range(-14, 15)),
    lookback_seconds: float = 2.0,
    lookahead_seconds: float = 0.5,
    training_fraction: float = 0.7,
) -> AnchorCalibration:
    if len(observations) < 2:
        raise ValueError("At least two anchor observations are required")
    if tick_size <= 0:
        raise ValueError("Tick size must be positive")
    if not offset_hours:
        raise ValueError("At least one offset candidate is required")
    if lookback_seconds < 0 or lookahead_seconds < 0:
        raise ValueError("Calibration windows cannot be negative")
    if not 0 < training_fraction < 1:
        raise ValueError("Training fraction must be between zero and one")

    sources = ("bid", "ask", "midpoint", "last")
    queries: list[_AnchorQuery] = []
    query_lookup: dict[tuple[int, int], _AnchorQuery] = {}
    for observation_index, observation in enumerate(observations):
        if observation.anchor <= 0:
            raise ValueError("Observed anchors must be positive")
        for offset in offset_hours:
            center = server_time_to_utc(
                observation.server_time, timedelta(hours=offset)
            )
            query = _AnchorQuery(
                observation_index=observation_index,
                offset_hours=offset,
                start=center - timedelta(seconds=lookback_seconds),
                end=center + timedelta(seconds=lookahead_seconds),
                anchor=observation.anchor,
                best_errors={source: inf for source in sources},
                best_matches={source: None for source in sources},
            )
            queries.append(query)
            query_lookup[(observation_index, offset)] = query

    queries.sort(key=lambda query: query.start)
    active: list[_AnchorQuery] = []
    query_index = 0
    last_tick_time: datetime | None = None
    final_query_end = max(query.end for query in queries)
    saw_tick = False
    for tick in ticks:
        saw_tick = True
        if tick.time.tzinfo is None:
            raise ValueError("Tick timestamps must be timezone-aware")
        if last_tick_time is not None and tick.time < last_tick_time:
            raise ValueError("Ticks must be in chronological order")
        last_tick_time = tick.time
        if tick.time > final_query_end and query_index == len(queries):
            break
        while (
            query_index < len(queries)
            and queries[query_index].start <= tick.time
        ):
            active.append(queries[query_index])
            query_index += 1
        active = [query for query in active if query.end >= tick.time]
        if not active:
            continue

        prices = {
            "bid": tick.bid,
            "ask": tick.ask,
            "midpoint": (tick.bid + tick.ask) / 2,
            "last": tick.last,
        }
        for query in active:
            for source, price in prices.items():
                if price <= 0:
                    continue
                error = abs(price - query.anchor)
                if error < query.best_errors[source]:
                    query.best_errors[source] = error
                    query.best_matches[source] = (tick.time, price)
    if not saw_tick:
        raise ValueError("Tick samples are required")

    split_at = int(len(observations) * training_fraction)
    split_at = max(1, min(len(observations) - 1, split_at))
    candidate_scores: list[AnchorCandidateScore] = []
    source_priority = {"midpoint": 0, "bid": 1, "ask": 2, "last": 3}
    selection: tuple[tuple[float, ...], AnchorCandidateScore] | None = None
    for offset in offset_hours:
        for source in sources:
            errors = [
                query_lookup[(index, offset)].best_errors[source]
                for index in range(len(observations))
            ]
            train_metrics = _error_metrics(errors[:split_at], tick_size)
            validation_metrics = _error_metrics(errors[split_at:], tick_size)
            candidate = AnchorCandidateScore(
                offset_hours=offset,
                source=source,
                training_missing=train_metrics[0],
                validation_missing=validation_metrics[0],
                training_mean_tick_error=train_metrics[1],
                validation_mean_tick_error=validation_metrics[1],
                training_maximum_tick_error=train_metrics[2],
                validation_maximum_tick_error=validation_metrics[2],
            )
            candidate_scores.append(candidate)
            training_mean = (
                candidate.training_mean_tick_error
                if candidate.training_mean_tick_error is not None
                else inf
            )
            training_maximum = (
                float(candidate.training_maximum_tick_error)
                if candidate.training_maximum_tick_error is not None
                else inf
            )
            score = (
                float(candidate.training_missing),
                training_mean,
                training_maximum,
                float(source_priority[source]),
                float(abs(offset)),
                float(offset),
            )
            if selection is None or score < selection[0]:
                selection = (score, candidate)

    assert selection is not None
    selected = selection[1]
    residuals: list[AnchorResidual] = []
    for index, observation in enumerate(observations):
        query = query_lookup[(index, selected.offset_hours)]
        error = query.best_errors[selected.source]
        match = query.best_matches[selected.source]
        residuals.append(
            AnchorResidual(
                observation_index=index,
                server_time=observation.server_time,
                label=observation.label,
                anchor=observation.anchor,
                matched_tick_time=match[0] if match else None,
                matched_price=match[1] if match else None,
                price_error=None if error == inf else error,
                tick_error=(
                    None if error == inf else round(error / tick_size)
                ),
                is_training=index < split_at,
            )
        )
    return AnchorCalibration(
        selected_offset_hours=selected.offset_hours,
        selected_source=selected.source,
        training_count=split_at,
        validation_count=len(observations) - split_at,
        training_missing=selected.training_missing,
        validation_missing=selected.validation_missing,
        training_mean_tick_error=selected.training_mean_tick_error,
        validation_mean_tick_error=selected.validation_mean_tick_error,
        training_maximum_tick_error=selected.training_maximum_tick_error,
        validation_maximum_tick_error=selected.validation_maximum_tick_error,
        candidates=tuple(candidate_scores),
        residuals=tuple(residuals),
    )


def infer_anchor_divisor(
    observations: Sequence[tuple[float, float]], tick_size: float
) -> DivisorFit:
    if not observations:
        raise ValueError("At least one observation is required")
    raw_ratios = [anchor / step for anchor, step in observations if step > 0]
    if len(raw_ratios) != len(observations):
        raise ValueError("All anchors and steps must be positive")
    center = statistics.median(raw_ratios)

    candidates = [
        center + offset / 10
        for offset in range(-500, 501)
        if center + offset / 10 > 0
    ]
    best: tuple[int, float, float, float] | None = None
    for divisor in candidates:
        errors = [
            round(
                abs(normalize_price(anchor / divisor, tick_size) - observed_step)
                / tick_size
            )
            for anchor, observed_step in observations
        ]
        round_number_penalty = abs(divisor - round(divisor / 100) * 100)
        score = (
            max(errors),
            statistics.fmean(errors),
            round_number_penalty,
            abs(divisor - center),
        )
        if best is None or score < (
            best[0],
            best[1],
            best[2],
            abs(best[3] - center),
        ):
            best = (score[0], score[1], score[2], divisor)
    assert best is not None
    return DivisorFit(
        divisor=best[3],
        maximum_tick_error=best[0],
        mean_tick_error=best[1],
    )


def calibrate_deployments(
    deployments: Sequence[DeploymentRecord], tick_size: float
) -> dict[str, ProfileCalibration]:
    grouped: dict[str, list[DeploymentRecord]] = {}
    for deployment in deployments:
        grouped.setdefault(deployment.profile_hint, []).append(deployment)

    result: dict[str, ProfileCalibration] = {}
    for profile, items in grouped.items():
        steps = [item.step for item in items]
        divisor_fit: DivisorFit | None = None
        if profile in {"LATEST_30", "LOW_RISK_30", "AGGRESSIVE_30"}:
            divisor_fit = infer_anchor_divisor(
                [(item.anchor, item.step) for item in items],
                tick_size=tick_size,
            )
        result[profile] = ProfileCalibration(
            profile=profile,
            count=len(items),
            median_step=statistics.median(steps),
            minimum_step=min(steps),
            maximum_step=max(steps),
            anchor_divisor=divisor_fit.divisor if divisor_fit else None,
            maximum_tick_error=(
                divisor_fit.maximum_tick_error if divisor_fit else None
            ),
        )
    return result
