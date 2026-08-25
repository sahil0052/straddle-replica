from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parent))

from analyze_live_capture import analyze_lifecycle, load_history  # noqa: E402


def capture_sessions(root: Path) -> list[Path]:
    if any(root.glob("history-orders-*.jsonl")):
        return [root]
    return sorted(
        path
        for path in root.iterdir()
        if path.is_dir() and any(path.glob("history-orders-*.jsonl"))
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--minimum-delay-ms", type=int, default=20_000)
    parser.add_argument("--server-offset-seconds", type=int, default=7_200)
    args = parser.parse_args(argv)

    sessions = capture_sessions(args.capture_root)
    if not sessions:
        raise ValueError("No capture sessions with history orders were found")
    orders, deals = load_history(sessions)
    lifecycle = analyze_lifecycle(
        orders,
        deals,
        deployments=[],
        summaries=[],
        ticks=[],
        server_offset_ms=args.server_offset_seconds * 1_000,
    )
    delays = lifecycle["rearm_delays_ms"]
    below_minimum = sum(
        delay < args.minimum_delay_ms for delay in delays
    )
    gate_pass = bool(delays) and below_minimum == 0
    payload = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "capture_root": str(args.capture_root),
        "session_count": len(sessions),
        "historical_order_count": lifecycle["historical_order_count"],
        "historical_deal_count": lifecycle["historical_deal_count"],
        "complete_deployment_count": len(
            lifecycle["history_deployments"]
        ),
        "rearm_count": lifecycle["rearm_count"],
        "rearm_delay_ms": lifecycle["rearm_delay_ms"],
        "minimum_delay_gate": {
            "minimum_delay_ms": args.minimum_delay_ms,
            "events_below_minimum": below_minimum,
            "pass": gate_pass,
        },
        "unmatched_rearm_stop_exits": lifecycle[
            "unmatched_rearm_stop_exits"
        ],
        "first_20_rearms": lifecycle["first_20_rearms"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "rearm_count": payload["rearm_count"],
                "minimum_delay_gate": payload["minimum_delay_gate"],
            },
            sort_keys=True,
        )
    )
    return 0 if gate_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
