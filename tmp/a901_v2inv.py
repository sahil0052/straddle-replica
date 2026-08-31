"""Locate HISTORICAL_60's V2 inversion exactly: WHERE in the burst, and WHY.

Re-scoring V2 on the relaxed 285-deployment cut did not dissolve HISTORICAL_60's
inversions -- it multiplied them.  10 of 78 bursts are clean; 68 carry exactly
one inversion each (three carry two), against HISTORICAL_50 at 99/101 and
STARWAVE_30 at 103/103.  Nearly every offending burst has 119 legs, i.e. one leg
short of the full 120.  "One missing leg and one inversion" in 68 consecutive
deployments is a mechanism, not noise, and it has three candidate explanations
that this probe separates:

  (H1) MY SORT.  build_deployments sorts by (when, ticket) and ticket is a
       STRING, so ties inside one millisecond are ordered LEXICOGRAPHICALLY.
       If a ticket rolls a digit-count boundary, or if the broker hands out
       tickets out of dispatch order, the burst is mis-ordered by my own reader
       and the EA is innocent.  Signature: the two swapped legs share a
       timestamp, or their tickets are non-monotone.
  (H2) A REAL DISPATCH SWAP.  The EA placed Sk before Bk for one k.  Signature:
       strictly increasing timestamps AND tickets across the swap, with a normal
       ~100 ms gap -- the order really went out that way.
  (H3) A RE-ARM FOLDED INTO THE BURST.  The burst is a deployment plus one
       re-arm of an already-filled level that landed inside the same 2 s
       chain, so a low-rank leg reappears late.  Signature: the out-of-place leg
       sits far from its neighbours in rank, and its timestamp gap to the
       previous leg is the odd one out.

For every inversion the probe prints the six legs around it with dispatch time,
inter-leg gap, ticket, order state, and rank, plus which level is missing from
the burst.  That is enough to decide between the three without further guessing.
"""
from __future__ import annotations

import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from a901_v4578 import build_deployments, load_orders  # noqa: E402


def rank_of(row) -> int:
    return 2 * (row["level"] - 1) + (0 if row["is_buy"] else 1)


def tag(row) -> str:
    return f"{'B' if row['is_buy'] else 'S'}{row['level']}"


def main() -> int:
    records = build_deployments(load_orders())
    target = [r for r in records if str(r["assigned"]) == "HISTORICAL_60"]
    print(f"HISTORICAL_60 bursts on the new cut: {len(target)}")

    where: collections.Counter = collections.Counter()
    missing_hist: collections.Counter = collections.Counter()
    same_ms = 0
    ticket_nonmono = 0
    total_inv = 0
    shown = 0
    for record in target:
        cluster = record["cluster"]
        ranks = [rank_of(row) for row in cluster]
        bad = [i for i in range(len(ranks) - 1) if ranks[i + 1] < ranks[i]]
        total_inv += len(bad)
        if not bad:
            continue
        present = {(row["is_buy"], row["level"]) for row in cluster}
        absent = [
            f"{'B' if buy else 'S'}{level}"
            for level in range(1, record["n"] + 1)
            for buy in (True, False)
            if (buy, level) not in present
        ]
        missing_hist[tuple(absent)] += 1
        for index in bad:
            left = cluster[index]
            right = cluster[index + 1]
            where[(tag(left), tag(right))] += 1
            if left["when"] == right["when"]:
                same_ms += 1
            try:
                if int(left["ticket"]) > int(right["ticket"]):
                    ticket_nonmono += 1
            except ValueError:
                pass
        if shown < 6:
            shown += 1
            print(f"\n--- burst {record['when']} legs={record['legs']} "
                  f"n={record['n']} missing={absent} inversions={len(bad)}")
            for index in bad:
                lo = max(0, index - 2)
                hi = min(len(cluster), index + 4)
                print(f"    around leg #{index} -> #{index + 1}:")
                previous = None
                for j in range(lo, hi):
                    row = cluster[j]
                    gap = ("      -" if previous is None
                           else f"{(row['when'] - previous).total_seconds() * 1000.0:7.1f}")
                    mark = " <<<" if j in (index, index + 1) else ""
                    print(f"      #{j:4d} {tag(row):5s} rank={rank_of(row):4d} "
                          f"{row['when']} gap={gap} ms  ticket={row['ticket']} "
                          f"state={row['state']:9s} price={row['price']}{mark}")
                    previous = row["when"]

    print(f"\ninversions={total_inv}  swaps sharing a millisecond={same_ms}  "
          f"swaps with non-monotone tickets={ticket_nonmono}")
    print("\nwhich (left,right) pairs invert:")
    for (left, right), count in where.most_common(20):
        print(f"  {left:5s} -> {right:5s}  x{count}")
    print("\nwhich legs are missing from the inverting bursts:")
    for absent, count in missing_hist.most_common(12):
        print(f"  x{count:3d}  {list(absent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
