from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .live_monitor import (
    LiveMonitorConfig,
    read_monitor_status,
    run_live_monitor,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="straddle-observer")
    subcommands = parser.add_subparsers(dest="command", required=True)

    monitor = subcommands.add_parser("monitor-live")
    monitor.add_argument(
        "--terminal",
        type=Path,
        default=Path(r"C:\Program Files\MetaTrader 5\terminal64.exe"),
    )
    monitor.add_argument("--output", required=True, type=Path)
    monitor.add_argument("--symbol", default="XAUUSD")
    monitor.add_argument("--account", type=int, default=901018)
    monitor.add_argument(
        "--server",
        default="AchieverGlobalMarkets-Server",
    )
    monitor.add_argument("--poll-ms", type=int, default=50)
    monitor.add_argument("--checkpoint-seconds", type=float, default=30.0)
    monitor.add_argument("--history-poll-seconds", type=float, default=0.25)
    monitor.add_argument("--history-seed-days", type=float, default=0.0)
    monitor.add_argument("--history-rates-timeframe", default="")
    monitor.add_argument(
        "--history-rates-seed-days",
        type=float,
        default=0.0,
    )
    monitor.add_argument("--heartbeat-seconds", type=float, default=1.0)
    monitor.add_argument("--duration-hours", type=float, default=0.0)
    monitor.add_argument(
        "--exit-on-connection-error",
        action="store_true",
        default=False,
    )
    monitor.add_argument(
        "--require-read-only",
        action="store_true",
        default=True,
    )

    status = subcommands.add_parser("monitor-status")
    status.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "monitor-live":
        session_dir = run_live_monitor(
            LiveMonitorConfig(
                terminal_path=args.terminal,
                output_root=args.output,
                symbol=args.symbol,
                expected_login=args.account,
                expected_server=args.server,
                require_read_only=args.require_read_only,
                poll_ms=args.poll_ms,
                checkpoint_seconds=args.checkpoint_seconds,
                history_poll_seconds=args.history_poll_seconds,
                history_seed_days=args.history_seed_days,
                history_rates_timeframe=args.history_rates_timeframe,
                history_rates_seed_days=args.history_rates_seed_days,
                heartbeat_seconds=args.heartbeat_seconds,
                duration_hours=args.duration_hours,
                exit_on_connection_error=args.exit_on_connection_error,
            )
        )
        print(session_dir)
        return 0

    if args.command == "monitor-status":
        print(
            json.dumps(
                read_monitor_status(args.output),
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    raise AssertionError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
