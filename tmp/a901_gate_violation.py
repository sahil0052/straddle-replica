"""The 14 negative attested stops are GATE VIOLATIONS. Who wrote them?

a901_negative_lock.py killed the stale-field hypothesis: 0 of 9 AGGRESSIVE_30
field-negatives were rescued by the broker's attested `[sl X]` price, and in all
28 rows of that era the field and the attested price agree to the cent -- so the
column was never stale and the stop that fired IS the stop that was written.
Attested negatives per era: H50 0/3478, H60 5/7742, AGGRESSIVE_30 9/28,
LOW_RISK_30 0/25, STARWAVE_30 0/2599.

That makes the negatives a one-line contradiction, with no appeal to the market
price needed.  `Calculate()` is MARKET-anchored: it writes

    desired = market - dir*D*step,      D in {pre_tighten, trail} = {2.0, 1.0}

behind the gate `favorable_steps = dir*(market - entry)/step >= 2.0`.  Substitute
the write into the gate and the market cancels:

    locked = dir*(desired - entry)/step
           = dir*(market - dir*D*step - entry)/step
           = favorable - D                     >= 2.0 - D

so a D=2.0 write satisfies locked >= 0 and a D=1.0 write satisfies locked >= 1.0
(and in fact >= 2.0, since D=1.0 additionally requires favorable >= 3.0).  The
union is locked >= 0 FOR EVERY POSSIBLE MARKET PRICE.  A negative attested lock
is therefore not "an unlikely market" -- it is arithmetically outside the range
of the function, and the clamp is excluded because no step on this tape is below
0.25 (a901_negative_lock.py part 4).

Two authors remain: the human operator, or an EA behaviour that is not
`Calculate()`.  They separate cleanly, because a market-anchored write is a
BROADCAST -- every position polled in the same pass at the same market gets the
IDENTICAL price -- whereas a hand-set stop is a broadcast too, but one that
ignores the gate.  So the discriminator is not "is the price shared" but "does
every member of a shared-price group satisfy locked >= 0":

    EA broadcast   -> all members passed the same gate at the same market,
                      so min(locked) over the group is >= 0
    hand-set price -> membership is whatever was selected in the terminal, so
                      the group straddles zero

The AGGRESSIVE_30 table already shows 4061.90 on nine positions whose entries
span 4059.24..4065.22 and whose locked values run -3.912..+4.882, and 4060.00 --
a hand-typed round number -- on three more.  This script tests that formally, per
era, and dates the result against the operator's known activity.
"""
from __future__ import annotations

import collections
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.forensics.dataset import load_all  # noqa: E402
from tools.forensics.linkage import (  # noqa: E402
    CLOSE_BY_RE, SL_RE, exit_reason, link_exits,
)

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
    step_by_cycle = {c.index: c.step for c in cycles if c.step}
    era_by_cycle = {c.index: era_of(c.start) for c in cycles}

    rows = []
    for position in positions:
        if position.is_open or position.close_time is None:
            continue
        if exit_reason(position, exit_order) != "sl":
            continue
        step = step_by_cycle.get(position.cycle)
        order = exit_order.get(position.position_id)
        match = SL_RE.fullmatch((order.comment or "") if order else "")
        if not step or match is None:
            continue
        attested = float(match.group(1))
        rows.append({
            "era": era_by_cycle.get(position.cycle, "?"),
            "cycle": position.cycle,
            "ticket": position.position_id,
            "side": position.side,
            "level": position.level or 0,
            "step": step,
            "open": position.open_price,
            "attested": attested,
            "locked": position.dir * (attested - position.open_price) / step,
            "opened": position.open_time,
            "closed": position.close_time,
        })

    print("=== part 1: gate violations (locked < 0) per era, on the attested price ===")
    print("    locked = favorable - D with D in {2.0, 1.0} and favorable >= 2.0, so")
    print("    locked >= 0 holds for EVERY market price. A negative is out of range.")
    print()
    print(f"    {'era':16s} {'n':>6} {'violations':>11} {'rate':>8} {'worst':>9}")
    per_era = collections.defaultdict(list)
    for row in rows:
        per_era[row["era"]].append(row)
    for era, _s, _e in ERAS:
        group = per_era.get(era, [])
        if not group:
            continue
        bad = [r for r in group if r["locked"] < -0.005]
        worst = min((r["locked"] for r in bad), default=0.0)
        print(f"    {era:16s} {len(group):>6d} {len(bad):>11d} "
              f"{100.0*len(bad)/len(group):>7.3f}% {worst:>+9.3f}")
    violations = [r for r in rows if r["locked"] < -0.005]
    print(f"    {'ALL':16s} {len(rows):>6d} {len(violations):>11d} "
          f"{100.0*len(violations)/len(rows):>7.3f}%")
    print()

    print("=== part 2: shared-price groups -- EA broadcast, or hand-set? ===")
    print("    an EA broadcast writes one market-anchored price to every position that")
    print("    passed the SAME gate, so min(locked) over the group must be >= 0.")
    print("    a group that straddles zero was not written by Calculate().")
    print()
    groups = collections.defaultdict(list)
    for row in rows:
        groups[(row["cycle"], round(row["attested"], 2), row["side"])].append(row)
    shared = {k: v for k, v in groups.items() if len(v) >= 2}
    straddling = {k: v for k, v in shared.items()
                  if min(r["locked"] for r in v) < -0.005}
    print(f"    (cycle, attested price, side) groups with >= 2 members: {len(shared)}")
    print(f"    of those, groups that STRADDLE zero: {len(straddling)}")
    census = collections.Counter(era_by_cycle.get(k[0], "?") for k in straddling)
    print("    straddling groups by era: "
          + ("  ".join(f"{k}={v}" for k, v in census.most_common()) or "none"))
    print()
    for key in sorted(straddling, key=lambda k: (k[0], k[1])):
        members = sorted(straddling[key], key=lambda r: r["locked"])
        print(f"    cycle {key[0]}  {key[2]} @ {key[1]:.2f}  "
              f"({era_by_cycle.get(key[0], '?')})  n={len(members)}  "
              f"locked {members[0]['locked']:+.3f} .. {members[-1]['locked']:+.3f}"
              f"   entries {min(r['open'] for r in members):.2f}"
              f"..{max(r['open'] for r in members):.2f}")
        print(f"      levels " + ",".join(str(r["level"]) for r in members)
              + f"   closed {min(r['closed'] for r in members)}"
              f" .. {max(r['closed'] for r in members)}")
    print()

    print("=== part 3: every gate violation, with its shared-price cohort ===")
    print("      ticket     era              side lvl  step   open     attested   locked"
          "   cohort  cohort locked range")
    for row in sorted(violations, key=lambda r: (r["era"], r["locked"])):
        cohort = groups[(row["cycle"], round(row["attested"], 2), row["side"])]
        lows = min(r["locked"] for r in cohort)
        highs = max(r["locked"] for r in cohort)
        print(f"      {row['ticket']:10d} {row['era']:16s} {row['side']:4s} "
              f"{row['level']:3d} {row['step']:5.2f} {row['open']:9.2f} "
              f"{row['attested']:9.2f} {row['locked']:+8.3f} "
              f"{len(cohort):>7d}   {lows:+.3f} .. {highs:+.3f}")
    print()

    print("=== part 4: are the violating prices HUMAN numbers? ===")
    print("    a market-anchored write inherits the market's cents, so whole-dollar and")
    print("    round-10-cent prices should appear at their chance rate (1% and 10%).")

    def roundness(values):
        whole = sum(1 for v in values if abs(v - round(v)) < 0.0005)
        dime = sum(1 for v in values if abs(v * 10 - round(v * 10)) < 0.005)
        return whole, dime

    for label, population in (("all attested stops", rows),
                              ("gate violations   ", violations)):
        prices = [r["attested"] for r in population]
        whole, dime = roundness(prices)
        print(f"    {label}: n={len(prices):5d}  whole-dollar {whole:5d} "
              f"({100.0*whole/max(1,len(prices)):5.2f}%)  "
              f"round-10c {dime:5d} ({100.0*dime/max(1,len(prices)):5.2f}%)")
    distinct = sorted({round(r["attested"], 2) for r in violations})
    print(f"    distinct violating prices: {len(distinct)} -> {distinct}")
    print()

    print("=== part 5: operator proximity -- how close is the nearest manual order? ===")
    print("    `close by` is PositionCloseBy, which has NO call site in the EA, so every")
    print("    one of them is a hand action and dates the operator's presence exactly.")
    manual = sorted(o.open_time for o in orders
                    if o.comment and CLOSE_BY_RE.fullmatch(o.comment.strip()))
    print(f"    `close by` orders on the tape: {len(manual)}")
    if manual:
        print(f"    span {manual[0]} .. {manual[-1]}")
    for row in sorted(violations, key=lambda r: r["closed"]):
        gaps = [(abs((row["closed"] - when).total_seconds()), when) for when in manual]
        gaps.sort()
        nearest = gaps[0] if gaps else (float("inf"), None)
        same_day = sum(1 for when in manual if when.date() == row["closed"].date())
        print(f"      #{row['ticket']:<10d} {row['era']:16s} closed {row['closed']}  "
              f"nearest manual {nearest[0]/60.0:9.2f} min  "
              f"same-day manual orders {same_day}")
    print()

    print("=== part 6: control -- the same test on the era with the most SL exits ===")
    print("    HISTORICAL_60 runs a SINGLE-stage 2.0 trail (pre_tighten == trail == 2.0,")
    print("    DIV-4), so locked = favorable - 2.0 >= 0 there too: the bound is not a")
    print("    two-stage artifact and the control is valid.")
    for era in ("HISTORICAL_50", "HISTORICAL_60", "STARWAVE_30"):
        group = per_era.get(era, [])
        if not group:
            continue
        keys = {(r["cycle"], round(r["attested"], 2), r["side"]) for r in group}
        multi = [k for k in keys if len(groups[k]) >= 2]
        bad = [k for k in multi if min(r["locked"] for r in groups[k]) < -0.005]
        sizes = [len(groups[k]) for k in multi]
        print(f"    {era:16s} n={len(group):5d}  shared-price groups {len(multi):5d}  "
              f"max cohort {max(sizes, default=0):3d}  straddling {len(bad)}")
    print()

    print("=== part 7: did the violating positions ever get a SECOND stop write? ===")
    print("    Calculate() only ever tightens, so a hand-set stop that the EA later")
    print("    took over would end up tighter than the hand value. Field == attested")
    print("    on all 28 AGGRESSIVE_30 rows means the EA never touched them again --")
    print("    consistent with a gate that (correctly) refused to arm a losing stop.")
    window = timedelta(minutes=90)
    for era in ("AGGRESSIVE_30", "HISTORICAL_60"):
        bad = [r for r in per_era.get(era, []) if r["locked"] < -0.005]
        if not bad:
            continue
        first = min(r["closed"] for r in bad)
        last = max(r["closed"] for r in bad)
        neighbours = [r for r in per_era[era]
                      if first - window <= r["closed"] <= last + window]
        clean = [r for r in neighbours if r["locked"] >= -0.005]
        print(f"    {era:16s} violations {len(bad):3d}  closed {first} .. {last}"
              f"  ({(last-first).total_seconds():.1f} s apart)")
        print(f"      SL exits within +-90 min of that window: {len(neighbours)}  "
              f"of which non-violating {len(clean)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
