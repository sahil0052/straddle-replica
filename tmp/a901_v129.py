"""Re-score V1 / V2 / V9 on the RELAXED 285-deployment cut of the 901018 tape.

Why this file exists.  V1, V2 and V9 were first scored over the 210 deployments
the OLD predicate found -- a burst had to contain both B1 and S1, because the
geometry was recovered from that one pair.  Level 1 is the closest pending to the
anchor and is routinely FILLED during the deployment burst itself, so it never
reaches the canceled/working population the burst is rebuilt from, and the old
predicate silently discarded 70 real HISTORICAL_60 lattices along with 5 others.
a901_v4578.build_deployments() now uses density + k-agnostic geometry and finds
285.  Every V1/V2/V9 number therefore has to be re-measured on the new cut, and
the HISTORICAL_60 interleave inversions in particular were measured over the 7
mis-cut bursts and may not survive.

The tests, and what each one can actually falsify:

  V1a STEP LAW      step == round(anchor/divisor, 2), scored ONLY on the three
                    divisor eras (AGGRESSIVE_30 6000, LOW_RISK_30 3000,
                    STARWAVE_30 3000).  The two ATR eras have no divisor and are
                    exempt by construction, not by convenience.
  V1b WHOLE CENT    anchor and step must both be exact multiples of 0.01, which
                    is what NormalizeDouble(...,_Digits) with _Digits=2 forces.
                    This one bites on every era including the ATR pair.
  V1c 2k GEOMETRY   for EVERY concordant (Bk,Sk) pair in the burst, not just
                    k=1: (bk - sk) == 2*k*step.  The old B1-S1 == 2*step test is
                    the k=1 special case and is reported separately for the
                    bursts that still have both level-1 legs, so the two cuts
                    stay comparable.
  V1d RESIDUAL      max |price - (anchor +- level*step)| over every leg.  A
                    single mis-set level anywhere in 16k legs shows up here.
  V1e ANCHOR SPREAD max-min over the per-k anchor estimates inside one burst.
                    Non-zero means the burst is not a single lattice at all --
                    i.e. the clustering merged two deployments.
  V2  INTERLEAVE    dispatch order must be B1,S1,B2,S2,...  Rank the legs the
                    burst actually placed and count adjacent inversions; missing
                    legs cannot manufacture one.
  V9  LOT LADDER    every leg's volume against the assigned era's tier table.

Geometry is recovered at the LARGEST concordant k (error divided by k), so V1c
and V1d are near-tautological AT that k and fully falsifiable everywhere else.
"""
from __future__ import annotations

import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from a901_eras import BOUNDS, SIGNATURE  # noqa: E402
from a901_v4578 import build_deployments, eras_present, load_orders, pct  # noqa: E402

# ProfileCatalog.mqh anchor divisors; None = ATR step mode, exempt from V1a.
DIVISOR = {
    "HISTORICAL_50": None,
    "HISTORICAL_60": None,
    "AGGRESSIVE_30": 6000.0,
    "LOW_RISK_30": 3000.0,
    "STARWAVE_30": 3000.0,
}


def cents(value: float) -> float:
    """Distance from the nearest whole cent, in cents."""
    scaled = value * 100.0
    return abs(scaled - round(scaled))


def main() -> int:
    orders = load_orders()
    records = build_deployments(orders)
    by_era: dict[str, list[dict]] = collections.defaultdict(list)
    for record in records:
        by_era[str(record["assigned"])].append(record)

    print(f"=== deployment cut: {len(records)} bursts "
          f"(old B1+S1 predicate found 210) ===")
    print("  era                n  inherited   legs p05/p50/max   density min   "
          "pair_k p05/p50/max")
    for era in eras_present(by_era):
        subset = by_era[era]
        legs = [r["legs"] for r in subset]
        ks = [r["pair_k"] for r in subset]
        print(f"  {era:16s} {len(subset):4d} {sum(1 for r in subset if r['inherited']):9d}   "
              f"{pct(legs, 0.05):5.0f}/{pct(legs, 0.50):5.0f}/{max(legs):5d}   "
              f"{min(r['density'] for r in subset):11.4f}   "
              f"{pct(ks, 0.05):4.0f}/{pct(ks, 0.50):4.0f}/{max(ks):4d}")
    print()

    # ---------------------------------------------------------------- V1a/V1b/V1e
    print("=== V1 anchor & step geometry, re-scored on the new cut ===")
    print("  era               n   step-law hits   anchor whole-cent   "
          "step whole-cent   anchor-spread max   step min..max")
    law_total = law_hits = 0
    for era in eras_present(by_era):
        subset = by_era[era]
        divisor = DIVISOR.get(era)
        scored = [r for r in subset if divisor is not None]
        hits = sum(
            1 for r in scored
            if abs(r["step"] - round(r["anchor"] / divisor, 2)) < 5e-9
        )
        law_total += len(scored)
        law_hits += hits
        anchor_ok = sum(1 for r in subset if cents(r["anchor"]) < 1e-6)
        step_ok = sum(1 for r in subset if cents(r["step"]) < 1e-6)
        steps = [r["step"] for r in subset]
        law = "exempt (ATR)" if divisor is None else f"{hits:3d}/{len(scored):3d}"
        print(f"  {era:16s} {len(subset):3d}   {law:>13s}   "
              f"{anchor_ok:6d}/{len(subset):-6d}      {step_ok:6d}/{len(subset):-6d}   "
              f"{max(r['anchor_spread'] for r in subset):17.10f}   "
              f"{min(steps):.2f}..{max(steps):.2f}")
        for record in scored:
            want = round(record["anchor"] / divisor, 2)
            if abs(record["step"] - want) >= 5e-9:
                print(f"      STEP-LAW MISS {record['when']} anchor={record['anchor']:.2f} "
                      f"step={record['step']:.4f} want={want:.2f} legs={record['legs']} "
                      f"k={record['pair_k']} inherited={record['inherited']}")
        for record in subset:
            if cents(record["anchor"]) >= 1e-6 or cents(record["step"]) >= 1e-6:
                print(f"      OFF-CENT {record['when']} anchor={record['anchor']:.6f} "
                      f"step={record['step']:.6f} k={record['pair_k']} legs={record['legs']}")
    print(f"  step law overall: {law_hits}/{law_total} on the divisor eras "
          f"({100.0 * law_hits / law_total if law_total else float('nan'):.2f}%)")
    print()

    # -------------------------------------------------------------------- V1c/V1d
    print("=== V1c 2k geometry on EVERY concordant pair, and V1d lattice residual ===")
    print("  era               pairs   (bk-sk)==2k*step      k=1 bursts   "
          "B1-S1==2*step      legs   residual max")
    pair_tot = pair_ok = leg_tot = 0
    worst_all = 0.0
    for era in eras_present(by_era):
        subset = by_era[era]
        pairs = ok = 0
        k1_bursts = k1_ok = 0
        legs = 0
        worst = 0.0
        offenders = []
        for record in subset:
            anchor = record["anchor"]
            step = record["step"]
            buys = {r["level"]: r["price"] for r in record["cluster"] if r["is_buy"]}
            sells = {r["level"]: r["price"] for r in record["cluster"] if not r["is_buy"]}
            for level in sorted(set(buys) & set(sells)):
                pairs += 1
                if abs((buys[level] - sells[level]) - 2.0 * level * step) < 5e-9:
                    ok += 1
                else:
                    offenders.append((record["when"], level, buys[level], sells[level], step))
            if 1 in buys and 1 in sells:
                k1_bursts += 1
                if abs((buys[1] - sells[1]) - 2.0 * step) < 5e-9:
                    k1_ok += 1
            for row in record["cluster"]:
                legs += 1
                want = anchor + (row["level"] if row["is_buy"] else -row["level"]) * step
                worst = max(worst, abs(row["price"] - want))
        pair_tot += pairs
        pair_ok += ok
        leg_tot += legs
        worst_all = max(worst_all, worst)
        print(f"  {era:16s} {pairs:6d}   {ok:6d}/{pairs:-6d}   {k1_bursts:10d}   "
              f"{k1_ok:6d}/{k1_bursts:-6d}   {legs:7d}   {worst:.10f}")
        for when, level, bk, sk, step in offenders[:6]:
            print(f"      PAIR MISS {when} k={level} b={bk} s={sk} "
                  f"span={bk - sk:.4f} want={2.0 * level * step:.4f}")
    print(f"  overall: pairs {pair_ok}/{pair_tot} "
          f"({100.0 * pair_ok / pair_tot if pair_tot else float('nan'):.2f}%)   "
          f"legs {leg_tot}   residual max {worst_all:.10f}")
    print()

    # ------------------------------------------------------------------------- V2
    print("=== V2 interleave B1,S1,B2,S2,... re-scored on the new cut ===")
    inv_total = 0
    clean_total = 0
    burst_total = 0
    for era in eras_present(by_era):
        subset = by_era[era]
        clean = 0
        inversions = 0
        detail = []
        for record in subset:
            rank = [
                2 * (row["level"] - 1) + (0 if row["is_buy"] else 1)
                for row in record["cluster"]
            ]
            bad = sum(1 for a, b in zip(rank, rank[1:]) if b < a)
            inversions += bad
            if bad == 0:
                clean += 1
            else:
                detail.append((record["when"], record["legs"], record["n"], bad))
        burst_total += len(subset)
        clean_total += clean
        inv_total += inversions
        print(f"  {era:16s} zero-inversion={clean:4d}/{len(subset):-4d} "
              f"({100.0 * clean / len(subset):6.2f}%)  total_inversions={inversions}")
        for when, legs, n, bad in detail:
            print(f"      INVERSION {when} legs={legs} n={n} inversions={bad}")
    print(f"  overall: {clean_total}/{burst_total} bursts strictly interleaved "
          f"({100.0 * clean_total / burst_total:.2f}%), {inv_total} inversions")
    print()

    # ------------------------------------------------------------------------- V9
    print("=== V9 lot ladder, re-scored on the new cut ===")
    tot = hit = 0
    for era in eras_present(by_era):
        expected = BOUNDS.get(era)
        if expected is None:
            print(f"  {era}: no expected ladder")
            continue
        checked = ok = 0
        misses: collections.Counter = collections.Counter()
        for record in by_era[era]:
            for row in record["cluster"]:
                want = None
                for lo, hi, vol in expected:
                    if lo <= row["level"] <= hi:
                        want = vol
                        break
                if want is None:
                    continue
                checked += 1
                if abs(row["volume"] - want) < 1e-9:
                    ok += 1
                else:
                    misses[(row["level"], row["volume"], want)] += 1
        tot += checked
        hit += ok
        print(f"  {era:16s} legs={checked:6d} ladder_ok={ok:6d} "
              f"({100.0 * ok / checked if checked else float('nan'):6.2f}%)")
        for key, count in misses.most_common(8):
            print(f"      level={key[0]:3d} saw={key[1]} want={key[2]} x{count}")
    print(f"  overall: {hit}/{tot} legs "
          f"({100.0 * hit / tot if tot else float('nan'):.2f}%)")
    print()

    # Signature census -- which (N, tiers) pairs the new cut actually recovers.
    print("=== signature census on the new cut ===")
    census: collections.Counter = collections.Counter()
    for record in records:
        key = (record["n"], record["tiers"])
        census[(SIGNATURE.get(key, (None,))[0], record["n"], record["tiers"])] += 1
    for (name, n, tiers), count in sorted(
        census.items(), key=lambda item: (-item[1], str(item[0]))
    ):
        print(f"  {str(name):16s} N={n:3d} tiers={tiers}  x{count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
