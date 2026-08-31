"""Split the 14 negatives: 9 are gate violations, 5 are entry slippage. Prove it.

a901_gate_violation.py found 14 attested stops with locked < 0 and showed the two
eras behave nothing alike:

    AGGRESSIVE_30   9 of 28   worst -10.559 steps
    HISTORICAL_60   5 of 7742 worst  -0.163 steps

-0.163 steps at that era's 0.43 step is SEVEN CENTS.  The other four are 5c, 3c,
2c and 1c.  So the H60 five are not "a stop on the losing side" in any economic
sense -- they are a measurement artifact with exactly one candidate cause, and it
is checkable rather than rhetorical.

`locked` is measured from the FILL price, but a stop order fills AT OR BEYOND its
price, so

    fill = lattice + dir*slip,   slip >= 0

and the ratchet is anchored on the market, not on either of those.  A position
whose stop was broadcast at the instant it first satisfied `favorable == 2.0`
lands at locked == 0.00 measured from the LATTICE price, and therefore at
locked == -slip/step measured from the fill.  One cent of entry slippage on a
0.43 step is -0.023 steps.  That predicts a specific, falsifiable outcome:

    re-measure the five from the lattice price and they must ALL become >= 0,
    while re-measuring AGGRESSIVE_30's nine must leave them deeply negative,
    because 7.18 in price is 700x more slippage than any stop fill carries.

This is the same fill-vs-lattice reference test asw_trail.py part 6 ran on the
Starwave tape (where it moved 0 of 25 forbidden-band cases, because that tape's
entry slippage is identically zero).  Here it is aimed at the negatives.

Part 2 then checks the other direction on the same population: whether the
AGGRESSIVE_30 stops could have come from ANY market-anchored broadcast, by
solving each shared-price group for the market price it implies and asking
whether every member of the group passed the gate at that market.
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
    cycle_by_index = {c.index: c for c in cycles}

    rows = []
    for position in positions:
        if position.is_open or position.close_time is None:
            continue
        if exit_reason(position, exit_order) != "sl":
            continue
        cycle = cycle_by_index.get(position.cycle)
        if cycle is None or not cycle.step:
            continue
        order = exit_order.get(position.position_id)
        match = SL_RE.fullmatch((order.comment or "") if order else "")
        if match is None:
            continue
        attested = float(match.group(1))
        code = "B" if position.side == "buy" else "S"
        lattice = cycle.lattice_price(code, position.level or 0)
        rows.append({
            "era": era_of(cycle.start),
            "cycle": position.cycle,
            "ticket": position.position_id,
            "side": position.side,
            "dir": position.dir,
            "level": position.level or 0,
            "step": cycle.step,
            "open": position.open_price,
            "lattice": lattice,
            "slip": (position.dir * (position.open_price - lattice)
                     if lattice is not None else None),
            "attested": attested,
            "locked": position.dir * (attested - position.open_price) / cycle.step,
            "alt": (position.dir * (attested - lattice) / cycle.step
                    if lattice is not None else None),
            "closed": position.close_time,
        })

    violations = [r for r in rows if r["locked"] < -0.005]

    print("=== part 1: the 14 negatives in PRICE, not steps ===")
    print("    steps are era-specific, so -0.163 steps and -10.559 steps are not the")
    print("    same kind of object. price makes the two populations self-separating.")
    print()
    print("      ticket     era              side lvl  step   locked(steps)  "
          "locked(price)   lattice   slip")
    for row in sorted(violations, key=lambda r: r["locked"]):
        lattice = f"{row['lattice']:9.2f}" if row["lattice"] is not None else "        -"
        slip = f"{row['slip']:+6.2f}" if row["slip"] is not None else "     -"
        print(f"      {row['ticket']:10d} {row['era']:16s} {row['side']:4s} "
              f"{row['level']:3d} {row['step']:5.2f} {row['locked']:+13.3f}  "
              f"{row['locked']*row['step']:+13.2f}   {lattice} {slip}")
    print()
    for era in ("AGGRESSIVE_30", "HISTORICAL_60"):
        group = [r for r in violations if r["era"] == era]
        if not group:
            continue
        prices = sorted(r["locked"] * r["step"] for r in group)
        print(f"    {era:16s} n={len(group)}  price offset below entry: "
              f"worst {prices[0]:+.2f}  best {prices[-1]:+.2f}")
    print()

    print("=== part 2: re-measure from the LATTICE price instead of the fill ===")
    print("    prediction: all 5 HISTORICAL_60 cases clear (they are entry slippage on")
    print("    an exact-activation broadcast); all 9 AGGRESSIVE_30 cases stay negative")
    print("    (7.18 in price is not slippage).  Either half failing kills the split.")
    print()
    measurable = [r for r in violations if r["alt"] is not None]
    print(f"    violations with a burst lattice price available: "
          f"{len(measurable)}/{len(violations)}")
    print()
    print("      ticket     era              locked(fill)  slip   locked(lattice)  verdict")
    for row in sorted(measurable, key=lambda r: r["locked"]):
        verdict = "CLEARED" if row["alt"] >= -0.005 else "still negative"
        print(f"      {row['ticket']:10d} {row['era']:16s} {row['locked']:+12.3f} "
              f"{row['slip']:+6.2f} {row['alt']:+16.3f}  {verdict}")
    print()
    for era in ("HISTORICAL_60", "AGGRESSIVE_30"):
        group = [r for r in measurable if r["era"] == era]
        if not group:
            continue
        cleared = sum(1 for r in group if r["alt"] >= -0.005)
        print(f"    {era:16s} cleared by the lattice reference: {cleared}/{len(group)}")
    print()

    print("=== part 3: tape-wide entry slippage, to bound what it can explain ===")
    print("    if slippage were large enough to fake a 7.18 offset it would show up in")
    print("    the whole population, not only in the nine.")
    slips = sorted(r["slip"] for r in rows if r["slip"] is not None)
    if slips:
        n = len(slips)
        print(f"    n={n}  min {slips[0]:+.2f}  p50 {slips[n//2]:+.2f}  "
              f"p95 {slips[int(0.95*n)]:+.2f}  p99 {slips[int(0.99*n)]:+.2f}  "
              f"max {slips[-1]:+.2f}")
        negative = sum(1 for v in slips if v < -0.005)
        print(f"    fills BETTER than the lattice price (impossible for a stop): "
              f"{negative} ({100.0*negative/n:.2f}%)")
        print(f"    fills needing >= 1.00 of slippage to explain: "
              f"{sum(1 for v in slips if v >= 1.0)}")
        print(f"    fills needing >= 7.18 of slippage to explain: "
              f"{sum(1 for v in slips if v >= 7.18)}")
    print()

    print("=== part 4: solve each AGGRESSIVE_30 group for the market it implies ===")
    print("    a broadcast writes desired = market - dir*D*step, so a group sharing one")
    print("    price implies market = attested + dir*D*step for D in {2.0, 1.0}.  At that")
    print("    market every member must satisfy favorable = dir*(market-entry)/step >= 2.")
    print()
    groups = collections.defaultdict(list)
    for row in rows:
        if row["era"] == "AGGRESSIVE_30":
            groups[(row["cycle"], round(row["attested"], 2), row["side"])].append(row)
    for key in sorted(groups, key=lambda k: -len(groups[k])):
        members = sorted(groups[key], key=lambda r: r["level"])
        if len(members) < 2:
            continue
        step = members[0]["step"]
        direction = members[0]["dir"]
        print(f"    cycle {key[0]}  {key[2]} @ {key[1]:.2f}  n={len(members)}  "
              f"step {step:.2f}  levels "
              f"{members[0]['level']}..{members[-1]['level']}")
        for label, D in (("D=2.0 (activation / stage 1)", 2.0), ("D=1.0 (stage 2)", 1.0)):
            market = key[1] + direction * D * step
            favorable = [(r["level"], direction * (market - r["open"]) / step)
                         for r in members]
            passed = sum(1 for _lv, f in favorable if f >= 2.0 - 1e-9)
            print(f"      {label}: implied market {market:9.2f}  "
                  f"members passing the >=2.0 gate {passed}/{len(members)}  "
                  f"favorable {min(f for _l, f in favorable):+.2f}"
                  f"..{max(f for _l, f in favorable):+.2f}")
        print()

    print("=== part 5: the same solve on a clean control group of comparable size ===")
    print("    a genuine broadcast must pass the gate for ALL members at ONE market.")
    control = collections.defaultdict(list)
    for row in rows:
        if row["era"] in ("HISTORICAL_50", "STARWAVE_30"):
            control[(row["cycle"], round(row["attested"], 2), row["side"])].append(row)
    big = sorted((k for k, v in control.items() if len(v) >= 6),
                 key=lambda k: -len(control[k]))[:6]
    for key in big:
        members = control[key]
        step = members[0]["step"]
        direction = members[0]["dir"]
        best = None
        for D in (2.0, 1.0):
            market = key[1] + direction * D * step
            favorable = [direction * (market - r["open"]) / step for r in members]
            passed = sum(1 for f in favorable if f >= 2.0 - 1e-9)
            if best is None or passed > best[0]:
                best = (passed, D, min(favorable), max(favorable))
        print(f"    cycle {key[0]:3d} {key[2]:4s} @ {key[1]:9.2f}  n={len(members):3d}  "
              f"best D={best[1]:.1f}  gate {best[0]}/{len(members)}  "
              f"favorable {best[2]:+.2f}..{best[3]:+.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
