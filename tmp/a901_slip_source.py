"""Is the LATTICE reference trustworthy on the 901018 report? Part 3 says maybe not.

a901_slip_vs_hand.py part 3 measured entry slippage dir*(fill - lattice) across
13,709 SL-closed positions and found a distribution that cannot be slippage:

    min -27.72   p50 +0.06   p95 +0.53   p99 +7.11   max +26.98
    fills BETTER than the lattice price (impossible for a stop): 170 (1.24%)
    fills needing >= 7.18 of slippage to explain: 134

A stop order cannot fill better than its price, so those 170 are proof that for
~1% of rows the `lattice` price I am differencing against is NOT the price that
position's pending order actually carried.  The core of the distribution (p50 six
cents, p95 fifty-three cents) is credible slippage; the tail is an attribution
defect, and I need its mechanism before quoting any lattice-referenced verdict.

The suspected mechanism is specific and checkable.  `dataset._burst_clusters()`
groups grid orders into a deployment burst by a 45 s gap rule and then trims the
run at the first repeat of an already-seen (side, level); `_fit_lattice()` then
takes `{(side, level): price}` from that trimmed sweep.  But this tape carries
11,549 re-arm pendings dispatched OUTSIDE bursts, and a re-arm of the PREVIOUS
cycle's level that lands within 45 s of the next burst's first order gets swept
into the new burst -- contributing the OLD cycle's price for that (side, level).
The error is then the whole anchor difference between the two cycles, i.e. dollars,
and it hits only the handful of levels that were re-armed across the boundary.

The falsifiable consequence: for a row with impossible (negative) slip, the fill
price should match a NEIGHBOURING cycle's lattice for the same (side, level)
better than it matches its own.  If that holds, the tail is an attribution defect
with a known blast radius, the 45 s / first-repeat heuristic is its cause, and the
right response is to stop using the lattice reference for verdicts -- not to
"fix" the negatives it manufactures.

Part 3 then re-runs the H60 borderline question on the ONE instrument that needs
no lattice at all: the per-group gate solve.
"""
from __future__ import annotations

import collections
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.forensics.dataset import load_all  # noqa: E402
from tools.forensics.linkage import SL_RE, exit_reason, link_exits  # noqa: E402

ERAS = [
    ("HISTORICAL_50", datetime(2026, 6, 23, 16, 17, 27), datetime(2026, 7, 2, 15, 24, 57)),
    ("HISTORICAL_60", datetime(2026, 7, 2, 15, 24, 57), datetime(2026, 7, 13, 11, 2, 45)),
    ("AGGRESSIVE_30", datetime(2026, 7, 13, 11, 2, 45), datetime(2026, 7, 13, 12, 32, 29)),
    ("LOW_RISK_30", datetime(2026, 7, 13, 12, 32, 29), datetime(2026, 7, 13, 15, 59, 39)),
    ("STARWAVE_30", datetime(2026, 7, 13, 15, 59, 39), datetime(2027, 1, 1)),
]


def era_of(when):
    for name, start, end in ERAS:
        if start <= when < end:
            return name
    return "?"


def main() -> int:
    orders, positions, deals, cycles = load_all()
    exit_order, _ed, _en, _st = link_exits(orders, positions, deals)
    by_index = {c.index: c for c in cycles}

    rows = []
    for position in positions:
        if position.is_open or position.close_time is None:
            continue
        if exit_reason(position, exit_order) != "sl":
            continue
        cycle = by_index.get(position.cycle)
        if cycle is None or not cycle.step or not position.level:
            continue
        order = exit_order.get(position.position_id)
        match = SL_RE.fullmatch((order.comment or "") if order else "")
        if match is None:
            continue
        code = "B" if position.side == "buy" else "S"
        own = cycle.lattice_price(code, position.level)
        if own is None:
            continue
        rows.append({
            "era": era_of(cycle.start),
            "cycle": position.cycle,
            "code": code,
            "level": position.level,
            "dir": position.dir,
            "step": cycle.step,
            "open": position.open_price,
            "own": own,
            "slip": position.dir * (position.open_price - own),
            "attested": float(match.group(1)),
            "opened": position.open_time,
            "burst_end": cycle.burst_end,
        })

    print("=== part 1: does a NEIGHBOURING cycle's lattice fit the bad rows better? ===")
    print("    for each row, find the cycle in [own-3, own+3] whose lattice price for the")
    print("    same (side, level) is CLOSEST to the fill.  a correctly attributed row")
    print("    picks its own cycle; an attribution defect picks a neighbour.")
    print()
    reattributed = collections.Counter()
    totals = collections.Counter()
    examples = []
    for row in rows:
        best = None
        for offset in range(-3, 4):
            other = by_index.get(row["cycle"] + offset)
            if other is None:
                continue
            price = other.lattice_price(row["code"], row["level"])
            if price is None:
                continue
            gap = abs(row["open"] - price)
            if best is None or gap < best[0] - 1e-9:
                best = (gap, offset, price)
        if best is None:
            continue
        bucket = ("impossible slip" if row["slip"] < -0.005
                  else "slip >= 1.00" if row["slip"] >= 1.0
                  else "ordinary")
        totals[bucket] += 1
        if best[1] != 0:
            reattributed[bucket] += 1
            if bucket != "ordinary" and len(examples) < 12:
                examples.append((row, best))
    for bucket in ("impossible slip", "slip >= 1.00", "ordinary"):
        n = totals[bucket]
        if not n:
            continue
        print(f"    {bucket:18s} n={n:6d}  a NEIGHBOUR cycle fits the fill better: "
              f"{reattributed[bucket]:5d} ({100.0*reattributed[bucket]/n:6.2f}%)")
    print()
    print("    worked examples (own cycle vs the better-fitting neighbour):")
    print("      era              cyc  lvl  fill      own lattice  slip     "
          "best cyc  its price   gap")
    for row, best in examples:
        print(f"      {row['era']:16s} {row['cycle']:3d} {row['code']}{row['level']:<3d} "
              f"{row['open']:9.2f} {row['own']:12.2f} {row['slip']:+7.2f} "
              f"{row['cycle']+best[1]:9d} {best[2]:10.2f} {best[0]:6.2f}")
    print()

    print("=== part 2: how far past the burst did the bad rows open? ===")
    print("    a re-arm swept into the wrong burst opens LONG after that burst ended,")
    print("    so the offenders should sit far out in the age distribution.")
    for bucket, pick in (("impossible slip", lambda r: r["slip"] < -0.005),
                         ("slip >= 1.00", lambda r: r["slip"] >= 1.0),
                         ("ordinary", lambda r: -0.005 <= r["slip"] < 1.0)):
        ages = sorted((r["opened"] - r["burst_end"]).total_seconds()
                      for r in rows if pick(r))
        if not ages:
            continue
        n = len(ages)
        print(f"    {bucket:18s} n={n:6d}  age after burst end (s): "
              f"p05 {ages[int(0.05*n)]:10.1f}  p50 {ages[n//2]:10.1f}  "
              f"p95 {ages[int(0.95*n)]:10.1f}")
    print()

    print("=== part 3: the H60 borderline five, on the lattice-free instrument ===")
    print("    the per-group gate solve uses only (attested, fill, step, dir): a shared")
    print("    price implies market = attested + dir*D*step, and every member of a true")
    print("    broadcast must satisfy favorable = dir*(market-fill)/step >= 2.0 there.")
    print("    this needs no lattice price, so the attribution defect cannot touch it.")
    print()
    groups = collections.defaultdict(list)
    for row in rows:
        groups[(row["cycle"], round(row["attested"], 2), row["code"])].append(row)
    watch = {20226522, 20219252, 20256261, 20226515, 20257148}
    seen = set()
    for position in positions:
        if position.position_id not in watch:
            continue
        cycle = by_index.get(position.cycle)
        if cycle is None:
            continue
        order = exit_order.get(position.position_id)
        match = SL_RE.fullmatch((order.comment or "") if order else "")
        if match is None:
            continue
        code = "B" if position.side == "buy" else "S"
        key = (position.cycle, round(float(match.group(1)), 2), code)
        if key in seen:
            continue
        seen.add(key)
        members = sorted(groups.get(key, []), key=lambda r: r["level"])
        if not members:
            continue
        step = members[0]["step"]
        direction = members[0]["dir"]
        print(f"    cycle {key[0]}  {code} @ {key[1]:.2f}  n={len(members)}  "
              f"step {step:.2f}  levels "
              f"{members[0]['level']}..{members[-1]['level']}   "
              f"(contains #{position.position_id})")
        for label, D in (("D=2.0", 2.0), ("D=1.0", 1.0)):
            market = key[1] + direction * D * step
            favorable = [direction * (market - r["open"]) / step for r in members]
            passed = sum(1 for f in favorable if f >= 2.0 - 1e-9)
            near = sum(1 for f in favorable if f >= 1.95)
            print(f"      {label}: implied market {market:9.2f}  gate {passed}/{len(members)}"
                  f"  within 0.05 of the gate {near}/{len(members)}  "
                  f"favorable {min(favorable):+.3f}..{max(favorable):+.3f}")
        print()

    print("=== part 4: how tightly does the worst member of a clean group hug the gate? ===")
    print("    a broadcast fired on the first poll that passes leaves its worst member")
    print("    just above 2.0.  measure that margin across every large clean group.")
    margins = []
    for key, members in groups.items():
        if len(members) < 5:
            continue
        step = members[0]["step"]
        direction = members[0]["dir"]
        market = key[1] + direction * 2.0 * step
        favorable = [direction * (market - r["open"]) / step for r in members]
        if min(favorable) < 2.0 - 1e-9:
            continue
        margins.append(min(favorable) - 2.0)
    margins.sort()
    if margins:
        n = len(margins)
        print(f"    groups with >=5 members that pass the gate for ALL members at D=2.0: {n}")
        print(f"    margin of the WORST member above the 2.0 gate: "
              f"p05 {margins[int(0.05*n)]:+.3f}  p25 {margins[int(0.25*n)]:+.3f}  "
              f"p50 {margins[n//2]:+.3f}  p95 {margins[int(0.95*n)]:+.3f}")
        print(f"    groups whose worst member is within 0.50 steps of the gate: "
              f"{sum(1 for m in margins if m <= 0.5)}/{n} "
              f"({100.0*sum(1 for m in margins if m <= 0.5)/n:.1f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
