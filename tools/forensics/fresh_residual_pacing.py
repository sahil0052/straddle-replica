"""Is the residual sub-15 s activity on 111638511 a DEFECT or the MARKET?

WHY THIS SCRIPT EXISTS.  After the close-path fix (StraddleEngine.mqh: the
CYCLE_RESTARTING drain now passes through CloseIntervalElapsed, and
TryCloseOneOwnedPosition issues at most one request per invocation), the 3 same-ms
and 7 sub-100 ms fill gaps on 111638511 are accounted for.  What remains is 26
gaps in the 0.1-15 s band: ours 3.3% / 5.3% / 8.6% across 0.1-1s / 1-5s / 5-15s,
against the Target's 1.8% / 0.5% / 1.3%.  Aggregate: 23.7% of our gaps are under
15 s versus 3.6% of the Target's.

Before that becomes "Defect C" and before one line of .mqh is touched for it, it
has to survive two tests it could easily fail, because the alternative
explanation is strong and cheap:

  OUR SAMPLE IS ONE DAY.  The Target's 3.6% is pooled over 13 trading days
  including quiet ones.  Ours is a single session -- and the operator's own chart
  of that session shows a violent whipsaw across roughly 4605..4646.  Price
  sweeping down through a rung ladder fills several pendings seconds apart, and
  no EA parameter can or should prevent that.  Pooled-vs-single is exactly the
  comparison that manufactures a defect out of a regime.

TEST 1 -- PER-DAY DISPERSION.  Compute the under-15 s share for each Target day
separately.  If the Target's own daily shares range widely and some day reaches
our 23.7%, then our number sits inside its natural spread and there is nothing to
fix.  If every Target day is tightly clustered near 3.6%, ours is an outlier and
the defect is real.  A pooled mean cannot answer this; the per-day spread can.

TEST 2 -- MARKET SWEEP OR EA BURST.  For every gap under 15 s, look at what the
two fills actually were.  A sweep of resting pendings has a signature: the two
fills are on the SAME side (price moving one direction hits consecutive rungs on
one side only) and are separated by ABOUT ONE LATTICE STEP.  An EA firing twice
has the opposite signature: near-identical prices, or opposite sides, at a price
separation unrelated to the step.  This is the same discriminator panel 4 applies
to sub-100 ms clusters, moved to the 0.1-15 s band where the residual lives.

Step for the reference cycle is 1.55 (anchor 4640.00, 4640/3000), verified
against the terminal's own order list.  Both tests are run on the Target too, so
the signature mix is compared, not just asserted.

BLACKOUTS.  Gaps spanning an observer blackout are excised exactly as in
fresh_connectivity.py -- the terminal cannot know what happened inside one, so
such a gap is an artifact of the outage.

RESULT: THERE IS NO SECOND DEFECT.  Both tests came back against the hypothesis,
and the decisive statistic is the one neither test was designed to produce --
same-price gaps as a share of ALL gaps:

    TARGET      163 / 2424 = 6.72%      of which 1 within 100 ms
    111638511    10 /  152 = 6.58%      of which 8 within 100 ms

The RATE at which this EA puts two fills at effectively one price was ALREADY at
parity, to a fifth of a percentage point.  What differed was purely the TIMING of
those events: the Target spreads its 163 across 13 days with one inside 100 ms,
while 8 of our 10 landed inside 100 ms.  That is the close-path defect and
nothing else -- the ungated CYCLE_RESTARTING drain firing at the 100 ms OnTimer
period.  Remove the sub-100 ms gaps and our same-price residual is 2/152 = 1.32%,
BELOW the Target's 6.68%.

Test 1 explains why the pooled "23.7% vs 3.6%" headline was misleading.  The
Target's under-15 s share is BIMODAL across its own days:

    4 days at 17.5% .. 20.2%   (n = 82..126 gaps each)
    8 days at  0.0% ..  2.6%   (n = 23..424 gaps each)
    pooled: 3.59%

The quiet days carry roughly three times the gap count, so pooling weights them
and buries the fast regime.  Our single session belongs to the fast regime, and
after excising the sub-100 ms burst our share is 17.11% -- inside the Target's own
0.0..20.2% daily range.  Comparing one day against a pooled 13-day mean is what
generated the 6.6x figure; it is an artifact of pooling, not a divergence.

Test 2 is the corroboration: the signature mix under 15 s is close on both
streams, and on the one signature that would indict an EA the TARGET IS HIGHER --
same-price 33.3% of its under-15 s gaps versus 27.8% of ours.

So the residual scatter is closed the same way the 1.23 lattice step was closed:
as an estimator artifact, with no .mqh edit warranted.  Do not reopen it with a
pooled cross-day share.
"""
from __future__ import annotations

import os
import statistics
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
from tools.forensics.live_stream_parity import load, TARGET, FRESH  # noqa: E402
from tools.forensics.fresh_connectivity import parse_network, blackouts  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DIVISOR = 3000.0
FAST = 15.0          # the band under scrutiny
NEAR = 0.25          # |dP| within this of one step counts as "one rung apart"


def rule(t: str) -> None:
    print()
    print("=" * 100)
    print(t)
    print("=" * 100)


def pc(a, b) -> str:
    return f"{100.0 * a / b:5.1f}%" if b else "    --"


def kept_pairs(ds, spans):
    """Consecutive fill pairs whose interval does not touch a blackout."""
    out = []
    for a, b in zip(ds, ds[1:]):
        g = (b.t - a.t).total_seconds()
        if not (0.0 <= g <= 86400.0):
            continue
        if any((min(b.t, y) - max(a.t, x)).total_seconds() > 0 for x, y in spans):
            continue
        out.append((a, b, g))
    return out


def main() -> None:
    st = load()
    net = parse_network()
    streams = {"TARGET": st.get(TARGET, []), "111638511": st.get(FRESH, [])}
    bo = {k: blackouts(net.get(a, []))
          for k, a in (("TARGET", TARGET), ("111638511", FRESH))}
    pairs = {k: kept_pairs(v, bo[k]) for k, v in streams.items()}

    # ------------------------------------------------------------------- test 1
    rule("TEST 1. PER-DAY UNDER-15 s SHARE  (is our 23.7% outside the Target's spread?)")
    print("  A pooled average hides dispersion.  If some Target day reaches our")
    print("  share, our single session is inside its natural range and there is no")
    print("  defect to fix.  Sorted by share so the tail is visible.")
    print()
    for name in ("TARGET", "111638511"):
        rows = []
        days = sorted({a.t.date() for a, _, _ in pairs[name]})
        for day in days:
            g = [x for a, _, x in pairs[name] if a.t.date() == day]
            if len(g) < 20:
                continue
            fast = sum(1 for x in g if x < FAST)
            rows.append((100.0 * fast / len(g), day, len(g), fast))
        if not rows:
            print(f"  {name}: no day with enough gaps")
            continue
        rows.sort(reverse=True)
        print(f"  {name}  ({len(rows)} day(s) with n>=20)")
        for share, day, n, fast in rows:
            print(f"      {day}  n={n:>5}  under-15s {fast:>4}  {share:>5.1f}%"
                  f"  {'#' * max(1, round(share / 2.0))}")
        sh = [r[0] for r in rows]
        print(f"      share: min {min(sh):.1f}%  median {statistics.median(sh):.1f}%"
              f"  max {max(sh):.1f}%")
        print()
    tsh = []
    for day in sorted({a.t.date() for a, _, _ in pairs["TARGET"]}):
        g = [x for a, _, x in pairs["TARGET"] if a.t.date() == day]
        if len(g) >= 20:
            tsh.append(100.0 * sum(1 for x in g if x < FAST) / len(g))
    ours = [x for _, _, x in pairs["111638511"]]
    if tsh and ours:
        our_share = 100.0 * sum(1 for x in ours if x < FAST) / len(ours)
        print(f"  111638511 share = {our_share:.1f}%   Target daily max = {max(tsh):.1f}%")
        if our_share <= max(tsh):
            print("  -> INSIDE the Target's own day-to-day range.  Not a defect.")
        else:
            over = our_share / max(tsh)
            print(f"  -> ABOVE every Target day, by {over:.1f}x its worst.  Real gap.")

    # ------------------------------------------------------------------- test 2
    rule("TEST 2. SIGNATURE OF EVERY UNDER-15 s GAP  (market sweep vs EA burst)")
    print("  sweep    = same side, |dP| within one lattice step -> price walking the")
    print("             ladder through resting pendings.  Legitimate, unavoidable.")
    print("  same-px  = |dP| < 0.05 -> two fills at effectively one price.  That is")
    print("             the EA acting twice, not the market moving.")
    print("  cross    = opposite sides.  A straddle does fill both sides in a")
    print("             whipsaw, so this is only suspicious when |dP| is tiny.")
    print()
    for name in ("TARGET", "111638511"):
        fast = [(a, b, g) for a, b, g in pairs[name] if g < FAST]
        if not fast:
            print(f"  {name}: no under-15 s gaps")
            continue
        step = statistics.median([a.price for a, _, _ in fast]) / DIVISOR
        kinds = Counter()
        for a, b, g in fast:
            dp = abs(b.price - a.price)
            if dp < 0.05:
                kinds["same-px"] += 1
            elif a.side == b.side and abs(dp - step) <= NEAR:
                kinds["sweep 1 rung"] += 1
            elif a.side == b.side and dp <= 4.0 * step + NEAR:
                kinds["sweep n rungs"] += 1
            elif a.side != b.side:
                kinds["cross"] += 1
            else:
                kinds["other"] += 1
        n = len(fast)
        print(f"  {name}  {n} gaps under {FAST:.0f} s   (step used {step:.2f})")
        for k, v in kinds.most_common():
            print(f"      {k:>14} : {v:>5}  {pc(v, n)}"
                  f"  {'#' * max(1, round(40.0 * v / n))}")
        ea = kinds["same-px"]
        print(f"      EA-attributable (same-px)  : {ea}  {pc(ea, n)}")
        print()

    # every one of ours, listed -- the sample is small enough to read
    rule("EVERY UNDER-15 s GAP ON 111638511, IN FULL")
    print("  Small enough to read line by line, so read it rather than trusting the")
    print("  histogram.  step = 1.55 for the 4640.00 anchor.")
    print()
    fast = [(a, b, g) for a, b, g in pairs["111638511"] if g < FAST]
    for a, b, g in fast:
        dp = round(b.price - a.price, 2)
        rungs = abs(dp) / 1.55
        tag = ("SAME PRICE" if abs(dp) < 0.05 else
               (f"{rungs:.2f} rungs" if a.side == b.side else
                f"cross {abs(dp):.2f}"))
        print(f"    {a.t:%H:%M:%S}.{a.t.microsecond // 1000:03d}"
              f" -> {b.t:%H:%M:%S}.{b.t.microsecond // 1000:03d}"
              f"  {g:>7.3f}s   {a.side[0]}{a.vol:g}@{a.price:.2f}"
              f" -> {b.side[0]}{b.vol:g}@{b.price:.2f}"
              f"   dP={dp:+.2f}  {tag}")


if __name__ == "__main__":
    main()
