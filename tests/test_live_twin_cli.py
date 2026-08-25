from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "compare_live_twin.py"
UTC = timezone.utc


def deployment_events(*, cycle_id: str, start: datetime) -> list[dict]:
    events = []
    for level in range(1, 31):
        volume = 0.01 if level <= 10 else 0.06 if level <= 20 else 0.15
        for side in ("B", "S"):
            index = (level - 1) * 2 + (0 if side == "B" else 1)
            events.append(
                {
                    "cycle_id": cycle_id,
                    "time_utc": (
                        start + timedelta(milliseconds=index * 100)
                    ).isoformat(),
                    "kind": "pending_request",
                    "comment": f"STR {side}{level}",
                    "side": "buy" if side == "B" else "sell",
                    "volume": volume,
                    "price": 4080.0
                    + (1 if side == "B" else -1) * level * 1.36,
                    "sl": 0.0,
                    "tp": 0.0,
                    "commission": 0.0,
                    "swap": 0.0,
                    "profit": 0.0,
                }
            )
    return events


def test_live_twin_cli_writes_passing_cycle_report(tmp_path: Path) -> None:
    target_events = deployment_events(
        cycle_id="cycle-1",
        start=datetime(2026, 8, 4, 14, 0, tzinfo=UTC),
    )
    target_events.append(
        {
            "cycle_id": "cycle-1",
            "time_utc": "2026-08-04T14:01:00+00:00",
            "kind": "cycle_complete",
            "comment": "",
            "side": "",
            "volume": 0.0,
            "price": 0.0,
            "sl": 0.0,
            "tp": 0.0,
            "retcode": 0,
            "commission": 0.0,
            "swap": 0.0,
            "profit": 0.0,
        }
    )
    target_path = tmp_path / "target.jsonl"
    target_path.write_text(
        "".join(json.dumps(event) + "\n" for event in target_events),
        encoding="utf-8",
    )

    demo_path = tmp_path / "demo.csv"
    fields = (
        "utc_time",
        "cycle_id",
        "kind",
        "comment",
        "side",
        "volume",
        "price",
        "sl",
        "tp",
        "retcode",
        "commission",
        "swap",
        "profit",
    )
    with demo_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for event in target_events:
            kind = (
                "shadow_reset_complete"
                if event["kind"] == "cycle_complete"
                else event["kind"]
            )
            writer.writerow(
                {
                    "utc_time": event["time_utc"],
                    "cycle_id": event["cycle_id"],
                    "kind": kind,
                    "comment": event["comment"],
                    "side": event["side"],
                    "volume": event["volume"],
                    "price": event["price"],
                    "sl": event["sl"],
                    "tp": event["tp"],
                    "retcode": event.get("retcode", 0),
                    "commission": event["commission"],
                    "swap": event["swap"],
                    "profit": event["profit"],
                }
            )

    output = tmp_path / "comparison.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--target-events",
            str(target_path),
            "--demo-telemetry",
            str(demo_path),
            "--tick-size",
            "0.01",
            "--time-tolerance-seconds",
            "1",
            "--build-id",
            "build-1",
            "--certification-started-utc",
            "2026-08-04T13:00:00+00:00",
            "--output",
            str(output),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["status"] == "PASS"
    assert report["cycle_id"] == "cycle-1"
    assert report["build_id"] == "build-1"
    assert (
        report["certification_started_utc"]
        == "2026-08-04T13:00:00+00:00"
    )
    summary = json.loads(completed.stdout)
    assert "strict_lifecycle_fidelity_percent" in summary
    assert "conditional_logic_fidelity_percent" in summary


def test_live_twin_cli_refreshes_every_cycle_in_output_directory(
    tmp_path: Path,
) -> None:
    start = datetime(2026, 8, 4, 14, 0, tzinfo=UTC)
    target_events = []
    demo_events = []
    for index in range(2):
        cycle_id = f"cycle-{index + 1}"
        cycle_start = start + timedelta(hours=index)
        target_cycle = deployment_events(
            cycle_id=cycle_id,
            start=cycle_start,
        )
        demo_cycle = [dict(event) for event in target_cycle]
        target_cycle.append(
            {
                "cycle_id": cycle_id,
                "time_utc": (
                    cycle_start + timedelta(minutes=1)
                ).isoformat(),
                "kind": "cycle_complete",
                "comment": "",
                "side": "",
                "volume": 0.0,
                "price": 0.0,
                "sl": 0.0,
                "tp": 0.0,
                "retcode": 0,
                "commission": 0.0,
                "swap": 0.0,
                "profit": 0.0,
            }
        )
        demo_cycle.append(
            {
                **target_cycle[-1],
                "kind": "shadow_reset_complete",
            }
        )
        target_events.extend(target_cycle)
        demo_events.extend(demo_cycle)

    target_path = tmp_path / "target.jsonl"
    target_path.write_text(
        "".join(json.dumps(event) + "\n" for event in target_events),
        encoding="utf-8",
    )
    demo_path = tmp_path / "demo.csv"
    fields = (
        "utc_time",
        "cycle_id",
        "kind",
        "comment",
        "side",
        "volume",
        "price",
        "sl",
        "tp",
        "retcode",
        "commission",
        "swap",
        "profit",
    )
    with demo_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for event in demo_events:
            row = {field: event.get(field, "") for field in fields}
            row["utc_time"] = event["time_utc"]
            writer.writerow(row)
    output_dir = tmp_path / "comparisons"

    completed = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--target-events",
            str(target_path),
            "--demo-telemetry",
            str(demo_path),
            "--tick-size",
            "0.01",
            "--time-tolerance-seconds",
            "1",
            "--build-id",
            "build-1",
            "--certification-started-utc",
            "2026-08-04T13:00:00+00:00",
            "--output-dir",
            str(output_dir),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    reports = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(output_dir.glob("*.json"))
    ]
    assert [report["cycle_id"] for report in reports] == [
        "cycle-1",
        "cycle-2",
    ]
    assert {report["status"] for report in reports} == {"PASS"}
