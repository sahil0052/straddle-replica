"""Is level-1 deferral a STOP-LEVEL effect?  Score it against step across all eras.

The V2 probe established WHAT happens in HISTORICAL_60: 68 of 78 deployments
dispatch level 1 LAST, after S60, and 61 of those carry only ONE side of level 1
at all.  Tickets and timestamps are monotone across every swap and the gap to the
tail leg is one ~100 ms tick, so the EA really sent the orders in that order.

The proposed cause is a broker minimum-stop-distance rejection: a BUY_STOP must
sit at least SYMBOL_TRADE_STOPS_LEVEL above the ask, and level 1 sits only one
step from the anchor.  HISTORICAL_60's step range is 0.37..0.78 -- the smallest of
any era -- while HISTORICAL_50 runs 0.75..1.68 and STARWAVE_30 1.32..1.39.  If the
cause is a fixed price distance, then level-1 deferral must be a FUNCTION OF STEP
and nothing else, and three predictions follow that the tape can refute:

  P1  Across all 285 bursts, level-1 trouble concentrates at small step.  The
      cleanly-placed bursts should have a strictly higher step distribution than
      the deferred ones, and there should be a step threshold above which the
      effect vanishes entirely.
  P2  WITHIN HISTORICAL_60, the 10 clean bursts should be its large-step bursts.
  P3  HISTORICAL_50's 2 inversions should show the SAME S50 -> level-1-at-tail
      signature (the mechanism is era-independent, just rarer), and its offending
      bursts should sit at the bottom of its step range.

Classification per burst, from dispatch order alone:
  LEAD   both level-1 legs present and dispatched in the first two slots -- the
         designed B1,S1,B2,S2,... order, no rejection happened.
  TAIL   at least one level-1 leg dispatched after some higher level -- deferred.
  GONE   no level-1 leg at all -- both attempts failed and neither retry landed.
  ODD    level 1 present, not deferred, but not in the first two slots either.
"""
from __future__ import annotations

import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from a901_v4578 import build_deployments, eras_present, load_orders, pct  # noqa: E402


def classify(cluster) -> tuple[str, list[str]]:
    """Return (verdict, which level-1 legs are present) from dispatch order."""
    positions = [i for i, row in enumerate(cluster) if row["level"] == 1]
    present = [f"{'B' if cluster[i]['is_buy'] else 'S'}1" for i in positions]
    if not positions:
        return "GONE", present
    # Deferred if any level-1 leg is dispatched after a higher level.
    highest_before = [max((cluster[j]["level"] for j in range(i)), default=0)
                      for i in positions]
    if any(high > 1 for high in highest_before):
        return "TAIL", present
    if max(positions) <= 1:
        return "LEAD", present
    return "ODD", present


def main() -> int:
    records = build_deployments(load_orders())
    by_era: dict[str, list[dict]] = collections.defaultdict(list)
    for record in records:
        by_era[str(record["assigned"])].append(record)

    print("=== P1: how each era dispatches level 1, against its step range ===")
    print("  era               n   LEAD   TAIL   GONE    ODD   "
          "step p05/p50/p95   level-1 legs present p50")
    for era in eras_present(by_era):
        subset = by_era[era]
        tally: collections.Counter = collections.Counter()
        legs = []
        for record in subset:
            verdict, present = classify(record["cluster"])
            tally[verdict] += 1
            legs.append(len(present))
        steps = [r["step"] for r in subset]
        print(f"  {era:16s} {len(subset):3d}  {tally['LEAD']:5d}  {tally['TAIL']:5d}  "
              f"{tally['GONE']:5d}  {tally['ODD']:5d}   "
              f"{pct(steps, 0.05):.2f}/{pct(steps, 0.50):.2f}/{pct(steps, 0.95):.2f}   "
              f"{pct(legs, 0.50):.1f}")
    print()

    print("=== P1/P2: step distribution of clean vs deferred bursts, per era ===")
    print("  era              verdict   n   step min   p05    p50    p95    max")
    for era in eras_present(by_era):
        groups: dict[str, list[float]] = collections.defaultdict(list)
        for record in by_era[era]:
            groups[classify(record["cluster"])[0]].append(record["step"])
        for verdict in ("LEAD", "TAIL", "GONE", "ODD"):
            steps = sorted(groups.get(verdict, []))
            if not steps:
                continue
            print(f"  {era:16s} {verdict:6s} {len(steps):4d}   "
                  f"{steps[0]:.4f}  {pct(steps, 0.05):.4f}  {pct(steps, 0.50):.4f}  "
                  f"{pct(steps, 0.95):.4f}  {steps[-1]:.4f}")
    print()

    # A fixed stop distance predicts a single global threshold on step, not five
    # per-era ones.  Score every burst on one axis and look for the knee.
    print("=== P1 decisive: one global step axis, all 285 bursts ===")
    rows = [(r["step"], classify(r["cluster"])[0], str(r["assigned"]), r["when"])
            for r in records]
    edges = [0.0, 0.40, 0.50, 0.60, 0.70, 0.80, 1.00, 1.40, 9.99]
    print("  step band        n   LEAD   TAIL   GONE    ODD   %clean   eras")
    for lo, hi in zip(edges, edges[1:]):
        band = [row for row in rows if lo <= row[0] < hi]
        if not band:
            continue
        tally = collections.Counter(row[1] for row in band)
        eras = sorted({row[2][:4] for row in band})
        clean = 100.0 * tally["LEAD"] / len(band)
        print(f"  [{lo:.2f},{hi:.2f}) {len(band):6d}  {tally['LEAD']:5d}  "
              f"{tally['TAIL']:5d}  {tally['GONE']:5d}  {tally['ODD']:5d}  "
              f"{clean:6.2f}%   {','.join(eras)}")
    print()

    print("=== P3: HISTORICAL_50's non-LEAD bursts in full ===")
    for record in by_era.get("HISTORICAL_50", []):
        verdict, present = classify(record["cluster"])
        if verdict == "LEAD":
            continue
        cluster = record["cluster"]
        print(f"  {verdict} {record['when']} legs={record['legs']} "
              f"step={record['step']:.4f} anchor={record['anchor']:.2f} present={present}")
        for index, row in enumerate(cluster):
            if row["level"] != 1:
                continue
            lo = max(0, index - 2)
            for j in range(lo, min(len(cluster), index + 2)):
                mark = " <<<" if j == index else ""
                print(f"        #{j:4d} {'B' if cluster[j]['is_buy'] else 'S'}"
                      f"{cluster[j]['level']:<3d} {cluster[j]['when']} "
                      f"ticket={cluster[j]['ticket']} state={cluster[j]['state']:9s}"
                      f"{mark}")
    print()

    # Which side survives?  A rising market invalidates the BUY_STOP and frees the
    # SELL_STOP, so the surviving side is a read on drift during the 12 s burst.
    print("=== which level-1 side survives the retry, per era ===")
    for era in eras_present(by_era):
        tally: collections.Counter = collections.Counter()
        for record in by_era[era]:
            verdict, present = classify(record["cluster"])
            if verdict in ("TAIL", "GONE"):
                tally[tuple(sorted(present))] += 1
        if tally:
            detail = "  ".join(f"{k or ('none',)}={v}" for k, v in tally.most_common())
            print(f"  {era:16s} {detail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
