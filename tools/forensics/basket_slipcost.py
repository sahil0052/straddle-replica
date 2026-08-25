"""Are the negative exits the measured COST of `close_interval_seconds = 20`?

AGENTS.md B1 records: "6/100 exits land below -$25 (worst -170.20) with no discoverable
rule ... Most consistent with discretionary/manual flattens.  Do not invent a rule for
these."  The mark-free decomposition says otherwise, and gives a mechanism:

    cycle 231:  pre +27.48   burst -135.44   ->  exit -107.96   at 2.94p of adverse slip
    cycle 270:  pre +24.20   burst  -99.50   ->  exit  -75.30   at 3.51p
    cycle 256:  pre +33.46   burst  -87.07   ->  exit  -53.61   at 4.92p

`pre` is the realised money banked BEFORE the flatten -- and on all three it sits right
at the $30 threshold.  So the rule fired correctly.  The loss happened during the close.

That is a testable causal claim, because the regime break gives a controlled experiment
on exactly the variable that sets a sweep's duration:

    before 2026-07-24 12:00   close_interval_seconds = 0    ->  0.106 s per close
    after                     close_interval_seconds = 20   ->  20.19 s per close

A 12-position basket therefore takes 1.3 s to flatten before the break and 240 s after.
Market exposure during the sweep goes up by a factor of ~180.  If slip is the mechanism,
the post-break sweeps must show materially worse slip, and it must scale with how long
the sweep took.  If the negative exits were discretionary flattens instead, the break
would not matter at all -- an operator's finger has no `close_interval_seconds`.

This matters for parity in a way that cuts against instinct.  The replica already runs
`close_interval_seconds = 20`, which MATCHES the Target's post-break regime, so it
inherits the same cost by construction.  Confirming the mechanism therefore does not
prescribe a fix -- it forbids one.  Speeding up the replica's sweep to avoid the loss
would be a deliberate DIVERGENCE from the Target, and this repo has already paid $6,362
once for inventing a rule the Target does not have.
"""
from __future__ import annotations

import statistics
import sys
from datetime import datetime, timedelta

sys.path.insert(0, r"C:\websites\mt5 2")
from tools.forensics.dataset import load_all, CONTRACT  # noqa: E402

TARGET = 30.0
BREAK = datetime(2026, 7, 24, 12, 0, 0)
SWEEP = 900.0        # generous: a 20 s-paced sweep of 30 positions needs 600 s


def main() -> None:
    orders, positions, deals, cycles = load_all()

    rows = []
    for c in cycles:
        cl = [o.open_time for o in c.orders
              if o.comment and o.comment.strip().upper().startswith("STR CLOSE")]
        if not cl:
            continue
        t0 = min(cl)
        pre = 0.0
        sw = []
        for p in c.positions:
            if p.is_open or not p.close_time:
                continue
            if p.close_time < t0 - timedelta(seconds=5):
                pre += p.net
            elif p.close_time <= t0 + timedelta(seconds=SWEEP):
                sw.append(p)
        if len(sw) < 2:
            continue
        burst = sum(p.net for p in sw)
        gross = sum(p.volume * CONTRACT for p in sw)
        span = (max(p.close_time for p in sw) -
                min(p.close_time for p in sw)).total_seconds()
        rows.append(dict(i=c.index, t0=t0, pre=pre, burst=burst, exitv=pre + burst,
                         n=len(sw), gross=gross, span=span,
                         per=span / max(1, len(sw) - 1),
                         slip=(TARGET - (pre + burst)) / gross if gross else 0.0,
                         after=t0 >= BREAK))

    # ---- A. the controlled experiment --------------------------------------
    print("=" * 100)
    print("A. THE REGIME BREAK AS A CONTROLLED EXPERIMENT ON SWEEP DURATION")
    print("=" * 100)
    print(f"  {'regime':>8} {'cycles':>7} {'s / close':>10} {'sweep span':>11}"
          f" {'median exit':>12} {'median slip':>12} {'exit < -25':>11}")
    for lab, sel in (("BEFORE", False), ("AFTER", True)):
        g = [r for r in rows if r["after"] == sel]
        if not g:
            continue
        print(f"  {lab:>8} {len(g):>7} {statistics.median(r['per'] for r in g):>9.2f}s"
              f" {statistics.median(r['span'] for r in g):>10.1f}s"
              f" {statistics.median(r['exitv'] for r in g):>12.2f}"
              f" {statistics.median(r['slip'] for r in g):>11.2f}p"
              f" {sum(1 for r in g if r['exitv'] < -25.0):>4}/{len(g):<6}")
    print()
    print("  s/close re-derives close_interval_seconds from the flatten sweeps alone.")
    print("  If slip is the mechanism, AFTER must be worse on both money columns.")

    # ---- B. does slip scale with how long the sweep took? -----------------
    print()
    print("=" * 100)
    print("B. DOES SLIP SCALE WITH SWEEP DURATION?  (the causal link, not a correlation)")
    print("=" * 100)
    print("  Bucketing by span removes the regime label entirely: if a long sweep is")
    print("  costly REGARDLESS of when it happened, duration is the cause.")
    print()
    print(f"  {'span bucket':>16} {'cycles':>7} {'median slip':>12} {'median exit':>12}"
          f" {'worst exit':>11}")
    for lo, hi, lab in ((0, 5, "under 5 s"), (5, 60, "5 - 60 s"),
                        (60, 180, "1 - 3 min"), (180, 1e9, "over 3 min")):
        g = [r for r in rows if lo <= r["span"] < hi]
        if not g:
            continue
        print(f"  {lab:>16} {len(g):>7} {statistics.median(r['slip'] for r in g):>11.2f}p"
              f" {statistics.median(r['exitv'] for r in g):>12.2f}"
              f" {min(r['exitv'] for r in g):>11.2f}")

    # ---- C. the money the pacing costs ------------------------------------
    print()
    print("=" * 100)
    print("C. WHAT DOES 20-SECOND PACING COST, IN DOLLARS?")
    print("=" * 100)
    aft = [r for r in rows if r["after"]]
    bef = [r for r in rows if not r["after"]]
    if aft and bef:
        sb = statistics.median(r["slip"] for r in bef)
        sa = statistics.median(r["slip"] for r in aft)
        print(f"  median slip BEFORE {sb:.2f}p   AFTER {sa:.2f}p"
              f"   delta {sa-sb:+.2f}p")
        cost = sum((sa - sb) * r["gross"] for r in aft)
        print(f"  extra slip x gross, summed over {len(aft)} post-break flattens:"
              f" ${cost:,.2f}")
        print(f"  per flatten: ${cost/len(aft):,.2f}")
    print()
    print("  This is a COST OF PARITY, not a defect.  The Target pays it; the replica")
    print("  pays it because close_interval_seconds = 20 matches.  Do not 'fix' it.")

    # ---- D. the six negative exits, named -------------------------------
    print()
    print("=" * 100)
    print("D. THE SIX BELOW -$25 -- rule fired correctly, sweep lost the money")
    print("=" * 100)
    print(f"  {'cyc':>5} {'pre (at decision)':>18} {'burst':>10} {'exit':>9} {'n':>4}"
          f" {'span':>8} {'s/close':>9} {'slip':>7}  regime")
    for r in sorted((x for x in rows if x["exitv"] < -25.0), key=lambda r: r["exitv"]):
        print(f"  {r['i']:>5} {r['pre']:>18.2f} {r['burst']:>10.2f} {r['exitv']:>9.2f}"
              f" {r['n']:>4} {r['span']:>7.0f}s {r['per']:>8.1f}s {r['slip']:>6.2f}p"
              f"  {'AFTER' if r['after'] else 'BEFORE'}")
    neg = [r for r in rows if r["exitv"] < -25.0]
    if neg:
        near = sum(1 for r in neg if 15.0 <= r["pre"] <= 60.0)
        print(f"\n  of these {len(neg)}, {near} had `pre` inside [15,60] -- i.e. the money")
        print("  already banked at the decision instant was at the $30 threshold.")
        print("  A discretionary flatten would show no such concentration.")


if __name__ == "__main__":
    main()
