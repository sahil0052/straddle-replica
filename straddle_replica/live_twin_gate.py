from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


UTC = timezone.utc


def _parse_time(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def evaluate_live_twin_gate(
    *,
    reports: list[dict[str, Any]],
    market_open_hours: float,
    sequence_gaps: int,
    dropped_transactions: int,
    account_terms_match: bool,
    duplicate_sequences: int = 0,
    session_restarts: int = 0,
    operational_guard_failures: int = 0,
    request_evidence_available: bool = True,
    certification_started_utc: datetime | str | None = None,
    evaluated_utc: datetime | str | None = None,
    required_cycles: int = 20,
    required_market_hours: float = 48.0,
) -> dict[str, Any]:
    fallback_start = (
        _parse_time(certification_started_utc).isoformat()
        if certification_started_utc is not None
        else ""
    )
    latest_build = (
        str(reports[-1].get("build_id") or "") if reports else ""
    )
    latest_start = (
        str(
            reports[-1].get("certification_started_utc")
            or fallback_start
        )
        if reports
        else fallback_start
    )
    active_reports: list[dict[str, Any]] = []
    for report in reversed(reports):
        report_build = str(report.get("build_id") or "")
        report_start = str(
            report.get("certification_started_utc") or fallback_start
        )
        if report_build != latest_build or report_start != latest_start:
            break
        active_reports.append(report)
    active_reports.reverse()

    unique_reversed: list[dict[str, Any]] = []
    seen_cycles: set[str] = set()
    invalid_cycle_reports = 0
    for report in reversed(active_reports):
        cycle_id = str(report.get("cycle_id") or "")
        if not cycle_id:
            invalid_cycle_reports += 1
            continue
        if cycle_id in seen_cycles:
            continue
        seen_cycles.add(cycle_id)
        unique_reversed.append(report)
    unique_reports = list(reversed(unique_reversed))

    consecutive = 0
    for report in reversed(unique_reports):
        if report.get("status") != "PASS":
            break
        consecutive += 1

    evaluated = _parse_time(evaluated_utc or datetime.now(tz=UTC))
    elapsed_hours = 0.0
    valid_start = False
    if latest_start:
        try:
            started = _parse_time(latest_start)
            elapsed_hours = max(
                0.0,
                (evaluated - started).total_seconds() / 3600.0,
            )
            valid_start = True
        except ValueError:
            pass
    effective_market_hours = min(
        max(0.0, market_open_hours),
        elapsed_hours,
    )

    operational_blocking_reasons: list[str] = []
    if not latest_build:
        operational_blocking_reasons.append("build_id")
    if not valid_start:
        operational_blocking_reasons.append("certification_start")
    if effective_market_hours < required_market_hours:
        operational_blocking_reasons.append("market_open_hours")
    if consecutive < required_cycles:
        operational_blocking_reasons.append("consecutive_clean_cycles")
    if invalid_cycle_reports:
        operational_blocking_reasons.append("invalid_cycle_reports")
    if sequence_gaps != 0:
        operational_blocking_reasons.append("sequence_gaps")
    if duplicate_sequences != 0:
        operational_blocking_reasons.append("duplicate_sequences")
    if dropped_transactions != 0:
        operational_blocking_reasons.append("dropped_transactions")
    if session_restarts != 0:
        operational_blocking_reasons.append("session_restarts")
    if operational_guard_failures != 0:
        operational_blocking_reasons.append(
            "operational_guard_failures"
        )

    reset_reasons: list[str] = []
    if any(report.get("status") == "FAIL" for report in unique_reports):
        reset_reasons.append("cycle_mismatch")
    invalid_completed_cycle = any(
        report.get("status") in {"INVALID", "UNPAIRED"}
        and not (
            index == len(unique_reports) - 1
            and report.get("reason") == "Cycle lifecycle is not complete"
        )
        for index, report in enumerate(unique_reports)
    )
    if invalid_completed_cycle or invalid_cycle_reports:
        reset_reasons.append("cycle_invalid")
    if (
        sequence_gaps
        or duplicate_sequences
        or dropped_transactions
        or session_restarts
        or operational_guard_failures
    ):
        reset_reasons.append("capture_operational_failure")
    if reset_reasons:
        operational_blocking_reasons.append("certification_reset")

    operational_pass = not operational_blocking_reasons
    formal_blocking_reasons = [
        reason
        for reason, blocked in (
            (
                "direct_request_evidence",
                not request_evidence_available,
            ),
            ("account_terms", not account_terms_match),
        )
        if blocked
    ]
    formal_pass = operational_pass and not formal_blocking_reasons
    best_effort_pass = operational_pass and not formal_pass
    qualification_status = (
        "FORMAL_PASS"
        if formal_pass
        else "BEST_EFFORT_PASS"
        if best_effort_pass
        else "BLOCKED"
    )

    return {
        "qualification_status": qualification_status,
        "ready_for_formal_fidelity": formal_pass,
        "ready_for_best_effort_candidate": best_effort_pass,
        "reset_required": bool(reset_reasons),
        "reset_reasons": reset_reasons,
        "active_build_id": latest_build,
        "certification_started_utc": latest_start,
        "evaluated_utc": evaluated.isoformat(),
        "market_open_hours": {
            "actual": market_open_hours,
            "effective": round(effective_market_hours, 4),
            "elapsed_since_certification_start": round(
                elapsed_hours,
                4,
            ),
            "required": required_market_hours,
            "pass": effective_market_hours >= required_market_hours,
        },
        "consecutive_clean_cycles": consecutive,
        "required_clean_cycles": required_cycles,
        "distinct_cycle_reports": len(unique_reports),
        "invalid_cycle_reports": invalid_cycle_reports,
        "sequence_gaps": sequence_gaps,
        "duplicate_sequences": duplicate_sequences,
        "dropped_transactions": dropped_transactions,
        "session_restarts": session_restarts,
        "operational_guard_failures": operational_guard_failures,
        "direct_request_evidence_available": request_evidence_available,
        "account_terms_match": account_terms_match,
        "blocking_reasons": operational_blocking_reasons,
        "formal_blocking_reasons": formal_blocking_reasons,
    }
