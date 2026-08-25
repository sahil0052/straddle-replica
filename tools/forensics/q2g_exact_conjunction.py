"""Q2g: the definitive conjunction, evaluated only where the data is EXACT.

Two results constrain this script.

q2e proved the mark is unusable away from trade prints: median print gap 32.4 s, p90
388 s, max 49.4 h, and only 0.3% of the timeline has a mark fresher than 15 s.  So
any instant that is not a print carries an unbounded floating error.

q2f then measured the exact, price-free structural features, and one of them carries
real signal where the price features carried none:

    maxfill[trend] >= 16    miss=1  fals=21  side 5/6  lead median  10.3 min
    maxfill[trend] >= 19    miss=2  fals=10  side 4/6  lead median   4.3 min, no neg
    gone[trend] > gone[opp] identifies the rescued side 5/6 (price proxy managed 3/6)

versus the best price-based row anywhere in q2d/q2e: lead median 212 min, side 3/6.

So the structure is where the information is, and the remaining question is what the
structure is conjoined WITH.  This script answers it the only way the dataset
permits: restrict the grid to the cycle's own position open/close instants.  At those
instants the mark IS the printed trade price -- staleness is exactly zero and
floating is exact, not reconstructed.  The M15 prior close remains a last-print
proxy, but that is a 90-minute-old reference whose error is bounded by one bar's
range, not by hours of drift.

Sweep is over the full cross product so the trade-off surface is visible rather than
asserted, and dd=0 is included so "no drawdown gate at all" competes on equal terms
with every threshold.  A conjunct that only ever fires because another conjunct
already fired is a filter, not a trigger, and the lead column is what distinguishes
them.

Panel A  each condition ALONE at print instants -- the baseline to beat.
Panel B  the full cross product: maxfill x floating x move.
Panel C  the best rows in detail, per event.
Panel D  what the surviving falsifiers look like, to judge whether the residual is
         a missing conjunct or the cooldown/latch the code already has.
"""
from __future__ import annotations

import statistics
import sys
from bisect import bisect_right
from datetime import datetime, timedelta

sys.path.insert(0, r"C:\websites\mt5 2")
from tools.forensics.dataset import load_all, FINAL_REGIME_START, CONTRACT  # noqa: E402

M15 = timedelta(minutes=15)
OPP = {"B": "S", "S": "B"}


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

    bars: dict[datetime, float] = {}
    for p in positions:
        bars[m15_floor(p.open_time)] = p.open_price
        if p.close_time and p.close_price:
            bars[m15_floor(p.close_time)] = p.close_price
    bar_keys = sorted(bars)

    def prior_close(t, back=6):
        i = bisect_right(bar_keys, m15_floor(t) - back * M15) - 1
        return bars[bar_keys[i]] if i >= 0 else None

    fin = [c for c in cycles if c.start >= FINAL_REGIME_START]

    events: dict[int, tuple[datetime, str]] = {}
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

    # ---- per-cycle exact timeline built once ---------------------------------
    class Tl:
        def __init__(self, cyc):
            self.pend, self.opos, self.fills = {}, {}, {}
            for sd in ("B", "S"):
                ps = sorted(o.open_time for o in cyc.orders
                            if o.is_grid and o.level is not None
                            and o.side == sd and is_base(o))
                pe = sorted((o.end_time or datetime.max) for o in cyc.orders
                            if o.is_grid and o.level is not None
                            and o.side == sd and is_base(o))
                self.pend[sd] = (ps, pe)
                sub = [p for p in cyc.positions
                       if p.grid_side == sd and p.level is not None]
                self.opos[sd] = (sorted(p.open_time for p in sub),
                                 sorted(p.close_time or datetime.max for p in sub))
                self.fills[sd] = sorted((p.open_time, p.level) for p in sub)
            # PRINT instants only: mark is exact here
            self.grid = sorted({p.open_time for p in cyc.positions} |
                               {p.close_time for p in cyc.positions if p.close_time})
            self.marks = {}
            for p in cyc.positions:
                self.marks[p.open_time] = p.open_price
                if p.close_time and p.close_price:
                    self.marks[p.close_time] = p.close_price
            ev = []
            for p in cyc.positions:
                a = p.dir * p.volume * CONTRACT
                ev.append((p.open_time, a, a * p.open_price, p.swap))
                if p.close_time:
                    ev.append((p.close_time, -a, -a * p.open_price, -p.swap))
            self.ev = sorted(ev, key=lambda r: r[0])

        def npend(self, sd, t):
            s, e = self.pend[sd]
            return bisect_right(s, t) - bisect_right(e, t)

        def nopen(self, sd, t):
            s, e = self.opos[sd]
            return bisect_right(s, t) - bisect_right(e, t)

        def maxfill(self, sd, t):
            m = 0
            for ot, lv in self.fills[sd]:
                if ot > t:
                    break
                m = max(m, lv)
            return m

    tls = {c.index: Tl(c) for c in fin}

    def scan(c, mf_min, dd, move_min, pend_min):
        """First PRINT instant where the whole conjunction holds. Exact floating."""
        tl = tls[c.index]
        A = B = C = 0.0
        j = 0
        for g in tl.grid:
            while j < len(tl.ev) and tl.ev[j][0] <= g:
                A += tl.ev[j][1]; B += tl.ev[j][2]; C += tl.ev[j][3]; j += 1
            mark = tl.marks.get(g)
            if mark is None:
                continue
            fl = mark * A - B + C
            if dd > 0 and fl > -dd:
                continue
            pc = prior_close(g)
            for sd in ("B", "S"):
                if move_min > 0:
                    if pc is None:
                        continue
                    mv = mark - pc
                    want = "B" if mv > 0 else "S"
                    if sd != want or abs(mv) < move_min:
                        continue
                if tl.maxfill(sd, g) < mf_min:
                    continue
                if tl.npend(sd, g) < pend_min:
                    continue
                return g, sd, fl
        return None, None, None

    def score(mf, dd, mv, pk):
        miss = fals = sideok = neg = 0
        leads = []
        for c in fin:
            g, sd, _ = scan(c, mf, dd, mv, pk)
            if c.index in events:
                dec, tr = events[c.index]
                if g is None:
                    miss += 1
                else:
                    v = (dec - g).total_seconds() / 60.0
                    leads.append(v)
                    neg += (v < -0.5)
                    sideok += (sd == tr)
            elif g is not None:
                fals += 1
        return miss, fals, sideok, neg, leads

    # ------------------------------------------------------------------ panel A
    print("=" * 100)
    print("A. EACH CONDITION ALONE, at print instants (exact mark)")
    print("=" * 100)
    print(f"  {'condition':<34} {'miss':>5} {'fals':>5} {'side':>5} "
          f"{'lead med':>9} {'lead max':>9}")
    for lab, a in (("move>=20 only", (0, 0.0, 20.0, 0)),
                   ("floating<=-150 only", (0, 150.0, 0.0, 0)),
                   ("floating<=-400 only", (0, 400.0, 0.0, 0)),
                   ("maxfill[trend]>=16 only", (16, 0.0, 0.0, 0)),
                   ("maxfill[trend]>=19 only", (19, 0.0, 0.0, 0)),
                   ("pend[trend]>=3 only", (0, 0.0, 0.0, 3))):
        m, f, s, n, L = score(*a)
        lm = statistics.median(L) if L else float("nan")
        print(f"  {lab:<34} {m:>5} {f:>5} {s:>3}/6 {lm:>9.1f} "
              f"{max(L) if L else 0:>9.1f}")

    # ------------------------------------------------------------------ panel B
    print()
    print("=" * 100)
    print("B. CROSS PRODUCT -- maxfill[trend] x floating x move, pend[trend]>=3")
    print("=" * 100)
    print("  dd=0 means NO drawdown gate.  mv=0 means NO move gate.")
    print()
    print(f"  {'mf':>3} {'dd':>5} {'mv':>4} {'miss':>5} {'fals':>5} {'side':>5} "
          f"{'neg':>4} {'lead med':>9} {'lead max':>9}   leads (min)")
    keep = []
    for mf in (0, 13, 16, 19, 22):
        for dd in (0.0, 150.0, 250.0, 400.0):
            for mv in (0.0, 20.0):
                m, f, s, n, L = score(mf, dd, mv, 3)
                lm = statistics.median(L) if L else float("nan")
                mx = max(L) if L else 0.0
                keep.append((m, f, -s, abs(lm) if L else 1e9, mf, dd, mv, n, L))
                flag = "  <==" if m == 0 and f <= 15 and L and abs(lm) <= 30 else ""
                print(f"  {mf:>3} {dd:>5.0f} {mv:>4.0f} {m:>5} {f:>5} {s:>3}/6 "
                      f"{n:>4} {lm:>9.1f} {mx:>9.1f}   "
                      + " ".join(f"{v:.0f}" for v in sorted(L)) + flag)
        print()

    # ------------------------------------------------------------------ panel C
    print("=" * 100)
    print("C. BEST ROWS, ranked by (misses, falsifiers, side, |lead|)")
    print("=" * 100)
    keep.sort()
    for m, f, ns, al, mf, dd, mv, n, L in keep[:10]:
        print(f"  maxfill>={mf:<3} floating<=-{dd:<5.0f} move>={mv:<4.0f}  "
              f"miss={m} fals={f:>2} side={-ns}/6 neg={n} "
              f"lead med={statistics.median(L) if L else float('nan'):>7.1f}m "
              f"max={max(L) if L else 0:>7.1f}m")

    top = keep[0]
    mf, dd, mv = top[4], top[5], top[6]
    print()
    print(f"  per-event detail for maxfill>={mf} floating<=-{dd:.0f} move>={mv:.0f}:")
    print(f"    {'cyc':>4} {'trend':>5} {'firstTrue':<23} {'side':>4} {'floating':>9} "
          f"{'decision':<23} {'lead(m)':>8}")
    for i in sorted(events):
        c = next(x for x in fin if x.index == i)
        g, sd, fl = scan(c, mf, dd, mv, 3)
        dec, tr = events[i]
        if g is None:
            print(f"    {i:>4} {tr:>5} {'never true':<23} {'':>4} {'':>9} "
                  f"{str(dec)[:23]:<23} {'MISS':>8}")
        else:
            print(f"    {i:>4} {tr:>5} {str(g)[:23]:<23} {sd:>4} {fl:>9.2f} "
                  f"{str(dec)[:23]:<23} {(dec-g).total_seconds()/60.0:>8.1f}")

    # ------------------------------------------------------------------ panel D
    print()
    print("=" * 100)
    print("D. SURVIVING FALSIFIERS -- rule went true, no rescue.  Why?")
    print("=" * 100)
    print("  m_trend_rescue_consumed_side latches per side until the trigger clears,")
    print("  and deployment_fill_cooldown_seconds gates each action, so a cycle that")
    print("  goes true briefly near its END may simply never get a tick to act on.")
    print()
    print(f"    {'cyc':>4} {'firstTrue':<23} {'side':>4} {'floating':>9} "
          f"{'cycle end':<23} {'time left':>10} {'pend':>5}")
    shown = 0
    for c in fin:
        if c.index in events:
            continue
        g, sd, fl = scan(c, mf, dd, mv, 3)
        if g is None:
            continue
        left = ((c.end - g).total_seconds() / 60.0) if c.end else float("nan")
        print(f"    {c.index:>4} {str(g)[:23]:<23} {sd:>4} {fl:>9.2f} "
              f"{str(c.end)[:23]:<23} {left:>9.1f}m {tls[c.index].npend(sd, g):>5}")
        shown += 1
    print(f"\n  {shown} falsifiers listed.")


if __name__ == "__main__":
    main()
