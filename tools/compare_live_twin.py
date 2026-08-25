from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from straddle_replica.canonical_events import (  # noqa: E402
    CanonicalizationResult,
)
from straddle_replica.live_twin import (  # noqa: E402
    compare_paired_cycles,
    load_demo_telemetry_stream,
    load_jsonl_event_stream,
)


def _cycle_ids(events: list[dict]) -> list[str]:
    values: list[str] = []
    for event in events:
        cycle_id = str(event.get("cycle_id") or "")
        if cycle_id and cycle_id not in values:
            values.append(cycle_id)
    return values


def _parse_time(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _cycle_events(
    events: list[dict],
    cycle_id: str,
) -> list[dict]:
    return [
        event for event in events if event.get("cycle_id") == cycle_id
    ]


def _cycle_capture(
    capture: CanonicalizationResult,
    cycle_id: str,
) -> CanonicalizationResult:
    marker = f":{cycle_id}:"
    return CanonicalizationResult(
        events=tuple(_cycle_events(list(capture.events), cycle_id)),
        duplicate_event_ids=tuple(
            event_id
            for event_id in capture.duplicate_event_ids
            if marker in event_id
        ),
        invalid_rows=capture.invalid_rows,
    )


def _eligible_after(
    target: list[dict],
    demo: list[dict],
    started: datetime,
) -> bool:
    timestamps = [
        _parse_time(event["time_utc"])
        for event in [*target, *demo]
        if event.get("time_utc")
    ]
    return bool(timestamps) and min(timestamps) >= started


def _decorate_report(
    report: dict,
    *,
    build_id: str,
    certification_started_utc: str,
    generated_utc: str,
) -> dict:
    report["build_id"] = build_id
    report["certification_started_utc"] = certification_started_utc
    report["generated_utc"] = generated_utc
    return report


def _exit_code(reports: list[dict]) -> int:
    if reports and all(report["status"] == "PASS" for report in reports):
        return 0
    if any(report["status"] == "FAIL" for report in reports):
        return 1
    return 2


def _aggregate_fidelity(reports: list[dict]) -> dict[str, float]:
    if not reports:
        return {
            "strict_lifecycle_fidelity_percent": 0.0,
            "conditional_logic_fidelity_percent": 0.0,
            "conditional_coverage_percent": 0.0,
        }
    strict_values = [
        float(
            dict(dict(report.get("fidelity") or {}).get("strict") or {}).get(
                "f1_percent"
            )
            or 0.0
        )
        for report in reports
    ]
    conditional_values = [
        float(
            dict(
                dict(report.get("fidelity") or {}).get("conditional") or {}
            ).get("f1_percent")
            or 0.0
        )
        for report in reports
    ]
    coverage_values = [
        float(
            dict(
                dict(report.get("fidelity") or {}).get("conditional") or {}
            ).get("coverage_percent")
            or 0.0
        )
        for report in reports
    ]
    count = len(reports)
    return {
        "strict_lifecycle_fidelity_percent": round(
            sum(strict_values) / count,
            4,
        ),
        "conditional_logic_fidelity_percent": round(
            sum(conditional_values) / count,
            4,
        ),
        "conditional_coverage_percent": round(
            sum(coverage_values) / count,
            4,
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-events", required=True, type=Path)
    parser.add_argument("--demo-telemetry", required=True, type=Path)
    parser.add_argument("--cycle-id")
    parser.add_argument("--tick-size", required=True, type=float)
    parser.add_argument(
        "--time-tolerance-seconds",
        required=True,
        type=float,
    )
    parser.add_argument("--tick-value-per-lot", type=float)
    parser.add_argument("--build-id", required=True)
    parser.add_argument("--certification-started-utc", required=True)
    output = parser.add_mutually_exclusive_group(required=True)
    output.add_argument("--output", type=Path)
    output.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    if args.output_dir is not None and args.cycle_id:
        parser.error("--cycle-id cannot be combined with --output-dir")

    target_capture = load_jsonl_event_stream(args.target_events)
    demo_capture = load_demo_telemetry_stream(args.demo_telemetry)
    target = list(target_capture.events)
    demo = list(demo_capture.events)
    certification_started = _parse_time(
        args.certification_started_utc
    )
    certification_started_text = certification_started.isoformat()
    generated_utc = datetime.now(tz=timezone.utc).isoformat()
    common = [
        cycle_id
        for cycle_id in _cycle_ids(target)
        if cycle_id in set(_cycle_ids(demo))
    ]
    eligible = []
    for cycle_id in common:
        target_cycle = _cycle_events(target, cycle_id)
        demo_cycle = _cycle_events(demo, cycle_id)
        if _eligible_after(
            target_cycle,
            demo_cycle,
            certification_started,
        ):
            eligible.append(cycle_id)

    if args.output_dir is not None:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        reports = []
        outputs = []
        for cycle_id in eligible:
            report = compare_paired_cycles(
                _cycle_events(target, cycle_id),
                _cycle_events(demo, cycle_id),
                tick_size=args.tick_size,
                time_tolerance_seconds=args.time_tolerance_seconds,
                tick_value_per_lot=args.tick_value_per_lot,
                target_capture=_cycle_capture(target_capture, cycle_id),
                demo_capture=_cycle_capture(demo_capture, cycle_id),
            )
            _decorate_report(
                report,
                build_id=args.build_id,
                certification_started_utc=certification_started_text,
                generated_utc=generated_utc,
            )
            safe_cycle_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", cycle_id)
            destination = args.output_dir / f"{safe_cycle_id}.json"
            destination.write_text(
                json.dumps(report, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            reports.append(report)
            outputs.append(str(destination))
        print(
            json.dumps(
                {
                    "comparison_count": len(reports),
                    "statuses": {
                        status: sum(
                            report["status"] == status
                            for report in reports
                        )
                        for status in ("PASS", "FAIL", "INVALID", "UNPAIRED")
                    },
                    "outputs": outputs,
                    **_aggregate_fidelity(reports),
                },
                sort_keys=True,
            )
        )
        return _exit_code(reports)

    cycle_id = args.cycle_id or (eligible[-1] if eligible else None)
    if cycle_id is None:
        report = {
            "status": "UNPAIRED",
            "reason": "No eligible common target/demo cycle ID",
        }
    else:
        target_cycle = _cycle_events(target, cycle_id)
        demo_cycle = _cycle_events(demo, cycle_id)
        if not _eligible_after(
            target_cycle,
            demo_cycle,
            certification_started,
        ):
            report = {
                "status": "INVALID",
                "cycle_id": cycle_id,
                "reason": "Cycle predates the active certification run",
            }
        else:
            report = compare_paired_cycles(
                target_cycle,
                demo_cycle,
                tick_size=args.tick_size,
                time_tolerance_seconds=args.time_tolerance_seconds,
                tick_value_per_lot=args.tick_value_per_lot,
                target_capture=_cycle_capture(target_capture, cycle_id),
                demo_capture=_cycle_capture(demo_capture, cycle_id),
            )
    _decorate_report(
        report,
        build_id=args.build_id,
        certification_started_utc=certification_started_text,
        generated_utc=generated_utc,
    )
    assert args.output is not None
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "status": report["status"],
                "cycle_id": report.get("cycle_id"),
                **_aggregate_fidelity([report]),
            },
            sort_keys=True,
        )
    )
    return _exit_code([report])


if __name__ == "__main__":
    raise SystemExit(main())
