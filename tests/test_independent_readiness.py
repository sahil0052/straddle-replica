from datetime import datetime, timedelta, timezone
import csv
import json
from pathlib import Path

import pytest

from straddle_replica.independent_readiness import (
    evaluate_independent_readiness,
)


UTC = timezone.utc
LOGIN = 5_054_999_999


def write_heartbeat(
    path: Path,
    now: datetime,
    *,
    read_only: bool = True,
    dropped: int = 0,
) -> None:
    path.write_text(
        json.dumps(
            {
                "capture_time_utc": now.isoformat(),
                "healthy": True,
                "stopped": False,
                "read_only_verified": read_only,
                "dropped_transactions": dropped,
            }
        ),
        encoding="utf-8",
    )


def write_manifest(
    path: Path,
    *,
    runtime_mode: str = "0",
    login: int = LOGIN,
) -> None:
    rows = {
        "runtime_mode": runtime_mode,
        "runtime_magic": "901018",
        "runtime_require_demo_account": "1",
        "runtime_expected_account_login": str(login),
        "profile": "4",
        "profile_levels_per_side": "30",
    }
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("key", "value"))
        writer.writerows(rows.items())


def write_telemetry(
    path: Path,
    now: datetime,
    *,
    slots: int = 60,
) -> None:
    fields = (
        "utc_time",
        "cycle_id",
        "kind",
        "comment",
        "retcode",
    )
    rows = [
        {
            "utc_time": now.isoformat(),
            "cycle_id": "candidate-cycle",
            "kind": "cycle_start",
            "comment": "",
            "retcode": "0",
        }
    ]
    comments = [
        f"STR {side}{level}"
        for level in range(1, 31)
        for side in ("B", "S")
    ]
    rows.extend(
        {
            "utc_time": now.isoformat(),
            "cycle_id": "candidate-cycle",
            "kind": "pending_request",
            "comment": comment,
            "retcode": "10008",
        }
        for comment in comments[:slots]
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def paths(tmp_path: Path, now: datetime) -> dict[str, Path]:
    values = {
        "target": tmp_path / "target-heartbeat.json",
        "candidate": tmp_path / "candidate-heartbeat.json",
        "manifest": tmp_path / "candidate-manifest.csv",
        "telemetry": tmp_path / "candidate-telemetry.csv",
    }
    write_heartbeat(values["target"], now)
    write_heartbeat(values["candidate"], now)
    write_manifest(values["manifest"])
    write_telemetry(values["telemetry"], now)
    return values


def evaluate(
    values: dict[str, Path],
    now: datetime,
) -> dict:
    return evaluate_independent_readiness(
        target_heartbeat=values["target"],
        candidate_heartbeat=values["candidate"],
        candidate_manifest=values["manifest"],
        candidate_telemetry=values["telemetry"],
        expected_login=LOGIN,
        max_age_seconds=10.0,
        now=now,
    )


def test_fresh_read_only_normal_mode_candidate_is_ready(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 8, 12, tzinfo=UTC)
    result = evaluate(paths(tmp_path, now), now)

    assert result["ready"] is True
    assert result["failures"] == []
    assert result["accepted_initial_slots"] == 60


@pytest.mark.parametrize(
    ("runtime_mode", "login", "failure"),
    [
        ("1", LOGIN, "manifest_runtime_mode"),
        (
            "0",
            LOGIN + 1,
            "manifest_runtime_expected_account_login",
        ),
    ],
)
def test_manifest_mismatch_blocks_readiness(
    tmp_path: Path,
    runtime_mode: str,
    login: int,
    failure: str,
) -> None:
    now = datetime(2026, 8, 12, tzinfo=UTC)
    values = paths(tmp_path, now)
    write_manifest(
        values["manifest"],
        runtime_mode=runtime_mode,
        login=login,
    )

    result = evaluate(values, now)

    assert result["ready"] is False
    assert failure in result["failures"]


@pytest.mark.parametrize(
    ("read_only", "dropped", "failure"),
    [
        (False, 0, "candidate_read_only_not_verified"),
        (True, 1, "candidate_dropped_transactions"),
    ],
)
def test_candidate_collector_safety_failure_blocks_readiness(
    tmp_path: Path,
    read_only: bool,
    dropped: int,
    failure: str,
) -> None:
    now = datetime(2026, 8, 12, tzinfo=UTC)
    values = paths(tmp_path, now)
    write_heartbeat(
        values["candidate"],
        now,
        read_only=read_only,
        dropped=dropped,
    )

    result = evaluate(values, now)

    assert result["ready"] is False
    assert failure in result["failures"]


def test_stale_target_heartbeat_blocks_readiness(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 8, 12, tzinfo=UTC)
    values = paths(tmp_path, now)
    write_heartbeat(values["target"], now - timedelta(seconds=11))

    result = evaluate(values, now)

    assert result["ready"] is False
    assert "target_heartbeat_stale" in result["failures"]


def test_stale_telemetry_blocks_readiness(tmp_path: Path) -> None:
    now = datetime(2026, 8, 12, tzinfo=UTC)
    values = paths(tmp_path, now)
    write_telemetry(
        values["telemetry"],
        now - timedelta(seconds=11),
    )

    result = evaluate(values, now)

    assert result["ready"] is False
    assert "telemetry_stale" in result["failures"]


def test_incomplete_initial_grid_blocks_readiness(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 8, 12, tzinfo=UTC)
    values = paths(tmp_path, now)
    write_telemetry(values["telemetry"], now, slots=59)

    result = evaluate(values, now)

    assert result["ready"] is False
    assert "telemetry_initial_slots_incomplete" in result["failures"]
