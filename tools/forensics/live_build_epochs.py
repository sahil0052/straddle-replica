"""Split the replica's live fill stream by BUILD EPOCH, not by calendar overlap.

This script exists to correct a measurement fault in live_same_window.py, which
was itself written to correct three faults in live_stream_parity.py.  The fault
is subtle and it inverted a headline conclusion, so it is worth stating plainly.

live_same_window.py restricted both streams to the days on which BOTH accounts
traded, on the reasoning that holding the market fixed isolates the EA.  That is
sound for the market.  It is NOT sound for the build.  The only shared days are
2026-08-20 and 2026-08-21, and those are precisely the last two days the replica
ran the PRE-FIX binary.  The parity fixes (20 s pacing family, rearm_delay 20 s,
TradeGateway dynamic filling mode, close-loop resilience, refuted exits removed)
landed between 08-21 and 08-24.  So "hold the market fixed" silently pinned the
comparison to the one build we had already replaced.

The measured consequence, from the volume-tier-by-day table:

    replica 2026-08-20   295 fills   16.72 lots   68x0.15 + 10x0.30   (pre-fix)
    replica 2026-08-21   317 fills   13.37 lots   45x0.15             (pre-fix)
    replica 2026-08-24   675 fills    8.58 lots    0 tier-3           (post-fix)
    replica 2026-08-25   432 fills    5.22 lots    0 tier-3           (post-fix)
    TARGET  all 13 days 2649 fills   49.40 lots    7 tier-3 (0.26%)

Lots per fill -- the exposure density that sets a basket's $/point:

    TARGET  overall            0.0187
    replica pre-fix  08-20     0.0567     3.0x the Target
    replica pre-fix  08-21     0.0422     2.3x the Target
    replica post-fix 08-24     0.0127     0.68x the Target
    replica post-fix 08-25     0.0121     0.65x the Target

The "3.2x exposure gap" is therefore a REGRESSION THAT WAS ALREADY FIXED, not a
live divergence, and the missing-recentre theory advanced to explain it is void.
(That theory was independently dead anyway: q3p_replicarules.py scored a
distance-based recentre at 49/100 cycles firing, 27 of them >5 min early,
destroying $5,738.88 -- see the note at StraddleEngine.mqh:2877.)

WHAT THIS SCRIPT MEASURES.  For every axis a terminal log can see, report the
Target, the replica PRE-fix, and the replica POST-fix side by side.  An axis on
which post-fix moved toward the Target is a fix confirmed in production.  An axis
on which post-fix still differs is a live, open defect -- and that is the only
list worth acting on.

CAVEAT, stated up front because it bounds every number below: post-fix and
Target days do not overlap at all (Target ends 08-21, post-fix starts 08-24), so
post-fix-vs-Target comparisons are market-confounded in the way live_same_window
was written to avoid.  Ratios that survive a 26x change in tier-3 rate are safe
to cite; small differences are not.  The pre-fix-vs-post-fix comparison, which
is the one that establishes whether the fixes took, is market-confounded too but
in the opposite direction: 08-24/25 were HIGHER volume days (675/432 fills vs
295/317), so a defect driven by activity had more opportunity to appear, not
less.
"""
from __future__ import annotations

import os
import statistics
import sys
from collections import Counter
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
from tools.forensics.live_stream_parity import load, TARGET, REPLICA, FRESH  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# The parity rebuild landed between these two dates.  Everything the replica did
# on or before PRE_LAST is the old binary; on or after POST_FIRST is the new one.
PRE_LAST = date(2026, 8, 21)
POST_FIRST = date(2026, 8, 24)

# Manual "Close All Positions" on the replica -- a human, not the EA.  Our code
# contains no CloseBy call anywhere (grep: zero hits), so these fills must be
# excised before any pacing claim; five of them share one millisecond.
MANUAL_LO = datetime(2026, 8, 20, 21, 50, 45)
MANUAL_HI = datetime(2026, 8, 20, 21, 52, 0)

DIVISOR = 3000.0        # LATEST_30: step = anchor / anchor_divisor
LOTS = (0.01, 0.06, 0.15)   # base volume for levels 1-10, 11-20, 21-30
RESCUE_MULT = 2.0


def is_manual(d) -> bool:
    return d.acc == REPLICA and MANUAL_LO <= d.t <= MANUAL_HI


def rule(t: str) -> None:
    print()
    print("=" * 100)
    print(t)
    print("=" * 100)


def pc(a: int, b: int) -> str:
    return f"{100.0 * a / b:5.1f}%" if b else "    --"


def tier_of(vol: float) -> str:
    """Volume tags the level band.  Rescue legs trade at exactly 2x the tier."""
    for i, base in enumerate(LOTS, start=1):
        if abs(vol - base) < 1e-9:
            return f"L{(i-1)*10+1}-{i*10}"
        if abs(vol - base * RESCUE_MULT) < 1e-9:
            return f"L{(i-1)*10+1}-{i*10}*"      # * = rescue replacement
    return f"?{vol:g}"


def cohorts(st):
    tgt = [d for d in st.get(TARGET, [])]
    rep = [d for d in st.get(REPLICA, []) if not is_manual(d)]
    pre = [d for d in rep if d.t.date() <= PRE_LAST]
    post = [d for d in rep if d.t.date() >= POST_FIRST]
    fresh = st.get(FRESH, [])
    return (("TARGET      ", tgt), ("replica PRE ", pre),
            ("replica POST", post), ("fresh  POST ", fresh))


def gaps_of(ds):
    return [(b.t - a.t).total_seconds() for a, b in zip(ds, ds[1:])
            if 0.0 <= (b.t - a.t).total_seconds() <= 86400.0]


def clusters_of(ds, window=0.100):
    out, cur = [], [ds[0]] if ds else []
    for a, b in zip(ds, ds[1:]):
        if (b.t - a.t).total_seconds() < window:
            cur.append(b)
        else:
            if len(cur) > 1:
                out.append(cur)
            cur = [b]
    if len(cur) > 1:
        out.append(cur)
    return out


def main() -> None:
    st = load()
    co = cohorts(st)

    rule("0. COHORTS")
    for name, ds in co:
        if not ds:
            print(f"  {name}: empty")
            continue
        days = sorted({d.t.date() for d in ds})
        print(f"  {name}  n={len(ds):>5}  {len(days)} days  "
              f"{days[0]} .. {days[-1]}  lots={sum(d.vol for d in ds):.2f}")
    print()
    print("  Post-fix and Target days do NOT overlap, so post-vs-Target is")
    print("  market-confounded.  Pre-vs-post is confounded the OTHER way:")
    print("  08-24/25 were busier (675/432 fills vs 295/317), so an")
    print("  activity-driven defect had MORE opportunity post-fix, not less.")

    # ------------------------------------------------------------------ panel 1
    rule("1. EXPOSURE DENSITY -- lots per fill, and level-band penetration")
    print("  A basket's $/point is set by lots, not fill count, and volume tags")
    print("  the level band it is living in (rescue = 2x the tier, marked *).")
    print()
    for name, ds in co:
        if not ds:
            continue
        n = len(ds)
        lots = sum(d.vol for d in ds)
        c = Counter(tier_of(d.vol) for d in ds)
        deep = sum(k for t, k in c.items() if t.startswith("L21"))
        print(f"  {name}  n={n:>5}  lots={lots:>7.2f}  lots/fill={lots/n:.4f}"
              f"   L21-30 share={pc(deep, n)}")
        for t, k in sorted(c.items()):
            print(f"      {t:>9} : {k:>5}  {pc(k, n)}  "
                  f"{'#' * max(1, round(40.0 * k / n))}")
        print()
    tn = sum(d.vol for d in co[0][1]) / max(1, len(co[0][1]))
    for name, ds in co[1:]:
        if ds:
            r = (sum(d.vol for d in ds) / len(ds)) / tn
            print(f"  {name} exposure density vs TARGET : {r:.2f}x")

    # ------------------------------------------------------------------ panel 2
    rule("2. LATTICE STEP vs THE PROFILE'S OWN FORMULA  (step = anchor/3000)")
    print("  LATEST_30 sets step_mode=ANCHOR_DIVISOR, anchor_divisor=3000, so the")
    print("  step is PRICE-PROPORTIONAL and must drift with gold.  Measure it from")
    print("  consecutive-in-time same-side fills, then divide the day's median")
    print("  price by the modal step to recover the divisor the EA actually used.")
    print()
    print(f"  {'cohort':>13} {'day':>11} {'n':>5} {'mode':>6} {'share':>6}"
          f" {'medpx':>7} {'expect':>7} {'err':>7} {'adhere':>6}")
    for name, ds in co:
        if len(ds) < 4:
            continue
        byday: dict[date, list] = {}
        last: dict[str, object] = {}
        for d in ds:
            p = last.get(d.side)
            if p is not None and p.t.date() == d.t.date():
                dt = (d.t - p.t).total_seconds()
                g = round(abs(d.price - p.price), 2)
                if 0 < dt <= 120.0 and 0.05 <= g <= 8.0:
                    byday.setdefault(d.t.date(), []).append((g, d.price))
            last[d.side] = d
        for day in sorted(byday):
            rows = byday[day]
            if len(rows) < 12:
                continue
            mode, mcount = Counter(g for g, _ in rows).most_common(1)[0]
            share = 100.0 * mcount / len(rows)
            medpx = statistics.median([p for _, p in rows])
            expect = medpx / DIVISOR
            err = 100.0 * (mode - expect) / expect
            # Adherence: fraction of gaps within +-5% of the mandated step.  This
            # is the non-circular statistic -- it needs no mode at all.
            adh = 100.0 * sum(1 for g, _ in rows
                              if abs(g - expect) <= 0.05 * expect) / len(rows)
            # A mode carrying only a few percent of a continuum is a noise spike,
            # not a step.  Only a DOMINANT mode that deviates is a real defect.
            flag = ("  <== WRONG STEP" if (abs(err) > 8.0 and share >= 10.0)
                    else ("  (mode is noise)" if abs(err) > 8.0 else ""))
            print(f"  {name:>13} {str(day):>11} {len(rows):>5} {mode:>6.2f}"
                  f" {share:>5.1f}% {medpx:>7.0f} {expect:>7.2f}"
                  f" {err:>+6.1f}% {adh:>5.1f}%{flag}")
    print()
    print("  READ THIS BEFORE CITING A ROW.  The Target's step is a CONTINUUM: it")
    print("  re-anchors every cycle and step=anchor/3000, so a day holds many")
    print("  slightly different steps and no single mode dominates (mode share")
    print("  2-4%).  Picking the modal gap on such a day returns a noise spike --")
    print("  an earlier version of this panel flagged four TARGET days as 'wrong")
    print("  step' for exactly that reason, which was the estimator's fault and")
    print("  not the Target's behaviour.  A row is only a defect when a DOMINANT")
    print("  mode (share >= 10%) sits away from anchor/3000.  The 'adhere' column")
    print("  is the honest cross-check: it needs no mode, just the share of gaps")
    print("  within +-5% of the mandated step.")
    print()
    print("  A step X% too tight reaches a given level band on a price move")
    print("  (1-X) as large, so it over-penetrates the ladder and inflates volume.")

    # ------------------------------------------------------------------ panel 3
    rule("3. THE 20-SECOND METRONOME -- rearm_delay_seconds=20")
    print("  The Target's fill stream is quantised to 20 s: that cadence IS the")
    print("  re-arm delay, and its share is the sharpest single parity statistic")
    print("  available from a terminal log.")
    print()
    buckets = [(0.0, 0.001, "same ms"), (0.001, 0.1, "<100ms"),
               (0.1, 1.0, "0.1-1s"), (1.0, 5.0, "1-5s"), (5.0, 15.0, "5-15s"),
               (15.0, 25.0, "15-25s <- 20s"), (25.0, 60.0, "25-60s"),
               (60.0, 86400.0, ">1min")]
    for name, ds in co:
        dl = gaps_of(ds)
        if len(dl) < 10:
            continue
        print(f"  {name}  n={len(dl)} gaps")
        for lo, hi, nm in buckets:
            k = sum(1 for x in dl if lo <= x < hi)
            print(f"      {nm:>16} : {k:>5}  {pc(k, len(dl))}"
                  f"  {'#' * round(40.0 * k / len(dl))}")
        band = [x for x in dl if 19.0 <= x <= 21.5]
        if band:
            print(f"      [19.0,21.5] n={len(band)} ({pc(len(band), len(dl))})"
                  f" median={statistics.median(band):.3f}s"
                  f" min={min(band):.3f} max={max(band):.3f}")
        print()

    # ------------------------------------------------------------------ panel 4
    rule("4. ONE ACTION PER TICK -- sub-100 ms clusters")
    print("  A cluster whose members sit ~one lattice step apart is the broker")
    print("  sweeping resting pendings (legitimate).  A cluster whose members sit")
    print("  at near-identical prices is the EA firing several actions in one")
    print("  tick, or duplicate orders on one level (our defect).")
    print()
    for name, ds in co:
        if len(ds) < 4:
            continue
        cl = clusters_of(ds)
        dl = gaps_of(ds)
        involved = sum(len(c) for c in cl)
        print(f"  {name}  {len(cl)} clusters, {involved} fills involved"
              f" ({pc(involved, len(ds))} of stream)")
        if not cl:
            print("      (none -- stream fully serialised)")
            print()
            continue
        print(f"      sizes: {dict(sorted(Counter(len(c) for c in cl).items()))}")
        spreads = sorted(round(max(d.price for d in c) - min(d.price for d in c), 2)
                         for c in cl)
        tight = sum(1 for s in spreads if s < 0.30)
        print(f"      intra-cluster spread: median {statistics.median(spreads):.2f}"
              f"  max {spreads[-1]:.2f}   tighter-than-0.30: {tight}/{len(cl)}"
              f" = {pc(tight, len(cl))}")
        print(f"      same-ms gaps: {sum(1 for x in dl if x < 0.001)}")
        for c in cl[:4]:
            desc = " | ".join(f"{d.t.strftime('%H:%M:%S.%f')[:-3]} {d.side[0]}"
                              f"{d.vol:g}@{d.price:.2f}" for d in c)
            print(f"        {c[0].t.date()}  {desc}")
        print()


if __name__ == "__main__":
    main()
