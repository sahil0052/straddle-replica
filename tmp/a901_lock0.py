"""Discriminate the two activation laws by looking for a price-space ATOM.

StopScheduler has two activation modes and they leave different fingerprints in
dir*(sl - open) measured in PRICE, not in steps:

  activation_uses_trailing_distance = false   (ResetProfile default, so what
      HISTORICAL_50 / HISTORICAL_60 inherit)
      activate at lock_trigger_steps = 2.0 favourable steps, first stop at
      open + dir*lock_offset_price = entry + 0.20.  Every position that is
      stopped before the trail ever advances therefore carries raw = +0.20
      EXACTLY, whatever the cycle's step is.  A hard atom at 0.20.

  activation_uses_trailing_distance = true    (what STARWAVE_30 sets)
      activate at the trailing distance itself, first stop at
      market - dir*D*step = open + dir*(2*step) - dir*(2*step) = open.
      So the atom sits at raw = 0.00 and scales with nothing.

The two are mutually exclusive, so counting exact cents settles which build ran
each era.  Everything here is 2-dp gold price, so the atoms are exact.
"""
from __future__ import annotations

import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from a901_v4578 import build_deployments, load_orders, load_positions  # noqa: E402

ERAS = ("HISTORICAL_50", "HISTORICAL_60", "AGGRESSIVE_30", "LOW_RISK_30", "STARWAVE_30")


def main() -> int:
    positions = load_positions()
    deployments = build_deployments(load_orders())

    def cycle_of(when):
        chosen = None
        for record in deployments:
            if record["when"] <= when:
                chosen = record
            else:
                break
        return chosen

    raw_hist = collections.defaultdict(collections.Counter)
    totals = collections.Counter()
    stragglers = []
    for row in positions:
        if row["sl"] == 0.0:
            continue
        cycle = cycle_of(row["opened"])
        if cycle is None or cycle["step"] <= 0.0:
            continue
        era = str(cycle["assigned"])
        direction = 1.0 if row["is_buy"] else -1.0
        raw = round(direction * (row["sl"] - row["open_price"]), 2)
        raw_hist[era][raw] += 1
        totals[era] += 1
        locked = raw / cycle["step"]
        if era == "STARWAVE_30" and 1.0 <= locked < 2.0:
            stragglers.append((row["opened"], row["ticket"], "buy" if row["is_buy"] else "sell",
                               row["open_price"], row["sl"], cycle["step"], locked))

    print("=== raw = dir*(sl - open) in PRICE, 12 most common exact values per era ===")
    for era in ERAS:
        counter = raw_hist.get(era)
        if not counter:
            continue
        n = totals[era]
        print(f"  -- {era} n={n}")
        line = [f"{value:+.2f}:{count} ({100.0*count/n:4.1f}%)"
                for value, count in counter.most_common(12)]
        print("     " + "  ".join(line))
        at_zero = counter.get(0.0, 0)
        at_twenty = counter.get(0.20, 0)
        print(f"     atom at 0.00: {at_zero:5d} ({100.0*at_zero/n:5.2f}%)     "
              f"atom at 0.20: {at_twenty:5d} ({100.0*at_twenty/n:5.2f}%)     "
              f"distinct values: {len(counter)}     min={min(counter):+.2f}")

    print()
    print("=== the 8 STARWAVE_30 positions inside the forbidden [1,2) trough ===")
    for opened, ticket, side, open_price, sl, step, locked in sorted(stragglers):
        print(f"  {opened}  #{ticket}  {side:4s} open={open_price:9.2f} sl={sl:9.2f} "
              f"step={step:.4f} locked={locked:6.3f} raw={locked*step:+.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
