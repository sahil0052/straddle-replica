"""Q2a: the trend-rescue population, and what was TRUE at the decision instant.

The replica encodes the rescue trigger as a four-way conjunction (StraddleEngine
TrendRescueSide + HasTrendRescueBasePending):

    floating <= -trend_rescue_drawdown_money          (400.0)   [floating ONLY,
                                                                 not realized]
  AND |price - iClose(M15, 6 bars back)| >= trend_rescue_move_price   (20.0)
  AND >= trend_rescue_minimum_pending_levels base-volume pendings on the
      trend side                                                     (3)

All three are reconstructible from the report:

  floating       every position's open_time / open_price / volume / dir is known,
                 so the open set at t is exact and only the MARK is approximate.
  M15 move       bucket every price print into 15-minute bars, take the last
                 print in each bar as its close, look back 6 bars.
  base pendings  exact -- an order is pending on side S at t iff
                 open_time <= t < end_time and volume == tier lot.

This script does NOT test the rule yet.  It establishes the population and prints
the RAW value of each condition at the moment the Target EA actually acted, so the
threshold is read off the data instead of assumed.  q2b runs the lead-time test.

Rescue volume is 2x the tier lot: 0.02 (L1-10), 0.12 (L11-20), 0.30 (L21-30).
"""
from __future__ import annotations

import statistics
import sys
from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import datetime, timedelta

sys.path.insert(0, r"C:\websites\mt5 2")
from tools.forensics.dataset import load_all, FINAL_REGIME_START, CONTRACT  # noqa: E402

BREAK = datetime(2026, 7, 24, 12, 0, 0)
M15 = timedelta(minutes=15)
RESCUE_BARS = 6


def tier_lot(level: int) -> float:
    if level <= 10:
        return 0.01
    if level <= 20:
        return 0.06
    return 0.15


def is_base(o) -> bool:
    return abs(o.volume - tier_lot(o.level)) < 1e-9


def is_rescue(o) -> bool:
    return abs(o.volume - 2.0 * tier_lot(o.level)) < 1e-9


def regime(t: datetime) -> str:
    return "EARLY" if t < BREAK else "LATE"


def m15_floor(t: datetime) -> datetime:
    return t.replace(minute=(t.minute // 15) * 15, second=0, microsecond=0)


def main() -> None:
    orders, positions, deals, cycles = load_all()

    # ---------------------------------------------------------------- price map
    prints: list[tuple[datetime, float]] = []
    for p in positions:
        prints.append((p.open_time, p.open_price))
        if p.close_time and p.close_price:
            prints.append((p.close_time, p.close_price))
    prints.sort(key=lambda r: r[0])
    ptimes = [t for t, _ in prints]
    pvals = [v for _, v in prints]

    def price_at(t: datetime) -> float | None:
        i = bisect_right(ptimes, t) - 1
        return pvals[i] if i >= 0 else None

    bars: dict[datetime, float] = {}
    for t, v in prints:
        bars[m15_floor(t)] = v          # last print in the bar == its close
    bar_keys = sorted(bars)

    def prior_close(t: datetime) -> float | None:
        """iClose(M15, 6) -- close of the bar 6 bars before the one holding t."""
        target = m15_floor(t) - RESCUE_BARS * M15
        i = bisect_right(bar_keys, target) - 1
        return bars[bar_keys[i]] if i >= 0 else None

    def floating_at(t: datetime, mark: float) -> tuple[float, int]:
        tot, n = 0.0, 0
        for p in positions:
            if p.open_time <= t and (p.close_time is None or p.close_time > t):
                tot += p.dir * (mark - p.open_price) * p.volume * CONTRACT + p.swap
                n += 1
        return tot, n

    grid = [o for o in orders if o.is_grid and o.level is not None]

    def base_pendings_at(t: datetime, side: str) -> int:
        n = 0
        for o in grid:
            if o.side != side or not is_base(o):
                continue
            if o.open_time <= t and (o.end_time is None or o.end_time > t):
                n += 1
        return n

    # ------------------------------------------------------------------ panel A
    print("=" * 100)
    print("A. VOLUME CENSUS -- final regime grid orders by tier")
    print("=" * 100)
    census: dict[tuple[str, float], int] = Counter()
    for o in grid:
        if o.open_time < FINAL_REGIME_START:
            continue
        tier = "L1-10" if o.level <= 10 else ("L11-20" if o.level <= 20 else "L21-30")
        census[(tier, round(o.volume, 4))] += 1
    for tier in ("L1-10", "L11-20", "L21-30"):
        row = sorted((v, n) for (t, v), n in census.items() if t == tier)
        exp_base = tier_lot(5 if tier == "L1-10" else (15 if tier == "L11-20" else 25))
        print(f"  {tier:<7} base={exp_base:<5} rescue={2*exp_base:<5} "
              + "  ".join(f"{v}:{n}" for v, n in row))

    # ------------------------------------------------------------------ panel B
    print()
    print("=" * 100)
    print("B. PER-CYCLE RESCUE INVENTORY (final regime)")
    print("=" * 100)
    fin = [c for c in cycles if c.start >= FINAL_REGIME_START]
    pos_by_order = {p.position_id: p for p in positions}

    rows = []
    for c in fin:
        resc = [o for o in c.orders if o.is_grid and o.level is not None and is_rescue(o)]
        if not resc:
            continue
        resc.sort(key=lambda o: o.open_time)
        fills = [o for o in resc if o.state == "filled"]
        sides = Counter(o.side for o in resc)
        rows.append((c, resc, fills, sides))

    print(f"  cycles with any rescue ORDER: {len(rows)} of {len(fin)}")
    print(f"  cycles with any rescue FILL : "
          f"{sum(1 for _, _, f, _ in rows if f)} of {len(fin)}")
    print()
    print(f"  {'cyc':>4} {'reg':<5} {'ord':>4} {'fil':>4} {'B/S':>7}  "
          f"{'first rescue placement':<21} {'cycle start':<19}")
    for c, resc, fills, sides in rows:
        print(f"  {c.index:>4} {regime(resc[0].open_time):<5} {len(resc):>4} "
              f"{len(fills):>4} {sides['B']:>3}/{sides['S']:<3}  "
              f"{str(resc[0].open_time):<21} {str(c.start):<19}")

    # ------------------------------------------------------------------ panel C
    print()
    print("=" * 100)
    print("C. DECISION INSTANT -- raw value of each condition at the FIRST rescue")
    print("=" * 100)
    print("  'move' is price - iClose(M15,6): positive = market rose above the")
    print("  90-minute-old close.  'baseB'/'baseS' are base-volume pendings alive.")
    print()
    print(f"  {'cyc':>4} {'reg':<5} {'side':>4} {'floating':>10} {'openpos':>7} "
          f"{'move':>8} {'baseB':>6} {'baseS':>6}  {'when':<19}")
    snap = []
    for c, resc, fills, sides in rows:
        t = resc[0].open_time
        mark = price_at(t)
        if mark is None:
            continue
        fl, npos = floating_at(t, mark)
        pc = prior_close(t)
        move = (mark - pc) if pc else float("nan")
        bb = base_pendings_at(t, "B")
        bs = base_pendings_at(t, "S")
        first_side = resc[0].side
        snap.append((c.index, regime(t), first_side, fl, npos, move, bb, bs, t))
        print(f"  {c.index:>4} {regime(t):<5} {first_side:>4} {fl:>10.2f} {npos:>7} "
              f"{move:>8.2f} {bb:>6} {bs:>6}  {str(t):<19}")

    if snap:
        print()
        for lab, idx in (("floating", 3), ("move", 5)):
            v = sorted(r[idx] for r in snap if r[idx] == r[idx])
            print(f"  {lab:<9} min={v[0]:>9.2f}  med={statistics.median(v):>9.2f}  "
                  f"max={v[-1]:>9.2f}   n={len(v)}")
        print(f"  base pendings on the rescued side: "
              + " ".join(str(r[6] if r[2] == 'B' else r[7]) for r in snap))


if __name__ == "__main__":
    main()
