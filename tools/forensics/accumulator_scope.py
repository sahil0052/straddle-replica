"""Is the Target's $30 accumulator CYCLE-scoped, DAY-scoped, or RUN-scoped?

basket_resolution.py settled the THRESHOLD (30.0, four independent estimators, mark-free
median 29.32 at n=99).  It did not settle the SCOPE of the accumulator that is compared
against it -- and scope is a bigger divergence than value.  The replica zeroes
`m_cycle_realized` at cycle start (StraddleEngine.mqh:1642/1798/2537), i.e. it is
per-cycle.  If the Target's were day-scoped or run-scoped instead, EVERY exit in the run
would fire at the wrong moment and no amount of threshold tuning would fix it.

The three hypotheses make different, testable predictions, and the test needs no mark
because the mark-free identity applies: a flatten closes the whole basket, so
`realised_before_sweep + realised_by_sweep` IS the total the EA was looking at.

  CYCLE-SCOPED.  Each cycle's own realised money is compared against 30.  Prediction:
      per-cycle exit value centres on 30 with NO relationship to where the cycle sits in
      its trading day, and no drift across the run.

  DAY-SCOPED.  The accumulator carries across cycles within a day and resets at rollover.
      Prediction: the FIRST cycle of a day needs its own +30, but the second only needs
      the day total to reach 30 -- which it already has -- so cycles 2..n of each day
      would exit almost immediately at a per-cycle value near ZERO or negative.  Strong
      negative relationship between ordinal-within-day and per-cycle exit value.

  RUN-SCOPED.  The accumulator never resets.  Prediction: after the first profitable
      cycle the condition is permanently satisfied and every subsequent cycle exits on
      its first poll.  Per-cycle exit values collapse toward zero and stay there.

DAY- and RUN-scoped are therefore not subtle alternatives -- they are catastrophic, and
they are trivially falsifiable.  That is exactly why this test is worth running: a cheap
test that can only come back "confirmed" or "the whole exit model is wrong".
"""
from __future__ import annotations

import statistics
import sys
from collections import defaultdict
from datetime import timedelta

sys.path.insert(0, r"C:\websites\mt5 2")
from tools.forensics.dataset import load_all, FINAL_REGIME_START  # noqa: E402

TARGET = 30.0
SWEEP = 300.0


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
        pre = burst = 0.0
        for p in c.positions:
            if p.is_open or not p.close_time:
                continue
            if p.close_time < t0 - timedelta(seconds=5):
                pre += p.net
            elif p.close_time <= t0 + timedelta(seconds=SWEEP):
                burst += p.net
        rows.append(dict(i=c.index, t0=t0, day=t0.date(), val=pre + burst))

    rows.sort(key=lambda r: r["t0"])
    byday: dict[object, list] = defaultdict(list)
    for r in rows:
        byday[r["day"]].append(r)
    for day, g in byday.items():
        for k, r in enumerate(g, start=1):
            r["ord"] = k
            r["nday"] = len(g)

    print("=" * 100)
    print("A. EXIT VALUE vs ORDINAL WITHIN THE TRADING DAY")
    print("=" * 100)
    print("  DAY-scoped predicts cycles 2..n exit near zero (the day total already")
    print("  cleared 30).  CYCLE-scoped predicts every ordinal centres on 30 alike.")
    print()
    print(f"  {'ordinal in day':>15} {'cycles':>7} {'median exit $':>14}"
          f" {'mean exit $':>12} {'frac >= 20':>11}")
    for k in range(1, 7):
        g = [r for r in rows if r.get("ord") == k]
        if not g:
            continue
        v = [r["val"] for r in g]
        print(f"  {k:>15} {len(g):>7} {statistics.median(v):>14.2f}"
              f" {statistics.mean(v):>12.2f}"
              f" {sum(1 for x in v if x >= 20.0)/len(v):>10.0%}")
    later = [r["val"] for r in rows if r.get("ord", 1) >= 2]
    first = [r["val"] for r in rows if r.get("ord") == 1]
    if later and first:
        print()
        print(f"  first-of-day  : n={len(first):>3}  median {statistics.median(first):>8.2f}")
        print(f"  later-in-day  : n={len(later):>3}  median {statistics.median(later):>8.2f}")
        print(f"  difference    : {statistics.median(later)-statistics.median(first):+.2f}"
              "   (DAY-scoped predicts a large NEGATIVE number)")

    print()
    print("=" * 100)
    print("B. EXIT VALUE vs POSITION IN THE RUN  (the RUN-scoped test)")
    print("=" * 100)
    print("  RUN-scoped predicts collapse toward zero after the first winning cycle.")
    print()
    q = max(1, len(rows) // 4)
    print(f"  {'quartile of run':>17} {'cycles':>7} {'median exit $':>14} {'frac >= 20':>11}")
    for k in range(4):
        g = rows[k*q:(k+1)*q] if k < 3 else rows[3*q:]
        if not g:
            continue
        v = [r["val"] for r in g]
        print(f"  {'Q'+str(k+1):>17} {len(g):>7} {statistics.median(v):>14.2f}"
              f" {sum(1 for x in v if x >= 20.0)/len(v):>10.0%}")

    print()
    print("=" * 100)
    print("C. THE DECISIVE COUNT")
    print("=" * 100)
    v = [r["val"] for r in rows]
    near = sum(1 for x in v if x >= 20.0)
    print(f"  final-regime flatten cycles measured : {len(v)}")
    print(f"  median per-cycle exit value          : {statistics.median(v):.2f}"
          f"   (hypothesised threshold {TARGET:.2f})")
    print(f"  cycles exiting at >= $20 of their OWN money : {near}/{len(v)}"
          f" = {100.0*near/len(v):.0f}%")
    print(f"  cycles exiting at <= $5 of their own money  : "
          f"{sum(1 for x in v if x <= 5.0)}/{len(v)}")
    print()
    print("  Under DAY- or RUN-scoping the third line would be the large one and the")
    print("  second would be near zero, because a carried-over accumulator is already")
    print("  past 30 when the cycle opens.  Read the numbers above and conclude.")
    ndays = len(byday)
    multi = sum(1 for g in byday.values() if len(g) >= 2)
    print()
    print(f"  trading days covered : {ndays};  days with >=2 cycles : {multi}")
    print("  (the day-scoped test only has power if multi-cycle days exist -- they do)")

    # ---- D. the tails.  A mean of 345.78 against a median of 30.94 at n=13 means
    # ONE cycle carries ~4.1k, and that has to be explained before the medians above
    # are trusted.  Two candidates: (a) a real gap-through, in which case the cycle's
    # own SL harvest ran far past 30 between two polls, or (b) a cycle-attribution
    # bug pulling in another cycle's positions, which would contaminate everything.
    # (a) and (b) are distinguishable: under (a) the money is realised BEFORE t0 by
    # the ratchet and the sweep contributes little; under (b) the pre/burst split is
    # arbitrary and the cycle's span will be implausibly long.
    print()
    print("=" * 100)
    print("D. THE TAILS -- is the ordinal-1 mean of 345.78 real, or an attribution bug?")
    print("=" * 100)
    span = {c.index: (c.end - c.start).total_seconds() / 3600.0
            for c in fin if c.end and c.start}
    npos = {c.index: len(c.positions) for c in fin}
    print(f"  {'cycle':>7} {'exit value $':>13} {'pre $':>11} {'burst $':>10}"
          f" {'span h':>8} {'pos':>5}")
    for r in sorted(rows, key=lambda r: -abs(r["val"]))[:6]:
        c = next(x for x in fin if x.index == r["i"])
        pre = burst = 0.0
        for p in c.positions:
            if p.is_open or not p.close_time:
                continue
            if p.close_time < r["t0"] - timedelta(seconds=5):
                pre += p.net
            elif p.close_time <= r["t0"] + timedelta(seconds=SWEEP):
                burst += p.net
        print(f"  {r['i']:>7} {r['val']:>13,.2f} {pre:>11,.2f} {burst:>10,.2f}"
              f" {span.get(r['i'], float('nan')):>8.1f} {npos.get(r['i'], 0):>5}")
    print()
    v2 = sorted(r["val"] for r in rows)
    trimmed = v2[len(v2)//20: len(v2) - len(v2)//20]
    print(f"  median      (n={len(v2)}) : {statistics.median(v2):>8.2f}")
    print(f"  5%-trimmed mean       : {statistics.mean(trimmed):>8.2f}"
          f"   <- if this is near 30 the tails are noise, not a bug")
    print(f"  raw mean              : {statistics.mean(v2):>8.2f}"
          f"   <- dominated by the tails, which is why the median is the statistic")


if __name__ == "__main__":
    main()
