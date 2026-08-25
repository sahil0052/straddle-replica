"""Q2i: characterise the 4 falsifiers, and bound the threshold from both sides.

q2h confirmed trend_rescue_drawdown_money = 400.0 rather than refuting it:

    floating <= -400, asked correctly ("did it reach -X at or before the first
    observable action", which is the right question for a LATCH):
        miss = 0        falsifiers = 4 of 94        negative leads = 1

    and the closed-form reconciliation showed every event sits ON the threshold
    once mark staleness is accounted for:
        cycle 197  needed the mark to move  0.17 pts   (floating -398.82, $1.18 short)
        cycle 252  needed                   1.01 pts   (floating -382.85)
        cycle 250  needed                   4.08 pts   (mark was 196 s stale)
        cycle 244  needed                   6.44 pts   (mark was 227 s stale)
        cycle 187  needed                  22.98 pts   (10.5-min blind gap, and the
                                                        local 6 h range runs 50 pts
                                                        below the mark)
        cycle 234  already at -759.25, far past the gate

The earlier "-400 blocks 5 of 6" reading came from demanding that -400 and the M15
move gate be true at the SAME print instant.  Prints are sparse (median gap 32 s) and
q2e proved the M15 proxy points at the wrong side in half the events, so simultaneity
on a sparse grid is a property of the reconstruction, not of the EA.

Two things left to nail down.

1. The 4 falsifiers.  If the move gate kills them, the conjunction is complete and the
   residual is zero.  Measured at the instant floating first crosses -400.
2. The upper bound.  Panel C showed falsifiers stop improving above 400 while negative
   leads start accumulating (400 -> 1 neg, 450 -> 2, 500 -> 3).  A negative lead is
   proof of measurement error OR of a threshold set too deep; either way it bounds the
   parameter from above.  Print the fine grid around 400 so the plateau is explicit.
"""
from __future__ import annotations

import statistics
import sys
from bisect import bisect_right
from datetime import datetime, timedelta

sys.path.insert(0, r"C:\websites\mt5 2")
from tools.forensics.dataset import load_all, FINAL_REGIME_START, CONTRACT  # noqa: E402

M15 = timedelta(minutes=15)


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

    prints = []
    for p in positions:
        prints.append((p.open_time, p.open_price))
        if p.close_time and p.close_price:
            prints.append((p.close_time, p.close_price))
    prints.sort(key=lambda r: r[0])
    ptimes = [t for t, _ in prints]
    pvals = [v for _, v in prints]
    bars = {}
    for t, v in prints:
        bars[m15_floor(t)] = v
    bar_keys = sorted(bars)

    def prior_close(t, back=6):
        i = bisect_right(bar_keys, m15_floor(t) - back * M15) - 1
        return bars[bar_keys[i]] if i >= 0 else None

    fin = [c for c in cycles if c.start >= FINAL_REGIME_START]

    events = {}
    for c in fin:
        resc = sorted((o for o in c.orders
                       if o.is_grid and o.level is not None and is_rescue(o)),
                      key=lambda o: o.open_time)
        if not resc:
            continue
        slots = {}
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

    def pend_idx(cyc):
        idx = {}
        for sd in ("B", "S"):
            st, en = [], []
            for o in cyc.orders:
                if (o.is_grid and o.level is not None and o.side == sd
                        and is_base(o)):
                    st.append(o.open_time)
                    en.append(o.end_time if o.end_time else datetime.max)
            idx[sd] = (sorted(st), sorted(en))
        return idx

    def first_cross(cyc, x):
        """First PRINT instant where exact floating <= -x.  Returns (t, mark, A)."""
        ev = []
        marks = {}
        for p in cyc.positions:
            a = p.dir * p.volume * CONTRACT
            ev.append((p.open_time, a, a * p.open_price, p.swap))
            marks[p.open_time] = p.open_price
            if p.close_time:
                ev.append((p.close_time, -a, -a * p.open_price, -p.swap))
                if p.close_price:
                    marks[p.close_time] = p.close_price
        ev.sort(key=lambda r: r[0])
        A = B = C = 0.0
        j = 0
        for g in sorted(marks):
            while j < len(ev) and ev[j][0] <= g:
                A += ev[j][1]; B += ev[j][2]; C += ev[j][3]; j += 1
            m = marks[g]
            if m * A - B + C <= -x:
                return g, m, A, m * A - B + C
        return None, None, None, None

    # ------------------------------------------------------------------ panel A
    print("=" * 102)
    print("A. THE 4 FALSIFIERS of floating<=-400 -- does the move gate kill them?")
    print("=" * 102)
    print("  Measured at the instant floating FIRST crosses -400, which is when the")
    print("  latch would have been evaluated.  |move| = mark - iClose(M15, 6 bars back).")
    print("  The EA needs |move| >= 20 AND >= 3 base pendings on the MOVE side.")
    print()
    print(f"  {'cyc':>4} {'crossed at':<23} {'float':>9} {'mark':>9} {'M15-6':>9} "
          f"{'move':>8} {'side':>4} {'pend':>5} {'>=20?':>6} {'>=3?':>5}   verdict")
    killed = 0
    for c in fin:
        if c.index in events:
            continue
        g, m, A, fl = first_cross(c, 400.0)
        if g is None:
            continue
        pc = prior_close(g)
        mv = (m - pc) if pc is not None else float("nan")
        sd = "B" if mv > 0 else "S"
        st, en = pend_idx(c)[sd]
        npd = bisect_right(st, g) - bisect_right(en, g)
        ok_mv = abs(mv) >= 20.0
        ok_pd = npd >= 3
        v = "rescue expected" if (ok_mv and ok_pd) else "BLOCKED"
        killed += not (ok_mv and ok_pd)
        print(f"  {c.index:>4} {str(g)[:23]:<23} {fl:>9.2f} {m:>9.2f} "
              f"{pc if pc else float('nan'):>9.2f} {mv:>+8.2f} {sd:>4} {npd:>5} "
              f"{'yes' if ok_mv else 'NO':>6} {'yes' if ok_pd else 'NO':>5}   {v}")
    print(f"\n  {killed} of 4 falsifiers blocked by the confirmed move/pend gates.")

    # ------------------------------------------------------------------ panel B
    print()
    print("=" * 102)
    print("B. SAME MEASUREMENT on the 6 REAL events -- the gates must NOT block these")
    print("=" * 102)
    print(f"  {'cyc':>4} {'crossed at':<23} {'float':>9} {'move':>8} {'side':>4} "
          f"{'trend':>5} {'pend':>5} {'>=20?':>6} {'side ok?':>9} {'lead(m)':>8}")
    passed = 0
    for i in sorted(events):
        c = next(x for x in fin if x.index == i)
        dec, tr = events[i]
        g, m, A, fl = first_cross(c, 400.0)
        if g is None:
            print(f"  {i:>4} {'never crossed -400':<23}")
            continue
        pc = prior_close(g)
        mv = (m - pc) if pc is not None else float("nan")
        sd = "B" if mv > 0 else "S"
        st, en = pend_idx(c)[sd]
        npd = bisect_right(st, g) - bisect_right(en, g)
        ok = abs(mv) >= 20.0 and npd >= 3
        passed += ok
        print(f"  {i:>4} {str(g)[:23]:<23} {fl:>9.2f} {mv:>+8.2f} {sd:>4} {tr:>5} "
              f"{npd:>5} {'yes' if abs(mv)>=20 else 'NO':>6} "
              f"{'yes' if sd==tr else 'no':>9} "
              f"{(dec-g).total_seconds()/60.0:>8.1f}")
    print(f"\n  {passed}/6 real events pass the move+pend gates at their -400 crossing.")

    # ------------------------------------------------------------------ panel C
    print()
    print("=" * 102)
    print("C. FINE GRID around 400 -- where does the falsifier count plateau?")
    print("=" * 102)
    print("  neg = leads < -0.5 min, i.e. the EA acted BEFORE the gate opened.  Those")
    print("  are impossible for a real gate, so a rising neg count bounds -X above.")
    print()
    print(f"  {'-X':>6} {'miss':>5} {'fals':>5} {'neg':>4} {'lead med':>9}   leads (min)")
    for x in range(300, 561, 20):
        leads, miss, fals = [], 0, 0
        for c in fin:
            g, _, _, _ = first_cross(c, float(x))
            if c.index in events:
                dec, _ = events[c.index]
                if g is None:
                    miss += 1
                else:
                    leads.append((dec - g).total_seconds() / 60.0)
            elif g is not None:
                fals += 1
        neg = sum(1 for v in leads if v < -0.5)
        lm = statistics.median(leads) if leads else float("nan")
        mark = "  <== plateau" if x == 400 else ""
        print(f"  {x:>6} {miss:>5} {fals:>5} {neg:>4} {lm:>9.1f}   "
              + " ".join(f"{v:.0f}" for v in sorted(leads)) + mark)


if __name__ == "__main__":
    main()
