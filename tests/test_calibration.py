from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from straddle_replica.calibration import (
    AnchorObservation,
    calibrate_anchor_model,
    calibrate_deployments,
    infer_anchor_divisor,
    select_anchor_deployments,
    split_train_validation,
)
from straddle_replica.report import parse_mt5_report
from straddle_replica.ticks import TickSample


REPORT_PATH = Path(r"D:\Downloads\ReportHistory-901018.xlsx")
RECENT_REPORT_PATH = Path(r"D:\Downloads\ReportHistory-last2days.xlsx")


def test_infers_anchor_divisor_after_tick_rounding():
    observations = [
        (4025.34, 1.34),
        (4091.80, 1.36),
        (4104.83, 1.37),
        (4142.43, 1.38),
    ]

    result = infer_anchor_divisor(observations, tick_size=0.01)

    assert result.divisor == pytest.approx(3000.0, abs=5.0)
    assert result.maximum_tick_error <= 1


def test_split_is_chronological_and_70_30():
    values = list(range(10))
    training, validation = split_train_validation(values, training_fraction=0.7)

    assert training == list(range(7))
    assert validation == list(range(7, 10))


def test_calibrates_observed_report_profile_families():
    report = parse_mt5_report(REPORT_PATH)

    result = calibrate_deployments(report.deployments, tick_size=0.01)

    assert result["LATEST_30"].count == 103
    assert result["LATEST_30"].anchor_divisor == pytest.approx(3000.0, abs=5.0)
    assert result["AGGRESSIVE_30"].count == 2
    assert result["AGGRESSIVE_30"].anchor_divisor == pytest.approx(6000.0, abs=10.0)
    assert result["HISTORICAL_50"].median_step == pytest.approx(1.0)
    assert result["HISTORICAL_60"].median_step == pytest.approx(0.5)


def test_anchor_model_selects_offset_and_midpoint_on_holdout():
    observations = []
    ticks = []
    for index in range(10):
        server_time = datetime(2026, 7, 1, 12, index)
        utc_time = (server_time - timedelta(hours=3)).replace(
            tzinfo=timezone.utc
        )
        bid = 4100.0 + index
        ask = bid + 0.2
        observations.append(AnchorObservation(server_time, bid + 0.1))
        ticks.extend(
            [
                TickSample(
                    utc_time - timedelta(milliseconds=50),
                    bid - 0.3,
                    ask - 0.3,
                ),
                TickSample(utc_time, bid, ask),
            ]
        )

    result = calibrate_anchor_model(
        observations,
        ticks,
        tick_size=0.01,
        offset_hours=(-1, 0, 3),
        lookback_seconds=0.1,
        lookahead_seconds=0.1,
    )

    assert result.selected_offset_hours == 3
    assert result.selected_source == "midpoint"
    assert result.training_count == 7
    assert result.validation_count == 3
    assert result.training_maximum_tick_error == 0
    assert result.validation_maximum_tick_error == 0
    assert len(result.residuals) == 10
    assert all(residual.tick_error == 0 for residual in result.residuals)


def test_anchor_calibration_excludes_incomplete_deployments():
    report = parse_mt5_report(REPORT_PATH)

    selected = select_anchor_deployments(
        report.deployments, minimum_order_coverage=0.9
    )

    assert len(report.deployments) == 284
    assert len(selected) == 282
    assert all(
        deployment.initial_order_count
        >= 0.9 * deployment.levels_per_side * 2
        for deployment in selected
    )


import pytest

@pytest.mark.skipif(not RECENT_REPORT_PATH.exists(), reason="Requires RECENT_REPORT_PATH fixture")
def test_recent_anchor_selection_excludes_partial_30_level_deployment():
    report = parse_mt5_report(RECENT_REPORT_PATH)

    selected = select_anchor_deployments(
        report.deployments, minimum_order_coverage=0.9
    )

    assert len(report.deployments) == 22
    assert len(selected) == 21
    assert all(
        deployment.start.isoformat(sep=" ")
        != "2026-07-30 15:46:33.118000"
        for deployment in selected
    )
