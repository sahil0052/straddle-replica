"""Cross-check: does the INDEPENDENT deployment detector see the 11 bursts that
tmp/a901_rearm.py's cycle segmenter missed?

a901_v4578.build_deployments() finds bursts from order density plus k-agnostic
geometry, with no knowledge of build_cycles()' boundaries -- it is the instrument
that produced the 285-deployment cut V1/V2/V9 are scored on.  If the ten
lattice-like clusters (and cycle 169's post-flatten redeploy) are real
deployments, they must appear there as bursts of their own.
"""

from __future__ import annotations

import collections
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from a901_v4578 import build_deployments, load_orders  # noqa: E402

# (label, fitted anchor, fitted step) as measured by a901_rearm.py part 10.
# Geometry, not time: the independent detector clusters on its own 2 s gap rule,
# so matching on (anchor, step) avoids importing this probe's cluster boundaries.
SUSPECTS = [
    ("cycle 7",   4039.53, 0.93),
    ("cycle 29",  4034.25, 0.94),
    ("cycle 51",  4028.10, 1.18),
    ("cycle 90",  4072.77, 0.98),
    ("cycle 93",  4115.13, 1.10),
    ("cycle 113", 4174.04, 0.63),
    ("cycle 127", 4113.16, 0.47),
    ("cycle 167", 4084.51, 0.57),
    ("cycle 169", 4074.73, 0.49),
    ("cycle 176", 4098.86, 1.37),
    # the two same-lattice cases: their re-arms fit the PARENT cycle's geometry,
    # so the independent cut should show ONE burst there, not two.
    ("cycle 119*", 4162.37, 0.45),
    ("cycle 152*", 4095.46, 0.47),
]


def main() -> int:
    orders = load_orders()
    records = build_deployments(orders)
    print(f"independent deployment cut: {len(records)} bursts")
    print()
    print("independently-detected bursts matching each suspected missed deployment:")
    for label, anchor, step in SUSPECTS:
        hits = [
            r for r in records
            if abs(r["anchor"] - anchor) <= 0.15 and abs(r["step"] - step) <= 0.02
        ]
        if not hits:
            best = min(records, key=lambda r: abs(r["anchor"] - anchor))
            print(f"    {label:<11} anchor {anchor:>9.2f} step {step:.2f}"
                  f"  ->  NO MATCH (nearest anchor {best['anchor']:.2f} step {best['step']:.2f})")
            continue
        for record in sorted(hits, key=lambda r: r["when"]):
            print(f"    {label:<11} anchor {anchor:>9.2f} step {step:.2f}"
                  f"  ->  {record['when']}  anchor {record['anchor']:>9.2f}"
                  f" step {record['step']:.2f} N {record['n']:>3} legs {record['legs']:>3}"
                  f" density {record['density']:.2f}")
    print()
    print("bursts on 2026-07-13 (the operator-flatten day):")
    for record in sorted(records, key=lambda r: r["when"]):
        if record["when"].date() == datetime(2026, 7, 13).date():
            print(f"    {record['when']}  anchor {record['anchor']:>9.2f}"
                  f" step {record['step']:.2f} N {record['n']:>3} legs {record['legs']:>3}"
                  f" density {record['density']:.2f}  end {record['end']}")

    # ----------------------------------------------------------------- census
    # Exact accounting instead of arithmetic: how many independent bursts start
    # INSIDE a cycle the segmenter had already opened?  Each such burst is a
    # deployment the cycle builder swallowed, and its orders are what part 2 of
    # a901_rearm.py charges as "moved re-arms".
    from tools.forensics.dataset import load_all

    _o, _p, _d, cycles = load_all()
    cycles = sorted(cycles, key=lambda c: c.start)
    print()
    print("=" * 78)
    print("independent bursts vs detected cycles")
    print("=" * 78)
    print(f"    detected cycles {len(cycles)}   independent bursts {len(records)}")
    inside = collections.defaultdict(list)
    homeless = []
    for record in sorted(records, key=lambda r: r["when"]):
        owner = None
        for cycle in cycles:
            if cycle.start <= record["when"] <= cycle.end:
                owner = cycle
                break
        if owner is None:
            homeless.append(record)
        else:
            inside[owner.index].append(record)
    extra = {ci: rs[1:] for ci, rs in inside.items() if len(rs) > 1}
    print(f"    bursts with no containing cycle: {len(homeless)}")
    print(f"    cycles containing >1 burst     : {len(extra)}"
          f"   swallowed bursts {sum(len(v) for v in extra.values())}")
    for cycle_index in sorted(extra):
        for record in extra[cycle_index]:
            print(f"      cycle {cycle_index:>3} swallowed {record['when']}"
                  f"  anchor {record['anchor']:>9.2f} step {record['step']:.2f}"
                  f" N {record['n']:>3} legs {record['legs']:>3}")
    print(f"    cycles containing no burst at all: "
          f"{len([c for c in cycles if c.index not in inside])}")

    # ------------------------------------------------- where did their legs go?
    # 15 swallowed bursts, but a901_rearm.py part 10 fits a missed deployment in
    # only 10 cycles.  Not a contradiction unless the legs are unaccounted, so
    # count them: a leg the segmenter already filed under some cycle's
    # burst_orders was never a re-arm CANDIDATE (part 1 excludes burst ids), so
    # it cannot appear in part 10's unexplained population at all.
    burst_ids = set()
    for cycle in cycles:
        for order in cycle.burst_orders:
            burst_ids.add(str(order.order_id))
    candidate_cycle = {}
    for order in _o:
        if not order.is_grid or order.price is None or order.cycle < 0:
            continue
        if str(order.order_id) in burst_ids:
            continue
        candidate_cycle[str(order.order_id)] = order.cycle
    print()
    print("=" * 78)
    print("legs of each swallowed burst: burst order (never a candidate) vs re-arm candidate")
    print("=" * 78)
    for cycle_index in sorted(extra):
        for record in extra[cycle_index]:
            legs = [str(r["ticket"]) for r in record["cluster"]]
            filed = sum(1 for t in legs if t in burst_ids)
            cands = [t for t in legs if t in candidate_cycle]
            homes = collections.Counter(candidate_cycle[t] for t in cands)
            print(f"    cycle {cycle_index:>3} burst {record['when']} legs {len(legs):>3}"
                  f"  filed-as-burst {filed:>3}  candidates {len(cands):>3}"
                  f"  other {len(legs) - filed - len(cands):>3}"
                  f"  candidate cycles {dict(homes) if homes else '-'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
