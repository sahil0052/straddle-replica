"""Measure the Target's trailing DISTANCE directly, per era.

The Positions table gives, for every position, its final S/L and its close price.
Two disjoint populations fall out once the sign is read correctly (dir = +1 buy,
-1 sell):

  dir*(close - sl) <= 0   the stop was the exit (0 = clean fill, <0 = slipped
                          through).  13,680 of the tape's 13,872 "[sl ...]"
                          closes land here; the other 192 filled just beyond it.
  dir*(close - sl) >  0   the position was still alive and something else closed
                          it -- the basket sweep.  Here the offset IS the live
                          trailing distance, because the scheduler holds
                          sl = market - dir*D*step, so dir*(close - sl) = D*step.

So dividing that offset by the cycle's own step recovers D in steps, with no
model assumption at all.  A two-stage ratchet must show D clustered at exactly
two values (2.0 pre-tighten, 1.0 post-tighten); a single-stage trail shows one.
"""
from __future__ import annotations

import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from a901_v4578 import build_deployments, load_orders, load_positions, pct  # noqa: E402

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

    live = collections.defaultdict(list)   # era -> D in steps, sweep-closed
    locked = collections.defaultdict(list)  # era -> locked in steps, all with S/L
    for row in positions:
        if row["sl"] == 0.0:
            continue
        cycle = cycle_of(row["opened"])
        if cycle is None or cycle["step"] <= 0.0:
            continue
        era = str(cycle["assigned"])
        direction = 1.0 if row["is_buy"] else -1.0
        offset = direction * (row["close_price"] - row["sl"])
        locked[era].append(direction * (row["sl"] - row["open_price"]) / cycle["step"])
        if offset > 5e-9:
            live[era].append(offset / cycle["step"])

    print("=== trailing distance D (steps) read off sweep-closed positions ===")
    for era in ERAS:
        values = live.get(era)
        if not values:
            continue
        print(f"  {era:14s} n={len(values):5d} p05={pct(values,0.05):6.3f} "
              f"p25={pct(values,0.25):6.3f} p50={pct(values,0.50):6.3f} "
              f"p75={pct(values,0.75):6.3f} p95={pct(values,0.95):6.3f} "
              f"min={min(values):6.3f} max={max(values):7.3f}")
        grid = collections.Counter()
        for value in values:
            grid[round(value * 4.0) / 4.0 if value < 6.0 else "out"] += 1
        line = [f"{k:+.2f}:{v}" if k != "out" else f"out:{v}"
                for k, v in sorted(grid.items(), key=lambda kv: (kv[0] == "out", kv[0]))]
        print("      " + "  ".join(line))
        near1 = sum(1 for v in values if 0.90 <= v <= 1.10)
        near2 = sum(1 for v in values if 1.90 <= v <= 2.10)
        print(f"      within +-0.10 of 1.0: {near1}/{len(values)} "
              f"({100.0*near1/len(values):5.2f}%)   of 2.0: {near2}/{len(values)} "
              f"({100.0*near2/len(values):5.2f}%)   both: "
              f"{100.0*(near1+near2)/len(values):5.2f}%")
    print()

    print("=== locked distance, band scoring over ALL positions carrying an S/L ===")
    print("  (two-stage model forbids [1,2); single-stage trail fills it smoothly)")
    for era in ERAS:
        values = locked.get(era)
        if not values:
            continue
        below = sum(1 for v in values if v < -1e-9)
        stage1 = sum(1 for v in values if -1e-9 <= v < 1.0)
        trough = sum(1 for v in values if 1.0 <= v < 2.0)
        stage2 = sum(1 for v in values if v >= 2.0)
        n = len(values)
        print(f"  {era:14s} n={n:5d}  <0={below:5d}  [0,1)={stage1:5d}  "
              f"[1,2)={trough:5d} ({100.0*trough/n:5.2f}%)  [2,inf)={stage2:5d}")
    print()

    print("=== is the ATR-era locked distribution smooth?  chi-square-free test: ===")
    print("  compare density in [1,2) against the mean of [0,1) and [2,3)")
    for era in ERAS:
        values = locked.get(era)
        if not values:
            continue
        a = sum(1 for v in values if 0.0 <= v < 1.0)
        b = sum(1 for v in values if 1.0 <= v < 2.0)
        c = sum(1 for v in values if 2.0 <= v < 3.0)
        neighbours = (a + c) / 2.0
        ratio = (b / neighbours) if neighbours else float("nan")
        verdict = "TWO-STAGE (trough)" if ratio < 0.15 else "SINGLE-STAGE (smooth)"
        print(f"  {era:14s} [0,1)={a:5d} [1,2)={b:5d} [2,3)={c:5d} "
              f"ratio={ratio:6.3f}  -> {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
