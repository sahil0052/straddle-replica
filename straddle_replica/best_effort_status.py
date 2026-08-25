from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence


UTC = timezone.utc


def build_best_effort_status(
    *,
    account_terms: Mapping[str, Any],
    adapter_state: Mapping[str, Any],
    coordinator_state: Mapping[str, Any],
    comparisons: Sequence[Mapping[str, Any]],
    source_mode: str,
    operational_guard_failures: Sequence[str] = (),
) -> dict[str, Any]:
    normalized_source = source_mode.strip().lower()
    broker_terms = sorted(
        str(key)
        for key in dict(account_terms.get("mismatches") or {})
    )
    statuses = [
        str(comparison.get("status") or "INVALID")
        for comparison in comparisons
    ]
    guard_failures = sorted(
        {
            str(failure).strip()
            for failure in operational_guard_failures
            if str(failure).strip()
        }
    )
    latest_status = (
        "INVALID"
        if guard_failures
        else statuses[-1] if statuses else "WAITING"
    )
    latest = comparisons[-1] if comparisons else {}
    fidelity = dict(latest.get("fidelity") or {})
    strict = dict(fidelity.get("strict") or {})
    conditional = dict(fidelity.get("conditional") or {})
    capture_limits = []
    if normalized_source == "observer":
        capture_limits.append("originating_request_payload")
        capture_limits.append("exact_request_timestamp")
    formal_eligible = (
        normalized_source == "probe"
        and bool(account_terms.get("match"))
        and not broker_terms
    )
    return {
        "generated_utc": datetime.now(tz=UTC).isoformat(),
        "mode": (
            "FORMAL" if normalized_source == "probe" else "BEST_EFFORT"
        ),
        "source_mode": normalized_source,
        "formal_certification_eligible": formal_eligible,
        "broker_terms": broker_terms,
        "capture_limits": capture_limits,
        "ea_logic": {
            "latest_status": latest_status,
            "paired_cycle_count": len(comparisons),
            "pass_count": statuses.count("PASS"),
            "fail_count": statuses.count("FAIL"),
            "invalid_count": statuses.count("INVALID"),
            "unpaired_count": statuses.count("UNPAIRED"),
            "strict_lifecycle_fidelity_percent": float(
                strict.get("f1_percent") or 0.0
            ),
            "conditional_logic_fidelity_percent": float(
                conditional.get("f1_percent") or 0.0
            ),
            "conditional_coverage_percent": float(
                conditional.get("coverage_percent") or 0.0
            ),
        },
        "adapter": {
            "initialized": bool(adapter_state.get("initialized")),
            "waiting_for_flat": bool(
                adapter_state.get("waiting_for_flat")
            ),
            "armed_for_next_cycle": bool(
                adapter_state.get("armed_for_next_cycle")
            ),
            "next_sequence": int(
                adapter_state.get("next_sequence") or 0
            ),
        },
        "operations": {
            "guard_failures": guard_failures,
            "skipped_cycles": int(
                coordinator_state.get("skipped_cycles") or 0
            ),
            "sequence_gaps": int(
                coordinator_state.get("sequence_gaps") or 0
            ),
            "session_restarts": int(
                coordinator_state.get("session_restarts") or 0
            ),
        },
    }
