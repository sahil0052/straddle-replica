from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from straddle_replica.independent_cycle_archive import (  # noqa: E402
    IndependentCycleArchive,
    IndependentCycleArchiveConfig,
)
from straddle_replica.observer_adapter import (  # noqa: E402
    ObserverAdapterConfig,
    ObserverEventAdapter,
)


def _write_health(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    for attempt in range(20):
        try:
            os.replace(temporary, path)
            return
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(0.05)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--observer-root", required=True, type=Path)
    parser.add_argument("--observer-state", required=True, type=Path)
    parser.add_argument("--archive-state", required=True, type=Path)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--health", required=True, type=Path)
    parser.add_argument("--poll-ms", type=int, default=100)
    parser.add_argument(
        "--heartbeat-max-age-seconds",
        type=float,
        default=5.0,
    )
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    if args.poll_ms < 20:
        parser.error("--poll-ms must be at least 20")

    adapter = ObserverEventAdapter(
        ObserverAdapterConfig(
            observer_root=args.observer_root,
            state_path=args.observer_state,
            heartbeat_max_age_seconds=args.heartbeat_max_age_seconds,
        )
    )
    archive = IndependentCycleArchive(
        IndependentCycleArchiveConfig(
            state_path=args.archive_state,
            archive_path=args.archive,
        )
    )
    while True:
        result: dict[str, int] = {}
        try:
            result = archive.process_events(adapter.poll())
            _write_health(
                args.health,
                {
                    "status": "RUNNING",
                    "updated_at_utc": datetime.now(
                        tz=timezone.utc
                    ).isoformat(),
                    **result,
                },
            )
        except (
            FileNotFoundError,
            OSError,
            RuntimeError,
            json.JSONDecodeError,
        ) as error:
            _write_health(
                args.health,
                {
                    "status": "WAITING_FOR_TARGET",
                    "updated_at_utc": datetime.now(
                        tz=timezone.utc
                    ).isoformat(),
                    "error_type": type(error).__name__,
                    "error": str(error),
                },
            )
            if args.once:
                raise
        if args.once:
            print(json.dumps(result, sort_keys=True))
            return 0
        time.sleep(args.poll_ms / 1000.0)


if __name__ == "__main__":
    raise SystemExit(main())
