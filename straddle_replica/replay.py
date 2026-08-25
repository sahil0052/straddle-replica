from __future__ import annotations

from datetime import datetime, timedelta

from .compare import Event
from .profiles import StrategyProfile, build_grid


def build_deployment_events(
    profile: StrategyProfile,
    anchor: float,
    tick_size: float,
    start: datetime,
    inter_order_delay_ms: int,
    atr_value: float | None = None,
) -> list[Event]:
    if inter_order_delay_ms < 1:
        raise ValueError("Inter-order delay must be positive")
    events: list[Event] = []
    for index, order in enumerate(
        build_grid(profile, anchor, tick_size, atr_value=atr_value)
    ):
        events.append(
            Event(
                time=start
                + timedelta(milliseconds=index * inter_order_delay_ms),
                kind="pending",
                comment=order.comment,
                side=order.side,
                volume=order.volume,
                price=order.price,
            )
        )
    return events
