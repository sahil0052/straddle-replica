from __future__ import annotations

import csv
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from straddle_replica.live_comparison import (
    build_live_target_demo_comparison,
)


UTC = timezone.utc
ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "compare_live_target_demo.py"


def lot_for_level(level: int) -> float:
    if level <= 10:
        return 0.01
    if level <= 20:
        return 0.06
    return 0.15


def write_target_snapshot(root: Path) -> None:
    session_id = "20260804T120000Z_901018_XAUUSD"
    session = root / session_id
    session.mkdir(parents=True)
    (root / "current-session.json").write_text(
        json.dumps({"session_id": session_id}),
        encoding="utf-8",
    )

    anchor = 4082.48
    step = 1.36
    started_msc = 1_785_857_444_000
    orders = []
    for level in range(1, 31):
        for side in ("B", "S"):
            sequence = (level - 1) * 2 + (1 if side == "S" else 0)
            setup_msc = started_msc + sequence * 100
            if level == 29:
                setup_msc = started_msc + (20_000 if side == "B" else 40_000)
            elif level == 30:
                setup_msc = started_msc + (60_000 if side == "B" else 80_000)
            orders.append(
                {
                    "comment": f"STR {side}{level}",
                    "price_open": anchor
                    + (1 if side == "B" else -1) * level * step,
                    "time_setup_msc": setup_msc,
                    "volume_initial": lot_for_level(level),
                }
            )

    snapshot = {
        "capture_time_utc": "2026-08-04T14:42:23+00:00",
        "orders": orders,
        "positions": [],
        "sequence": 123,
    }
    (session / "snapshots-20260804-14.jsonl").write_text(
        json.dumps(snapshot) + "\n",
        encoding="utf-8",
    )


def write_demo_telemetry(path: Path) -> None:
    fields = (
        "time",
        "kind",
        "comment",
        "side",
        "volume",
        "price",
        "state",
        "level",
        "ticket",
    )
    started = datetime(2026, 8, 4, 17, 41, 2, tzinfo=UTC)
    anchor = 4079.67
    step = 1.36
    rows = [
        {
            "time": started.isoformat().replace("+00:00", "Z"),
            "kind": "cycle_start",
            "comment": "",
            "side": "",
            "volume": "0",
            "price": str(anchor),
            "state": "CYCLE_DEPLOYING",
            "level": "",
            "ticket": "0",
        }
    ]
    for level in range(1, 31):
        for side in ("B", "S"):
            sequence = (level - 1) * 2 + (1 if side == "S" else 0)
            event_time = started + timedelta(milliseconds=sequence * 100)
            rows.append(
                {
                    "time": event_time.isoformat().replace("+00:00", "Z"),
                    "kind": "pending",
                    "comment": f"STR {side}{level}",
                    "side": "buy" if side == "B" else "sell",
                    "volume": str(lot_for_level(level)),
                    "price": str(
                        anchor
                        + (1 if side == "B" else -1) * level * step
                    ),
                    "state": "CYCLE_DEPLOYING",
                    "level": f"STR {side}{level}",
                    "ticket": str(10_000 + sequence),
                }
            )
    rows.append(
        {
            "time": (started + timedelta(seconds=7))
            .isoformat()
            .replace("+00:00", "Z"),
            "kind": "deployment_complete",
            "comment": "",
            "side": "",
            "volume": "0",
            "price": "0",
            "state": "CYCLE_RUNNING",
            "level": "",
            "ticket": "0",
        }
    )

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_compares_latest_target_grid_with_latest_complete_demo_cycle(
    tmp_path: Path,
) -> None:
    target_root = tmp_path / "target"
    target_root.mkdir()
    demo_telemetry = tmp_path / "demo.csv"
    write_target_snapshot(target_root)
    write_demo_telemetry(demo_telemetry)

    report = build_live_target_demo_comparison(
        target_python_root=target_root,
        demo_telemetry=demo_telemetry,
    )

    assert report["target"]["observed_slots"] == 60
    assert report["target"]["sequence_match"] is True
    assert report["target"]["volume_match"] is True
    assert report["target"]["step"] == pytest.approx(1.36)
    assert report["target"]["deployment_span_seconds"] == pytest.approx(80.0)

    assert report["demo"]["pending_count"] == 60
    assert report["demo"]["sequence_match"] is True
    assert report["demo"]["volume_match"] is True
    assert report["demo"]["step"] == pytest.approx(1.36)
    assert report["demo"]["deployment_duration_seconds"] == pytest.approx(7.0)

    assert report["comparison"]["profile_match"] is True
    assert report["comparison"]["step_match"] is True
    assert report["comparison"]["deployment_duration_delta_seconds"] == pytest.approx(
        -73.0
    )


def test_rejects_target_session_without_snapshots(tmp_path: Path) -> None:
    target_root = tmp_path / "target"
    session = target_root / "session"
    session.mkdir(parents=True)
    (target_root / "current-session.json").write_text(
        json.dumps({"session_id": "session"}),
        encoding="utf-8",
    )
    demo_telemetry = tmp_path / "demo.csv"
    write_demo_telemetry(demo_telemetry)

    with pytest.raises(FileNotFoundError, match="snapshot"):
        build_live_target_demo_comparison(
            target_python_root=target_root,
            demo_telemetry=demo_telemetry,
        )


def mutate_latest_target_snapshot(
    target_root: Path,
    mutator,
) -> None:
    session = next(path for path in target_root.iterdir() if path.is_dir())
    snapshot_path = next(session.glob("snapshots-*.jsonl"))
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    mutator(snapshot)
    snapshot_path.write_text(
        json.dumps(snapshot) + "\n",
        encoding="utf-8",
    )


def test_profile_match_requires_all_target_slots(tmp_path: Path) -> None:
    target_root = tmp_path / "target"
    target_root.mkdir()
    demo_telemetry = tmp_path / "demo.csv"
    write_target_snapshot(target_root)
    write_demo_telemetry(demo_telemetry)

    mutate_latest_target_snapshot(
        target_root,
        lambda snapshot: snapshot.update(
            orders=[
                row
                for row in snapshot["orders"]
                if row["comment"] != "STR B1"
            ]
        ),
    )

    report = build_live_target_demo_comparison(
        target_python_root=target_root,
        demo_telemetry=demo_telemetry,
    )

    assert report["target"]["missing_slots"] == ["STR B1"]
    assert report["comparison"]["profile_match"] is False


def test_profile_match_requires_target_sequence(tmp_path: Path) -> None:
    target_root = tmp_path / "target"
    target_root.mkdir()
    demo_telemetry = tmp_path / "demo.csv"
    write_target_snapshot(target_root)
    write_demo_telemetry(demo_telemetry)

    def swap_first_pair(snapshot: dict) -> None:
        first = snapshot["orders"][0]
        second = snapshot["orders"][1]
        first["time_setup_msc"], second["time_setup_msc"] = (
            second["time_setup_msc"],
            first["time_setup_msc"],
        )

    mutate_latest_target_snapshot(target_root, swap_first_pair)

    report = build_live_target_demo_comparison(
        target_python_root=target_root,
        demo_telemetry=demo_telemetry,
    )

    assert report["target"]["sequence_match"] is False
    assert report["comparison"]["profile_match"] is False


def test_profile_match_rejects_duplicate_target_slots(tmp_path: Path) -> None:
    target_root = tmp_path / "target"
    target_root.mkdir()
    demo_telemetry = tmp_path / "demo.csv"
    write_target_snapshot(target_root)
    write_demo_telemetry(demo_telemetry)

    def duplicate_first_order(snapshot: dict) -> None:
        snapshot["positions"].append(
            {
                "comment": "STR B1",
                "price_open": snapshot["orders"][0]["price_open"],
                "volume": snapshot["orders"][0]["volume_initial"],
            }
        )

    mutate_latest_target_snapshot(target_root, duplicate_first_order)

    report = build_live_target_demo_comparison(
        target_python_root=target_root,
        demo_telemetry=demo_telemetry,
    )

    assert report["target"]["duplicate_slots"] == ["STR B1"]
    assert report["comparison"]["profile_match"] is False


def test_cli_runs_outside_repository_working_directory(tmp_path: Path) -> None:
    target_root = tmp_path / "target"
    target_root.mkdir()
    demo_telemetry = tmp_path / "demo.csv"
    output = tmp_path / "comparison.json"
    write_target_snapshot(target_root)
    write_demo_telemetry(demo_telemetry)

    result = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--target-python-root",
            str(target_root),
            "--demo-telemetry",
            str(demo_telemetry),
            "--output",
            str(output),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(output.read_text(encoding="utf-8"))["comparison"][
        "profile_match"
    ]
