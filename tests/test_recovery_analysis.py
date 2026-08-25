from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from straddle_replica.recovery_analysis import (
    find_latest_30_cycles,
    find_recovery_episodes,
    reconstruct_cycle_state,
    recovery_level_volume_sequences,
)


MAGIC = 26011001
SYMBOL = "XAUUSD"
ROOT = Path(__file__).resolve().parents[1]


def _base_volume(level: int) -> float:
    if level <= 10:
        return 0.01
    if level <= 20:
        return 0.06
    return 0.15


def _deployment(
    *,
    start_msc: int = 1_000,
    wrong_slot: str | None = None,
) -> list[dict[str, object]]:
    orders: list[dict[str, object]] = []
    ticket = 10_000
    for level in range(1, 31):
        for side in ("B", "S"):
            comment = f"STR {side}{level}"
            volume = _base_volume(level)
            if comment == wrong_slot:
                volume += 0.01
            price = 4_400.0 + level * 1.48 * (1 if side == "B" else -1)
            orders.append(
                {
                    "ticket": ticket,
                    "time_setup_msc": start_msc + len(orders) * 10,
                    "time_done_msc": start_msc + 1_000_000,
                    "comment": comment,
                    "magic": MAGIC,
                    "symbol": SYMBOL,
                    "type": 4 if side == "B" else 5,
                    "state": 1,
                    "volume_initial": volume,
                    "price_open": price,
                }
            )
            ticket += 1
    return orders


def test_latest_30_cycles_require_exact_sequence_and_lot_geometry() -> None:
    exact = _deployment()
    contaminated = _deployment(start_msc=2_000_000, wrong_slot="STR S11")

    cycles = find_latest_30_cycles([*exact, *contaminated])

    assert len(cycles) == 1
    assert cycles[0].started_msc == 1_000
    assert cycles[0].deployment_end_msc == 1_590
    assert cycles[0].anchor == pytest.approx(4_400.0)
    assert cycles[0].step == pytest.approx(1.48)


def test_cycle_state_ignores_every_deal_before_cycle_start() -> None:
    state = reconstruct_cycle_state(
        [
            {
                "ticket": 1,
                "time_msc": 999,
                "entry": 0,
                "type": 0,
                "magic": MAGIC,
                "symbol": SYMBOL,
                "position_id": 101,
                "volume": 9.99,
                "price": 4_300.0,
                "comment": "STR B30",
            },
            {
                "ticket": 2,
                "time_msc": 1_100,
                "entry": 0,
                "type": 0,
                "magic": MAGIC,
                "symbol": SYMBOL,
                "position_id": 102,
                "volume": 0.01,
                "price": 4_401.48,
                "comment": "STR B1",
            },
            {
                "ticket": 3,
                "time_msc": 1_200,
                "entry": 1,
                "type": 1,
                "magic": MAGIC,
                "symbol": SYMBOL,
                "position_id": 102,
                "volume": 0.01,
                "price": 4_402.0,
                "profit": 0.52,
                "swap": -0.01,
                "commission": -0.02,
                "fee": 0.0,
                "comment": "[sl 4402.00]",
            },
            {
                "ticket": 4,
                "time_msc": 1_300,
                "entry": 0,
                "type": 1,
                "magic": MAGIC,
                "symbol": SYMBOL,
                "position_id": 103,
                "volume": 0.06,
                "price": 4_398.52,
                "comment": "STR S1",
            },
        ],
        cycle_started_msc=1_000,
        through_msc=2_000,
        magic=MAGIC,
        symbol=SYMBOL,
    )

    assert state.realized == pytest.approx(0.49)
    assert state.position_count == 1
    assert state.gross_lots == pytest.approx(0.06)
    assert state.positions[0].comment == "STR S1"
    assert state.positions[0].position_id == 103


def test_recovery_episode_requires_same_price_multi_level_double_replacement() -> None:
    orders = _deployment()
    for row in orders:
        if row["comment"] in {"STR B3", "STR B4"}:
            row["state"] = 2
            row["time_done_msc"] = 4_900 if row["comment"] == "STR B4" else 5_000

    prices = {
        row["comment"]: row["price_open"]
        for row in orders
        if row["comment"] in {"STR B3", "STR B4"}
    }
    orders.extend(
        [
            {
                "ticket": 20_001,
                "time_setup_msc": 5_100,
                "time_done_msc": 7_000,
                "comment": "STR B3",
                "magic": MAGIC,
                "symbol": SYMBOL,
                "type": 4,
                "state": 4,
                "volume_initial": 0.02,
                "price_open": prices["STR B3"],
            },
            {
                "ticket": 20_002,
                "time_setup_msc": 5_200,
                "time_done_msc": 7_100,
                "comment": "STR B4",
                "magic": MAGIC,
                "symbol": SYMBOL,
                "type": 4,
                "state": 4,
                "volume_initial": 0.02,
                "price_open": prices["STR B4"],
            },
            {
                "ticket": 20_003,
                "time_setup_msc": 9_000,
                "time_done_msc": 9_500,
                "comment": "STR B2",
                "magic": MAGIC,
                "symbol": SYMBOL,
                "type": 4,
                "state": 4,
                "volume_initial": 0.02,
                "price_open": next(
                    row["price_open"]
                    for row in orders
                    if row["comment"] == "STR B2"
                ),
            },
        ]
    )

    cycles = find_latest_30_cycles(orders)
    episodes = find_recovery_episodes(orders, cycles)

    assert len(episodes) == 1
    assert episodes[0].side == "B"
    assert episodes[0].first_double_setup_msc == 5_100
    assert episodes[0].replacement_levels == (3, 4)
    assert episodes[0].volume_multiplier == pytest.approx(2.0)
    assert episodes[0].price_mismatch_count == 0


def test_recovery_volume_sequences_distinguish_reset_from_persistence() -> None:
    orders = _deployment()
    for row in orders:
        if row["comment"] in {"STR B3", "STR B4"}:
            row["state"] = 2
            row["time_done_msc"] = 4_900

    by_comment = {row["comment"]: row for row in orders}
    orders.extend(
        [
            {
                **deepcopy(by_comment["STR B3"]),
                "ticket": 30_001,
                "time_setup_msc": 5_100,
                "time_done_msc": 7_000,
                "volume_initial": 0.02,
            },
            {
                **deepcopy(by_comment["STR B4"]),
                "ticket": 30_002,
                "time_setup_msc": 5_200,
                "time_done_msc": 7_100,
                "volume_initial": 0.02,
            },
            {
                **deepcopy(by_comment["STR B2"]),
                "ticket": 30_003,
                "time_setup_msc": 6_000,
                "time_done_msc": 8_000,
                "volume_initial": 0.02,
            },
            {
                **deepcopy(by_comment["STR B3"]),
                "ticket": 30_004,
                "time_setup_msc": 8_100,
                "time_done_msc": 9_000,
                "volume_initial": 0.02,
            },
            {
                **deepcopy(by_comment["STR B2"]),
                "ticket": 30_005,
                "time_setup_msc": 9_100,
                "time_done_msc": 10_000,
                "volume_initial": 0.01,
            },
        ]
    )

    episode = find_recovery_episodes(
        orders,
        find_latest_30_cycles(orders),
    )[0]
    sequences = recovery_level_volume_sequences(orders, episode)

    assert sequences["STR B2"] == (2.0, 1.0)
    assert sequences["STR B3"] == (2.0, 2.0)


def test_recovery_analyzer_cli_writes_machine_readable_report(
    tmp_path: Path,
) -> None:
    from tools.analyze_target_recovery import main

    orders = _deployment()
    for row in orders:
        if row["comment"] in {"STR S15", "STR S16"}:
            row["state"] = 2
            row["time_done_msc"] = 4_900
    by_comment = {row["comment"]: row for row in orders}
    orders.extend(
        [
            {
                **deepcopy(by_comment["STR S15"]),
                "ticket": 40_001,
                "time_setup_msc": 5_100,
                "time_done_msc": 8_000,
                "volume_initial": 0.12,
            },
            {
                **deepcopy(by_comment["STR S16"]),
                "ticket": 40_002,
                "time_setup_msc": 5_200,
                "time_done_msc": 8_100,
                "volume_initial": 0.12,
            },
        ]
    )
    deals = [
        {
            "ticket": 50_001,
            "time_msc": 2_000,
            "entry": 0,
            "type": 0,
            "magic": MAGIC,
            "symbol": SYMBOL,
            "position_id": 60_001,
            "volume": 0.01,
            "price": 4_401.48,
            "comment": "STR B1",
        }
    ]
    orders_path = tmp_path / "orders.jsonl"
    deals_path = tmp_path / "deals.jsonl"
    output_path = tmp_path / "analysis.json"
    orders_path.write_text(
        "".join(json.dumps(row) + "\n" for row in orders),
        encoding="utf-8",
    )
    deals_path.write_text(
        "".join(json.dumps(row) + "\n" for row in deals),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "--orders",
                str(orders_path),
                "--deals",
                str(deals_path),
                "--output",
                str(output_path),
            ]
        )
        == 0
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["exact_cycle_count"] == 1
    assert payload["recovery_episode_count"] == 1
    assert payload["episodes"][0]["side"] == "S"
    assert payload["episodes"][0]["replacement_levels"] == [15, 16]
    assert payload["episodes"][0]["state_at_first_cancel"]["position_count"] == 1


def test_recovery_analyzer_runs_as_a_direct_tool_script() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "analyze_target_recovery.py"),
            "--help",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "--orders" in completed.stdout
