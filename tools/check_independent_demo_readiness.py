from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from straddle_replica.independent_readiness import (  # noqa: E402
    evaluate_independent_readiness,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-heartbeat", required=True, type=Path)
    parser.add_argument(
        "--candidate-heartbeat",
        required=True,
        type=Path,
    )
    parser.add_argument(
        "--candidate-manifest",
        required=True,
        type=Path,
    )
    parser.add_argument(
        "--candidate-telemetry",
        required=True,
        type=Path,
    )
    parser.add_argument("--expected-login", required=True, type=int)
    parser.add_argument("--max-age-seconds", type=float, default=10.0)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    result = evaluate_independent_readiness(
        target_heartbeat=args.target_heartbeat,
        candidate_heartbeat=args.candidate_heartbeat,
        candidate_manifest=args.candidate_manifest,
        candidate_telemetry=args.candidate_telemetry,
        expected_login=args.expected_login,
        max_age_seconds=args.max_age_seconds,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
