"""Is the $30 basket check STARVED by pending re-arm work?

basket_leadtime.py found 13 of 99 cycles where `m_cycle_realized + floating` was
>= 30 well before the EA flattened -- leads of 2 to 306 minutes.  Five of the six
longest are 187, 197, 244, 250, 252: five of the six TREND RESCUE cycles.  The sixth
rescue cycle, 234, sits in the sub-30 group.  Every rescue cycle is a basket-rule
anomaly.  That is not a coincidence at 6 events in 99 cycles.

The replica cannot reproduce this.  StraddleEngine.mqh:3114-3122 --

    case CYCLE_RUNNING:
       ReconcileLevels();
       UpdatePositionStops();
       ProcessTrendRescue();
       if(m_trend_rescue_side==0) RearmOneMissingLevel();
       CheckCycleTargets();          <-- UNCONDITIONAL, every 100 ms tick

-- so the replica flattens the instant the sum crosses 30.  On these 13 cycles it
would exit up to 5 hours earlier than the Target did.

The hypothesis is starvation.  A one-action-per-tick machine written the natural way
returns after doing work:

    if(ProcessTrendRescue())    return;   // did a cancel or a placement
    if(RearmOneMissingLevel())  return;   // did a placement
    CheckCycleTargets();                  // only reached when idle

With rearm_delay_seconds=20 and PendingPriceIsValid destroying trend-side levels as
price runs, there is ALWAYS re-arm work during a rescue -- so the basket check never
runs.  That predicts something specific and falsifiable:

  * across a gated interval the EA is CONTINUOUSLY busy: an order action at least
    every ~20-25 s, never an idle gap long enough for the check to slip through.
  * the on-time cycles must NOT look like that, otherwise the test has no power.

If instead the gated intervals contain long idle stretches while the value sat above
30, starvation is refuted and something else is gating the exit.

Also corrects the decision instant.  cancel_before_close=true, so a flatten OPENS
with a cancel sweep, not with the first 'STR CLOSE'.  At 20 s per cancel a 20-pending
sweep takes 6.7 min -- which is the whole size of the seven short leads.  t0 here is
the first cancel of the terminal sweep.
"""
from __future__ import annotations

import statistics
import sys

sys.path.insert(0, r"C:\websites\mt5 2")
from tools.forensics.dataset import load_all, FINAL_REGIME_START, CONTRACT  # noqa: E402

TARGET = 30.0
CHAIN = 45.0     # seconds; joins a cancel run in either regime (0.1 s and 20 s)


def main() -> None:
    orders, positions, deals, cycles = load_all()
    fin = [c for c in cycles if c.start >= FINAL_REGIME_START]

    marks = []
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
        t_close = min(cl)

        # every order action in the cycle: placement (open_time), cancel (end_time)
        acts = []
        for o in c.orders:
            if not o.is_grid:
                continue
            if o.open_time and o.open_time <= t_close:
                acts.append(o.open_time)
            if o.state == "canceled" and o.end_time and o.end_time <= t_close:
                acts.append(o.end_time)
        acts.sort()

        # t0 = first cancel of the terminal cancel sweep before the closes
        cancels = sorted(o.end_time for o in c.orders
                         if o.is_grid and o.state == "canceled" and o.end_time
                         and o.end_time <= t_close)
        t0 = t_close
        if cancels:
            k = len(cancels) - 1
            while k > 0 and (cancels[k] - cancels[k - 1]).total_seconds() <= CHAIN:
                k -= 1
            if (t_close - cancels[-1]).total_seconds() <= 120.0:
                t0 = cancels[k]

        rel = [p for p in positions
               if p.open_time <= t_close and (p.is_open or
                                              (p.close_time and p.close_time >= c.start))]
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
        for t, m in marks:
            if t < c.start:
                continue
            if t > t0:
                break
            while j < len(ev) and ev[j][0] <= t:
                _, _, da, db, dc, dr = ev[j]
                A += da; B += db; C += dc; R += dr
                j += 1
            if R + m * A - B + C >= TARGET:
                first = (t, R + m * A - B + C)
                break
        rows.append(dict(i=c.index, t0=t0, t_close=t_close, first=first,
                         acts=acts, start=c.start,
                         ncancel=len(cancels),
                         cancel_span=((cancels[-1] - cancels[0]).total_seconds()
                                      if len(cancels) > 1 else 0.0)))

    def busy(acts, a, b):
        """max idle gap in [a,b], counting the edges."""
        pts = [a] + [t for t in acts if a < t < b] + [b]
        return max((pts[k + 1] - pts[k]).total_seconds()
                   for k in range(len(pts) - 1)), len(pts) - 2

    scored = [r for r in rows if r["first"]]
    lead = {r["i"]: (r["t0"] - r["first"][0]).total_seconds() for r in scored}
    late = [r for r in scored if lead[r["i"]] > 120]
    ontime = [r for r in scored if lead[r["i"]] <= 120]

    print("=" * 104)
    print("A. DECISION INSTANT CORRECTED to the first cancel of the terminal sweep")
    print("=" * 104)
    print(f"  cycles scored: {len(scored)} of {len(rows)}")
    print(f"    lead <= 2 min (fired on time) : {len(ontime):>3} = {len(ontime)/len(scored):.1%}")
    print(f"    lead >  2 min (GATED)         : {len(late):>3} = {len(late)/len(scored):.1%}")
    sp = [r["cancel_span"] for r in rows if r["cancel_span"] > 0]
    print(f"    terminal cancel sweep length: median {statistics.median(sp)/60:.1f} min"
          f"  (this is what the naive t0 was double-counting as lead)")

    print()
    print("=" * 104)
    print("B. WAS THE EA BUSY across the gated interval?  (starvation test)")
    print("=" * 104)
    print("  max idle = longest stretch with NO placement and NO cancel while the")
    print("  basket was already >= 30.  Under starvation this must stay near the")
    print("  20 s rearm_delay; a multi-minute idle gap refutes it.")
    print()
    print(f"  {'cyc':>5} {'lead':>9} {'actions':>8} {'max idle':>10} {'act/min':>8} "
          f"{'rescue?':>8}  verdict")
    RESCUE = {187, 197, 234, 244, 250, 252}
    ok = 0
    for r in sorted(late, key=lambda r: -lead[r["i"]]):
        gap, n = busy(r["acts"], r["first"][0], r["t0"])
        ld = lead[r["i"]]
        rate = n / (ld / 60.0) if ld else 0.0
        v = "BUSY (starved)" if gap <= 45.0 else f"IDLE {gap/60:.1f} min -> not starvation"
        ok += gap <= 45.0
        print(f"  {r['i']:>5} {ld/60:>7.1f}m {n:>8} {gap:>9.1f}s {rate:>8.2f} "
              f"{'YES' if r['i'] in RESCUE else '-':>8}  {v}")
    print(f"\n  {ok}/{len(late)} gated intervals are continuously busy.")

    print()
    print("=" * 104)
    print("C. CONTROL -- are the ON-TIME cycles busy too?  (does the test discriminate?)")
    print("=" * 104)
    ctl = []
    for r in ontime:
        gap, n = busy(r["acts"], r["first"][0], r["t0"]) if lead[r["i"]] > 5 else (0.0, 0)
        # measure the 10 min BEFORE the decision instead, so the window is comparable
        from datetime import timedelta
        g2, n2 = busy(r["acts"], r["t0"] - timedelta(minutes=10), r["t0"])
        ctl.append(g2)
    lat = []
    for r in late:
        from datetime import timedelta
        g2, _ = busy(r["acts"], r["t0"] - timedelta(minutes=10), r["t0"])
        lat.append(g2)
    print(f"  max idle gap in the 10 min before the decision instant:")
    print(f"    ON-TIME cycles (n={len(ctl)}): median {statistics.median(ctl):.1f}s"
          f"   >45 s idle: {sum(1 for g in ctl if g>45)}/{len(ctl)}")
    print(f"    GATED   cycles (n={len(lat)}): median {statistics.median(lat):.1f}s"
          f"   >45 s idle: {sum(1 for g in lat if g>45)}/{len(lat)}")
    print()
    print("  If the on-time cycles show long idle gaps and the gated ones do not, the")
    print("  difference between firing and not firing IS the presence of pending work.")


if __name__ == "__main__":
    main()
