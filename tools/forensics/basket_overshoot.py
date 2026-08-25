"""Did the total GAP THROUGH $30, or did the Target HOLD past it?

The mark-free estimator settles the rule's value: `final = pre + burst` is the total at
the exit decision, needing no mark, and its median is 29.32 against a hypothesised
30.00.  Three in-code estimators said 29.31 / 29.36 / 30.46.  The value is not in
doubt any more.

What is in doubt is the right tail.  Only 29/99 land inside [25,35]; p75 is 45.83 and
the tail runs to 632.83.  A threshold rule cannot exit at 632 unless something lets it.
Two candidates, and they are distinguishable without any mark:

  GAP-THROUGH.  The basket total is NOT a continuous function of time.  It has a
      sensitivity of `gross` dollars per point -- 30 to 100 $/pt here -- so a 4-point
      tick sequence moves the total by $120-400 with no rule involved.  The EA polls
      at 100 ms but PRICE does not move in $1 increments.  If the total was below 30
      on one poll and 400 on the next, a correct EA exits at 400.  The signature: the
      implied price move needed to explain the overshoot is SMALL and consistent
      across cycles -- a few points, the same size as ordinary XAUUSD noise.

  HOLD RULE.  The Target sees 30, declines, and exits later on some other condition.
      The signature: the implied move is absurd (tens to hundreds of points), i.e. no
      plausible tick sequence explains the overshoot, so time must have passed.

The test is a division.  overshoot = final - 30; sensitivity = gross $/pt at the exit;
implied_move = overshoot / sensitivity, in points.  Then compare implied_move against
the price dispersion actually observed inside the flatten sweeps (median 0.610 pt, p90
6.790 pt).  If the overshoots need moves of that order, they are gap-throughs and the
threshold rule is complete as written.

This also re-reads the "gated" cycles one last time.  They are exactly the high-P&L
cycles -- 252 (+632.83), 253 (+518.03), 187 (+112.61), 194 (+111.93) -- which is not a
coincidence and cannot be waved away as noise: the mark-free path agrees they exited
far above 30.  So the question is not whether they overshot.  They did.  It is whether
a tick can carry a heavy basket that far in one poll interval.
"""
from __future__ import annotations

import statistics
import sys
from datetime import timedelta

sys.path.insert(0, r"C:\websites\mt5 2")
from tools.forensics.dataset import load_all, FINAL_REGIME_START, CONTRACT  # noqa: E402

TARGET = 30.0
SWEEP = 300.0
GATED = {194, 252, 187, 244, 250, 197, 219, 253, 181, 269}


def main() -> None:
    orders, positions, deals, cycles = load_all()
    fin = [c for c in cycles if c.start >= FINAL_REGIME_START]

    rows = []
    for c in fin:
        cl = [o.open_time for o in c.orders
              if o.comment and o.comment.strip().upper().startswith("STR CLOSE")]
        if not cl:
            continue
        t0 = min(cl)
        pre = burst = post = 0.0
        sw = []
        for p in c.positions:
            if p.is_open or not p.close_time:
                continue
            if p.close_time < t0 - timedelta(seconds=5):
                pre += p.net
            elif p.close_time <= t0 + timedelta(seconds=SWEEP):
                burst += p.net
                sw.append(p)
            else:
                post += p.net
        if not sw:
            continue
        gross = sum(p.volume * CONTRACT for p in sw)          # $ per point
        net_d = abs(sum(p.dir * p.volume * CONTRACT for p in sw))
        exitv = pre + burst
        rows.append(dict(i=c.index, exitv=exitv, over=exitv - TARGET, gross=gross,
                         netd=net_d, n=len(sw), pre=pre, burst=burst, post=post,
                         final=c.realized))

    # ---- A. the implied price move behind each overshoot -------------------
    print("=" * 104)
    print("A. HOW BIG A PRICE MOVE WOULD EXPLAIN EACH OVERSHOOT?")
    print("=" * 104)
    print("  implied = (exit value - 30) / gross $-per-point, in POINTS of XAUUSD.")
    print("  Observed price dispersion inside a flatten sweep: median 0.61 pt, p90 6.79 pt.")
    print("  An overshoot needing a move of that order is a gap-through, not a hold.")
    print()
    big = sorted((r for r in rows if r["over"] > 15.0), key=lambda r: -r["over"])
    print(f"  {'cyc':>5} {'exit val':>9} {'overshoot':>10} {'gross':>8} {'net d':>7}"
          f" {'implied pt':>11} {'gated':>6}  reading")
    for r in big[:22]:
        imp = r["over"] / r["gross"] if r["gross"] else 0.0
        note = ("ordinary tick noise -> GAP-THROUGH" if imp <= 7.0
                else "large but plausible intraday" if imp <= 25.0
                else "implausible in one poll -> HOLD")
        print(f"  {r['i']:>5} {r['exitv']:>9.2f} {r['over']:>10.2f} {r['gross']:>8.1f}"
              f" {r['netd']:>7.1f} {imp:>10.2f}p {'YES' if r['i'] in GATED else '-':>6}"
              f"  {note}")

    imps = [r["over"] / r["gross"] for r in rows if r["gross"] and r["over"] > 0]
    print()
    print(f"  all {len(imps)} cycles with a positive overshoot:")
    print(f"    implied move  median {statistics.median(imps):.2f}p"
          f"   p75 {sorted(imps)[3*len(imps)//4]:.2f}p"
          f"   p90 {sorted(imps)[9*len(imps)//10]:.2f}p"
          f"   max {max(imps):.2f}p")
    print(f"    within ordinary sweep dispersion (<= 6.79p): "
          f"{sum(1 for x in imps if x <= 6.79)}/{len(imps)}")

    # ---- B. the same question from the other end: undershoots -------------
    print()
    print("=" * 104)
    print("B. THE SYMMETRY TEST -- a threshold rule cannot UNDERSHOOT")
    print("=" * 104)
    print("  Gap-through is one-sided: you can only overshoot a rising threshold.")
    print("  Any exit materially BELOW 30 needs a different explanation entirely --")
    print("  closing slippage on a market-order sweep, which is also one-sided.")
    print()
    under = sorted((r for r in rows if r["exitv"] < 20.0), key=lambda r: r["exitv"])
    print(f"  cycles exiting below $20: {len(under)}/{len(rows)}")
    print(f"  {'cyc':>5} {'exit val':>9} {'pre':>9} {'burst':>9} {'n sweep':>8}"
          f" {'gross':>8} {'slip pt':>9}")
    for r in under[:14]:
        slip = (TARGET - r["exitv"]) / r["gross"] if r["gross"] else 0.0
        print(f"  {r['i']:>5} {r['exitv']:>9.2f} {r['pre']:>9.2f} {r['burst']:>9.2f}"
              f" {r['n']:>8} {r['gross']:>8.1f} {slip:>8.2f}p")
    if under:
        sl = [(TARGET - r["exitv"]) / r["gross"] for r in under if r["gross"]]
        print(f"\n  implied adverse slip: median {statistics.median(sl):.2f}p"
              f"   max {max(sl):.2f}p")
        print("  -> if this is the same order as the overshoot moves, ONE mechanism")
        print("     (price moving faster than the basket can be valued) explains both")
        print("     tails and the rule needs no extra condition.")

    # ---- C. the distribution, stated honestly -----------------------------
    print()
    print("=" * 104)
    print("C. THE RULE, RESTATED WITH ITS ACTUAL TOLERANCE")
    print("=" * 104)
    ev = [r["exitv"] for r in rows]
    print(f"  exit value, mark-free, n={len(ev)}:")
    print(f"    median {statistics.median(ev):>8.2f}   <- the threshold")
    for lo, hi in ((25, 35), (20, 40), (15, 50), (0, 100)):
        print(f"    inside [{lo:>3},{hi:>3}]: {sum(1 for x in ev if lo<=x<=hi):>3}/{len(ev)}"
              f"  = {sum(1 for x in ev if lo<=x<=hi)/len(ev):>5.1%}")
    print(f"    below 0:  {sum(1 for x in ev if x < 0)}/{len(ev)}"
          f"    above 100: {sum(1 for x in ev if x > 100)}/{len(ev)}")
    print()
    print("  A $30 threshold on a basket carrying 30-100 $/pt cannot land ON 30.  The")
    print("  quantum of the decision variable is one tick x gross, which is $3-30.  So")
    print("  the rule is `first poll at which total >= 30`, and the OUTCOME distribution")
    print("  is 30 plus one tick-jump of overshoot, minus sweep slippage.  Median 29.32")
    print("  is the correct signature of exactly that, and it is what the replica does.")


if __name__ == "__main__":
    main()
