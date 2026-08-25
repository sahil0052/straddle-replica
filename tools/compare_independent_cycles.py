from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from straddle_replica.independent_fidelity import (  # noqa: E402
    compare_independent_cycle_pair,
    pair_complete_cycles,
)
from straddle_replica.live_twin import (  # noqa: E402
    load_demo_telemetry_events,
    load_jsonl_events,
)


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _filter_eligible_cycles(
    events: list[dict],
    *,
    certification_started_utc: datetime,
    excluded_cycle_ids: set[str],
    start_grace_seconds: float = 0.0,
) -> list[dict]:
    if start_grace_seconds < 0:
        raise ValueError("start_grace_seconds must be non-negative")
    eligible_not_before = certification_started_utc - timedelta(
        seconds=start_grace_seconds
    )
    starts: dict[str, datetime] = {}
    for event in events:
        cycle_id = str(event.get("cycle_id") or "")
        time_utc = str(event.get("time_utc") or "")
        if not cycle_id or not time_utc:
            continue
        observed = _parse_utc(time_utc)
        current = starts.get(cycle_id)
        if current is None or observed < current:
            starts[cycle_id] = observed
    eligible = {
        cycle_id
        for cycle_id, started in starts.items()
        if started >= eligible_not_before
        and cycle_id not in excluded_cycle_ids
    }
    return [
        event
        for event in events
        if str(event.get("cycle_id") or "") in eligible
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-events", required=True, type=Path)
    parser.add_argument(
        "--candidate-telemetry",
        required=True,
        type=Path,
    )
    parser.add_argument(
        "--pairing",
        choices=("nearest", "ordinal"),
        required=True,
    )
    parser.add_argument(
        "--max-start-gap-seconds",
        type=float,
        default=5.0,
    )
    parser.add_argument(
        "--normalized-price-tolerance",
        type=float,
        default=0.02,
    )
    parser.add_argument(
        "--target-start-grace-seconds",
        type=float,
        default=0.0,
    )
    parser.add_argument("--build-id", required=True)
    parser.add_argument("--certification-started-utc", required=True)
    parser.add_argument(
        "--exclude-target-cycle-id",
        action="append",
        default=[],
    )
    parser.add_argument(
        "--exclude-candidate-cycle-id",
        action="append",
        default=[],
    )
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)

    certification_started_utc = _parse_utc(
        args.certification_started_utc
    )
    target = _filter_eligible_cycles(
        load_jsonl_events(args.target_events),
        certification_started_utc=certification_started_utc,
        excluded_cycle_ids=set(args.exclude_target_cycle_id),
        start_grace_seconds=args.target_start_grace_seconds,
    )
    candidate = _filter_eligible_cycles(
        load_demo_telemetry_events(args.candidate_telemetry),
        certification_started_utc=certification_started_utc,
        excluded_cycle_ids=set(args.exclude_candidate_cycle_id),
    )
    pairs = pair_complete_cycles(
        target,
        candidate,
        pairing=args.pairing,
        max_start_gap_seconds=args.max_start_gap_seconds,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    reports = []
    outputs = []
    for index, (target_cycle, candidate_cycle) in enumerate(
        pairs,
        start=1,
    ):
        report = compare_independent_cycle_pair(
            target_cycle,
            candidate_cycle,
            start_tolerance_seconds=args.max_start_gap_seconds,
            normalized_price_tolerance=(
                args.normalized_price_tolerance
            ),
        )
        report.update(
            {
                "pair_index": index,
                "build_id": args.build_id,
                "certification_started_utc": (
                    args.certification_started_utc
                ),
                "generated_utc": datetime.now(
                    tz=timezone.utc
                ).isoformat(),
            }
        )
        safe_id = re.sub(
            r"[^A-Za-z0-9_.-]+",
            "_",
            str(report["cycle_id"]),
        )
        destination = args.output_dir / f"{index:04d}-{safe_id}.json"
        destination.write_text(
            json.dumps(report, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        reports.append(report)
        outputs.append(str(destination))
    summary = {
        "pair_count": len(reports),
        "pass_count": sum(
            report["status"] == "PASS" for report in reports
        ),
        "fail_count": sum(
            report["status"] == "FAIL" for report in reports
        ),
        "outputs": outputs,
    }
    print(json.dumps(summary, sort_keys=True))
    if not reports:
        return 2
    return 0 if summary["fail_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
