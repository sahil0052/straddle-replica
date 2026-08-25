from datetime import datetime, timedelta, timezone

import pytest

from straddle_replica.ticks import TickSample
from straddle_replica.volatility import (
    ATRModelSpec,
    StepFeatureRow,
    StepObservation,
    calibrate_atr_spacing,
    extract_atr_features,
)


UTC = timezone.utc


def test_extracts_current_bar_atr_at_observation_time():
    start = datetime(2026, 7, 1, tzinfo=UTC)
    ticks = [
        TickSample(start, 100.0, 100.2),
        TickSample(start + timedelta(seconds=30), 101.0, 101.2),
        TickSample(start + timedelta(minutes=1), 102.0, 102.2),
        TickSample(start + timedelta(minutes=1, seconds=30), 103.0, 103.2),
        TickSample(start + timedelta(minutes=2), 104.0, 104.2),
        TickSample(start + timedelta(minutes=2, seconds=30), 105.0, 105.2),
    ]
    observation = StepObservation(
        time=start + timedelta(minutes=2, seconds=30),
        profile="HISTORICAL_50",
        step=0.2,
    )
    spec = ATRModelSpec(timeframe_minutes=1, period=2, closed_bar=False)

    rows = extract_atr_features(
        [observation],
        ticks,
        timeframes=(1,),
        periods=(2,),
    )

    assert len(rows) == 1
    assert rows[0].values[spec] == pytest.approx(2.0)


def test_selects_atr_model_on_training_and_accepts_holdout_improvement():
    good = ATRModelSpec(timeframe_minutes=15, period=17, closed_bar=False)
    bad = ATRModelSpec(timeframe_minutes=5, period=2, closed_bar=True)
    rows = []
    start = datetime(2026, 7, 1, tzinfo=UTC)
    for index in range(10):
        atr = 10.0 + index
        rows.append(
            StepFeatureRow(
                observation=StepObservation(
                    time=start + timedelta(minutes=index),
                    profile="HISTORICAL_50",
                    step=round(atr * 0.1, 2),
                ),
                values={good: atr, bad: 1.0},
            )
        )

    result = calibrate_atr_spacing(rows, tick_size=0.01)
    fit = result["HISTORICAL_50"]

    assert fit.spec == good
    assert fit.multiplier == pytest.approx(0.1, abs=0.001)
    assert fit.training_count == 7
    assert fit.validation_count == 3
    assert fit.validation_mean_tick_error == 0
    assert fit.accepted
