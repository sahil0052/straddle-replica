"""Diagnostics for two suspicious readings in the per-era pass.

(1) close_price == S/L identified only 1,856 SL exits, but the tape carries 13,872
    "[sl ...]" closing deals.  Measure the signed offset dir*(close - sl) to find
    out what the Positions table is actually showing.
(2) V4's [1,2) trough is 0.34% in STARWAVE_30 but 22-26% in the ATR eras.  If the
    ATR build used different trail constants its trough sits somewhere else, so
    histogram the locked distance at 0.25-step resolution per era instead of
    forcing STARWAVE_30's band edges onto every era.
"""
from __future__ import annotations

import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from a901_v4578 import build_deployments, load_orders, load_positions, pct  # noqa: E402


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

    print("=== (1) signed offset dir*(close - sl) for positions that HAVE an S/L ===")
    withsl = [r for r in positions if r["sl"] != 0.0]
    offs = [(1.0 if r["is_buy"] else -1.0) * (r["close_price"] - r["sl"]) for r in withsl]
    exact = sum(1 for v in offs if abs(v) < 5e-9)
    print(f"  positions with S/L={len(withsl)}  exact close==sl={exact}")
    print(f"  offset p01={pct(offs,0.01):9.3f} p05={pct(offs,0.05):9.3f} "
          f"p25={pct(offs,0.25):9.3f} p50={pct(offs,0.50):9.3f} "
          f"p75={pct(offs,0.75):9.3f} p95={pct(offs,0.95):9.3f}")
    print(f"  min={min(offs):9.3f} max={max(offs):9.3f}")
    buckets = collections.Counter()
    for value in offs:
        if abs(value) < 5e-9:
            buckets["exact 0"] += 1
        elif -0.01 <= value < 0.0:
            buckets["[-0.01,0)"] += 1
        elif -0.10 <= value < -0.01:
            buckets["[-0.10,-0.01)"] += 1
        elif -1.00 <= value < -0.10:
            buckets["[-1.0,-0.10)"] += 1
        elif value < -1.00:
            buckets["< -1.0"] += 1
        elif 0.0 < value <= 0.01:
            buckets["(0,0.01]"] += 1
        elif 0.01 < value <= 0.10:
            buckets["(0.01,0.10]"] += 1
        elif 0.10 < value <= 1.00:
            buckets["(0.10,1.0]"] += 1
        else:
            buckets["> 1.0"] += 1
    for key, count in buckets.most_common():
        print(f"    {key:16s} {count:6d}")
    print()

    print("=== (1b) same split, per era ===")
    per_era = collections.defaultdict(collections.Counter)
    for row in withsl:
        cycle = cycle_of(row["opened"])
        era = str(cycle["assigned"]) if cycle else "?"
        value = (1.0 if row["is_buy"] else -1.0) * (row["close_price"] - row["sl"])
        per_era[era]["n"] += 1
        if abs(value) < 5e-9:
            per_era[era]["exact"] += 1
        elif value < 0.0:
            per_era[era]["short of sl"] += 1
        else:
            per_era[era]["beyond sl"] += 1
    for era, counter in per_era.items():
        print(f"  {era:14s} n={counter['n']:6d} exact={counter['exact']:6d} "
              f"short={counter['short of sl']:6d} beyond={counter['beyond sl']:6d}")
    print()

    print("=== (2) locked = dir*(sl-open)/step, 0.25-wide bins, per era ===")
    grids = collections.defaultdict(collections.Counter)
    totals = collections.Counter()
    for row in withsl:
        cycle = cycle_of(row["opened"])
        if cycle is None or cycle["step"] <= 0.0:
            continue
        era = str(cycle["assigned"])
        direction = 1.0 if row["is_buy"] else -1.0
        locked = direction * (row["sl"] - row["open_price"]) / cycle["step"]
        if locked < -0.5 or locked >= 6.0:
            grids[era]["out"] += 1
            totals[era] += 1
            continue
        grids[era][int(locked * 4.0) / 4.0] += 1
        totals[era] += 1
    edges = [i / 4.0 for i in range(-2, 24)]
    for era in ("HISTORICAL_50", "HISTORICAL_60", "AGGRESSIVE_30", "LOW_RISK_30",
                "STARWAVE_30"):
        if era not in totals:
            continue
        print(f"  -- {era} n={totals[era]}")
        line = []
        for edge in edges:
            count = grids[era].get(edge, 0)
            if count:
                line.append(f"{edge:+.2f}:{count}")
        print("     " + "  ".join(line))
        print(f"     out-of-range={grids[era].get('out',0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
