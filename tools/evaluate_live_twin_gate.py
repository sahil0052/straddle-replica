from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from straddle_replica.live_twin_gate import (  # noqa: E402
    evaluate_live_twin_gate,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--comparison",
        action="append",
        default=[],
        type=Path,
    )
    parser.add_argument("--market-open-hours", type=float)
    parser.add_argument("--sequence-gaps", type=int)
    parser.add_argument("--duplicate-sequences", type=int, default=0)
    parser.add_argument("--dropped-transactions", type=int)
    parser.add_argument("--session-restarts", type=int, default=0)
    parser.add_argument(
        "--operational-guard-failures",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--request-evidence-unavailable",
        action="store_true",
    )
    parser.add_argument("--account-terms-match", action="store_true")
    parser.add_argument("--probe-health", type=Path)
    parser.add_argument("--account-terms-report", type=Path)
    parser.add_argument("--certification-started-utc")
    parser.add_argument("--required-cycles", type=int, default=20)
    parser.add_argument("--required-market-hours", type=float, default=48.0)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)

    reports = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in args.comparison
    ]
    if args.probe_health is not None:
        health = json.loads(
            args.probe_health.read_text(encoding="utf-8")
        )
        market_open_hours = float(health.get("market_open_hours") or 0.0)
        sequence_gaps = int(health.get("sequence_gaps") or 0)
        duplicate_sequences = int(
            health.get("duplicate_sequences") or 0
        )
        dropped_transactions = int(
            health.get("dropped_transactions") or 0
        )
        session_restarts = int(health.get("session_restarts") or 0)
        request_evidence_available = bool(
            health.get("direct_request_evidence_available")
        )
    else:
        if (
            args.market_open_hours is None
            or args.sequence_gaps is None
            or args.dropped_transactions is None
        ):
            parser.error(
                "provide --probe-health or all manual capture metrics"
            )
        market_open_hours = args.market_open_hours
        sequence_gaps = args.sequence_gaps
        duplicate_sequences = args.duplicate_sequences
        dropped_transactions = args.dropped_transactions
        session_restarts = args.session_restarts
        request_evidence_available = (
            not args.request_evidence_unavailable
        )

    account_terms_match = args.account_terms_match
    if args.account_terms_report is not None:
        account_terms_match = bool(
            json.loads(
                args.account_terms_report.read_text(encoding="utf-8")
            ).get("match")
        )
    result = evaluate_live_twin_gate(
        reports=reports,
        market_open_hours=market_open_hours,
        sequence_gaps=sequence_gaps,
        duplicate_sequences=duplicate_sequences,
        dropped_transactions=dropped_transactions,
        session_restarts=session_restarts,
        operational_guard_failures=args.operational_guard_failures,
        request_evidence_available=request_evidence_available,
        account_terms_match=account_terms_match,
        certification_started_utc=args.certification_started_utc,
        required_cycles=args.required_cycles,
        required_market_hours=args.required_market_hours,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "qualification_status": result[
                    "qualification_status"
                ],
                "ready_for_formal_fidelity": result[
                    "ready_for_formal_fidelity"
                ],
                "ready_for_best_effort_candidate": result[
                    "ready_for_best_effort_candidate"
                ],
                "blocking_reasons": result["blocking_reasons"],
                "output": str(args.output),
            },
            sort_keys=True,
        )
    )
    return 0 if result["qualification_status"] != "BLOCKED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
