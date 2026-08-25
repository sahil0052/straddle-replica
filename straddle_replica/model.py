from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from .profiles import GridOrder, StrategyProfile, build_grid, normalize_price


class CycleState(str, Enum):
    IDLE = "IDLE"
    DEPLOYING = "DEPLOYING"
    RUNNING = "RUNNING"
    CLOSING = "CLOSING"
    CANCELING = "CANCELING"
    RESTARTING = "RESTARTING"


@dataclass(frozen=True)
class Tick:
    time: datetime
    bid: float
    ask: float

    @property
    def midpoint(self) -> float:
        return (self.bid + self.ask) / 2


@dataclass(frozen=True)
class ScheduledOrder:
    scheduled_at: datetime
    level_key: str
    side: str
    volume: float
    price: float
    comment: str


@dataclass
class PositionState:
    level_key: str
    ticket: int
    side: str
    entry_price: float
    volume: float
    stop_loss: float | None = None


class CycleEngine:
    def __init__(
        self,
        profile: StrategyProfile,
        tick_size: float,
        inter_order_delay_ms: int = 100,
    ) -> None:
        if tick_size <= 0:
            raise ValueError("Tick size must be positive")
        if inter_order_delay_ms < 1:
            raise ValueError("Inter-order delay must be positive")
        self.profile = profile
        self.tick_size = tick_size
        self.inter_order_delay_ms = inter_order_delay_ms
        self.state = CycleState.IDLE
        self.anchor: float | None = None
        self.step: float | None = None
        self._grid: dict[str, GridOrder] = {}
        self._positions: dict[str, PositionState] = {}

    def start_cycle(
        self, tick: Tick, atr_value: float | None = None
    ) -> list[ScheduledOrder]:
        if self.state is not CycleState.IDLE:
            raise RuntimeError(f"Cannot start cycle from {self.state.value}")
        self.anchor = normalize_price(tick.midpoint, self.tick_size)
        self.step = self.profile.calculate_step(
            self.anchor, self.tick_size, atr_value=atr_value
        )
        grid = build_grid(
            self.profile,
            self.anchor,
            self.tick_size,
            atr_value=atr_value,
        )
        self._grid = {order.level_key: order for order in grid}
        self._positions.clear()
        self.state = CycleState.DEPLOYING
        return [
            ScheduledOrder(
                scheduled_at=tick.time
                + timedelta(milliseconds=index * self.inter_order_delay_ms),
                level_key=order.level_key,
                side=order.side,
                volume=order.volume,
                price=order.price,
                comment=order.comment,
            )
            for index, order in enumerate(grid)
        ]

    def mark_deployment_complete(self) -> None:
        if self.state is not CycleState.DEPLOYING:
            raise RuntimeError("Deployment is not active")
        self.state = CycleState.RUNNING

    def on_level_filled(
        self, level_key: str, ticket: int, fill_price: float
    ) -> PositionState:
        if self.state is not CycleState.RUNNING:
            raise RuntimeError("Cycle is not running")
        order = self._grid[level_key]
        position = PositionState(
            level_key=level_key,
            ticket=ticket,
            side=order.side,
            entry_price=fill_price,
            volume=order.volume,
        )
        self._positions[level_key] = position
        return position

    def on_position_closed(self, level_key: str, ticket: int) -> GridOrder:
        position = self._positions.get(level_key)
        if position is None or position.ticket != ticket:
            raise KeyError(f"Unknown position {level_key}/{ticket}")
        del self._positions[level_key]
        return self._grid[level_key]

    def next_stop(
        self, position: PositionState, market_price: float, step: float
    ) -> float | None:
        if step <= 0:
            raise ValueError("Step must be positive")
        direction = 1.0 if position.side == "buy" else -1.0
        favorable_steps = (
            direction * (market_price - position.entry_price) / step
        )
        if favorable_steps < self.profile.lock_trigger_steps:
            return None

        if position.stop_loss is None:
            if self.profile.activation_uses_trailing_distance:
                desired = market_price - (
                    direction
                    * self.profile.pre_tighten_trail_distance_steps
                    * step
                )
            else:
                desired = position.entry_price + (
                    direction * self.profile.lock_offset_price
                )
        else:
            trail_distance_steps = (
                self.profile.trail_distance_steps
                if favorable_steps >= self.profile.tighten_trigger_steps
                else self.profile.pre_tighten_trail_distance_steps
            )
            desired = market_price - (
                direction * trail_distance_steps * step
            )

        desired = normalize_price(desired, self.tick_size)
        if position.stop_loss is None:
            return desired
        if position.side == "buy" and desired > position.stop_loss:
            return desired
        if position.side == "sell" and desired < position.stop_loss:
            return desired
        return None

    def begin_close(self) -> CycleState:
        if self.state not in {CycleState.RUNNING, CycleState.DEPLOYING}:
            raise RuntimeError(f"Cannot close from {self.state.value}")
        self.state = (
            CycleState.CANCELING
            if self.profile.cancel_before_close
            else CycleState.CLOSING
        )
        return self.state

    def mark_positions_flat(self) -> CycleState:
        if self.state is not CycleState.CLOSING:
            raise RuntimeError("Cycle is not closing")
        self.state = (
            CycleState.RESTARTING
            if self.profile.cancel_before_close
            else CycleState.CANCELING
        )
        return self.state

    def mark_orders_canceled(self) -> CycleState:
        if self.state is not CycleState.CANCELING:
            raise RuntimeError("Orders are not being canceled")
        self.state = (
            CycleState.CLOSING
            if self.profile.cancel_before_close
            else CycleState.RESTARTING
        )
        return self.state

    def mark_restart_ready(self) -> CycleState:
        if self.state is not CycleState.RESTARTING:
            raise RuntimeError("Cycle is not restarting")
        self.state = CycleState.IDLE
        return self.state
