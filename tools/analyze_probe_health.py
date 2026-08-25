from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from straddle_replica.probe_health import analyze_probe_health  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe-root", required=True, type=Path)
    parser.add_argument("--certification-started-utc", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)

    result = analyze_probe_health(
        args.probe_root,
        certification_started_utc=args.certification_started_utc,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "healthy": not result["operational_failures"],
                "operational_failures": result["operational_failures"],
                "output": str(args.output),
            },
            sort_keys=True,
        )
    )
    return 0 if not result["operational_failures"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
