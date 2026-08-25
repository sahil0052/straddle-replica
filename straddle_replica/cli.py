from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from .calibration import (
    AnchorObservation,
    calibrate_anchor_model,
    calibrate_deployments,
    select_anchor_deployments,
)
from .compare import ComparisonTolerance, Event, compare_events
from .geometry import compare_report_grid_geometry
from .report import export_golden_dataset, parse_mt5_report
from .ticks import (
    audit_tick_archive,
    download_ticks_to_csv,
    iter_tick_archive,
)
from .tester_report import parse_mt5_tester_report
from .validation import compare_report_fills_to_tester
from .volatility import (
    StepObservation,
    calibrate_atr_spacing,
    extract_atr_features,
)


UTC = timezone.utc


def _datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, default=str, sort_keys=True),
        encoding="utf-8",
    )


def _load_events(path: Path) -> list[Event]:
    with path.open(encoding="utf-8", newline="") as source:
        return [
            Event(
                time=_datetime(row["time"]),
                kind=row["kind"],
                comment=row["comment"],
                side=row["side"],
                volume=float(row["volume"]),
                price=float(row["price"]),
            )
            for row in csv.DictReader(source)
        ]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="straddle-replica")
    subcommands = parser.add_subparsers(dest="command", required=True)

    export = subcommands.add_parser("export-report")
    export.add_argument("--input", required=True, type=Path)
    export.add_argument("--output", required=True, type=Path)

    calibrate = subcommands.add_parser("calibrate")
    calibrate.add_argument("--input", required=True, type=Path)
    calibrate.add_argument("--output", required=True, type=Path)
    calibrate.add_argument("--tick-size", type=float, default=0.01)

    calibrate_anchor = subcommands.add_parser("calibrate-anchor")
    calibrate_anchor.add_argument("--report", required=True, type=Path)
    calibrate_anchor.add_argument("--ticks", required=True, type=Path)
    calibrate_anchor.add_argument("--start", required=True, type=_datetime)
    calibrate_anchor.add_argument("--end", required=True, type=_datetime)
    calibrate_anchor.add_argument("--segment-hours", type=int, default=12)
    calibrate_anchor.add_argument("--symbol", default="XAUUSD")
    calibrate_anchor.add_argument("--tick-size", type=float, default=0.01)
    calibrate_anchor.add_argument("--offset-min", type=int, default=-14)
    calibrate_anchor.add_argument("--offset-max", type=int, default=14)
    calibrate_anchor.add_argument("--lookback-seconds", type=float, default=2.0)
    calibrate_anchor.add_argument("--lookahead-seconds", type=float, default=0.5)
    calibrate_anchor.add_argument(
        "--minimum-order-coverage", type=float, default=0.9
    )
    calibrate_anchor.add_argument("--output", required=True, type=Path)

    calibrate_spacing = subcommands.add_parser("calibrate-spacing")
    calibrate_spacing.add_argument("--report", required=True, type=Path)
    calibrate_spacing.add_argument(
        "--anchor-calibration", required=True, type=Path
    )
    calibrate_spacing.add_argument("--ticks", required=True, type=Path)
    calibrate_spacing.add_argument("--start", required=True, type=_datetime)
    calibrate_spacing.add_argument("--end", required=True, type=_datetime)
    calibrate_spacing.add_argument("--segment-hours", type=int, default=12)
    calibrate_spacing.add_argument("--symbol", default="XAUUSD")
    calibrate_spacing.add_argument("--tick-size", type=float, default=0.01)
    calibrate_spacing.add_argument(
        "--timeframes", type=int, nargs="+", default=[5, 15, 30]
    )
    calibrate_spacing.add_argument("--period-min", type=int, default=2)
    calibrate_spacing.add_argument("--period-max", type=int, default=80)
    calibrate_spacing.add_argument("--output", required=True, type=Path)

    ticks = subcommands.add_parser("download-ticks")
    ticks.add_argument(
        "--terminal",
        type=Path,
        default=Path(r"C:\Program Files\MetaTrader 5\terminal64.exe"),
    )
    ticks.add_argument("--symbol", default="XAUUSD")
    ticks.add_argument("--start", required=True, type=_datetime)
    ticks.add_argument("--end", required=True, type=_datetime)
    ticks.add_argument("--output", required=True, type=Path)
    ticks.add_argument("--chunk-days", type=float, default=1)

    audit_ticks = subcommands.add_parser("audit-ticks")
    audit_ticks.add_argument("--input", required=True, type=Path)
    audit_ticks.add_argument("--symbol", default="XAUUSD")
    audit_ticks.add_argument("--start", required=True, type=_datetime)
    audit_ticks.add_argument("--end", required=True, type=_datetime)
    audit_ticks.add_argument("--segment-hours", type=int, default=12)
    audit_ticks.add_argument("--output", required=True, type=Path)

    compare = subcommands.add_parser("compare-events")
    compare.add_argument("--expected", required=True, type=Path)
    compare.add_argument("--actual", required=True, type=Path)
    compare.add_argument("--output", required=True, type=Path)
    compare.add_argument("--time-tolerance", type=float, default=1.0)
    compare.add_argument("--price-tolerance", type=float, default=0.01)

    geometry = subcommands.add_parser("compare-geometry")
    geometry.add_argument("--input", required=True, type=Path)
    geometry.add_argument("--output", required=True, type=Path)
    geometry.add_argument("--tick-size", type=float, default=0.01)
    geometry.add_argument("--include-rearms", action="store_true")

    tester = subcommands.add_parser("compare-tester")
    tester.add_argument("--report", required=True, type=Path)
    tester.add_argument("--tester", required=True, type=Path)
    tester.add_argument("--output", required=True, type=Path)
    tester.add_argument("--time-tolerance", type=float, default=1.0)
    tester.add_argument("--price-tolerance", type=float, default=0.01)

    telemetry = subcommands.add_parser("compare-telemetry")
    telemetry.add_argument("--report", required=True, type=Path)
    telemetry.add_argument("--telemetry", required=True, type=Path)
    telemetry.add_argument("--output", required=True, type=Path)
    telemetry.add_argument("--time-tolerance", type=float, default=1.0)
    telemetry.add_argument("--price-tolerance", type=float, default=0.01)

    monitor = subcommands.add_parser("monitor-live")
    monitor.add_argument(
        "--terminal",
        type=Path,
        default=Path(r"C:\Program Files\MetaTrader 5\terminal64.exe"),
    )
    monitor.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/live"),
    )
    monitor.add_argument("--symbol", default="XAUUSD")
    monitor.add_argument("--account", type=int, default=901018)
    monitor.add_argument(
        "--server",
        default="AchieverGlobalMarkets-Server",
    )
    monitor.add_argument("--poll-ms", type=int, default=50)
    monitor.add_argument("--checkpoint-seconds", type=float, default=5.0)
    monitor.add_argument("--history-poll-seconds", type=float, default=0.25)
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

    monitor_status = subcommands.add_parser("monitor-status")
    monitor_status.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/live"),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "export-report":
        report = parse_mt5_report(args.input)
        export_golden_dataset(report, args.output)
        _write_json(
            args.output / "summary.json",
            {
                "metadata": report.metadata,
                "closed_positions": len(report.closed_positions),
                "open_positions": len(report.open_positions),
                "historical_orders": len(report.historical_orders),
                "working_orders": len(report.working_orders),
                "deals": len(report.deals),
                "deployments": len(report.deployments),
                "total_trades": report.total_trades,
            },
        )
        return 0

    if args.command == "calibrate":
        report = parse_mt5_report(args.input)
        result = calibrate_deployments(report.deployments, args.tick_size)
        _write_json(
            args.output,
            {name: asdict(calibration) for name, calibration in result.items()},
        )
        return 0

    if args.command == "calibrate-anchor":
        if args.offset_min > args.offset_max:
            raise ValueError("offset-min cannot exceed offset-max")
        report = parse_mt5_report(args.report)
        selected_deployments = select_anchor_deployments(
            report.deployments,
            minimum_order_coverage=args.minimum_order_coverage,
        )
        observations = [
            AnchorObservation(
                deployment.start,
                deployment.anchor,
                deployment.profile_hint,
            )
            for deployment in selected_deployments
        ]
        ticks = iter_tick_archive(
            input_directory=args.ticks,
            symbol=args.symbol,
            start_utc=args.start,
            end_utc=args.end,
            segment_hours=args.segment_hours,
        )
        result = calibrate_anchor_model(
            observations=observations,
            ticks=ticks,
            tick_size=args.tick_size,
            offset_hours=tuple(
                range(args.offset_min, args.offset_max + 1)
            ),
            lookback_seconds=args.lookback_seconds,
            lookahead_seconds=args.lookahead_seconds,
        )
        payload = asdict(result)
        payload["source_deployment_count"] = len(report.deployments)
        payload["selected_deployment_count"] = len(selected_deployments)
        payload["minimum_order_coverage"] = args.minimum_order_coverage
        _write_json(args.output, payload)
        return 0

    if args.command == "calibrate-spacing":
        if args.period_min < 2 or args.period_min > args.period_max:
            raise ValueError("Invalid ATR period range")
        report = parse_mt5_report(args.report)
        deployment_by_time = {
            deployment.start.isoformat(sep=" "): deployment
            for deployment in report.deployments
        }
        anchor_calibration = json.loads(
            args.anchor_calibration.read_text(encoding="utf-8")
        )
        observations: list[StepObservation] = []
        for residual in anchor_calibration["residuals"]:
            if residual["label"] not in {"HISTORICAL_50", "HISTORICAL_60"}:
                continue
            if residual["matched_tick_time"] is None:
                continue
            deployment = deployment_by_time[residual["server_time"]]
            observations.append(
                StepObservation(
                    time=_datetime(residual["matched_tick_time"]),
                    profile=residual["label"],
                    step=deployment.step,
                )
            )
        feature_rows = extract_atr_features(
            observations=observations,
            ticks=iter_tick_archive(
                input_directory=args.ticks,
                symbol=args.symbol,
                start_utc=args.start,
                end_utc=args.end,
                segment_hours=args.segment_hours,
            ),
            timeframes=tuple(args.timeframes),
            periods=tuple(range(args.period_min, args.period_max + 1)),
        )
        calibration = calibrate_atr_spacing(
            feature_rows, tick_size=args.tick_size
        )
        _write_json(
            args.output,
            {
                profile: asdict(fit)
                for profile, fit in calibration.items()
            },
        )
        return 0 if all(fit.accepted for fit in calibration.values()) else 1

    if args.command == "download-ticks":
        coverage = download_ticks_to_csv(
            terminal_path=args.terminal,
            symbol=args.symbol,
            start_utc=args.start,
            end_utc=args.end,
            output_path=args.output,
            chunk_days=args.chunk_days,
        )
        _write_json(args.output.with_suffix(".coverage.json"), asdict(coverage))
        return 0

    if args.command == "audit-ticks":
        audit = audit_tick_archive(
            input_directory=args.input,
            symbol=args.symbol,
            start_utc=args.start,
            end_utc=args.end,
            segment_hours=args.segment_hours,
        )
        _write_json(args.output, asdict(audit))
        return 0 if audit.is_complete else 1

    if args.command == "compare-events":
        expected = _load_events(args.expected)
        actual = _load_events(args.actual)
        result = compare_events(
            expected,
            actual,
            ComparisonTolerance(
                time_seconds=args.time_tolerance,
                price=args.price_tolerance,
            ),
        )
        _write_json(args.output, asdict(result))
        return 0 if result.is_match else 1

    if args.command == "compare-geometry":
        report = parse_mt5_report(args.input)
        result = compare_report_grid_geometry(
            report,
            tick_size=args.tick_size,
            include_rearms=args.include_rearms,
        )
        payload = asdict(result)
        payload["is_match"] = result.is_match
        _write_json(args.output, payload)
        return 0 if result.is_match else 1

    if args.command == "compare-tester":
        report = parse_mt5_report(args.report)
        tester = parse_mt5_tester_report(args.tester)
        result = compare_report_fills_to_tester(
            report,
            tester,
            ComparisonTolerance(
                time_seconds=args.time_tolerance,
                price=args.price_tolerance,
            ),
        )
        payload = asdict(result)
        payload["fill_alignment"]["deterministic_match"] = (
            result.fill_alignment.deterministic_match
        )
        payload["fill_alignment"]["is_match"] = result.fill_alignment.is_match
        _write_json(args.output, payload)
        return 0 if result.fill_alignment.is_match else 1

    if args.command == "compare-telemetry":
        from .validation import compare_report_lifecycle_to_telemetry

        report = parse_mt5_report(args.report)
        result = compare_report_lifecycle_to_telemetry(
            report,
            args.telemetry,
            ComparisonTolerance(
                time_seconds=args.time_tolerance,
                price=args.price_tolerance,
            ),
        )
        payload = asdict(result)
        payload["deterministic_match"] = result.deterministic_match
        payload["is_match"] = result.is_match
        _write_json(args.output, payload)
        return 0 if result.is_match else 1

    if args.command == "monitor-live":
        from .live_monitor import LiveMonitorConfig, run_live_monitor

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
                heartbeat_seconds=args.heartbeat_seconds,
                duration_hours=args.duration_hours,
                exit_on_connection_error=args.exit_on_connection_error,
            )
        )
        print(session_dir)
        return 0

    if args.command == "monitor-status":
        from .live_monitor import read_monitor_status

        print(json.dumps(read_monitor_status(args.output), indent=2, sort_keys=True))
        return 0

    raise AssertionError(f"Unhandled command: {args.command}")
