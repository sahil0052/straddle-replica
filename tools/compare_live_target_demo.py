from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from straddle_replica.live_comparison import (
    build_live_target_demo_comparison,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-python-root", required=True, type=Path)
    parser.add_argument("--demo-telemetry", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    report = build_live_target_demo_comparison(
        target_python_root=args.target_python_root,
        demo_telemetry=args.demo_telemetry,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "profile_match": report["comparison"]["profile_match"],
                "step_match": report["comparison"]["step_match"],
                "target_slots": report["target"]["observed_slots"],
                "demo_pending": report["demo"]["pending_count"],
                "duration_delta_seconds": report["comparison"][
                    "deployment_duration_delta_seconds"
                ],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
