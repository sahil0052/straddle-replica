from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import statistics
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from straddle_replica.broker_execution import (  # noqa: E402
    StopChange,
    StopExit,
    detect_serialized_stop_runs,
)


STOP_COMMENT = re.compile(r"\[sl\s+([0-9.]+)", re.IGNORECASE)


def load_stop_changes(paths: list[Path]) -> list[StopChange]:
    changes: list[StopChange] = []
    seen: set[tuple[str, int, float, float]] = set()
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for row in payload["stops"]["change_rows"]:
            key = (
                row["server_time"],
                int(row["ticket"]),
                float(row["previous_sl"]),
                float(row["new_sl"]),
            )
            if key in seen:
                continue
            seen.add(key)
            changes.append(
                StopChange(
                    position_id=int(row["ticket"]),
                    time=datetime.strptime(
                        row["server_time"],
                        "%Y.%m.%d %H:%M:%S",
                    ).replace(tzinfo=timezone.utc),
                    stop_price=float(row["new_sl"]),
                )
            )
    return changes


def load_stop_exits(capture_root: Path, symbol: str) -> list[StopExit]:
    deals: dict[int, dict[str, object]] = {}
    for path in capture_root.glob("*/history-deals-*.jsonl"):
        for line in path.read_text(
            encoding="utf-8",
            errors="ignore",
        ).splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("symbol") == symbol:
                deals[int(row["ticket"])] = row

    exits: list[StopExit] = []
    for row in deals.values():
        if int(row.get("entry", -1)) != 1 or int(row.get("reason", -1)) != 4:
            continue
        match = STOP_COMMENT.search(str(row.get("comment", "")))
        if match is None:
            continue
        exits.append(
            StopExit(
                position_id=int(row["position_id"]),
                time=datetime.fromtimestamp(
                    int(row["time_msc"]) / 1000,
                    timezone.utc,
                ),
                stop_price=float(match.group(1)),
            )
        )
    return exits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture-root", required=True, type=Path)
    parser.add_argument(
        "--analysis",
        action="append",
        required=True,
        type=Path,
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--symbol", default="XAUUSD")
    args = parser.parse_args(argv)

    changes = load_stop_changes(args.analysis)
    exits = load_stop_exits(args.capture_root, args.symbol)
    runs = detect_serialized_stop_runs(exits, changes)
    gaps = [
        gap
        for run in runs
        for gap in run.exit_gaps_seconds
    ]
    payload = {
        "symbol": args.symbol,
        "stop_change_count": len(changes),
        "stop_exit_count": len(exits),
        "serialized_run_count": len(runs),
        "serialized_position_count": sum(
            len(run.position_ids) for run in runs
        ),
        "all_stops_preassigned_run_count": sum(
            run.all_stops_set_before_first_exit for run in runs
        ),
        "ascending_ticket_run_count": sum(
            run.ticket_order == "ascending" for run in runs
        ),
        "exit_gap_seconds": (
            {
                "count": len(gaps),
                "min": min(gaps),
                "median": statistics.median(gaps),
                "max": max(gaps),
            }
            if gaps
            else {"count": 0}
        ),
        "runs": [
            {
                **asdict(run),
                "first_exit_time": run.first_exit_time.isoformat(),
            }
            for run in runs
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps({key: value for key, value in payload.items() if key != "runs"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
