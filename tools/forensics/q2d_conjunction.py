"""Q2d: the rescue trigger as a CONJUNCTION, under first-fire lead time.

q2c's corrected snapshot (measured at the first cancel of a trend-side base pending,
which is the first observable consequence of trend_rescue_start, rather than at the
first 2x placement which happens many ticks later):

  cyc  trend  floating    move  pendTrend  cancels
  187    B     -147.25  +40.97      2 (3)     3      <- pendings read one low because
  197    S     -398.82  -21.08     16        15         end_time of the FIRST cancel
  234    S     -759.25  -29.74     10        11         is already post-cancel
  244    B      -77.92  +36.37      6         8
  250    B     -375.51  +21.87     19        20
  252    S     -382.85  -19.85     11        12

Two independent confirmations fell out of that table:

  * the cancel COUNT equals the trend-side base pending count almost exactly
    (3/3, 11/11, 20/20, 12/12) -- the rescue cancels EVERY surviving base pending on
    the trend side and re-places it at 2x, which is exactly what
    TryCancelOneTrendRescueOrder + PlaceOneTrendRescueReplacement do, and the 0.10-
    0.12 s cancel gaps re-derive the 100 ms one-action-per-tick timer a fourth time.
  * trend_rescue_bars = 6 is the unique argmax over lookbacks {2,4,6,8,10,12,16,24}:
    only at 6 do all six events clear 20 (min 19.85).  Every other lookback lets an
    event fire below the threshold.

What is still open is the drawdown gate.  400 blocks 5 of 6.  But q2b showed that
NO floating threshold can be the trigger on its own -- leads run 56 to 3297 minutes.
In a conjunction that is fine: the LAST condition to turn true is the trigger and
the others are filters.  So the test has to be run on the conjunction as a whole,
evaluated at a single instant, which is what this script does.

Implementation note: floating is linear in the mark, so
    floating(t) = mark(t) * SUM(dir*vol*100) - SUM(dir*open*vol*100) + SUM(swap)
over the open set.  Maintaining those three running sums across a time-ordered event
sweep makes a fine grid over all 100 cycles cheap and exact, instead of rescanning
every position at every grid point.
"""
from __future__ import annotations

import statistics
import sys
from bisect import bisect_right
from datetime import datetime, timedelta

sys.path.insert(0, r"C:\websites\mt5 2")
from tools.forensics.dataset import load_all, FINAL_REGIME_START, CONTRACT  # noqa: E402

BREAK = datetime(2026, 7, 24, 12, 0, 0)
M15 = timedelta(minutes=15)
MOVE = 20.0


def tier_lot(level: int) -> float:
    return 0.01 if level <= 10 else (0.06 if level <= 20 else 0.15)


def is_base(o) -> bool:
    return abs(o.volume - tier_lot(o.level)) < 1e-9


def is_rescue(o) -> bool:
    return abs(o.volume - 2.0 * tier_lot(o.level)) < 1e-9


def m15_floor(t: datetime) -> datetime:
    return t.replace(minute=(t.minute // 15) * 15, second=0, microsecond=0)


def main() -> None:
    orders, positions, deals, cycles = load_all()

    prints: list[tuple[datetime, float]] = []
    for p in positions:
        prints.append((p.open_time, p.open_price))
        if p.close_time and p.close_price:
            prints.append((p.close_time, p.close_price))
    prints.sort(key=lambda r: r[0])
    ptimes = [t for t, _ in prints]
    pvals = [v for _, v in prints]
    bars: dict[datetime, float] = {}
    for t, v in prints:
        bars[m15_floor(t)] = v
    bar_keys = sorted(bars)

    def price_at(t):
        i = bisect_right(ptimes, t) - 1
        return pvals[i] if i >= 0 else None

    def prior_close(t, back=6):
        i = bisect_right(bar_keys, m15_floor(t) - back * M15) - 1
        return bars[bar_keys[i]] if i >= 0 else None

    fin = [c for c in cycles if c.start >= FINAL_REGIME_START]

    # ---- corrected decision instant per rescue cycle -------------------------
    events = {}
    for c in fin:
        resc = sorted((o for o in c.orders
                       if o.is_grid and o.level is not None and is_rescue(o)),
                      key=lambda o: o.open_time)
        if not resc:
            continue
        slots: dict[tuple, list] = {}
        for o in c.orders:
            if o.is_grid and o.level is not None:
                slots.setdefault((o.side, o.level), []).append(o)
        for v in slots.values():
            v.sort(key=lambda o: o.open_time)
        trend = resc[0].side
        cancels = [q.end_time for o in resc
                   for q in ([x for x in slots[(o.side, o.level)]
                              if x.open_time < o.open_time][-1:])
                   if q.state == "canceled" and q.end_time and o.side == trend]
        events[c.index] = (min(cancels) if cancels else resc[0].open_time, trend)

    # ---- per-cycle sweep -----------------------------------------------------
    def scan(cyc, dd: float, pend_k: int):
        """First instant where all three conditions hold together."""
        # base-pending interval index per side
        idx = {}
        for sd in ("B", "S"):
            st, en = [], []
            for o in cyc.orders:
                if (o.is_grid and o.level is not None and o.side == sd
                        and is_base(o)):
                    st.append(o.open_time)
                    en.append(o.end_time if o.end_time else datetime.max)
            idx[sd] = (sorted(st), sorted(en))

        # floating event stream: linear in the mark
        ev = []
        for p in cyc.positions:
            a = p.dir * p.volume * CONTRACT
            ev.append((p.open_time, a, a * p.open_price, p.swap))
            if p.close_time:
                ev.append((p.close_time, -a, -a * p.open_price, -p.swap))
        ev.sort(key=lambda r: r[0])

        grid = sorted({e[0] for e in ev} |
                      {o.open_time for o in cyc.orders} |
                      {o.end_time for o in cyc.orders if o.end_time})
        A = B = C = 0.0
        j = 0
        for g in grid:
            while j < len(ev) and ev[j][0] <= g:
                A += ev[j][1]; B += ev[j][2]; C += ev[j][3]; j += 1
            mark = price_at(g)
            pc = prior_close(g)
            if mark is None or pc is None:
                continue
            mv = mark - pc
            if abs(mv) < MOVE:
                continue
            if mark * A - B + C > -dd:
                continue
            sd = "B" if mv > 0 else "S"
            st, en = idx[sd]
            if bisect_right(st, g) - bisect_right(en, g) < pend_k:
                continue
            return g, sd
        return None, None

    print("=" * 100)
    print("A. CONJUNCTION SWEEP -- |move|>=20 (M15,6) AND floating<=-X AND "
          "pendTrend>=K")
    print("=" * 100)
    print("  miss       = a cycle where the rescue DID fire but the rule never went true")
    print("  falsifier  = a cycle where the rule went true but NO rescue fired")
    print("  lead       = decision - first_true, in minutes.  ~0 admissible, >>0 refuted")
    print()
    print(f"  {'-X':>5} {'K':>3} {'miss':>5} {'fals':>5} {'sideOK':>7} "
          f"{'lead med':>9} {'lead max':>9}   leads per event (min)")
    best = []
    for dd in (0.0, 75.0, 150.0, 200.0, 250.0, 300.0, 350.0, 400.0, 450.0):
        for k in (1, 3, 5):
            miss, fals, leads, sideok = 0, 0, [], 0
            for c in fin:
                g, sd = scan(c, dd, k)
                if c.index in events:
                    dec, trend = events[c.index]
                    if g is None:
                        miss += 1
                    else:
                        leads.append((dec - g).total_seconds() / 60.0)
                        sideok += (sd == trend)
                elif g is not None:
                    fals += 1
            row = (miss, fals, dd, k, leads, sideok)
            best.append(row)
            lm = statistics.median(leads) if leads else float("nan")
            print(f"  {dd:>5.0f} {k:>3} {miss:>5} {fals:>5} {sideok:>5}/6 "
                  f"{lm:>9.1f} {max(leads) if leads else 0:>9.1f}   "
                  + " ".join(f"{v:.0f}" for v in sorted(leads)))

    print()
    print("=" * 100)
    print("B. RANKED -- zero misses first, then fewest falsifiers, then tightest lead")
    print("=" * 100)
    best.sort(key=lambda r: (r[0], r[1],
                             statistics.median(r[4]) if r[4] else 1e9))
    for miss, fals, dd, k, leads, sideok in best[:8]:
        lm = statistics.median(leads) if leads else float("nan")
        print(f"  floating<=-{dd:<5.0f} pendTrend>={k}   miss={miss} falsifiers={fals:>2} "
              f"side {sideok}/6   lead median={lm:.1f}m max={max(leads) if leads else 0:.1f}m")


if __name__ == "__main__":
    main()
