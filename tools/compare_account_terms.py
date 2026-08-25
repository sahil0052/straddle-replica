from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from straddle_replica.account_terms import compare_account_terms  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--demo", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)

    result = compare_account_terms(args.target, args.demo)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "match": result["match"],
                "mismatch_count": len(result["mismatches"]),
                "output": str(args.output),
            },
            sort_keys=True,
        )
    )
    return 0 if result["match"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
