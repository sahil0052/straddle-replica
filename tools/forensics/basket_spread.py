"""The $30 crossings are a BID/ASK artifact, not a gate.  Quantified.

basket_starvation.py refuted the starvation hypothesis outright.  If the basket
check were skipped while re-arm work was outstanding, the gated intervals would be
continuously busy.  They are the opposite: 0 of 10 were busy, and cycle 194 sat
IDLE for 85.9 minutes -- no placement, no cancel -- while my reconstruction says
the basket was already worth more than $30.  A one-action-per-tick machine with
nothing to do reaches CheckCycleTargets on the very next tick.  So either the
Target has a rule I cannot see, or my reconstruction is wrong.

It is my reconstruction, and the error is systematic in one direction.

    MT5:  POSITION_PROFIT for a LONG  is valued at BID
          POSITION_PROFIT for a SHORT is valued at ASK
          -- always the side the position would have to cross to exit.

    Mine: one mark `m` taken from the nearest trade print, used for both.

Write bid = m - s/2 and ask = m + s/2:

    true    = SUM_long  v*100*(m - s/2 - open) + SUM_short v*100*(open - m - s/2)
            = m*A - B + C  -  (s/2) * SUM(v*100)
    mine    = m*A - B + C

so mine overstates the trigger by (s/2) * GROSS exposure -- and it is GROSS, not
net, because the half-spread penalises longs and shorts alike.  The net delta A
cancels between the two sides; the spread cost does not.  That is the whole point:
a straddle basket can be delta-flat and still carry a large gross spread cost.

At 18 live positions across the 0.01/0.06/0.15 tiers, gross exposure is 100-150
$/point, so a 0.25-point spread is a $12-19 systematic overstatement.  Nine of the
thirteen "gated" cycles crossed at a value between 30.91 and 42.46.  Every one of
them is inside that correction.

This is the same error class as the B7 false alarm: I measured at the outcome
variable (a trade print, which is one side of the book) instead of the decision
variable (the book side the EA actually values against).

So: sweep the half-spread, re-score, and see whether the gated set dissolves.  A
real gate does not care what spread I assume.  An artifact decays to nothing.

t0 also corrected properly this time.  The previous chain-walk joined any two
cancels within 45 s, which during a rescue walks back through the trend-side cancel
churn and drags t0 hours earlier -- that is why it scored 40 cycles instead of 99.
The terminal sweep is a run of cancels with NO placement between them, and the
measured sweep is fast (median 6 s), so cancel_before_close costs seconds, not the
6.7 minutes I assumed.  The short leads were never a t0 artifact.
"""
from __future__ import annotations

import statistics
import sys

sys.path.insert(0, r"C:\websites\mt5 2")
from tools.forensics.dataset import load_all, FINAL_REGIME_START, CONTRACT  # noqa: E402

TARGET = 30.0
RESCUE = {187, 197, 234, 244, 250, 252}


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

        # terminal cancel sweep: contiguous cancels with NO placement between them
        acts = []
        for o in c.orders:
            if not o.is_grid:
                continue
            if o.open_time and o.open_time <= t_close:
                acts.append((o.open_time, "place"))
            if o.state == "canceled" and o.end_time and o.end_time <= t_close:
                acts.append((o.end_time, "cancel"))
        acts.sort()
        t0 = t_close
        k = len(acts) - 1
        while k >= 0 and acts[k][1] == "cancel":
            t0 = acts[k][0]
            k -= 1
        sweep = (t_close - t0).total_seconds()

        rel = [p for p in positions
               if p.open_time <= t_close and (p.is_open or
                                              (p.close_time and p.close_time >= c.start))]
        ev = []
        for p in rel:
            a = p.dir * p.volume * CONTRACT
            g = p.volume * CONTRACT
            ev.append((p.open_time, 0, a, a * p.open_price, p.swap, 0.0, g))
            if p.close_time:
                ev.append((p.close_time, 1, -a, -a * p.open_price, -p.swap,
                           p.net if p.close_time >= c.start else 0.0, -g))
        ev.sort(key=lambda r: (r[0], r[1]))

        # walk the marks once, recording (t, value, gross) at every print
        A = B = C = R = G = 0.0
        j = 0
        trail = []
        for t, m in marks:
            if t < c.start:
                continue
            if t > t0:
                break
            while j < len(ev) and ev[j][0] <= t:
                _, _, da, db, dc, dr, dg = ev[j]
                A += da; B += db; C += dc; R += dr; G += dg
                j += 1
            trail.append((t, R + m * A - B + C, G))
        if not trail:
            continue
        rows.append(dict(i=c.index, t0=t0, sweep=sweep, trail=trail,
                         start=c.start, final=c.realized))

    def score(half):
        """returns (ontime, gated, never) at a given half-spread in points."""
        on, gt, nv = [], [], []
        for r in rows:
            hit = next(((t, v - half * g, g)
                        for t, v, g in r["trail"] if v - half * g >= TARGET), None)
            if hit is None:
                nv.append(r)
            elif (r["t0"] - hit[0]).total_seconds() > 120:
                gt.append((r, hit))
            else:
                on.append((r, hit))
        return on, gt, nv

    print("=" * 104)
    print("A. t0 CORRECTED -- the terminal cancel sweep is FAST, not 20 s-paced")
    print("=" * 104)
    sw = [r["sweep"] for r in rows]
    print(f"  cycles: {len(rows)}")
    print(f"  first cancel of terminal sweep -> first STR CLOSE:")
    print(f"    median {statistics.median(sw):.1f}s   p90 "
          f"{sorted(sw)[int(len(sw)*0.9)]:.1f}s   max {max(sw):.1f}s")
    print("  -> cancel_before_close costs SECONDS.  The 2-6 min short leads were")
    print("     never a decision-instant artifact; they are real crossings.")

    print()
    print("=" * 104)
    print("B. SWEEP THE HALF-SPREAD -- does the gated set survive?")
    print("=" * 104)
    print("  half = assumed half-spread in points.  correction = half * gross $/pt.")
    print("  A real gate is indifferent to `half`.  An artifact decays.")
    print()
    print(f"  {'half':>6} {'spread':>8} {'on time':>9} {'GATED':>7} {'sub-30':>8}"
          f"   {'gated cycles'}")
    for half in (0.0, 0.05, 0.10, 0.125, 0.15, 0.20, 0.25):
        on, gt, nv = score(half)
        ids = ",".join(str(r["i"]) for r, _ in
                       sorted(gt, key=lambda x: -(x[0]["t0"] - x[1][0]).total_seconds()))
        print(f"  {half:>6.3f} {2*half:>8.2f} {len(on):>9} {len(gt):>7} {len(nv):>8}"
              f"   {ids}")

    print()
    print("=" * 104)
    print("C. PER-CYCLE: is the crossing inside the spread correction?")
    print("=" * 104)
    on0, gt0, nv0 = score(0.0)
    print("  gross = gross exposure in $/point at the crossing instant.")
    print("  margin = val@cross - 30.   corr(0.25) = the bid/ask cost at a 0.25-pt spread.")
    print()
    print(f"  {'cyc':>5} {'lead':>9} {'val@cross':>10} {'margin':>8} {'gross':>8}"
          f" {'corr(.25)':>10} {'resc':>5}  verdict")
    dissolved = 0
    for r, hit in sorted(gt0, key=lambda x: -(x[0]["t0"] - x[1][0]).total_seconds()):
        ld = (r["t0"] - hit[0]).total_seconds()
        t, v, g = hit
        margin = v - TARGET
        corr = 0.125 * g
        killed = margin <= corr
        dissolved += killed
        print(f"  {r['i']:>5} {ld/60:>7.1f}m {v:>10.2f} {margin:>8.2f} {g:>8.1f}"
              f" {corr:>10.2f} {'YES' if r['i'] in RESCUE else '-':>5}  "
              f"{'inside spread -> PHANTOM' if killed else 'SURVIVES the correction'}")
    print(f"\n  {dissolved}/{len(gt0)} gated crossings are inside a 0.25-point spread.")

    print()
    print("=" * 104)
    print("D. THE SURVIVORS -- how long was the value ACTUALLY above 30?")
    print("=" * 104)
    print("  The EA polls every 100 ms, so ONE genuine instant above 30 is enough to")
    print("  fire.  A phantom shows a single isolated print above 30; a real hold shows")
    print("  a long run of consecutive prints above it.")
    print()
    print(f"  {'cyc':>5} {'lead':>9} {'prints in lead':>15} {'above 30':>9}"
          f" {'longest run':>12} {'min val':>9}")
    for r, hit in sorted(gt0, key=lambda x: -(x[0]["t0"] - x[1][0]).total_seconds()):
        t, v, g = hit
        seg = [(tt, vv - 0.125 * gg) for tt, vv, gg in r["trail"] if tt >= t]
        above = sum(1 for _, vv in seg if vv >= TARGET)
        run = best = 0
        for _, vv in seg:
            run = run + 1 if vv >= TARGET else 0
            best = max(best, run)
        ld = (r["t0"] - t).total_seconds()
        print(f"  {r['i']:>5} {ld/60:>7.1f}m {len(seg):>15} {above:>9}"
              f" {best:>12} {min(vv for _, vv in seg):>9.2f}")
    print()
    print("  (values here already carry the 0.25-pt spread correction)")


if __name__ == "__main__":
    main()
