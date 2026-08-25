"""WHAT ARE THE TARGET'S "STR ORB / STR ORS / STR AVB / STR AVS" LEGS?

WHY THIS SCRIPT EXISTS.  parity_scorecard.py panel E found four exit-comment tags
in the Target's final regime that our account has never once produced:

    STR ORS  54      STR ORB  38          -> 92 legs over 100 cycles
    STR AVS  14      STR AVB  14          -> 28 legs over 100 cycles

Grepping our source for the same four strings gives an asymmetric answer:

    StraddleEngine.mqh:1366   recovery_comment = is_buy ? "STR ORB" : "STR ORS"
    StraddleEngine.mqh:991/995   EventSide() recognises ORB / ORS
    StraddleEngine.mqh:992/996   EventSide() recognises AVB / AVS

EventSide is a telemetry helper -- it maps a comment to "buy"/"sell" for the log.
So AVB/AVS exist in our code ONLY as strings the logger knows how to attribute.
There is no emission site for them anywhere.  And the ONE emission site for
ORB/ORS sits inside:

    if(IsHistoricalProfile() && !level_state.recovery_done)      // line 1355
    ...
    bool IsHistoricalProfile() { return profile==HISTORICAL_50 || HISTORICAL_60; }

The live profile is LATEST_30 (Profile=4 in profiles/latest_30_real_safe.set), so
that branch is UNREACHABLE in production.  The else at line 1376 logs
"deferred"/"crossed", sets recovery_done and abandons the level.

That makes the zero on our side NOT an unexercised branch -- an unexercised branch
is one that could fire and did not.  This one cannot fire at all.  The Poisson
argument in panel E is therefore beside the point either way.

BUT a missing emission is only a parity gap if the Target's legs are the thing our
dead branch would have emitted.  Two very different mechanisms could produce them:

  (a) CROSSED-SLOT RECOVERY.  A lattice slot cannot be armed as a stop order
      because price has already moved past it (PendingPriceIsValid fails), so the
      EA takes the fill at market instead.  Signature: the leg's price sits ON a
      lattice slot, volume equals that tier's base, it happens EARLY in the cycle
      near the deployment burst, and the basket is not in trouble.

  (b) DRAWDOWN RESCUE.  The basket is deep underwater and the EA adds an
      averaging leg.  Signature: price is unrelated to any slot, volume is a
      MULTIPLE of the base (Q2 forensics say 2x), it happens LATE in the cycle,
      and floating P&L at that moment is strongly negative (Q2 says ~-400).

These are mutually exclusive predictions, so the data decides it.  The naming is
suggestive but not evidence: OR = "opposite recovery"? AV = "averaging"?  Panel 3
measures rather than guesses.

WHAT WOULD FALSIFY THE CONCLUSION.  If ORB/ORS turn out to be (a) and land at
lattice slots with base volume early in the cycle, our dead branch is the right
implementation and the fix is to make it reachable on LATEST_30.  If they are (b),
the fix is a different feature entirely and line 1366 is a red herring.  Panel 5
prints the discriminator side by side so it cannot be fudged.
"""
from __future__ import annotations

import os
import statistics
import sys
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
import tools.forensics.dataset as DS  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TAGS = ("STR ORB", "STR ORS", "STR AVB", "STR AVS")
# Base ladder volume per tier, confirmed in parity_scorecard panel G on both
# accounts: L1-10 -> 0.01, L11-20 -> 0.06, L21-30 -> 0.15.
TIER = ((10, 0.01), (20, 0.06), (30, 0.15))


def rule(t: str) -> None:
    print()
    print("=" * 100)
    print(t)
    print("=" * 100)


def base_for(level: int | None) -> float | None:
    if level is None:
        return None
    for hi, vol in TIER:
        if level <= hi:
            return vol
    return None


def main() -> None:
    orders, positions, deals, cycles = DS.load_all()
    final = DS.final_regime(cycles)
    keep = {c.index for c in final}
    cyc = {c.index: c for c in final}

    rule("SCOPE")
    print(f"  golden dir        : {DS.GOLDEN}")
    print(f"  cycles            : {len(cycles)} total, {len(final)} in final regime")
    print(f"  regime start      : {DS.FINAL_REGIME_START:%Y-%m-%d}")

    legs = [o for o in orders if (o.comment or "") in TAGS and o.cycle in keep]
    leg_pos = [p for p in positions if (p.comment or "") in TAGS and p.cycle in keep]
    print(f"  rescue-tag orders : {len(legs)}")
    print(f"  rescue-tag posns  : {len(leg_pos)}")
    if not legs and not leg_pos:
        print("  none in scope -- nothing to characterise.")
        return

    # ------------------------------------------------------------------ panel 1
    rule("1. CENSUS  (type / state / volume -- (a) predicts market+base, (b) market+2x)")
    print(f"  {'tag':<9} {'n':>4}  {'order_type':<12} {'state':<10} volumes")
    for tag in TAGS:
        g = [o for o in legs if o.comment == tag]
        if not g:
            print(f"  {tag:<9} {0:>4}  --")
            continue
        ty = Counter(o.order_type for o in g)
        st = Counter(o.state for o in g)
        vol = Counter(round(o.volume, 2) for o in g)
        print(f"  {tag:<9} {len(g):>4}  {str(dict(ty)):<34} {str(dict(st)):<24}"
              f" {dict(sorted(vol.items()))}")
    print()
    print("  A 'buy'/'sell' order_type means MARKET execution; 'buy stop'/'sell stop'")
    print("  would mean these are ordinary pendings under a different comment.")

    # ------------------------------------------------------------------ panel 2
    rule("2. WHERE IN THE CYCLE  (early = crossed-slot recovery, late = drawdown)")
    print(f"  {'tag':<9} {'n':>4}  {'sec after burst_end':>28}   {'as % of cycle length':>22}")
    for tag in TAGS:
        g = [o for o in legs if o.comment == tag]
        if not g:
            continue
        offs, fracs = [], []
        for o in g:
            c = cyc[o.cycle]
            offs.append((o.open_time - c.burst_end).total_seconds())
            span = ((c.end or c.flat_time or o.open_time) - c.start).total_seconds()
            if span > 0:
                fracs.append(100.0 * (o.open_time - c.start).total_seconds() / span)
        q = statistics.quantiles(offs, n=4) if len(offs) > 3 else [float("nan")] * 3
        fq = statistics.quantiles(fracs, n=4) if len(fracs) > 3 else [float("nan")] * 3
        print(f"  {tag:<9} {len(g):>4}   min {min(offs):>9.0f}"
              f"  p25 {q[0]:>9.0f}  med {q[1]:>9.0f}  p75 {q[2]:>9.0f}"
              f"  max {max(offs):>9.0f}"
              f"    med {fq[1]:>5.1f}%")

    # ------------------------------------------------------------------ panel 3
    rule("3. PRICE vs THE LATTICE  (the decisive test)")
    print("  For each leg, distance from the NEAREST slot of the cycle's own lattice,")
    print("  in units of that cycle's step.  Crossed-slot recovery must land ON a")
    print("  slot (~0.00).  A drawdown averaging leg has no reason to.")
    print()
    print(f"  {'tag':<9} {'n':>4}  {'|dist| in steps: med':>22} {'p90':>8} {'max':>8}"
          f"   {'<0.10 step':>11}  nearest-level spread")
    for tag in TAGS:
        g = [o for o in legs if o.comment == tag and o.price]
        if not g:
            continue
        dists, lvls = [], []
        for o in g:
            c = cyc[o.cycle]
            if not c.lattice or c.step <= 0:
                continue
            best = min(c.lattice.items(), key=lambda kv: abs(kv[1] - o.price))
            dists.append(abs(best[1] - o.price) / c.step)
            lvls.append(best[0][1])
        if not dists:
            continue
        on = sum(1 for d in dists if d < 0.10)
        print(f"  {tag:<9} {len(dists):>4}  {statistics.median(dists):>22.3f}"
              f" {sorted(dists)[int(0.9 * (len(dists) - 1))]:>8.3f}"
              f" {max(dists):>8.3f}   {on:>4}/{len(dists):<6}"
              f"  L{min(lvls)}..L{max(lvls)} med L{int(statistics.median(lvls))}")

    # volume against the tier base of the nearest slot
    print()
    print("  Volume as a MULTIPLE of the base volume for the nearest slot's tier:")
    for tag in TAGS:
        g = [o for o in legs if o.comment == tag and o.price]
        mult = []
        for o in g:
            c = cyc[o.cycle]
            if not c.lattice or c.step <= 0:
                continue
            best = min(c.lattice.items(), key=lambda kv: abs(kv[1] - o.price))
            b = base_for(best[0][1])
            if b:
                mult.append(round(o.volume / b, 2))
        if mult:
            print(f"    {tag:<9} {dict(sorted(Counter(mult).items()))}")

    # ------------------------------------------------------------------ panel 4
    rule("4. BASKET STATE AT THE MOMENT THE LEG IS ISSUED")
    print("  realized-since-cycle-start + floating, marked at the nearest deal price.")
    print("  Q2 forensics put the rescue gate near -400 floating; crossed-slot")
    print("  recovery should show a basket in no particular trouble.")
    print()
    marks = sorted((d.time, d.price) for d in deals if d.price and d.time)
    mt = [t for t, _ in marks]
    by_cycle: dict[int, list] = defaultdict(list)
    for p in positions:
        if p.cycle in keep:
            by_cycle[p.cycle].append(p)

    def mark_at(t):
        i = bisect_left(mt, t)
        cand = [j for j in (i - 1, i, i + 1) if 0 <= j < len(marks)]
        if not cand:
            return None
        return min((abs((marks[j][0] - t).total_seconds()), marks[j][1])
                   for j in cand)[1]

    print(f"  {'tag':<9} {'n':>4}  {'basket P&L at issue: min':>26} {'p25':>9}"
          f" {'med':>9} {'p75':>9} {'max':>9}   {'open legs med':>13}")
    for tag in TAGS:
        g = [o for o in legs if o.comment == tag]
        vals, opens = [], []
        for o in g:
            mk = mark_at(o.open_time)
            if mk is None:
                continue
            ps = by_cycle.get(o.cycle, [])
            realized = sum(p.net for p in ps
                           if not p.is_open and p.close_time
                           and p.close_time < o.open_time)
            live = [p for p in ps if p.open_time < o.open_time
                    and (p.is_open or (p.close_time and p.close_time >= o.open_time))]
            floating = sum((mk - p.open_price) * p.dir * p.volume * DS.CONTRACT
                           for p in live)
            vals.append(realized + floating)
            opens.append(len(live))
        if not vals:
            continue
        q = statistics.quantiles(vals, n=4) if len(vals) > 3 else [float("nan")] * 3
        print(f"  {tag:<9} {len(vals):>4}  {min(vals):>26.2f} {q[0]:>9.2f}"
              f" {statistics.median(vals):>9.2f} {q[2]:>9.2f} {max(vals):>9.2f}"
              f"   {statistics.median(opens):>13.1f}")

    # ------------------------------------------------------------------ panel 5
    rule("5. VERDICT PER TAG  (mechanism (a) crossed-slot vs (b) drawdown rescue)")
    for tag in TAGS:
        g = [o for o in legs if o.comment == tag and o.price]
        if not g:
            print(f"  {tag}: absent in this dataset.")
            continue
        dists, mult, offs = [], [], []
        for o in g:
            c = cyc[o.cycle]
            if not c.lattice or c.step <= 0:
                continue
            best = min(c.lattice.items(), key=lambda kv: abs(kv[1] - o.price))
            dists.append(abs(best[1] - o.price) / c.step)
            b = base_for(best[0][1])
            if b:
                mult.append(o.volume / b)
            offs.append((o.open_time - c.burst_end).total_seconds())
        if not dists:
            continue
        on_slot = sum(1 for d in dists if d < 0.10) / len(dists)
        med_mult = statistics.median(mult) if mult else float("nan")
        med_off = statistics.median(offs)
        market = all(o.order_type in ("buy", "sell") for o in g)
        print(f"  {tag}: n={len(g)}  market={market}  on-slot={100*on_slot:.0f}%"
              f"  vol_mult_med={med_mult:.2f}  med_offset={med_off:.0f}s")
        if on_slot >= 0.8 and abs(med_mult - 1.0) < 0.2:
            print("      -> (a) CROSSED-SLOT RECOVERY: on a lattice slot, base volume.")
        elif med_mult >= 1.8:
            print("      -> (b) DRAWDOWN RESCUE: volume is a multiple of the base.")
        else:
            print("      -> INCONCLUSIVE on these two axes; read panels 3 and 4.")

    # ------------------------------------------------------------------ panel 6
    rule("6. EVERY LEG, IN FULL  (28+92 lines is readable; read it, do not trust a median)")
    print(f"  {'time':<19} {'cyc':>4} {'tag':<8} {'type':<10} {'vol':>5} {'price':>9}"
          f" {'state':<9} {'slot':>8} {'d/step':>7} {'+s after burst':>15}")
    for o in sorted(legs, key=lambda x: x.open_time):
        c = cyc[o.cycle]
        slot, dstep = "-", float("nan")
        if o.price and c.lattice and c.step > 0:
            (sd, lv), pr = min(c.lattice.items(), key=lambda kv: abs(kv[1] - o.price))
            slot, dstep = f"{sd}{lv}", (o.price - pr) / c.step
        print(f"  {o.open_time:%Y-%m-%d %H:%M:%S} {o.cycle:>4} {o.comment:<8}"
              f" {o.order_type:<10} {o.volume:>5.2f} {o.price or 0:>9.2f}"
              f" {str(o.state):<9} {slot:>8} {dstep:>7.2f}"
              f" {(o.open_time - c.burst_end).total_seconds():>15.0f}")

    # ------------------------------------------------------------------ panel 7
    rule("7. DID THE SLOT ALREADY EXIST?  (recovery implies the pending was never armed)")
    print("  For each leg, does the cycle carry an ordinary STR <side><level> order at")
    print("  the same slot?  Crossed-slot recovery replaces an order that could NOT be")
    print("  placed, so the slot should be MISSING from the deployment sweep or the")
    print("  order list -- if the pending is present and filled normally, the leg is")
    print("  something else.")
    print()
    hit = Counter()
    for o in sorted(legs, key=lambda x: x.open_time):
        c = cyc[o.cycle]
        if not (o.price and c.lattice and c.step > 0):
            continue
        (sd, lv), pr = min(c.lattice.items(), key=lambda kv: abs(kv[1] - o.price))
        same = [x for x in c.orders if x.is_grid and x.side == sd and x.level == lv]
        states = Counter(x.state for x in same)
        hit[(o.comment, tuple(sorted(states.items())))] += 1
    for (tag, states), n in sorted(hit.items()):
        print(f"  {tag:<9} {n:>4}  slot orders in that cycle: {dict(states)}")


if __name__ == "__main__":
    main()
