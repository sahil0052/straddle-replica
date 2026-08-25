"""Corrections and deep-dives on parity_ledger.py.

Three things in that run need resolving before any of it can be reported.

1. MY BUG.  I attributed the basket rule's money to the FLATTEN SWEEP alone,
   getting 42 cycles below -$25 and a -$7,122 exposure.  That is the wrong
   quantity.  The $30 rule is `realized_since_cycle_start + floating >= 30`,
   i.e. it targets the WHOLE CYCLE's net.  The flatten sweep is almost always
   negative on its own -- it is the leg that closes the losers, after the
   winners have already been banked by the ratchet.  Panel A measures the
   cycle net, which is what the rule actually governs.

2. B2 LOOKED LIKE A REFUTATION and is not.  Median restart latency came out
   2.0 s against a 20 s floor, but `fin` spans the Jul-24 regime break, so
   69 fast pre-break restarts swamp 32 paced post-break ones.  Panel B splits
   it.  If the post-break half is a clean 20 s floor, restart_delay_ms is
   reconfirmed; if not, it is broken.

3. B7 CONTRADICTS AGENTS.md TWICE, and this is the part that matters, because
   the ratchet governs 2,239 SL closures and ~30% of the realised money:
     - AGENTS.md: "hard GAP on (1,2) steps".  Measured: 90 closures (4.02%)
       land inside it.
     - AGENTS.md: "Zero losers ever closed at SL (SL is never placed below
       entry)."  Measured: 36 closures below entry.
   Both were established on 287 winners; this is 2,239.  Either the model is
   wrong, or both are boundary/slippage artifacts.  Panels C and D decide it
   quantitatively: a boundary artifact clusters at the boundary and scales with
   step-estimate error, a real model gap is spread out.

Panel E checks the weekend, since B3 showed zero Sat/Sun activity while every
restart gap was under 32 s -- which can only mean the Target holds baskets
straight through the weekend rather than flattening for it.
"""
from __future__ import annotations

import statistics
import sys
from collections import Counter
from datetime import datetime, timedelta

sys.path.insert(0, r"C:\websites\mt5 2")
from tools.forensics.dataset import load_all, FINAL_REGIME_START  # noqa: E402

BREAK = datetime(2026, 7, 24, 12, 0, 0)
SL_TOL = 0.60


def main() -> None:
    orders, positions, deals, cycles = load_all()
    fin = [c for c in cycles if c.start >= FINAL_REGIME_START]

    # ------------------------------------------------------------------ panel A
    print("=" * 100)
    print("A. CORRECTED MONEY LEDGER -- cycle NET vs the $30 basket target")
    print("=" * 100)
    print("  The rule is realized_since_cycle_start + floating >= 30, so the unit of")
    print("  account is the CYCLE, not the flatten sweep.")
    print()
    nets = [(c.index, c.realized, c) for c in fin if c.end]
    good = [(i, v) for i, v, _ in nets if v >= 25.0]
    band = [(i, v) for i, v, _ in nets if 25.0 <= v <= 35.0]
    bad = [(i, v) for i, v, _ in nets if v < -25.0]
    mid = [(i, v) for i, v, _ in nets if -25.0 <= v < 25.0]
    print(f"  closed cycles measured           : {len(nets)}")
    print(f"  net >= +25 (target honoured)     : {len(good):>4}  "
          f"= {len(good)/len(nets):.1%}   ${sum(v for _,v in good):>10.2f}")
    print(f"     of which in the [25,35] band  : {len(band):>4}  "
          f"= {len(band)/len(nets):.1%}")
    print(f"  net in (-25,+25) (near-flat)     : {len(mid):>4}  "
          f"= {len(mid)/len(nets):.1%}   ${sum(v for _,v in mid):>10.2f}")
    print(f"  net < -25  (UNEXPLAINED exits)   : {len(bad):>4}  "
          f"= {len(bad)/len(nets):.1%}   ${sum(v for _,v in bad):>10.2f}")
    print()
    print("  the unexplained exits in full:")
    for i, v in sorted(bad, key=lambda r: r[1]):
        c = next(x for x in fin if x.index == i)
        hrs = (c.end - c.start).total_seconds() / 3600.0
        print(f"    cyc {i:>4}  net ${v:>9.2f}   {hrs:>7.2f} h   "
              f"{len(c.positions):>4} positions   start {str(c.start)[:19]}")
    tot = sum(v for _, v, _ in nets)
    absall = sum(abs(v) for _, v, _ in nets)
    print()
    print(f"  TOTAL final-regime realised: ${tot:.2f}")
    print(f"  share of |money| in unexplained cycles: "
          f"{sum(abs(v) for _, v in bad) / absall:.2%}")

    # -- is the 31% near-flat band real, or a cycle-detection artifact? --------
    print()
    print("  THE 31% NEAR-FLAT BAND.  A 'cycle' here is detected as a dense run of")
    print("  >=40 distinct (side,level) FIRST placements.  A mid-cycle mass re-arm of")
    print("  40+ levels would be misdetected as a new cycle, splitting one real cycle")
    print("  in two and stranding the money in one half.  A REAL deployment sweeps all")
    print("  60 keys (30 per side); a misdetected re-arm will be short or one-sided.")
    print()
    print(f"    {'band':<22} {'n':>4} {'median keys':>12} {'median B':>9} "
          f"{'median S':>9} {'full 60':>8}")
    for lab, sel in (("net >= +25", lambda v: v >= 25.0),
                     ("net in (-25,+25)", lambda v: -25.0 <= v < 25.0),
                     ("net < -25", lambda v: v < -25.0)):
        sub = [c for _, v, c in nets if sel(v)]
        if not sub:
            continue
        keys = [len({(o.side, o.level) for o in c.burst_orders}) for c in sub]
        nb = [len({o.level for o in c.burst_orders if o.side == "B"}) for c in sub]
        ns = [len({o.level for o in c.burst_orders if o.side == "S"}) for c in sub]
        full = sum(1 for k in keys if k >= 60)
        print(f"    {lab:<22} {len(sub):>4} {statistics.median(keys):>12.0f} "
              f"{statistics.median(nb):>9.0f} {statistics.median(ns):>9.0f} "
              f"{full:>4}/{len(sub)}")

    # ------------------------------------------------------------------ panel B
    print()
    print("=" * 100)
    print("B. RESTART LATENCY split at the Jul-24 break")
    print("=" * 100)
    for lab, sel in (("BEFORE Jul-24 12:00", lambda c: c.start < BREAK),
                     ("AFTER  Jul-24 12:00", lambda c: c.start >= BREAK)):
        lat = [(c.end - c.flat_time).total_seconds()
               for c in fin if c.end and c.flat_time and sel(c)]
        if not lat:
            continue
        lat.sort()
        u20 = sum(1 for x in lat if x < 19.0)
        print(f"  {lab}:  n={len(lat):>3}  min={lat[0]:>6.1f}s  "
              f"median={statistics.median(lat):>6.1f}s  max={lat[-1]:>6.1f}s   "
              f"under 19 s: {u20}/{len(lat)}")
        print(f"      deciles: " + " ".join(
            f"{lat[min(len(lat)-1, int(len(lat)*k/10))]:.1f}" for k in range(10)))

    # ------------------------------------------------------------------ panel C
    print()
    print("=" * 100)
    print("C. THE (1,2)-STEP GAP -- boundary artifact or real model failure?")
    print("=" * 100)
    print("  A boundary artifact piles up just above 1.0 and just below 2.0, because")
    print("  `step` is a MEDIAN FIT of the lattice and a 0.5% error on a ~1.33 pt")
    print("  step moves a 1.0-step reading by 0.005 steps -- but SPREAD at the stop")
    print("  fill moves it far more.  A real failure spreads across the interval.")
    print()
    sl = []
    for c in fin:
        if not c.step:
            continue
        for p in c.positions:
            if p.is_open or p.stop_loss is None or p.close_price is None:
                continue
            if abs(p.close_price - p.stop_loss) > SL_TOL:
                continue
            steps = (p.dir * (p.close_price - p.open_price)) / c.step
            # what the SL was set to, in steps -- excludes fill slippage
            sl_steps = (p.dir * (p.stop_loss - p.open_price)) / c.step
            sl.append((steps, sl_steps, c.index, c.step, p))
    gap = [r for r in sl if 1.0 < r[0] < 2.0]
    print(f"  total matched SL closures: {len(sl)}      inside (1,2): {len(gap)}")
    print()
    print("  distribution INSIDE the gap, by tenth of a step:")
    h = Counter(round(r[0], 1) for r in gap)
    for k in sorted(h):
        print(f"    {k:>4.1f}  {h[k]:>4}  " + "#" * h[k])
    print()
    print("  same 90, but measured at the SL PRICE rather than the fill price")
    print("  (this removes slippage; if the EA never SETS a stop in (1,2) then")
    print("   these should collapse out of the interval):")
    h2 = Counter(round(r[1], 1) for r in gap)
    inside_sl = sum(n for k, n in h2.items() if 1.0 < k < 2.0)
    for k in sorted(h2):
        mark = "" if 1.0 < k < 2.0 else "   <- OUTSIDE the gap once slippage is removed"
        print(f"    {k:>4.1f}  {h2[k]:>4}  " + "#" * h2[k] + mark)
    print(f"\n  of {len(gap)} fills inside (1,2), only {inside_sl} had their STOP")
    print(f"  set inside (1,2).  slippage explains {len(gap)-inside_sl}.")

    # ------------------------------------------------------------------ panel D
    print()
    print("=" * 100)
    print("D. SL CLOSURES BELOW ENTRY -- does the EA ever stop out at a loss?")
    print("=" * 100)
    sub = sorted((r for r in sl if r[0] < -0.001), key=lambda r: r[0])
    print(f"  count: {len(sub)} of {len(sl)}  ({len(sub)/len(sl):.2%})")
    if sub:
        print()
        print(f"  {'steps':>8} {'sl_steps':>9} {'$net':>9} {'pts below entry':>16} "
              f"{'lvl':>4} {'vol':>6}  cyc")
        for st, sls, ci, stp, p in sub[:20]:
            print(f"  {st:>8.3f} {sls:>9.3f} {p.net:>9.2f} "
                  f"{p.dir*(p.close_price-p.open_price):>16.3f} "
                  f"{p.level if p.level else 0:>4} {p.volume:>6.2f}  {ci}")
        worst_pts = min(p.dir * (p.close_price - p.open_price)
                        for _, _, _, _, p in sub)
        neg_sl = sum(1 for _, sls, _, _, _ in sub if sls < -0.001)
        print()
        print(f"  worst excursion below entry: {worst_pts:.3f} points "
              f"= {worst_pts/1.3335:.3f} steps")
        print(f"  how many had the STOP ITSELF below entry: {neg_sl}/{len(sub)}")
        print(f"  net $ in this bucket: {sum(p.net for _,_,_,_,p in sub):.2f}")
        print()
        print("  VERDICT: " + (
            "the EA DOES place stops below entry -- ratchet model is wrong"
            if neg_sl > len(sub) * 0.2 else
            "stops were at/above entry; these are SLIPPAGE fills through a\n"
            "           breakeven stop, which is a broker effect the replica\n"
            "           inherits automatically.  Ratchet model holds."))

    # ------------------------------------------------------------------ panel E
    print()
    print("=" * 100)
    print("E. WEEKEND BEHAVIOUR -- does the Target flatten before the close?")
    print("=" * 100)
    span = []
    for c in fin:
        if not c.end:
            continue
        d = c.start
        crossed = []
        while d <= c.end:
            if d.weekday() == 5:
                crossed.append(d.date())
            d += timedelta(hours=6)
        if crossed:
            span.append((c.index, c.start, c.end,
                         (c.end - c.start).total_seconds() / 3600.0,
                         len([p for p in c.positions if p.is_open or (
                             p.close_time and p.close_time > c.start)])))
    print(f"  cycles whose lifetime spans a Saturday: {len(span)}")
    for i, s, e, h, n in span:
        print(f"    cyc {i:>4}  {str(s)[:16]} ({s.strftime('%a')}) -> "
              f"{str(e)[:16]} ({e.strftime('%a')})  {h:>7.2f} h  {n:>4} positions")
    fri = [c for c in fin if c.flat_time and c.flat_time.weekday() == 4]
    late = [c for c in fri if c.flat_time.hour >= 19]
    print()
    print(f"  Friday flattens: {len(fri)}   of those after 19:00: {len(late)}")
    print("  -> " + ("Target holds baskets THROUGH the weekend; no Friday-close rule."
                     if len(span) >= 2 and not late else
                     "possible Friday-close flatten rule -- INVESTIGATE"))


if __name__ == "__main__":
    main()
