from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from straddle_replica.best_effort_status import (  # noqa: E402
    build_best_effort_status,
)


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _guard_failure_codes(path: Path | None) -> list[str]:
    if path is None:
        return []
    payload = _read_json(path)
    failures = payload.get("active_failures") or []
    codes = []
    for failure in failures:
        if isinstance(failure, dict):
            code = str(failure.get("code") or "").strip()
        else:
            code = str(failure).strip()
        if code:
            codes.append(code)
    return codes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--account-terms", required=True, type=Path)
    parser.add_argument("--adapter-state", required=True, type=Path)
    parser.add_argument("--coordinator-state", required=True, type=Path)
    parser.add_argument("--comparisons-dir", required=True, type=Path)
    parser.add_argument(
        "--source-mode",
        choices=("observer", "probe"),
        default="observer",
    )
    parser.add_argument(
        "--operational-guard-report",
        type=Path,
    )
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)

    comparisons = [
        _read_json(path)
        for path in sorted(args.comparisons_dir.glob("*.json"))
    ]
    report = build_best_effort_status(
        account_terms=_read_json(args.account_terms),
        adapter_state=_read_json(args.adapter_state),
        coordinator_state=_read_json(args.coordinator_state),
        comparisons=comparisons,
        source_mode=args.source_mode,
        operational_guard_failures=_guard_failure_codes(
            args.operational_guard_report
        ),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
