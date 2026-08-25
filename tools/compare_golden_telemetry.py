from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from straddle_replica.validation import (
    compare_golden_lifecycle_to_telemetry,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--golden", required=True, type=Path)
    parser.add_argument("--telemetry", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    result = compare_golden_lifecycle_to_telemetry(
        args.golden,
        args.telemetry,
    )
    payload = {
        "expected_count": result.expected_count,
        "actual_count": result.actual_count,
        "matched_count": result.matched_count,
        "deterministic_match": result.deterministic_match,
        "is_match": result.is_match,
        "missing_expected_count": len(result.missing_expected),
        "unexpected_actual_count": len(result.unexpected_actual),
        "execution_mismatch_count": len(result.execution_mismatches),
        "missing_expected": [
            asdict(item) for item in result.missing_expected[:100]
        ],
        "unexpected_actual": [
            asdict(item) for item in result.unexpected_actual[:100]
        ],
        "execution_mismatches": [
            asdict(item) for item in result.execution_mismatches[:100]
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    print(json.dumps(
        {
            key: value
            for key, value in payload.items()
            if not isinstance(value, list)
        },
        sort_keys=True,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
