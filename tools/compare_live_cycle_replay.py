from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from straddle_replica.profiles import ProfileName, get_profile  # noqa: E402


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def load_live_deals(
    capture_root: Path,
    start: datetime,
    end: datetime,
    symbol: str,
) -> list[dict[str, object]]:
    deals: dict[int, dict[str, object]] = {}
    for path in capture_root.glob("*/history-deals*.jsonl"):
        for line in path.read_text(
            encoding="utf-8",
            errors="ignore",
        ).splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("symbol") == symbol:
                deals[int(row["ticket"])] = row
    start_msc = int(start.timestamp() * 1000)
    end_msc = int(end.timestamp() * 1000)
    return sorted(
        (
            row
            for row in deals.values()
            if start_msc <= int(row["time_msc"]) < end_msc
        ),
        key=lambda row: (int(row["time_msc"]), int(row["ticket"])),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--analysis", required=True, type=Path)
    parser.add_argument("--capture-root", required=True, type=Path)
    parser.add_argument("--telemetry", required=True, type=Path)
    parser.add_argument("--live-start", required=True)
    parser.add_argument("--live-next-start", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--symbol", default="XAUUSD")
    args = parser.parse_args(argv)

    live_start = parse_time(args.live_start)
    live_next_start = parse_time(args.live_next_start)
    analysis = json.loads(args.analysis.read_text(encoding="utf-8"))
    deployments = analysis["deployments"]["complete"]
    deployment = min(
        deployments,
        key=lambda item: abs(
            (
                datetime.strptime(
                    item["start_server_time"],
                    "%Y.%m.%d %H:%M:%S",
                ).replace(tzinfo=timezone.utc)
                - live_start
            ).total_seconds()
        ),
    )
    expected_anchor = float(deployment["grid"]["anchor"])
    expected_step = float(deployment["grid"]["normalized_step"])
    expected_order_count = int(deployment["order_count"])

    with args.telemetry.open(encoding="utf-8", newline="") as source:
        telemetry = list(csv.DictReader(source))
    cycle_starts = [
        (index, parse_time(row["time"]))
        for index, row in enumerate(telemetry)
        if row["kind"] == "cycle_start"
    ]
    start_position, actual_start = min(
        cycle_starts,
        key=lambda item: abs((item[1] - live_start).total_seconds()),
    )
    later_starts = [
        (index, item_time)
        for index, item_time in cycle_starts
        if index > start_position
    ]
    if not later_starts:
        raise ValueError("Telemetry does not contain the next cycle start")
    next_position, actual_next_start = later_starts[0]
    cycle_rows = telemetry[start_position:next_position]

    pending_rows: list[dict[str, str]] = []
    for row in cycle_rows[1:]:
        if row["kind"] == "deployment_complete":
            break
        if row["kind"] == "pending":
            pending_rows.append(row)
        elif row["kind"] not in {"cycle_start"} and pending_rows:
            break

    actual_anchor = float(telemetry[start_position]["price"])
    first_buy = next(
        (row for row in pending_rows if row["comment"] == "STR B1"),
        None,
    )
    first_sell = next(
        (row for row in pending_rows if row["comment"] == "STR S1"),
        None,
    )
    actual_step = (
        (float(first_buy["price"]) - float(first_sell["price"])) / 2
        if first_buy is not None and first_sell is not None
        else None
    )

    expected_comments = [
        f"STR {side}{level}"
        for level in range(1, expected_order_count // 2 + 1)
        for side in ("B", "S")
    ]
    actual_comments = [row["comment"] for row in pending_rows]
    profile = get_profile(ProfileName.LATEST_30)
    volume_match = all(
        abs(
            float(row["volume"])
            - profile.lot_for_level(int(row["comment"][5:]))
        )
        <= 1e-9
        for row in pending_rows
    )
    price_match = all(
        abs(
            float(row["price"])
            - (
                expected_anchor
                + (1 if row["side"] == "buy" else -1)
                * int(row["comment"][5:])
                * expected_step
            )
        )
        <= 0.011
        for row in pending_rows
    )
    anchor_match = abs(actual_anchor - expected_anchor) <= 0.011
    step_match = (
        actual_step is not None
        and abs(actual_step - expected_step) <= 0.011
    )
    sequence_match = actual_comments == expected_comments
    count_match = len(pending_rows) == expected_order_count

    live_deals = load_live_deals(
        args.capture_root,
        live_start,
        live_next_start,
        args.symbol,
    )
    live_lifecycle = Counter()
    live_fills: dict[str, dict[str, object]] = {}
    for row in live_deals:
        if int(row["entry"]) == 0:
            live_lifecycle["fill"] += 1
            live_fills.setdefault(str(row["comment"]), row)
        elif int(row["reason"]) == 4:
            live_lifecycle["stop_exit"] += 1
        elif str(row.get("comment", "")) == "STR CLOSE":
            live_lifecycle["close_fill"] += 1

    tester_lifecycle = Counter(
        row["kind"]
        for row in cycle_rows
        if row["kind"] in {"fill", "stop_exit", "close_fill"}
    )
    tester_fills: dict[str, dict[str, str]] = {}
    for row in cycle_rows:
        if row["kind"] == "fill":
            tester_fills.setdefault(row["comment"], row)
    first_fill_differences = []
    for comment in sorted(set(live_fills) & set(tester_fills)):
        live_row = live_fills[comment]
        tester_row = tester_fills[comment]
        live_time = datetime.fromtimestamp(
            int(live_row["time_msc"]) / 1000,
            timezone.utc,
        )
        tester_time = parse_time(tester_row["time"])
        first_fill_differences.append(
            {
                "comment": comment,
                "live_price": float(live_row["price"]),
                "tester_price": float(tester_row["price"]),
                "price_delta": round(
                    float(tester_row["price"]) - float(live_row["price"]),
                    8,
                ),
                "time_delta_seconds": (
                    tester_time - live_time
                ).total_seconds(),
            }
        )

    payload = {
        "live_start": live_start.isoformat(),
        "live_next_start": live_next_start.isoformat(),
        "deployment": {
            "anchor": {
                "expected": expected_anchor,
                "actual": actual_anchor,
                "match": anchor_match,
            },
            "step": {
                "expected": expected_step,
                "actual": actual_step,
                "match": step_match,
            },
            "pending_count": {
                "expected": expected_order_count,
                "actual": len(pending_rows),
            },
            "sequence_match": sequence_match,
            "volume_match": volume_match,
            "price_match": price_match,
            "deterministic_match": (
                anchor_match
                and step_match
                and count_match
                and sequence_match
                and volume_match
                and price_match
            ),
        },
        "live_lifecycle": dict(live_lifecycle),
        "tester_lifecycle": dict(tester_lifecycle),
        "next_cycle_start_actual": actual_next_start.isoformat(),
        "next_cycle_start_delta_seconds": (
            actual_next_start - live_next_start
        ).total_seconds(),
        "first_fill_differences": first_fill_differences,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "deployment_match": payload["deployment"][
                    "deterministic_match"
                ],
                "live_lifecycle": payload["live_lifecycle"],
                "tester_lifecycle": payload["tester_lifecycle"],
                "next_cycle_start_delta_seconds": payload[
                    "next_cycle_start_delta_seconds"
                ],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
