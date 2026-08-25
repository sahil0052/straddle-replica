from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping


EXIT_ENTRIES = {1, 2, 3}


@dataclass(frozen=True)
class CycleRealized:
    net: float
    unique_exit_deals: int
    duplicate_deal_tickets: tuple[int, ...]


def calculate_cycle_realized(
    deals: Iterable[Mapping[str, Any]],
    *,
    cycle_started_msc: int,
    magic: int,
    symbol: str,
) -> CycleRealized:
    seen: set[int] = set()
    duplicates: set[int] = set()
    total = 0.0
    accepted = 0
    for deal in deals:
        ticket = int(deal.get("ticket") or 0)
        if ticket <= 0:
            continue
        if ticket in seen:
            duplicates.add(ticket)
            continue
        seen.add(ticket)
        if int(deal.get("time_msc") or 0) < cycle_started_msc:
            continue
        if int(deal.get("magic") or 0) != magic:
            continue
        if str(deal.get("symbol") or "") != symbol:
            continue
        if int(deal.get("entry") or -1) not in EXIT_ENTRIES:
            continue
        accepted += 1
        total += sum(
            float(deal.get(field) or 0.0)
            for field in ("profit", "swap", "commission", "fee")
        )
    return CycleRealized(
        net=round(total, 10),
        unique_exit_deals=accepted,
        duplicate_deal_tickets=tuple(sorted(duplicates)),
    )
