from __future__ import annotations

import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Mapping


CERTIFICATION_KEYS = (
    "account_server",
    "account_leverage",
    "account_currency",
    "account_margin_mode",
    "account_limit_orders",
    "symbol",
    "symbol_digits",
    "symbol_tick_size",
    "symbol_tick_value",
    "symbol_tick_value_profit",
    "symbol_tick_value_loss",
    "symbol_contract_size",
    "symbol_volume_min",
    "symbol_volume_max",
    "symbol_volume_step",
    "symbol_stops_level",
    "symbol_freeze_level",
    "symbol_filling_mode",
    "symbol_swap_mode",
    "symbol_swap_long",
    "symbol_swap_short",
    "symbol_swap_rollover3days",
)


def _load(source: Mapping[str, object] | Path) -> dict[str, str]:
    if isinstance(source, Path):
        with source.open(encoding="utf-8-sig", newline="") as handle:
            return {
                str(row["key"]): str(row["value"])
                for row in csv.DictReader(handle)
            }
    return {str(key): str(value) for key, value in source.items()}


def _equivalent(left: str | None, right: str | None) -> bool:
    if left is None or right is None:
        return left is right
    if left == right:
        return True
    try:
        return Decimal(left) == Decimal(right)
    except InvalidOperation:
        return False


def compare_account_terms(
    target_source: Mapping[str, object] | Path,
    demo_source: Mapping[str, object] | Path,
) -> dict:
    target = _load(target_source)
    demo = _load(demo_source)
    mismatches = {}
    for key in CERTIFICATION_KEYS:
        target_value = target.get(key)
        demo_value = demo.get(key)
        if not _equivalent(target_value, demo_value):
            mismatches[key] = {
                "target": target_value,
                "demo": demo_value,
            }
    return {
        "match": not mismatches,
        "checked_keys": sorted(CERTIFICATION_KEYS),
        "mismatches": mismatches,
    }
