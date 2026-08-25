import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from straddle_replica.cli import main


REPORT_PATH = Path(r"D:\Downloads\ReportHistory-901018.xlsx")
RECENT_REPORT_PATH = Path(r"D:\Downloads\ReportHistory-last2days.xlsx")


def test_export_report_cli_writes_golden_dataset_and_summary(tmp_path):
    output_dir = tmp_path / "golden"

    exit_code = main(
        [
            "export-report",
            "--input",
            str(REPORT_PATH),
            "--output",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["total_trades"] == 17_638
    assert summary["deployments"] == 284


def test_calibrate_cli_writes_profile_results(tmp_path):
    output = tmp_path / "calibration.json"

    exit_code = main(
        [
            "calibrate",
            "--input",
            str(REPORT_PATH),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    calibration = json.loads(output.read_text(encoding="utf-8"))
    assert calibration["LATEST_30"]["count"] == 103
    assert abs(calibration["LATEST_30"]["anchor_divisor"] - 3000) <= 5


import pytest

@pytest.mark.skipif(not RECENT_REPORT_PATH.exists(), reason="Requires RECENT_REPORT_PATH fixture")
def test_compare_geometry_cli_can_include_rearmed_orders(tmp_path):
    output = tmp_path / "recent-geometry.json"

    exit_code = main(
        [
            "compare-geometry",
            "--input",
            str(RECENT_REPORT_PATH),
            "--output",
            str(output),
            "--include-rearms",
        ]
    )

    assert exit_code == 1
    comparison = json.loads(output.read_text(encoding="utf-8"))
    assert comparison["grid_orders"] == 1_623
    assert comparison["compared_orders"] == 1_582
    assert comparison["skipped_without_cycle"] == 41
    assert comparison["mismatches"] == []


def test_audit_ticks_cli_writes_complete_archive_manifest(tmp_path):
    start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    end = start + timedelta(hours=12)
    stem = "XAUUSD_20260701_0000_20260701_1200.csv"
    (tmp_path / f"{stem}.gz").write_bytes(b"placeholder")
    (tmp_path / f"{stem}.coverage.json").write_text(
        json.dumps(
            {
                "count": 12,
                "first_time": start.isoformat(),
                "last_time": (end - timedelta(seconds=1)).isoformat(),
                "large_gap_count": 0,
                "maximum_gap_seconds": 1.0,
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "archive.json"

    exit_code = main(
        [
            "audit-ticks",
            "--input",
            str(tmp_path),
            "--symbol",
            "XAUUSD",
            "--start",
            start.isoformat(),
            "--end",
            end.isoformat(),
            "--segment-hours",
            "12",
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    audit = json.loads(output.read_text(encoding="utf-8"))
    assert audit["is_complete"] is True
    assert audit["total_ticks"] == 12


@pytest.mark.skipif(not RECENT_REPORT_PATH.exists(), reason="Requires RECENT_REPORT_PATH fixture")
def test_compare_tester_cli_writes_aligned_lifecycle_summary(tmp_path):
    tester_report = tmp_path / "tester.htm"
    tester_report.write_text(
        """
        <html><body><table>
        <tr><th><b>Orders</b></th></tr>
        <tr><th><b>Deals</b></th></tr>
        <tr>
          <td>2026.07.30 00:05:47</td><td>2</td><td>XAUUSD</td>
          <td>sell</td><td>in</td><td>0.01</td><td>4071.88</td>
          <td>3</td><td>0.00</td><td>0.00</td><td>0.00</td>
          <td>19280.00</td><td>STR S1</td>
        </tr>
        </table></body></html>
        """,
        encoding="utf-16",
    )
    output = tmp_path / "comparison.json"

    exit_code = main(
        [
            "compare-tester",
            "--report",
            str(RECENT_REPORT_PATH),
            "--tester",
            str(tester_report),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 1
    comparison = json.loads(output.read_text(encoding="utf-8"))
    assert comparison["report_fills"] == 602
    assert comparison["tester_fills"] == 1
    assert comparison["fill_alignment"]["matched_count"] == 1


@pytest.mark.skipif(not RECENT_REPORT_PATH.exists(), reason="Requires RECENT_REPORT_PATH fixture")
def test_compare_telemetry_cli_writes_position_level_alignment(tmp_path):
    telemetry = tmp_path / "telemetry.csv"
    telemetry.write_text(
        "time,kind,comment,side,volume,price,state,level,ticket\n"
        "2026-07-30T00:05:47Z,fill,STR S1,sell,0.01,4071.80,"
        "CYCLE_RUNNING,STR S1,1\n",
        encoding="utf-8",
    )
    output = tmp_path / "telemetry-comparison.json"

    exit_code = main(
        [
            "compare-telemetry",
            "--report",
            str(RECENT_REPORT_PATH),
            "--telemetry",
            str(telemetry),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 1
    comparison = json.loads(output.read_text(encoding="utf-8"))
    assert comparison["expected_count"] == 1_200
    assert comparison["actual_count"] == 1
    assert comparison["matched_count"] == 1
