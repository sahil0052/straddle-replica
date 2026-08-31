from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum


class ProfileName(str, Enum):
    HISTORICAL_50 = "HISTORICAL_50"
    HISTORICAL_60 = "HISTORICAL_60"
    AGGRESSIVE_30 = "AGGRESSIVE_30"
    LOW_RISK_30 = "LOW_RISK_30"
    LATEST_30 = "LATEST_30"


class StepMode(str, Enum):
    FIXED = "FIXED"
    ANCHOR_DIVISOR = "ANCHOR_DIVISOR"
    ATR = "ATR"


@dataclass(frozen=True)
class LotTier:
    first_level: int
    last_level: int
    volume: float


@dataclass(frozen=True)
class StrategyProfile:
    name: ProfileName
    levels_per_side: int
    lot_tiers: tuple[LotTier, ...]
    step_mode: StepMode
    fixed_step: float | None = None
    anchor_divisor: float | None = None
    atr_timeframe_minutes: int | None = None
    atr_period: int | None = None
    atr_multiplier: float | None = None
    lock_trigger_steps: float = 2.0
    lock_offset_price: float = 0.2
    # DIV-4: the measured activation law, not a neutral default.  The false
    # branch writes the first stop at entry +/- lock_offset_price and only ever
    # improves it, so it forbids dir*(sl-open) < 0.20; ReportHistory-901018 puts
    # 351 of HISTORICAL_50's 4,094 and 1,068 of HISTORICAL_60's 7,952 S/L
    # positions strictly inside (0,0.20), min +0.01, with no atom at 0.20.  Every
    # profile below therefore activates at the trailing distance, and the default
    # matches so a profile added later inherits the law the target actually runs.
    # Mirrors mql5/include/ProfileCatalog.mqh ResetProfile().
    activation_uses_trailing_distance: bool = True
    pre_tighten_trail_distance_steps: float = 2.0
    tighten_trigger_steps: float = 3.0
    trail_distance_steps: float = 2.0
    cycle_target_balance_pct: float = 0.18
    cycle_target_money: float = 0.0
    cancel_before_close: bool = False
    deployment_fill_cooldown_seconds: int = 0
    close_interval_seconds: int = 0
    restart_delay_seconds: int = 3
    rearm_delay_seconds: int = 0
    stop_update_interval_seconds: int = 0
    max_stop_updates_per_pass: int = 0
    stop_scan_newest_first: bool = False
    stop_updates_on_timer: bool = False

    def lot_for_level(self, level: int) -> float:
        if not 1 <= level <= self.levels_per_side:
            raise ValueError(
                f"Level {level} is outside profile {self.name.value} "
                f"(1..{self.levels_per_side})"
            )
        for tier in self.lot_tiers:
            if tier.first_level <= level <= tier.last_level:
                return tier.volume
        raise ValueError(f"No lot tier configured for level {level}")

    def calculate_step(
        self,
        anchor: float,
        tick_size: float,
        atr_value: float | None = None,
    ) -> float:
        if anchor <= 0:
            raise ValueError("Anchor must be positive")
        if tick_size <= 0:
            raise ValueError("Tick size must be positive")
        if self.step_mode is StepMode.ANCHOR_DIVISOR:
            if not self.anchor_divisor:
                raise ValueError("Anchor divisor is not configured")
            raw_step = anchor / self.anchor_divisor
        elif self.step_mode is StepMode.ATR:
            if atr_value is None or atr_value <= 0:
                raise ValueError("A positive ATR value is required")
            if not self.atr_multiplier:
                raise ValueError("ATR multiplier is not configured")
            raw_step = atr_value * self.atr_multiplier
        else:
            if not self.fixed_step:
                raise ValueError("Fixed step is not configured")
            raw_step = self.fixed_step
        return normalize_price(raw_step, tick_size)


@dataclass(frozen=True)
class GridOrder:
    level: int
    side: str
    volume: float
    price: float
    comment: str

    @property
    def level_key(self) -> str:
        return f"{self.side[0].upper()}{self.level}"


def normalize_price(value: float, tick_size: float) -> float:
    if tick_size <= 0:
        raise ValueError("Tick size must be positive")
    decimal_value = Decimal(str(value))
    decimal_tick = Decimal(str(tick_size))
    ticks = (decimal_value / decimal_tick).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return float(ticks * decimal_tick)


def _tiers(*items: tuple[int, int, float]) -> tuple[LotTier, ...]:
    return tuple(LotTier(*item) for item in items)


_PROFILES = {
    ProfileName.HISTORICAL_50: StrategyProfile(
        name=ProfileName.HISTORICAL_50,
        levels_per_side=50,
        lot_tiers=_tiers((1, 15, 0.01), (16, 25, 0.03), (26, 50, 0.06)),
        step_mode=StepMode.ATR,
        atr_timeframe_minutes=15,
        atr_period=17,
        atr_multiplier=0.10422410545583288,
        # DIV-4, measured on 4,094 S/L positions (see the dataclass default).
        # trail_distance_steps is deliberately left at 2.0 so it equals
        # pre_tighten_trail_distance_steps and the ratchet collapses to a
        # single-stage 2.0-step trail -- band [1,2) occupancy 23.23%, which is
        # what this era's tape shows.  Do not copy 1.0 in from LATEST_30.
        activation_uses_trailing_distance=True,
        # DIV-6, measured on ReportHistory-901018's 271 terminal liquidations:
        # 259 are strictly cancel-first, 1 is close-first and 11 interleave, and
        # every exception sits beside a `close by` (PositionCloseBy) order, i.e. a
        # hand flatten.  This era alone is 95/95.  The dataclass default is False
        # for hygiene, so all four legacy profiles have to opt in explicitly --
        # the same repair applied to mql5/include/ProfileCatalog.mqh.
        cancel_before_close=True,
        cycle_target_balance_pct=0.63,
    ),
    ProfileName.HISTORICAL_60: StrategyProfile(
        name=ProfileName.HISTORICAL_60,
        levels_per_side=60,
        lot_tiers=_tiers((1, 15, 0.01), (16, 45, 0.02), (46, 60, 0.05)),
        step_mode=StepMode.ATR,
        atr_timeframe_minutes=5,
        atr_period=44,
        atr_multiplier=0.09188197447190301,
        # DIV-4, measured on 7,952 S/L positions; single-stage trail as above
        # (band [1,2) occupancy 23.04%, neighbour-density ratio 0.920).
        activation_uses_trailing_distance=True,
        # DIV-6, largest cohort: 72 liquidations, 71 cancel-first, and the one
        # close-first cycle (169) is a hand flatten.  Operator-free: 71/71.
        cancel_before_close=True,
        cycle_target_balance_pct=0.42,
    ),
    ProfileName.AGGRESSIVE_30: StrategyProfile(
        name=ProfileName.AGGRESSIVE_30,
        levels_per_side=30,
        lot_tiers=_tiers((1, 10, 0.08), (11, 20, 0.41), (21, 30, 0.82)),
        step_mode=StepMode.ANCHOR_DIVISOR,
        anchor_divisor=6000.0,
        trail_distance_steps=1.0,
        # DIV-4 by parsimony: 2 deployments over ~90 minutes on 2026.07.13, 29
        # S/L positions -- no falsifying power of its own, but the eras either
        # side of it demand this branch on 7,952 and 2,809 positions.
        activation_uses_trailing_distance=True,
        # DIV-6 by parsimony: this era authored exactly one liquidation of its own
        # (cycle 170, cancel-first); cycle 171 is a hand flatten.
        cancel_before_close=True,
        cycle_target_balance_pct=0.18,
    ),
    ProfileName.LOW_RISK_30: StrategyProfile(
        name=ProfileName.LOW_RISK_30,
        levels_per_side=30,
        lot_tiers=_tiers((1, 10, 0.01), (11, 20, 0.02), (21, 30, 0.05)),
        step_mode=StepMode.ANCHOR_DIVISOR,
        anchor_divisor=3000.0,
        trail_distance_steps=1.0,
        # DIV-4 by parsimony, as AGGRESSIVE_30; this era's band [1,2) is 0/29,
        # the same two-stage trough LATEST_30 shows.
        activation_uses_trailing_distance=True,
        # DIV-6: its single liquidation is cancel-first (1/1, no operator marker).
        cancel_before_close=True,
        cycle_target_balance_pct=0.18,
    ),
    ProfileName.LATEST_30: StrategyProfile(
        name=ProfileName.LATEST_30,
        levels_per_side=30,
        lot_tiers=_tiers((1, 10, 0.01), (11, 20, 0.06), (21, 30, 0.15)),
        step_mode=StepMode.ANCHOR_DIVISOR,
        anchor_divisor=3000.0,
        trail_distance_steps=1.0,
        activation_uses_trailing_distance=True,
        cycle_target_balance_pct=0.18,
        cycle_target_money=30.0,
        cancel_before_close=True,
        deployment_fill_cooldown_seconds=20,
        close_interval_seconds=20,
        restart_delay_seconds=20,
        rearm_delay_seconds=20,
        stop_scan_newest_first=True,
        max_stop_updates_per_pass=1,
        stop_updates_on_timer=True,
    ),
}


def get_profile(name: ProfileName | str) -> StrategyProfile:
    return _PROFILES[ProfileName(name)]


def build_grid(
    profile: StrategyProfile,
    anchor: float,
    tick_size: float,
    atr_value: float | None = None,
) -> list[GridOrder]:
    step = profile.calculate_step(anchor, tick_size, atr_value=atr_value)
    orders: list[GridOrder] = []
    for level in range(1, profile.levels_per_side + 1):
        volume = profile.lot_for_level(level)
        orders.append(
            GridOrder(
                level=level,
                side="buy",
                volume=volume,
                price=normalize_price(anchor + level * step, tick_size),
                comment=f"STR B{level}",
            )
        )
        orders.append(
            GridOrder(
                level=level,
                side="sell",
                volume=volume,
                price=normalize_price(anchor - level * step, tick_size),
                comment=f"STR S{level}",
            )
        )
    return orders
