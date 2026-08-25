from pathlib import Path

from straddle_replica.geometry import compare_report_grid_geometry
from straddle_replica.report import parse_mt5_report


REPORT_PATH = Path(r"D:\Downloads\ReportHistory-901018.xlsx")
RECENT_REPORT_PATH = Path(r"D:\Downloads\ReportHistory-last2days.xlsx")


def test_report_grid_orders_match_inferred_cycle_geometry_and_lot_tiers():
    report = parse_mt5_report(REPORT_PATH)

    result = compare_report_grid_geometry(report, tick_size=0.01)

    assert result.grid_orders == 37_047
    assert result.compared_orders == 25_614
    assert result.skipped_without_cycle == 0
    assert result.mismatches == ()
    assert result.is_match


import pytest

@pytest.mark.skipif(not RECENT_REPORT_PATH.exists(), reason="Requires RECENT_REPORT_PATH fixture")
def test_recent_report_rearms_and_working_orders_match_cycle_geometry():
    report = parse_mt5_report(RECENT_REPORT_PATH)

    result = compare_report_grid_geometry(
        report, tick_size=0.01, include_rearms=True
    )

    assert result.grid_orders == 1_623
    assert result.compared_orders == 1_582
    assert result.skipped_without_cycle == 41
    assert result.mismatches == ()
    assert not result.is_match
