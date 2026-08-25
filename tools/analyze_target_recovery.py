from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any, Iterable, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from straddle_replica.recovery_analysis import (
    CycleState,
    find_latest_30_cycles,
    find_recovery_episodes,
    reconstruct_cycle_state,
    recovery_level_volume_sequences,
)


UTC = timezone.utc


def _read_jsonl(paths: Iterable[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as error:
                    raise ValueError(
                        f"{path}:{line_number} is not valid JSON"
                    ) from error
                if not isinstance(value, dict):
                    raise ValueError(
                        f"{path}:{line_number} must contain a JSON object"
                    )
                rows.append(value)
    return rows


def _utc_iso(raw_msc: int, server_offset_seconds: int) -> str:
    return datetime.fromtimestamp(
        (raw_msc - server_offset_seconds * 1000) / 1000,
        tz=UTC,
    ).isoformat(timespec="milliseconds")


def _state_payload(state: CycleState) -> dict[str, Any]:
    return {
        "realized": state.realized,
        "unique_exit_deals": state.unique_exit_deals,
        "position_count": state.position_count,
        "gross_lots": state.gross_lots,
        "positions": [asdict(position) for position in state.positions],
    }


def build_report(
    orders: Sequence[dict[str, Any]],
    deals: Sequence[dict[str, Any]],
    *,
    magic: int,
    symbol: str,
    history_server_offset_seconds: int,
) -> dict[str, Any]:
    cycles = find_latest_30_cycles(
        orders,
        magic=magic,
        symbol=symbol,
    )
    episodes = find_recovery_episodes(orders, cycles)
    cycle_by_start = {
        cycle.started_msc: cycle
        for cycle in cycles
    }
    episode_payloads: list[dict[str, Any]] = []
    for episode in episodes:
        state = reconstruct_cycle_state(
            deals,
            cycle_started_msc=episode.cycle_started_msc,
            through_msc=episode.first_cancel_done_msc,
            magic=magic,
            symbol=symbol,
        )
        payload = asdict(episode)
        payload.update(
            {
                "cycle_started_utc": _utc_iso(
                    episode.cycle_started_msc,
                    history_server_offset_seconds,
                ),
                "first_cancel_done_utc": _utc_iso(
                    episode.first_cancel_done_msc,
                    history_server_offset_seconds,
                ),
                "first_double_setup_utc": _utc_iso(
                    episode.first_double_setup_msc,
                    history_server_offset_seconds,
                ),
                "last_double_setup_utc": _utc_iso(
                    episode.last_double_setup_msc,
                    history_server_offset_seconds,
                ),
                "replacement_levels": list(episode.replacement_levels),
                "state_at_first_cancel": _state_payload(state),
                "level_volume_sequences": {
                    key: list(value)
                    for key, value in recovery_level_volume_sequences(
                        orders,
                        episode,
                    ).items()
                },
            }
        )
        episode_payloads.append(payload)

    return {
        "schema_version": 1,
        "assessed_at_utc": datetime.now(tz=UTC).isoformat(),
        "magic": magic,
        "symbol": symbol,
        "history_server_offset_seconds": history_server_offset_seconds,
        "order_count": len(orders),
        "deal_count": len(deals),
        "exact_cycle_count": len(cycles),
        "recovery_episode_count": len(episodes),
        "cycles": [
            {
                **asdict(cycle),
                "started_utc": _utc_iso(
                    cycle.started_msc,
                    history_server_offset_seconds,
                ),
                "next_started_utc": (
                    _utc_iso(
                        cycle.next_started_msc,
                        history_server_offset_seconds,
                    )
                    if cycle.next_started_msc is not None
                    else None
                ),
            }
            for cycle in cycles
        ],
        "episodes": episode_payloads,
        "episode_cycle_coverage": (
            len(
                {
                    episode.cycle_started_msc
                    for episode in episodes
                    if episode.cycle_started_msc in cycle_by_start
                }
            )
            / len(cycles)
            if cycles
            else 0.0
        ),
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--orders", type=Path, action="append", required=True)
    parser.add_argument("--deals", type=Path, action="append", required=True)
    parser.add_argument("--magic", type=int, default=26011001)
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument(
        "--history-server-offset-seconds",
        type=int,
        default=0,
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    report = build_report(
        _read_jsonl(args.orders),
        _read_jsonl(args.deals),
        magic=args.magic,
        symbol=args.symbol,
        history_server_offset_seconds=args.history_server_offset_seconds,
    )
    if args.output is not None:
        _write_json(args.output, report)
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
