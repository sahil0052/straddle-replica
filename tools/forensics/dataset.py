"""Cycle reconstruction from the golden CSV export of ReportHistory-901018.xlsx.

A "cycle" is one full lifecycle of the Target EA basket:
    deployment burst (>=40 STR pendings placed in seconds)
        -> fills / trailing stop-outs / lattice re-arms
        -> basket liquidation (all positions closed, pendings cancelled)
        -> next deployment burst

Everything here is derived from the report only; no assumptions about our
replica's configuration leak into the reconstruction.
"""
from __future__ import annotations

import csv
import os
import re
import statistics
from bisect import bisect_right
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# Default is the Target's export.  GOLDEN_DIR redirects the whole loader at
# another directory written in the same schema -- which is how 111638511's own
# API history (see fresh_to_golden.py, output .cache/fresh/) is measured by the
# very same scripts, instead of by a parallel set of bespoke ones that would have
# to be trusted separately.  Nothing else in this module changes, so a script
# cannot tell which account it is reading and cannot special-case ours.
_DEFAULT_GOLDEN = Path(__file__).resolve().parents[2] / ".cache" / "golden"
GOLDEN = Path(os.environ.get("GOLDEN_DIR") or _DEFAULT_GOLDEN)
GRID_RE = re.compile(r"^STR ([BS])(\d+)$")
CONTRACT = 100.0  # XAUUSD: 1.00 lot = 100 oz, so profit = dprice * volume * 100

# Final production regime boundary, per AGENTS.md (verified in regimes.py).
FINAL_REGIME_START = datetime(2026, 7, 14)


def _dt(raw: str) -> datetime | None:
    if not raw:
        return None
    return datetime.fromisoformat(raw)


def _f(raw: str) -> float | None:
    return float(raw) if raw not in ("", None) else None


def _ff(raw: str, default: float = 0.0) -> float:
    v = _f(raw)
    return default if v is None else v


@dataclass
class Order:
    row: int
    open_time: datetime
    order_id: int
    order_type: str
    volume: float
    filled_volume: float
    price: float | None
    end_time: datetime | None
    state: str | None
    comment: str | None
    side: str | None = None     # 'B' | 'S'
    level: int | None = None
    cycle: int = -1

    @property
    def is_grid(self) -> bool:
        return self.side is not None


@dataclass
class Position:
    row: int
    open_time: datetime
    position_id: int
    side: str                   # 'buy' | 'sell'
    volume: float
    open_price: float
    stop_loss: float | None
    take_profit: float | None
    close_time: datetime | None
    close_price: float | None
    commission: float
    swap: float
    profit: float
    comment: str | None
    grid_side: str | None = None
    level: int | None = None
    cycle: int = -1
    is_open: bool = False

    @property
    def dir(self) -> float:
        return 1.0 if self.side == "buy" else -1.0

    @property
    def net(self) -> float:
        return self.profit + self.commission + self.swap


@dataclass
class Deal:
    row: int
    time: datetime
    deal_id: int
    deal_type: str
    direction: str | None
    volume: float
    price: float | None
    order_id: int | None
    commission: float
    fee: float
    swap: float
    profit: float
    balance: float
    comment: str | None


@dataclass
class Cycle:
    index: int
    start: datetime                     # first pending of the deployment burst
    burst_end: datetime                 # last pending of the deployment burst
    end: datetime | None = None         # start of the next burst (exclusive bound)
    anchor: float = 0.0
    step: float = 0.0
    levels_per_side: int = 0
    lattice: dict[tuple[str, int], float] = field(default_factory=dict)
    burst_orders: list[Order] = field(default_factory=list)
    orders: list[Order] = field(default_factory=list)
    positions: list[Position] = field(default_factory=list)

    def lattice_price(self, side: str, level: int) -> float | None:
        return self.lattice.get((side, level))

    @property
    def realized(self) -> float:
        return sum(p.net for p in self.positions if not p.is_open)

    @property
    def flat_time(self) -> datetime | None:
        closes = [p.close_time for p in self.positions if p.close_time]
        return max(closes) if closes else None


def load_orders() -> list[Order]:
    out: list[Order] = []
    with (GOLDEN / "orders.csv").open(newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            o = Order(
                row=int(r["row"]),
                open_time=_dt(r["open_time"]),
                order_id=int(r["order_id"]),
                order_type=r["order_type"],
                volume=_ff(r["volume"]),
                filled_volume=_ff(r["filled_volume"]),
                price=_f(r["price"]),
                end_time=_dt(r["end_time"]),
                state=r["state"] or None,
                comment=r["comment"] or None,
            )
            m = GRID_RE.fullmatch(o.comment or "")
            if m:
                o.side, o.level = m.group(1), int(m.group(2))
            out.append(o)
    with (GOLDEN / "working_orders.csv").open(newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            o = Order(
                row=int(r["row"]),
                open_time=_dt(r["open_time"]),
                order_id=int(r["order_id"]),
                order_type=r["order_type"],
                volume=_ff(r["volume"]),
                filled_volume=_ff(r["filled_volume"]),
                price=_f(r["price"]),
                end_time=None,
                state=r["state"] or None,
                comment=r["comment"] or None,
            )
            m = GRID_RE.fullmatch(o.comment or "")
            if m:
                o.side, o.level = m.group(1), int(m.group(2))
            out.append(o)
    out.sort(key=lambda o: (o.open_time, o.order_id))
    return out


def load_positions() -> list[Position]:
    out: list[Position] = []
    for name, is_open in (("positions.csv", False), ("open_positions.csv", True)):
        with (GOLDEN / name).open(newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                p = Position(
                    row=int(r["row"]),
                    open_time=_dt(r["open_time"]),
                    position_id=int(r["position_id"]),
                    side=r["side"],
                    volume=_ff(r["volume"]),
                    open_price=_ff(r["open_price"]),
                    stop_loss=_f(r["stop_loss"]),
                    take_profit=_f(r["take_profit"]),
                    close_time=_dt(r["close_time"]),
                    close_price=_f(r["close_price"]),
                    commission=_ff(r["commission"]),
                    swap=_ff(r["swap"]),
                    profit=_ff(r["profit"]),
                    comment=r["comment"] or None,
                    is_open=is_open,
                )
                m = GRID_RE.fullmatch(p.comment or "")
                if m:
                    p.grid_side, p.level = m.group(1), int(m.group(2))
                out.append(p)
    out.sort(key=lambda p: (p.open_time, p.position_id))
    return out


def load_deals() -> list[Deal]:
    out: list[Deal] = []
    with (GOLDEN / "deals.csv").open(newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out.append(
                Deal(
                    row=int(r["row"]),
                    time=_dt(r["time"]),
                    deal_id=int(r["deal_id"]),
                    deal_type=r["deal_type"],
                    direction=r["direction"] or None,
                    volume=_ff(r["volume"]),
                    price=_f(r["price"]),
                    order_id=int(float(r["order_id"])) if r["order_id"] else None,
                    commission=_ff(r["commission"]),
                    fee=_ff(r["fee"]),
                    swap=_ff(r["swap"]),
                    profit=_ff(r["profit"]),
                    balance=_ff(r["balance"]),
                    comment=r["comment"] or None,
                )
            )
    out.sort(key=lambda d: (d.time, d.deal_id))
    return out


def _burst_clusters(grid: list[Order], gap_seconds: float = 45.0,
                    min_size: int = 40) -> list[list[Order]]:
    """A deployment burst is a dense run of *first-time* level placements.

    The Target EA deploys the whole lattice in one sweep (both sides, levels
    ascending).  Re-arms are single orders scattered in time, so we detect a
    burst as a run in which >=min_size DISTINCT (side, level) keys appear with
    no inter-order gap larger than gap_seconds.
    """
    clusters: list[list[Order]] = []
    run: list[Order] = []
    for o in grid:
        if run and (o.open_time - run[-1].open_time).total_seconds() > gap_seconds:
            clusters.append(run)
            run = []
        run.append(o)
    if run:
        clusters.append(run)

    bursts: list[list[Order]] = []
    for run in clusters:
        keys = {(o.side, o.level) for o in run}
        if len(keys) < min_size:
            continue
        # Trim the run to the contiguous prefix that constitutes the sweep:
        # stop at the first repeat of an already-seen (side, level).
        seen: set[tuple[str, int]] = set()
        sweep: list[Order] = []
        for o in run:
            key = (o.side, o.level)
            if key in seen:
                break
            seen.add(key)
            sweep.append(o)
        if len({(o.side, o.level) for o in sweep}) >= min_size:
            bursts.append(sweep)
    return bursts


def _fit_lattice(sweep: list[Order]) -> tuple[float, float, dict[tuple[str, int], float]]:
    lattice = {(o.side, o.level): o.price for o in sweep if o.price is not None}
    diffs: list[float] = []
    for side in ("B", "S"):
        pts = sorted(((lv, pr) for (sd, lv), pr in lattice.items() if sd == side))
        for (l0, p0), (l1, p1) in zip(pts, pts[1:]):
            if l1 - l0 != 1:
                continue
            d = (p1 - p0) if side == "B" else (p0 - p1)
            if d > 0:
                diffs.append(d)
    step = statistics.median(diffs) if diffs else 0.0
    anchors = [
        (pr - lv * step) if sd == "B" else (pr + lv * step)
        for (sd, lv), pr in lattice.items()
    ]
    anchor = statistics.median(anchors) if anchors else 0.0
    return anchor, step, lattice


def build_cycles(orders: list[Order], positions: list[Position]) -> list[Cycle]:
    grid = [o for o in orders if o.is_grid and o.price is not None]
    bursts = _burst_clusters(grid)

    cycles: list[Cycle] = []
    for i, sweep in enumerate(bursts):
        anchor, step, lattice = _fit_lattice(sweep)
        cycles.append(
            Cycle(
                index=i,
                start=sweep[0].open_time,
                burst_end=sweep[-1].open_time,
                anchor=round(anchor, 6),
                step=round(step, 6),
                levels_per_side=max(lv for _, lv in lattice),
                lattice=lattice,
                burst_orders=sweep,
            )
        )
    for a, b in zip(cycles, cycles[1:]):
        a.end = b.start

    starts = [c.start for c in cycles]

    def which(ts: datetime) -> int:
        i = bisect_right(starts, ts) - 1
        return i if i >= 0 else -1

    for o in orders:
        o.cycle = which(o.open_time)
        if o.cycle >= 0:
            cycles[o.cycle].orders.append(o)
    for p in positions:
        p.cycle = which(p.open_time)
        if p.cycle >= 0:
            cycles[p.cycle].positions.append(p)
    return cycles


def load_all() -> tuple[list[Order], list[Position], list[Deal], list[Cycle]]:
    orders = load_orders()
    positions = load_positions()
    deals = load_deals()
    cycles = build_cycles(orders, positions)
    return orders, positions, deals, cycles


def final_regime(cycles: list[Cycle]) -> list[Cycle]:
    return [c for c in cycles if c.start >= FINAL_REGIME_START]
