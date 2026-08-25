"""Deterministic re-implementation of the Target EA decision rules (final
regime, Jul 14-30) as identified by the forensic audit. This models ONLY the
strategy decisions — no MT5 plumbing — so hypotheses can be swapped in and
scored against the report by replay.py + diff.py.

Every rule constant is exposed through Config so the Phase 2 refinement loop
can grid-test hypothesis variants (anchor source, basket target formula,
recenter gating, rescue trigger formulation, SL granularity...).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

XAU_USD_PER_POINT_PER_LOT = 100.0
TICK_SIZE = 0.01


@dataclass
class Config:
    # lattice
    levels_per_side: int = 30
    anchor_divisor: float = 3000.0
    # lot tiers: (from_level, to_level, volume)
    lot_tiers: tuple = ((1, 10, 0.01), (11, 20, 0.06), (21, 30, 0.15))
    # trailing (SL ratchet equation)
    lock_trigger_steps: float = 2.0        # activation: favorable steps before first SL
    pre_tighten_trail_steps: float = 2.0   # trail distance before tighten
    tighten_trigger_steps: float = 3.0     # favorable steps at which trail tightens
    trail_distance_steps: float = 1.0      # tightened (final) trail distance
    # cycle exits
    cycle_target_money: float = 30.0
    recenter_distance_pts: float = 20.0
    recenter_soft_distance_pts: float = 15.0
    recenter_soft_realized: float = 50.0
    recenter_soft_net_floor: float = -20.0
    breakeven_realized: float = 200.0
    breakeven_net_floor: float = -10.0
    # trend rescue
    rescue_drawdown_money: float = 400.0
    rescue_volume_multiplier: float = 2.0
    # scheduling
    rearm_delay_seconds: float = 5.0
    # hypothesis hooks (Phase 2): anchor price source and basket-target formula
    anchor_source: str = "mid"             # 'mid' | 'bid' | 'ask' | 'last'
    basket_target_fn: Callable | None = None  # (balance) -> target; None = fixed

    def tier_volume(self, level: int) -> float:
        for lo, hi, vol in self.lot_tiers:
            if lo <= level <= hi:
                return vol
        raise ValueError(f"level {level} outside tier schedule")


@dataclass
class SimPosition:
    pos_id: int
    side: str            # 'B' | 'S'
    lvl: int
    vol: float
    open_t: object       # datetime
    open_p: float
    sl: float | None = None
    tightened: bool = False
    close_t: object = None
    close_p: float | None = None
    profit: float | None = None
    close_reason: str | None = None


@dataclass
class SimOrder:
    side: str
    lvl: int
    vol: float
    price: float
    placed_t: object
    state: str = "placed"  # placed | filled | canceled


@dataclass
class EngineState:
    anchor: float = 0.0
    step: float = 0.0
    cycle_index: int = 0
    cycle_start: object = None
    realized: float = 0.0
    rescue_armed: bool = False
    pending: dict = field(default_factory=dict)     # (side,lvl) -> SimOrder
    lattice: dict = field(default_factory=dict)     # (side,lvl) -> price (immutable per cycle)
    open_positions: list = field(default_factory=list)
    rearm_queue: list = field(default_factory=list)  # (due_time, side, lvl)


class Engine:
    """Tick-driven simulator. Feed process_tick(t, bid, ask); read .events."""

    def __init__(self, cfg: Config, start_balance: float):
        self.cfg = cfg
        self.balance = start_balance
        self.state: EngineState | None = None
        self.events: list[dict] = []   # report-schema event log
        self._next_pos_id = 1
        self._closing = False
        self._pending_redeploy = False

    # ---------------- event log ----------------
    def _emit(self, kind: str, t, **kw) -> None:
        self.events.append({"kind": kind, "t": t, "cycle": self.state.cycle_index if self.state else -1, **kw})

    # ---------------- lifecycle ----------------
    def deploy(self, t, bid: float, ask: float) -> None:
        cfg = self.cfg
        anchor = {"mid": (bid + ask) / 2.0, "bid": bid, "ask": ask, "last": bid}[cfg.anchor_source]
        st = EngineState()
        st.cycle_index = (self.state.cycle_index + 1) if self.state else 1
        st.anchor = anchor
        st.step = anchor / cfg.anchor_divisor
        st.cycle_start = t
        self.state = st
        self._closing = False
        self._pending_redeploy = False
        for lvl in range(1, cfg.levels_per_side + 1):
            for side in ("B", "S"):
                price = anchor + lvl * st.step if side == "B" else anchor - lvl * st.step
                price = round(price / TICK_SIZE) * TICK_SIZE
                st.lattice[(side, lvl)] = price
                self._place(t, side, lvl, cfg.tier_volume(lvl), price)
        self._emit("deploy", t, anchor=anchor, step=st.step)

    def _place(self, t, side: str, lvl: int, vol: float, price: float) -> None:
        st = self.state
        st.pending[(side, lvl)] = SimOrder(side=side, lvl=lvl, vol=vol, price=price, placed_t=t)
        self._emit("order_place", t, side=side, lvl=lvl, vol=vol, price=price)

    # ---------------- per tick ----------------
    def process_tick(self, t, bid: float, ask: float) -> None:
        if self.state is None:
            self.deploy(t, bid, ask)
            return
        if self._pending_redeploy:
            self.deploy(t, bid, ask)
            return
        st, cfg = self.state, self.cfg

        if not self._closing:
            self._fill_pendings(t, bid, ask)
            self._trail_stops(t, bid, ask)
        self._stop_out(t, bid, ask)
        if not self._closing:
            self._process_rearms(t, bid, ask)
            self._check_rescue(t, bid, ask)
            self._check_exits(t, bid, ask)
        elif not st.open_positions:
            self._pending_redeploy = True

    # ---------------- fills ----------------
    def _fill_pendings(self, t, bid: float, ask: float) -> None:
        st = self.state
        for key, order in list(st.pending.items()):
            side, lvl = key
            hit = (ask >= order.price) if side == "B" else (bid <= order.price)
            if not hit:
                continue
            del st.pending[key]
            fill = max(ask, order.price) if side == "B" else min(bid, order.price)
            pos = SimPosition(pos_id=self._next_pos_id, side=side, lvl=lvl, vol=order.vol, open_t=t, open_p=fill)
            self._next_pos_id += 1
            st.open_positions.append(pos)
            self._emit("fill", t, side=side, lvl=lvl, vol=order.vol, price=fill)

    # ---------------- SL ratchet ----------------
    def _trail_stops(self, t, bid: float, ask: float) -> None:
        st, cfg = self.state, self.cfg
        step = st.step
        for pos in st.open_positions:
            market = bid if pos.side == "B" else ask   # close side quote
            favorable = (market - pos.open_p) / step if pos.side == "B" else (pos.open_p - market) / step
            if favorable < cfg.lock_trigger_steps:
                continue
            if not pos.tightened and favorable >= cfg.tighten_trigger_steps:
                pos.tightened = True
            trail = cfg.trail_distance_steps if pos.tightened else cfg.pre_tighten_trail_steps
            new_sl = market - trail * step if pos.side == "B" else market + trail * step
            # never below entry (breakeven floor), monotonic ratchet only
            if pos.side == "B":
                new_sl = max(new_sl, pos.open_p)
                if pos.sl is None or new_sl > pos.sl:
                    pos.sl = round(new_sl / TICK_SIZE) * TICK_SIZE
            else:
                new_sl = min(new_sl, pos.open_p)
                if pos.sl is None or new_sl < pos.sl:
                    pos.sl = round(new_sl / TICK_SIZE) * TICK_SIZE

    def _stop_out(self, t, bid: float, ask: float) -> None:
        st, cfg = self.state, self.cfg
        for pos in list(st.open_positions):
            if pos.sl is None:
                continue
            market = bid if pos.side == "B" else ask
            hit = (market <= pos.sl) if pos.side == "B" else (market >= pos.sl)
            if not hit:
                continue
            self._close_position(t, pos, pos.sl, "sl")
            if not self._closing:
                due = t.timestamp() + cfg.rearm_delay_seconds
                st.rearm_queue.append((due, pos.side, pos.lvl))

    def _process_rearms(self, t, bid: float, ask: float) -> None:
        st, cfg = self.state, self.cfg
        remaining = []
        for due, side, lvl in st.rearm_queue:
            if t.timestamp() < due or (side, lvl) in st.pending:
                remaining.append((due, side, lvl))
                continue
            price = st.lattice[(side, lvl)]  # STATIC LATTICE — never re-anchored
            valid = (ask < price) if side == "B" else (bid > price)
            if not valid:
                remaining.append((due, side, lvl))  # wait for price to return
                continue
            self._place(t, side, lvl, cfg.tier_volume(lvl), price)
        st.rearm_queue = remaining

    # ---------------- rescue / exits ----------------
    def _floating(self, bid: float, ask: float) -> float:
        total = 0.0
        for pos in self.state.open_positions:
            market = bid if pos.side == "B" else ask
            d = (market - pos.open_p) if pos.side == "B" else (pos.open_p - market)
            total += d * pos.vol * XAU_USD_PER_POINT_PER_LOT
        return total

    def _check_rescue(self, t, bid: float, ask: float) -> None:
        st, cfg = self.state, self.cfg
        if st.rescue_armed:
            return
        floating = self._floating(bid, ask)
        if st.realized + floating <= -cfg.rescue_drawdown_money:
            st.rescue_armed = True
            self._emit("rescue_trigger", t, drawdown=st.realized + floating)
            for (side, lvl), order in list(st.pending.items()):
                order.vol = round(cfg.tier_volume(lvl) * cfg.rescue_volume_multiplier, 2)
                self._emit("order_modify", t, side=side, lvl=lvl, vol=order.vol, price=order.price)

    def _check_exits(self, t, bid: float, ask: float) -> None:
        st, cfg = self.state, self.cfg
        if not st.open_positions and not st.pending:
            return
        floating = self._floating(bid, ask)
        net = st.realized + floating
        target = cfg.basket_target_fn(self.balance) if cfg.basket_target_fn else cfg.cycle_target_money
        mid = (bid + ask) / 2.0
        dist = abs(mid - st.anchor)
        reason = None
        if net >= target:
            reason = "basket_target"
        elif dist >= cfg.recenter_distance_pts:
            reason = "grid_recenter"
        elif (
            st.realized >= cfg.recenter_soft_realized
            and net >= cfg.recenter_soft_net_floor
            and dist >= cfg.recenter_soft_distance_pts
        ):
            reason = "grid_recenter"
        elif st.rescue_armed and st.realized >= cfg.breakeven_realized and net >= cfg.breakeven_net_floor:
            reason = "rescue_breakeven"
        if reason is None:
            return
        self._begin_close(t, bid, ask, reason)

    def _begin_close(self, t, bid: float, ask: float, reason: str) -> None:
        st = self.state
        self._closing = True
        st.rearm_queue.clear()
        for (side, lvl), _ in list(st.pending.items()):
            del st.pending[(side, lvl)]
            self._emit("order_cancel", t, side=side, lvl=lvl)
        for pos in list(st.open_positions):
            market = bid if pos.side == "B" else ask
            self._close_position(t, pos, market, reason)
        self._emit("cycle_close", t, reason=reason, realized=st.realized)
        self._pending_redeploy = True

    def _close_position(self, t, pos: SimPosition, price: float, reason: str) -> None:
        st = self.state
        d = (price - pos.open_p) if pos.side == "B" else (pos.open_p - price)
        pos.profit = d * pos.vol * XAU_USD_PER_POINT_PER_LOT
        pos.close_t = t
        pos.close_p = price
        pos.close_reason = reason
        st.open_positions.remove(pos)
        st.realized += pos.profit
        self.balance += pos.profit
        self._emit(
            "close", t, side=pos.side, lvl=pos.lvl, vol=pos.vol,
            open_p=pos.open_p, close_p=price, profit=pos.profit, reason=reason,
        )
