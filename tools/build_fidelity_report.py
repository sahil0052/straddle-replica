from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


UTC = timezone.utc


def _score(report: dict[str, Any], section: str, field: str) -> float:
    fidelity = dict(report.get("fidelity") or {})
    values = dict(fidelity.get(section) or {})
    return float(values.get(field) or 0.0)


def _report_paths(
    comparisons: list[Path],
    comparisons_dir: Path | None,
) -> list[Path]:
    paths = list(comparisons)
    if comparisons_dir is not None and comparisons_dir.is_dir():
        paths.extend(sorted(comparisons_dir.glob("*.json")))
    unique = {path.resolve(): path for path in paths}
    return sorted(
        unique.values(),
        key=lambda path: str(path.resolve()).lower(),
    )


def _load_reports(paths: list[Path]) -> list[dict[str, Any]]:
    reports = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in paths
    ]
    return sorted(
        reports,
        key=lambda report: (
            str(report.get("cycle_id") or ""),
            str(report.get("generated_utc") or ""),
        ),
    )


def _mismatch_register(reports: list[dict[str, Any]]) -> dict[str, Any]:
    cycles: list[dict[str, Any]] = []
    earliest_deterministic = None
    earliest_execution = None
    for report in reports:
        deterministic = list(
            report.get("deterministic_mismatches") or []
        )
        execution = list(report.get("execution_mismatches") or [])
        first_deterministic = deterministic[0] if deterministic else None
        first_execution = execution[0] if execution else None
        if earliest_deterministic is None and first_deterministic is not None:
            earliest_deterministic = first_deterministic
        if earliest_execution is None and first_execution is not None:
            earliest_execution = first_execution
        cycles.append(
            {
                "cycle_id": str(report.get("cycle_id") or ""),
                "status": str(report.get("status") or "INVALID"),
                "earliest_deterministic": first_deterministic,
                "earliest_execution": first_execution,
            }
        )
    return {
        "schema_version": 1,
        "earliest_deterministic": earliest_deterministic,
        "earliest_execution": earliest_execution,
        "cycles": cycles,
    }


def _live_summary(reports: list[dict[str, Any]]) -> dict[str, Any]:
    strict_scores = [
        _score(report, "strict", "f1_percent") for report in reports
    ]
    conditional_scores = [
        _score(report, "conditional", "f1_percent") for report in reports
    ]
    coverage_scores = [
        _score(report, "conditional", "coverage_percent")
        for report in reports
    ]
    return {
        "schema_version": 1,
        "generated_utc": datetime.now(tz=UTC).isoformat(),
        "comparison_count": len(reports),
        "evidence_grades": sorted(
            {
                str(report.get("evidence_grade") or "UNKNOWN")
                for report in reports
            }
        ),
        "status_counts": {
            status: sum(report.get("status") == status for report in reports)
            for status in ("PASS", "FAIL", "INVALID", "UNPAIRED")
        },
        "strict_lifecycle_fidelity_percent": {
            "mean": round(sum(strict_scores) / len(strict_scores), 4),
            "minimum": min(strict_scores),
        },
        "conditional_logic_fidelity_percent": {
            "mean": round(
                sum(conditional_scores) / len(conditional_scores),
                4,
            ),
            "minimum_coverage": min(coverage_scores),
        },
        "live_cycle_coverage_percent": 100.0,
    }


def _historical_summary(
    *,
    matched: int,
    target: int,
    evidence_grade: str,
) -> dict[str, Any]:
    strict_percent = round(matched / target * 100.0, 4)
    return {
        "schema_version": 1,
        "generated_utc": datetime.now(tz=UTC).isoformat(),
        "comparison_count": 0,
        "evidence_grades": [evidence_grade],
        "status_counts": {
            status: 0 for status in ("PASS", "FAIL", "INVALID", "UNPAIRED")
        },
        "strict_lifecycle_fidelity_percent": {
            "mean": strict_percent,
            "minimum": strict_percent,
        },
        "conditional_logic_fidelity_percent": {
            "mean": 0.0,
            "minimum_coverage": 0.0,
        },
        "live_cycle_coverage_percent": 0.0,
        "historical_baseline": {
            "matched": matched,
            "target": target,
        },
    }


def _markdown(summary: dict[str, Any]) -> str:
    strict = dict(summary["strict_lifecycle_fidelity_percent"])
    conditional = dict(summary["conditional_logic_fidelity_percent"])
    counts = dict(summary["status_counts"])
    return "\n".join(
        [
            "# Independent fidelity summary",
            "",
            (
                "The current historical baseline is 55.25% "
                "(663 of 1,200 lifecycle events)."
            ),
            "Prior unsupported closeness estimates are retired.",
            "",
            f"- Comparison reports: {summary['comparison_count']}",
            f"- Evidence grades: {', '.join(summary['evidence_grades'])}",
            f"- PASS: {counts['PASS']}",
            f"- FAIL: {counts['FAIL']}",
            f"- INVALID: {counts['INVALID']}",
            f"- UNPAIRED: {counts['UNPAIRED']}",
            (
                "- Mean strict lifecycle fidelity: "
                f"{strict['mean']:.4f}%"
            ),
            (
                "- Minimum strict lifecycle fidelity: "
                f"{strict['minimum']:.4f}%"
            ),
            (
                "- Mean conditional logic fidelity: "
                f"{conditional['mean']:.4f}%"
            ),
            (
                "- Minimum conditional coverage: "
                f"{conditional['minimum_coverage']:.4f}%"
            ),
            "",
            (
                "These scores measure saved evidence and do not promise "
                "identical broker profit."
            ),
            "",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--comparison",
        action="append",
        default=[],
        type=Path,
    )
    parser.add_argument("--comparisons-dir", type=Path)
    parser.add_argument("--historical-matched", type=int)
    parser.add_argument("--historical-target", type=int)
    parser.add_argument("--evidence-grade", default="BEST_EFFORT")
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)

    reports = _load_reports(
        _report_paths(args.comparison, args.comparisons_dir)
    )
    if reports:
        summary = _live_summary(reports)
    else:
        if (
            args.historical_matched is None
            or args.historical_target is None
            or args.historical_target <= 0
        ):
            parser.error(
                "provide comparison reports or a positive historical target"
            )
        summary = _historical_summary(
            matched=args.historical_matched,
            target=args.historical_target,
            evidence_grade=args.evidence_grade,
        )

    register = _mismatch_register(reports)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "fidelity-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (args.output_dir / "fidelity-summary.md").write_text(
        _markdown(summary),
        encoding="utf-8",
    )
    (args.output_dir / "mismatch-register.json").write_text(
        json.dumps(register, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "comparison_count": summary["comparison_count"],
                "output_dir": str(args.output_dir),
                "strict_lifecycle_fidelity_percent": dict(
                    summary["strict_lifecycle_fidelity_percent"]
                )["mean"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
