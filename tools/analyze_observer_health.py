from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from straddle_replica.observer_health import (  # noqa: E402
    analyze_observer_health,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", required=True, type=Path)
    parser.add_argument("--certification-started-utc", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)

    result = analyze_observer_health(
        args.session,
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
                "market_open_hours": result["market_open_hours"],
                "operational_failures": result["operational_failures"],
                "output": str(args.output),
            },
            sort_keys=True,
        )
    )
    return 0 if not result["operational_failures"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
