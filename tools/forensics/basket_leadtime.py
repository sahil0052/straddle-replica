"""First-fire-lead-time test on the $30 basket rule, using the EA's own definition.

The rule governs 64.5% of the |money| in the ledger, so it deserves the same
lead-time scoring the rescue trigger got (AGENTS.md #3), not just a coverage count.

basket_quantity.py measured the trigger value only AT the flatten instant and got a
median of 31.18 with a stdev of 269 -- median right on target, tails wild.  Two
reconstruction faults explain the tails, and both come from the same place:

  * dataset.py attributes a position to the cycle its OPEN time falls in.  The EA's
    m_cycle_realized instead accumulates every deal CLOSED since cycle start,
    whoever opened it.  Those sets differ for any basket that straddles a
    deployment, which is exactly the long/heavy cycles that showed the wild tails.
  * a single point-in-time reading cannot distinguish "fired on time" from "was
    already eligible an hour ago", and the second is the interesting failure.

So: rebuild the trigger EXACTLY as the engine computes it --

    trigger(t) = SUM(net of every position closed in [cycle_start, t])
               + SUM over positions open at t of dir*(mark - open)*vol*100 + swap

which is m_cycle_realized + OwnedFloatingProfit -- and evaluate it at every trade
print inside the cycle.  floating is exactly linear in the mark, so this is the
same closed-form A/B/C accumulator q2h_reconcile used:

    floating(m) = m*A - B + C

Score by lead = t_flatten - t_first_cross:

    lead ~ 0        the rule fired the moment it went true  -> ADMISSIBLE
    lead >> 0       eligible long before it acted           -> something GATES it
    never crossed   flattened while below 30                -> rule is INCOMPLETE

AGENTS.md already records 5 cycles that "sustained a total above $30 for 6-257 min
without closing" and calls the cause untested.  This is the test.
"""
from __future__ import annotations

import statistics
import sys
from datetime import timedelta

sys.path.insert(0, r"C:\websites\mt5 2")
from tools.forensics.dataset import load_all, FINAL_REGIME_START, CONTRACT  # noqa: E402

TARGET = 30.0


def main() -> None:
    orders, positions, deals, cycles = load_all()
    fin = [c for c in cycles if c.start >= FINAL_REGIME_START]

    # global print stream: every exact mark the report exposes
    marks: list[tuple] = []
    for p in positions:
        marks.append((p.open_time, p.open_price))
        if p.close_time and p.close_price:
            marks.append((p.close_time, p.close_price))
    marks.sort(key=lambda r: r[0])

    rows = []
    for c in fin:
        cl = [o.open_time for o in c.orders
              if o.comment and o.comment.strip().upper().startswith("STR CLOSE")]
        if not cl or not c.end:
            continue
        t0 = min(cl)

        # every position that is open at some point inside [c.start, t0]
        rel = [p for p in positions
               if p.open_time <= t0 and (p.is_open or
                                         (p.close_time and p.close_time >= c.start))]
        # event stream: +position at open, -position at close
        ev = []
        for p in rel:
            a = p.dir * p.volume * CONTRACT
            ev.append((p.open_time, 0, a, a * p.open_price, p.swap, 0.0))
            if p.close_time:
                ev.append((p.close_time, 1, -a, -a * p.open_price, -p.swap,
                           p.net if p.close_time >= c.start else 0.0))
        ev.sort(key=lambda r: (r[0], r[1]))

        A = B = C = R = 0.0
        j = 0
        first = None
        peak = -1e18
        at_t0 = None
        for t, m in marks:
            if t < c.start:
                continue
            if t > t0:
                break
            while j < len(ev) and ev[j][0] <= t:
                _, _, da, db, dc, dr = ev[j]
                A += da; B += db; C += dc; R += dr
                j += 1
            v = R + m * A - B + C
            if v > peak:
                peak = v
            if first is None and v >= TARGET:
                first = (t, v, m)
            at_t0 = v
        if at_t0 is None:
            continue
        rows.append(dict(i=c.index, t0=t0, first=first, peak=peak, at_t0=at_t0,
                         start=c.start, final=c.realized,
                         nlive=sum(1 for p in rel if p.is_open or
                                   (p.close_time and p.close_time >= t0))))

    print("=" * 104)
    print("A. LEAD-TIME SCORE of `m_cycle_realized + OwnedFloatingProfit >= 30`")
    print("=" * 104)
    ontime = [r for r in rows if r["first"] and
              (r["t0"] - r["first"][0]).total_seconds() <= 120]
    late = [r for r in rows if r["first"] and
            (r["t0"] - r["first"][0]).total_seconds() > 120]
    never = [r for r in rows if not r["first"]]
    print(f"  cycles scored: {len(rows)}")
    print(f"    fired within 2 min of going true (lead ~ 0) : {len(ontime):>3}"
          f"  = {len(ontime)/len(rows):.1%}")
    print(f"    eligible >2 min before it acted (GATED)     : {len(late):>3}"
          f"  = {len(late)/len(rows):.1%}")
    print(f"    flattened while BELOW 30 (rule incomplete)  : {len(never):>3}"
          f"  = {len(never)/len(rows):.1%}")
    if ontime:
        lv = [(r["t0"] - r["first"][0]).total_seconds() for r in ontime]
        print(f"    on-time lead: median {statistics.median(lv):.1f} s  "
              f"max {max(lv):.1f} s")
        tv = [r["first"][1] for r in ontime]
        print(f"    value at first crossing: median {statistics.median(tv):.2f}  "
              f"max {max(tv):.2f}   (must be barely over 30)")

    print()
    print("=" * 104)
    print("B. THE GATED CYCLES -- eligible, but the EA sat on it")
    print("=" * 104)
    if late:
        print(f"  {'cyc':>5} {'lead':>10} {'val@true':>9} {'val@flat':>9} "
              f"{'peak':>9} {'live':>5} {'age at true':>12}  first true")
        for r in sorted(late, key=lambda r: -(r["t0"] - r["first"][0]).total_seconds()):
            ld = (r["t0"] - r["first"][0]).total_seconds()
            age = (r["first"][0] - r["start"]).total_seconds() / 3600.0
            print(f"  {r['i']:>5} {ld/60:>8.1f}m {r['first'][1]:>9.2f} "
                  f"{r['at_t0']:>9.2f} {r['peak']:>9.2f} {r['nlive']:>5} "
                  f"{age:>10.2f} h  {str(r['first'][0])[:19]}")
    else:
        print("  none")

    print()
    print("=" * 104)
    print("C. THE SUB-30 FLATTENS -- what made it close early?")
    print("=" * 104)
    if never:
        print(f"  {'cyc':>5} {'val@flat':>9} {'peak':>9} {'final':>9} {'live':>5} "
              f"{'dur':>8}  start")
        for r in sorted(never, key=lambda r: r["at_t0"]):
            dur = (r["t0"] - r["start"]).total_seconds() / 3600.0
            print(f"  {r['i']:>5} {r['at_t0']:>9.2f} {r['peak']:>9.2f} "
                  f"{r['final']:>9.2f} {r['nlive']:>5} {dur:>7.2f}h  "
                  f"{str(r['start'])[:19]}")
        pk = [r["peak"] for r in never]
        print(f"\n  peak trigger value reached in these cycles: median "
              f"{statistics.median(pk):.2f}  max {max(pk):.2f}")
        print("  -> if the peaks sit just under 30 the threshold is slightly lower than")
        print("     30; if they are far under, a DIFFERENT exit path closed these.")
    else:
        print("  none -- every flatten happened at or above 30")


if __name__ == "__main__":
    main()
