from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path


def require_fresh(path: Path, max_age_seconds: float) -> None:
    if not path.is_file():
        raise RuntimeError(f"missing file: {path}")
    age = time.time() - path.stat().st_mtime
    if age > max_age_seconds:
        raise RuntimeError(f"stale file ({age:.1f}s): {path}")


def read_python(root: Path, max_age_seconds: float) -> dict[str, object]:
    pointer_path = root / "current-session.json"
    if not pointer_path.is_file():
        raise RuntimeError(f"missing file: {pointer_path}")
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    heartbeat_path = root / pointer["session_id"] / "heartbeat.json"
    require_fresh(heartbeat_path, max_age_seconds)
    heartbeat = json.loads(heartbeat_path.read_text(encoding="utf-8"))

    if not heartbeat.get("healthy"):
        raise RuntimeError(f"Python collector unhealthy: {heartbeat.get('last_error')}")
    if heartbeat.get("stopped"):
        raise RuntimeError("Python collector reports stopped=true")
    if not heartbeat.get("read_only_verified"):
        raise RuntimeError("Python collector did not verify read-only mode")
    return heartbeat


def read_last_csv_row(path: Path) -> dict[str, str]:
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line]
    if len(lines) < 2:
        raise RuntimeError(f"heartbeat CSV has no data rows: {path}")
    return next(csv.DictReader([lines[0], lines[-1]]))


def read_mql(root: Path, max_age_seconds: float) -> dict[str, str]:
    heartbeat_paths = sorted(root.rglob("heartbeat-*.csv"))
    if not heartbeat_paths:
        raise RuntimeError(f"no MQL heartbeat files below {root}")
    heartbeat_path = max(heartbeat_paths, key=lambda path: path.stat().st_mtime)
    require_fresh(heartbeat_path, max_age_seconds)
    heartbeat = read_last_csv_row(heartbeat_path)

    if heartbeat.get("connected") != "1":
        raise RuntimeError("MQL observer reports connected=0")
    if heartbeat.get("trade_allowed") != "0":
        raise RuntimeError("MQL observer reports trade_allowed!=0")
    if int(heartbeat.get("dropped_transactions") or 0) != 0:
        raise RuntimeError("MQL observer has dropped transactions")
    return heartbeat


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--python-root", required=True, type=Path)
    parser.add_argument("--mql-root", required=True, type=Path)
    parser.add_argument("--max-age-seconds", type=float, default=20.0)
    args = parser.parse_args()

    python_status = read_python(args.python_root, args.max_age_seconds)
    mql_status = read_mql(args.mql_root, args.max_age_seconds)
    print(
        json.dumps(
            {
                "mql": {
                    "connected": int(mql_status["connected"]),
                    "dropped_transactions": int(
                        mql_status["dropped_transactions"]
                    ),
                    "orders": int(mql_status["orders_total"]),
                    "positions": int(mql_status["positions_total"]),
                    "trade_allowed": int(mql_status["trade_allowed"]),
                },
                "python": {
                    "healthy": bool(python_status["healthy"]),
                    "orders": int(python_status["orders_total"]),
                    "positions": int(python_status["positions_total"]),
                    "read_only_verified": bool(
                        python_status["read_only_verified"]
                    ),
                },
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
