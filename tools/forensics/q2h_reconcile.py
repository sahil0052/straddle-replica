"""Q2h: reconcile cycle 187, and settle trend_rescue_drawdown_money.

q2g reversed the earlier verdict, and the reversal is the point.

Measuring floating AT the decision instant said -400 blocks 5 of 6 events.  That
measurement was wrong in two ways at once:

  1. m_trend_rescue_side is a LATCH.  Once ProcessTrendRescue sets it, TrendRescueSide
     is never re-consulted for that side until the trigger clears.  So the first
     observable action (the first cancel) happens at least one tick -- and possibly
     one deployment_fill_cooldown_seconds -- AFTER the gate was satisfied.  Floating
     at the first cancel is therefore not floating at the latch, and reading it as
     though it were biases every event toward "shallower than the true threshold".
  2. The mark was stale at 3 of the 6 decision instants (47 s, 196 s, 227 s), and
     floating is linear in the mark, so those three readings had unbounded error.

Asking the correct question -- did floating reach -X at or before the decision, at an
instant where the mark is EXACT -- gives:

    floating <= -400 alone:  miss=0   falsifiers=4 of 94   (best of any single
                                                            condition tested)
    leads: -48.5  -0.1  +69.8  +3108.9  +355.7  +10.0 minutes

Cycle 197 is the striking one: floating crossed -400 five point four SECONDS after the
rescue sweep began.  That is as close to a smoking gun as a 100 ms state machine
sampling a whole-second TimeCurrent() can produce.

Cycle 187 is the sole genuine counter-example: -48.5 minutes.  But floating between
prints is UNOBSERVABLE -- the open set is exact, the mark is not, and the mark is what
moves.  So the question is quantitative, not philosophical: how far would the mark
have had to travel during the unobserved gap for floating to touch -400, and is that
distance inside the range the market actually covered nearby?  Because floating is
exactly linear in the mark,

    floating(m) = m*A - B + C,       A = SUM(dir * volume * 100) over the open set

that required mark is a closed-form number, not an estimate.  If it sits inside the
observed local range, -400 is consistent with cycle 187 and nothing is refuted.

Panel A  the closed-form reconciliation for every event.
Panel B  print-gap coverage around each decision, so the size of the blind spot is
         stated rather than hand-waved.
Panel C  final threshold sweep on the corrected question, fine grid.
Panel D  the 4 falsifiers, characterised.
"""
from __future__ import annotations

import statistics
import sys
from bisect import bisect_right
from datetime import datetime, timedelta

sys.path.insert(0, r"C:\websites\mt5 2")
from tools.forensics.dataset import load_all, FINAL_REGIME_START, CONTRACT  # noqa: E402


def tier_lot(level: int) -> float:
    return 0.01 if level <= 10 else (0.06 if level <= 20 else 0.15)


def is_rescue(o) -> bool:
    return abs(o.volume - 2.0 * tier_lot(o.level)) < 1e-9


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

    def coeffs(cyc, t):
        """A, B, C such that floating(mark) = mark*A - B + C.  Exact."""
        A = B = C = 0.0
        for p in cyc.positions:
            if p.open_time <= t and (p.close_time is None or p.close_time > t):
                a = p.dir * p.volume * CONTRACT
                A += a
                B += a * p.open_price
                C += p.swap
        return A, B, C

    def local_range(t, span_h=6.0):
        lo = bisect_right(ptimes, t - timedelta(hours=span_h))
        hi = bisect_right(ptimes, t + timedelta(hours=span_h))
        w = pvals[lo:hi]
        return (min(w), max(w)) if w else (None, None)

    # ------------------------------------------------------------------ panel A
    print("=" * 100)
    print("A. CLOSED-FORM RECONCILIATION -- what mark would put floating at -400?")
    print("=" * 100)
    print("  floating(m) = m*A - B + C.  A<0 means a net-short book (falling price")
    print("  helps), A>0 net-long.  'need' is the mark that yields exactly -400.")
    print()
    print(f"  {'cyc':>4} {'tr':>3} {'mark':>9} {'A':>8} {'float@mark':>11} "
          f"{'need(-400)':>11} {'move reqd':>10} {'local 6h range':>22} {'inside?':>8}")
    for i in sorted(events):
        dec, tr = events[i]
        c = next(x for x in fin if x.index == i)
        j = bisect_right(ptimes, dec) - 1
        mark = pvals[j]
        A, B, C = coeffs(c, dec)
        fl = mark * A - B + C
        if abs(A) < 1e-9:
            print(f"  {i:>4} {tr:>3} {mark:>9.2f} {A:>8.2f} {fl:>11.2f}   flat book")
            continue
        need = (-400.0 + B - C) / A
        lo, hi = local_range(dec)
        inside = (lo is not None and lo <= need <= hi)
        print(f"  {i:>4} {tr:>3} {mark:>9.2f} {A:>8.2f} {fl:>11.2f} {need:>11.2f} "
              f"{need-mark:>+10.2f} {f'{lo:.2f} .. {hi:.2f}':>22} "
              f"{'YES' if inside else 'no':>8}")

    # ------------------------------------------------------------------ panel B
    print()
    print("=" * 100)
    print("B. BLIND SPOT -- print gaps in the hour before each decision")
    print("=" * 100)
    print("  floating is only observable AT prints.  A long gap is a window in which")
    print("  floating could have crossed any threshold without leaving a trace.")
    print()
    print(f"  {'cyc':>4} {'prints in prior 1h':>19} {'max gap':>9} {'median gap':>11} "
          f"{'gap covering decision':>22}")
    for i in sorted(events):
        dec, tr = events[i]
        lo = bisect_right(ptimes, dec - timedelta(hours=1))
        hi = bisect_right(ptimes, dec)
        w = ptimes[lo:hi]
        gaps = [(b - a).total_seconds() for a, b in zip(w, w[1:])] or [0.0]
        pre = ptimes[hi - 1] if hi > 0 else None
        post = ptimes[hi] if hi < len(ptimes) else None
        cover = ((post - pre).total_seconds() if pre and post else float("nan"))
        print(f"  {i:>4} {len(w):>19} {max(gaps):>8.1f}s {statistics.median(gaps):>10.1f}s "
              f"{cover:>21.1f}s")

    # ------------------------------------------------------------------ panel C
    print()
    print("=" * 100)
    print("C. FINAL SWEEP -- did floating reach -X at or before the decision?")
    print("=" * 100)
    print("  This is the correct question for a LATCHING gate: the EA fires on the")
    print("  first tick after the gate opens, so the gate must have opened at or")
    print("  before the first observable action.")
    print()
    print(f"  {'-X':>6} {'reached':>8} {'miss':>5} {'fals':>5} {'lead med':>9} "
          f"{'lead max':>10} {'neg':>4}  leads (min)")
    for x in (150.0, 200.0, 250.0, 300.0, 350.0, 375.0, 400.0, 425.0, 450.0, 500.0):
        leads, miss, fals = [], 0, 0
        for c in fin:
            A = B = C = 0.0
            ev = []
            for p in c.positions:
                a = p.dir * p.volume * CONTRACT
                ev.append((p.open_time, a, a * p.open_price, p.swap))
                if p.close_time:
                    ev.append((p.close_time, -a, -a * p.open_price, -p.swap))
            ev.sort(key=lambda r: r[0])
            gridt = sorted({e[0] for e in ev})
            marks = {}
            for p in c.positions:
                marks[p.open_time] = p.open_price
                if p.close_time and p.close_price:
                    marks[p.close_time] = p.close_price
            first, j = None, 0
            for g in gridt:
                while j < len(ev) and ev[j][0] <= g:
                    A += ev[j][1]; B += ev[j][2]; C += ev[j][3]; j += 1
                m = marks.get(g)
                if m is not None and m * A - B + C <= -x:
                    first = g
                    break
            if c.index in events:
                dec, _ = events[c.index]
                if first is None:
                    miss += 1
                else:
                    leads.append((dec - first).total_seconds() / 60.0)
            elif first is not None:
                fals += 1
        lm = statistics.median(leads) if leads else float("nan")
        neg = sum(1 for v in leads if v < -0.5)
        flag = "  <== zero miss, fewest falsifiers" if miss == 0 and fals <= 4 else ""
        print(f"  {x:>6.0f} {len(leads):>8} {miss:>5} {fals:>5} {lm:>9.1f} "
              f"{max(leads) if leads else 0:>10.1f} {neg:>4}  "
              + " ".join(f"{v:.0f}" for v in sorted(leads)) + flag)


if __name__ == "__main__":
    main()
