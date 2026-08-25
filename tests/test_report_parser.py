from pathlib import Path

import pytest

from straddle_replica.report import export_golden_dataset, parse_mt5_report


REPORT_PATH = Path(r"D:\Downloads\ReportHistory-901018.xlsx")
RECENT_REPORT_PATH = Path(r"D:\Downloads\ReportHistory-last2days.xlsx")


@pytest.fixture(scope="module")
def report():
    assert REPORT_PATH.exists(), f"Missing source report: {REPORT_PATH}"
    return parse_mt5_report(REPORT_PATH)


@pytest.fixture(scope="module")
def recent_report():
    if not RECENT_REPORT_PATH.exists():
        pytest.skip(f"Missing recent source report: {RECENT_REPORT_PATH}")
    return parse_mt5_report(RECENT_REPORT_PATH)


def test_extracts_authoritative_report_counts(report):
    assert report.metadata["name"] == "Straddle"
    assert report.metadata["account"].startswith("901018")
    assert len(report.closed_positions) == 17_632
    assert len(report.open_positions) == 6
    assert len(report.historical_orders) == 54_742
    assert len(report.working_orders) == 51
    assert len(report.deals) == 35_446
    assert report.total_trades == 17_638


def test_detects_observed_grid_deployments(report):
    assert len(report.deployments) == 284
    first = report.deployments[0]
    assert first.levels_per_side == 50
    assert first.anchor == pytest.approx(4136.94)
    assert first.step == pytest.approx(1.10)
    assert first.first_gap / first.step == pytest.approx(2.0)

    latest = report.deployments[-1]
    assert latest.start.isoformat(sep=" ") == "2026-07-30 17:12:09.286000"
    assert latest.levels_per_side == 30
    assert latest.step == pytest.approx(1.36)
    assert latest.profile_hint == "LATEST_30"


def test_merges_delayed_deployment_fragments(report):
    deployment = next(
        item
        for item in report.deployments
        if item.start.isoformat(sep=" ") == "2026-07-30 06:46:38.559000"
    )

    assert deployment.end.isoformat(sep=" ") == "2026-07-30 06:47:04.472000"
    assert deployment.initial_order_count == 60
    assert deployment.anchor == pytest.approx(4050.29)
    assert deployment.step == pytest.approx(1.35)


def test_detects_deployment_spanning_history_and_working_orders(recent_report):
    assert len(recent_report.deployments) == 22

    latest = recent_report.deployments[-1]
    assert latest.start.isoformat(sep=" ") == "2026-07-31 22:37:16.193000"
    assert latest.end.isoformat(sep=" ") == "2026-07-31 22:37:22.535000"
    assert latest.initial_order_count == 60
    assert latest.anchor == pytest.approx(4051.19)
    assert latest.step == pytest.approx(1.35)


def test_partial_latest_deployment_keeps_expected_30_level_profile(recent_report):
    deployment = next(
        item
        for item in recent_report.deployments
        if item.start.isoformat(sep=" ")
        == "2026-07-30 15:46:33.118000"
    )

    assert deployment.initial_order_count == 51
    assert deployment.levels_per_side == 30
    assert deployment.profile_hint == "LATEST_30"


def test_exports_canonical_golden_csv_files(report, tmp_path):
    output = export_golden_dataset(report, tmp_path)

    assert output["positions"].exists()
    assert output["orders"].exists()
    assert output["deals"].exists()
    assert output["deployments"].exists()
    assert sum(1 for _ in output["positions"].open(encoding="utf-8")) == 17_633
    assert sum(1 for _ in output["orders"].open(encoding="utf-8")) == 54_743
    assert sum(1 for _ in output["deals"].open(encoding="utf-8")) == 35_447
    assert sum(1 for _ in output["deployments"].open(encoding="utf-8")) == 285
