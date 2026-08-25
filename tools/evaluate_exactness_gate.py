from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def comparison_value(payload: dict, key: str) -> bool:
    if key in payload:
        return bool(payload[key])
    fill_alignment = payload.get("fill_alignment")
    if isinstance(fill_alignment, dict) and key in fill_alignment:
        return bool(fill_alignment[key])
    return False


def replay_execution_match(payload: dict) -> bool:
    lifecycle_match = (
        payload.get("live_lifecycle") == payload.get("tester_lifecycle")
    )
    restart_match = abs(
        float(payload.get("next_cycle_start_delta_seconds", float("inf")))
    ) <= 1e-9
    fills_match = all(
        abs(float(item.get("price_delta", float("inf")))) <= 1e-9
        and abs(float(item.get("time_delta_seconds", float("inf")))) <= 1e-9
        for item in payload.get("first_fill_differences", [])
    )
    return lifecycle_match and restart_match and fills_match


def check(actual: float | int, required: float | int, passed: bool) -> dict:
    return {
        "actual": actual,
        "required": required,
        "pass": passed,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--monitoring-check", required=True, type=Path)
    parser.add_argument("--capture-summary", required=True, type=Path)
    parser.add_argument(
        "--deployment-replay",
        required=True,
        action="append",
        type=Path,
    )
    parser.add_argument(
        "--lifecycle-comparison",
        required=True,
        action="append",
        type=Path,
    )
    parser.add_argument("--minimum-market-hours", type=float, default=48.0)
    parser.add_argument("--minimum-cycles", type=int, default=10)
    parser.add_argument("--minimum-comparisons", type=int, default=10)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)

    monitoring = load_json(args.monitoring_check)
    capture_summary = load_json(args.capture_summary)
    replays = [load_json(path) for path in args.deployment_replay]
    lifecycle = [
        load_json(path) for path in args.lifecycle_comparison
    ]

    market_hours = float(
        monitoring["preserved_non_overlapping_market_open_hours"]
    )
    complete_cycles = int(monitoring["preserved_complete_deployments"])
    sequence_gaps = int(
        capture_summary.get(
            "transaction_sequence_gaps",
            monitoring.get("latest_formal_sequence_gaps", -1),
        )
    )
    dropped_transactions = int(
        capture_summary.get(
            "dropped_transactions",
            monitoring.get("latest_formal_dropped_transactions", -1),
        )
    )

    capture = {
        "market_open_hours": check(
            market_hours,
            args.minimum_market_hours,
            market_hours >= args.minimum_market_hours,
        ),
        "complete_cycles": check(
            complete_cycles,
            args.minimum_cycles,
            complete_cycles >= args.minimum_cycles,
        ),
        "transaction_sequence_gaps": check(
            sequence_gaps,
            0,
            sequence_gaps == 0,
        ),
        "dropped_transactions": check(
            dropped_transactions,
            0,
            dropped_transactions == 0,
        ),
    }
    capture["pass"] = all(item["pass"] for item in capture.values())

    replay_matches = [
        bool(item.get("deployment", {}).get("deterministic_match"))
        for item in replays
    ]
    lifecycle_matches = [
        comparison_value(item, "deterministic_match")
        for item in lifecycle
    ]
    deployment_decisions = {
        "actual_comparisons": len(replays),
        "required_comparisons": args.minimum_comparisons,
        "all_match": all(replay_matches),
        "pass": (
            len(replays) >= args.minimum_comparisons
            and all(replay_matches)
        ),
    }
    lifecycle_decisions = {
        "actual_comparisons": len(lifecycle),
        "required_comparisons": args.minimum_comparisons,
        "all_match": all(lifecycle_matches),
        "pass": (
            len(lifecycle) >= args.minimum_comparisons
            and all(lifecycle_matches)
        ),
    }
    deterministic = {
        "deployment_decisions": deployment_decisions,
        "lifecycle_decisions": lifecycle_decisions,
        "pass": (
            deployment_decisions["pass"]
            and lifecycle_decisions["pass"]
        ),
    }

    replay_execution_matches = [
        replay_execution_match(item) for item in replays
    ]
    lifecycle_execution_matches = [
        comparison_value(item, "is_match") for item in lifecycle
    ]
    execution = {
        "deployment_replays_all_match": all(replay_execution_matches),
        "lifecycle_comparisons_all_match": all(
            lifecycle_execution_matches
        ),
        "pass": (
            len(replays) >= args.minimum_comparisons
            and len(lifecycle) >= args.minimum_comparisons
            and all(replay_execution_matches)
            and all(lifecycle_execution_matches)
        ),
        "note": (
            "Execution includes broker fill price, timing, slippage, and "
            "cycle timing; it is evaluated separately from EA decisions."
        ),
    }

    ready_for_deterministic_replica = (
        capture["pass"] and deterministic["pass"]
    )
    ready_for_100_percent_trade_claim = (
        ready_for_deterministic_replica and execution["pass"]
    )
    blocking_reasons = [
        key
        for key, item in capture.items()
        if key != "pass" and not item["pass"]
    ]
    blocking_reasons.extend(
        key
        for key, item in (
            ("deployment_decisions", deployment_decisions),
            ("lifecycle_decisions", lifecycle_decisions),
        )
        if not item["pass"]
    )
    if ready_for_deterministic_replica and not execution["pass"]:
        blocking_reasons.append("broker_execution_parity")

    payload = {
        "capture": capture,
        "deterministic_parity": deterministic,
        "execution_parity": execution,
        "ready_for_deterministic_replica": (
            ready_for_deterministic_replica
        ),
        "ready_for_100_percent_trade_claim": (
            ready_for_100_percent_trade_claim
        ),
        "blocking_reasons": blocking_reasons,
        "evidence": {
            "monitoring_check": str(args.monitoring_check),
            "capture_summary": str(args.capture_summary),
            "deployment_replays": [
                str(path) for path in args.deployment_replay
            ],
            "lifecycle_comparisons": [
                str(path) for path in args.lifecycle_comparison
            ],
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "ready_for_deterministic_replica": (
                    ready_for_deterministic_replica
                ),
                "ready_for_100_percent_trade_claim": (
                    ready_for_100_percent_trade_claim
                ),
                "blocking_reasons": blocking_reasons,
            },
            sort_keys=True,
        )
    )
    return 0 if ready_for_deterministic_replica else 1


if __name__ == "__main__":
    raise SystemExit(main())
