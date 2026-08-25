"""Shared loaders for the extracted report CSVs (final-regime filtered).

All downstream tools (fidelity, replay, diff, hypothesis tests) consume these
typed records instead of re-parsing the raw report themselves.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import datetime

REGIME_CUT = datetime(2026, 7, 14)
STR_COMMENT = re.compile(r"STR ([BS])(\d+)$")
DIVISOR = 3000.0
XAU_USD_PER_POINT_PER_LOT = 100.0

_TIME_FORMATS = ("%Y.%m.%d %H:%M:%S.%f", "%Y.%m.%d %H:%M:%S", "%Y.%m.%d %H:%M")


def parse_time(s: str) -> datetime:
    s = s.strip()
    for fmt in _TIME_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError(f"unparseable report time: {s!r}")


@dataclass
class Position:
    open_t: datetime
    pos_id: int
    typ: str  # 'buy' | 'sell'
    vol: float
    open_p: float
    sl: float | None
    tp: float | None
    close_t: datetime
    close_p: float
    profit: float


@dataclass
class Order:
    t: datetime
    order_id: int
    typ: str  # e.g. 'buy stop'
    vol: str
    price: float | None
    state: str
    side: str  # 'B' | 'S'
    lvl: int


@dataclass
class EntryDeal:
    t: datetime
    price: float
    side: str
    lvl: int
    vol: float


def load_positions(path: str, regime_cut: datetime | None = REGIME_CUT) -> list[Position]:
    out: list[Position] = []
    with open(path) as f:
        r = csv.reader(f)
        next(r)
        for row in r:
            try:
                t = parse_time(row[0])
            except ValueError:
                continue
            if regime_cut and t < regime_cut:
                continue
            out.append(
                Position(
                    open_t=t,
                    pos_id=int(row[1]),
                    typ=row[3],
                    vol=float(row[4]),
                    open_p=float(row[5]),
                    sl=float(row[6]) if row[6] else None,
                    tp=float(row[7]) if row[7] else None,
                    close_t=parse_time(row[8]),
                    close_p=float(row[9]),
                    profit=float(row[12] or 0),
                )
            )
    out.sort(key=lambda p: p.open_t)
    return out


def load_orders(path: str, regime_cut: datetime | None = REGIME_CUT) -> list[Order]:
    out: list[Order] = []
    with open(path) as f:
        r = csv.reader(f)
        next(r)
        for row in r:
            try:
                t = parse_time(row[0])
            except ValueError:
                continue
            if regime_cut and t < regime_cut:
                continue
            m = STR_COMMENT.match((row[11] or "").strip())
            if not m:
                continue
            out.append(
                Order(
                    t=t,
                    order_id=int(row[1]),
                    typ=row[3],
                    vol=row[4],
                    price=float(row[5]) if row[5] else None,
                    state=row[9],
                    side=m.group(1),
                    lvl=int(m.group(2)),
                )
            )
    out.sort(key=lambda o: o.t)
    return out


def load_entry_deals(path: str, regime_cut: datetime | None = REGIME_CUT) -> list[EntryDeal]:
    out: list[EntryDeal] = []
    with open(path) as f:
        r = csv.reader(f)
        next(r)
        for row in r:
            m = STR_COMMENT.match((row[13] or "").strip())
            if not m or row[4] != "in":
                continue
            try:
                t = parse_time(row[0])
            except ValueError:
                continue
            if regime_cut and t < regime_cut:
                continue
            out.append(EntryDeal(t=t, price=float(row[6]), side=m.group(1), lvl=int(m.group(2)), vol=float(row[5])))
    out.sort(key=lambda d: d.t)
    return out


def load_balance_timeline(path: str) -> list[tuple[datetime, float]]:
    """Running balance column from the Deals section (all history)."""
    out: list[tuple[datetime, float]] = []
    with open(path) as f:
        r = csv.reader(f)
        next(r)
        for row in r:
            if not row[12]:
                continue
            try:
                out.append((parse_time(row[0]), float(row[12])))
            except ValueError:
                continue
    out.sort(key=lambda x: x[0])
    return out


def segment_cycles(positions: list[Position]) -> list[tuple[list[Position], datetime]]:
    """Split positions into cycles at flat (zero open positions) instants."""
    events: list[tuple[datetime, int, Position]] = []
    for p in positions:
        events.append((p.open_t, 1, p))
        events.append((p.close_t, -1, p))
    events.sort(key=lambda e: (e[0], -e[1]))
    open_ct = 0
    cycles: list[tuple[list[Position], datetime]] = []
    cur: list[Position] = []
    for t, d, p in events:
        open_ct += d
        if d == 1:
            cur.append(p)
        if open_ct == 0:
            cycles.append((cur, t))
            cur = []
    return cycles


def find_deployment_bursts(orders: list[Order], gap_seconds: float = 30.0, min_size: int = 30):
    """Group orders into bursts; bursts >= min_size are full grid deployments."""
    if not orders:
        return [], []
    bursts: list[list[Order]] = []
    cur = [orders[0]]
    for o in orders[1:]:
        if (o.t - cur[-1].t).total_seconds() <= gap_seconds:
            cur.append(o)
        else:
            bursts.append(cur)
            cur = [o]
    bursts.append(cur)
    deployments = [b for b in bursts if len(b) >= min_size]
    rearms = [b for b in bursts if len(b) < min_size]
    return deployments, rearms
