from __future__ import annotations

import argparse
from contextlib import redirect_stdout
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import sys
import time
from typing import Any


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import compare_independent_cycles
from straddle_replica.live_twin import load_demo_telemetry_events


UTC = timezone.utc


def _parse_utc(value: object) -> datetime:
    parsed = datetime.fromisoformat(
        str(value).replace("Z", "+00:00")
    )
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _reports_for_build(
    reports_dir: Path,
    *,
    build_id: str,
    certification_started_utc: str,
) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    for path in sorted(reports_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if (
            str(payload.get("build_id") or "") == build_id
            and str(payload.get("certification_started_utc") or "")
            == certification_started_utc
        ):
            reports.append(payload)
    return reports


def run_once(
    *,
    qualification_state: Path,
    target_events: Path,
    candidate_telemetry: Path,
    reports_dir: Path,
    pairing: str,
    max_start_gap_seconds: float,
    normalized_price_tolerance: float,
    target_start_grace_seconds: float = 5.0,
) -> dict[str, Any]:
    state = json.loads(qualification_state.read_text(encoding="utf-8"))
    if (
        state.get("qualification_start_policy")
        == "alignment_controller"
        and not state.get("qualification_started_utc")
    ):
        return {
            "status": "WAITING_FOR_ALIGNED_CYCLE_START",
            "pair_count": 0,
            "fail_count": 0,
            "evidence_based_fidelity_percent": None,
            "strict_lifecycle_fidelity_percent": None,
            "conditional_logic_fidelity_percent": None,
            "conditional_coverage_percent": None,
            "qualified_at_or_above_95_percent": False,
            "qualified_at_or_above_99_percent": False,
            "comparator_exit_code": 2,
            "build_id": str(state["active_build_id"]),
            "certification_started_utc": str(
                state["active_deployed_utc"]
            ),
        }
    if not state.get("qualification_started_utc"):
        deployed = _parse_utc(state["active_deployed_utc"])
        excluded = {
            str(cycle_id)
            for cycle_id in (
                state.get("excluded_candidate_cycle_ids") or []
            )
        }
        starts = [
            event
            for event in load_demo_telemetry_events(
                candidate_telemetry
            )
            if str(event.get("kind") or "") == "cycle_start"
            and str(event.get("cycle_id") or "") not in excluded
            and _parse_utc(event["time_utc"]) >= deployed
        ]
        if starts:
            started = min(
                starts,
                key=lambda event: _parse_utc(event["time_utc"]),
            )
            state.update(
                {
                    "qualification_started_utc": str(
                        started["time_utc"]
                    ),
                    "active_cycle_id": str(started["cycle_id"]),
                    "active_cycle_eligible": True,
                    "staged_status": "QUALIFICATION_CYCLE_ACTIVE",
                }
            )
            _write_json_atomic(qualification_state, state)
    build_id = str(state["active_build_id"])
    certification_started_utc = str(
        state.get("qualification_started_utc")
        or state["active_deployed_utc"]
    )
    arguments = [
        "--target-events",
        str(target_events),
        "--candidate-telemetry",
        str(candidate_telemetry),
        "--pairing",
        pairing,
        "--max-start-gap-seconds",
        str(max_start_gap_seconds),
        "--normalized-price-tolerance",
        str(normalized_price_tolerance),
        "--target-start-grace-seconds",
        str(target_start_grace_seconds),
        "--build-id",
        build_id,
        "--certification-started-utc",
        certification_started_utc,
        "--output-dir",
        str(reports_dir),
    ]
    for cycle_id in state.get("excluded_target_cycle_ids") or []:
        arguments.extend(
            ["--exclude-target-cycle-id", str(cycle_id)]
        )
    for cycle_id in state.get("excluded_candidate_cycle_ids") or []:
        arguments.extend(
            ["--exclude-candidate-cycle-id", str(cycle_id)]
        )

    reports_dir.mkdir(parents=True, exist_ok=True)
    with redirect_stdout(io.StringIO()):
        exit_code = compare_independent_cycles.main(arguments)
    reports = _reports_for_build(
        reports_dir,
        build_id=build_id,
        certification_started_utc=certification_started_utc,
    )
    fail_count = sum(
        str(report.get("status") or "") != "PASS"
        for report in reports
    )
    strict_score = (
        min(
            float(
                dict(
                    dict(report.get("fidelity") or {}).get("strict")
                    or {}
                ).get("f1_percent")
                or 0.0
            )
            for report in reports
        )
        if reports
        else None
    )
    conditional_logic_score = (
        min(
            float(
                dict(
                    dict(report.get("fidelity") or {}).get(
                        "conditional"
                    )
                    or {}
                ).get("f1_percent")
                or 0.0
            )
            for report in reports
        )
        if reports
        else None
    )
    conditional_coverage_score = (
        min(
            float(
                dict(
                    dict(report.get("fidelity") or {}).get(
                        "conditional"
                    )
                    or {}
                ).get("coverage_percent")
                or 0.0
            )
            for report in reports
        )
        if reports
        else None
    )
    component_scores = [
        score
        for score in (
            strict_score,
            conditional_logic_score,
            conditional_coverage_score,
        )
        if score is not None
    ]
    evidence_score = min(component_scores) if component_scores else None
    qualified_95 = bool(
        reports
        and fail_count == 0
        and evidence_score is not None
        and evidence_score >= 95.0
    )
    qualified_99 = bool(
        qualified_95
        and evidence_score is not None
        and evidence_score >= 99.0
    )
    if reports:
        state.update(
            {
                "complete_paired_cycles": len(reports),
                "evidence_based_fidelity_percent": evidence_score,
                "strict_lifecycle_fidelity_percent": strict_score,
                "conditional_logic_fidelity_percent": (
                    conditional_logic_score
                ),
                "conditional_coverage_percent": (
                    conditional_coverage_score
                ),
                "qualified_at_or_above_95_percent": qualified_95,
                "qualified_at_or_above_99_percent": qualified_99,
                "last_scored_utc": datetime.now(tz=UTC).isoformat(),
            }
        )
        _write_json_atomic(qualification_state, state)
    status = (
        (
            "WAITING_FOR_COMPLETE_PAIR"
            if state.get("qualification_started_utc")
            else "WAITING_FOR_CLEAN_CYCLE_START"
        )
        if not reports
        else "MISMATCH_DETECTED"
        if fail_count
        else "QUALIFIED_AT_OR_ABOVE_99"
        if qualified_99
        else "QUALIFIED_AT_OR_ABOVE_95"
        if qualified_95
        else "BELOW_95"
    )
    return {
        "status": status,
        "pair_count": len(reports),
        "fail_count": fail_count,
        "evidence_based_fidelity_percent": evidence_score,
        "strict_lifecycle_fidelity_percent": strict_score,
        "conditional_logic_fidelity_percent": conditional_logic_score,
        "conditional_coverage_percent": conditional_coverage_score,
        "qualified_at_or_above_95_percent": qualified_95,
        "qualified_at_or_above_99_percent": qualified_99,
        "comparator_exit_code": exit_code,
        "build_id": build_id,
        "certification_started_utc": certification_started_utc,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--qualification-state",
        required=True,
        type=Path,
    )
    parser.add_argument("--target-events", required=True, type=Path)
    parser.add_argument(
        "--candidate-telemetry",
        required=True,
        type=Path,
    )
    parser.add_argument("--reports-dir", required=True, type=Path)
    parser.add_argument("--health", required=True, type=Path)
    parser.add_argument(
        "--pairing",
        choices=("nearest", "ordinal"),
        required=True,
    )
    parser.add_argument(
        "--max-start-gap-seconds",
        type=float,
        required=True,
    )
    parser.add_argument(
        "--normalized-price-tolerance",
        type=float,
        default=0.02,
    )
    parser.add_argument(
        "--target-start-grace-seconds",
        type=float,
        default=5.0,
    )
    parser.add_argument("--poll-seconds", type=float, default=30.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    if args.poll_seconds < 5.0:
        parser.error("--poll-seconds must be at least 5")

    while True:
        try:
            result = run_once(
                qualification_state=args.qualification_state,
                target_events=args.target_events,
                candidate_telemetry=args.candidate_telemetry,
                reports_dir=args.reports_dir,
                pairing=args.pairing,
                max_start_gap_seconds=args.max_start_gap_seconds,
                normalized_price_tolerance=(
                    args.normalized_price_tolerance
                ),
                target_start_grace_seconds=(
                    args.target_start_grace_seconds
                ),
            )
            _write_json_atomic(
                args.health,
                {
                    **result,
                    "updated_at_utc": datetime.now(tz=UTC).isoformat(),
                },
            )
            if args.once:
                print(json.dumps(result, sort_keys=True))
                return 0
        except (
            KeyError,
            OSError,
            RuntimeError,
            ValueError,
            json.JSONDecodeError,
        ) as error:
            _write_json_atomic(
                args.health,
                {
                    "status": "WAITING_FOR_EVIDENCE",
                    "updated_at_utc": datetime.now(tz=UTC).isoformat(),
                    "error_type": type(error).__name__,
                    "error": str(error),
                },
            )
            if args.once:
                return 1
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
