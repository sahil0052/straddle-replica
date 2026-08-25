"""Q4f: prove the deployment fill cooldown causally, and fit it.

q4e showed every LATE deployment burst that contains an in-burst fill has a max
internal gap of 20.15-20.20 s, while every EARLY one stays at the normal 0.13 s
cadence.  Burst span also scales with the fill count:

    fills  span    span - 6.4s baseline   / fills
     2     45.8s        39.4                19.7
     3     65.5s        59.1                19.7
     7    145.5s       139.1                19.9
    10    205.1s       198.7                19.9

A count fit alone is not proof: long gaps could be unrelated market pauses that
merely correlate with busy periods.  The causal test is ORDERING -- every long gap
must open immediately AFTER an order filled, and every fill must be followed by one.

Panel A  pair each in-burst fill with the very next placement gap.  Compare the
         "gap right after a fill" distribution against "gap after a non-fill".
Panel B  least-squares fit of burst span on fill count, per side.  Slope is the
         cooldown, intercept is (levels*2-1) * InterOrderDelayMs.
Panel C  the full 20 s pacing family across the break, one table.
"""
from __future__ import annotations

import statistics
import sys
from datetime import datetime

sys.path.insert(0, r"C:\websites\mt5 2")
from tools.forensics.dataset import load_all, FINAL_REGIME_START  # noqa: E402

BREAK = datetime(2026, 7, 24, 12, 0, 0)


def side(t: datetime) -> str:
    return "EARLY" if t < BREAK else "LATE"


def fit(xs: list[float], ys: list[float]) -> tuple[float, float]:
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        return 0.0, my
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den
    return b, my - b * mx


def main() -> None:
    orders, positions, deals, cycles = load_all()
    pos_by_id = {p.position_id: p for p in positions}
    fin = sorted((c for c in cycles
                  if c.start >= FINAL_REGIME_START and c.burst_orders),
                 key=lambda c: c.start)

    # ---------------------------------------------------------------- panel A
    print("=" * 100)
    print("A. CAUSAL TEST -- is the long gap the one that FOLLOWS a fill?")
    print("=" * 100)
    after_fill = {"EARLY": [], "LATE": []}
    after_none = {"EARLY": [], "LATE": []}
    for c in fin:
        b = sorted(c.burst_orders, key=lambda o: o.open_time)
        t0, t1 = b[0].open_time, b[-1].open_time
        s = side(c.start)
        for prev, nxt in zip(b, b[1:]):
            gap = (nxt.open_time - prev.open_time).total_seconds()
            # did anything fill in the window this gap spans?
            filled = False
            for o in b:
                if o.state != "filled":
                    continue
                p = pos_by_id.get(o.order_id)
                if p and prev.open_time <= p.open_time < nxt.open_time \
                        and t0 <= p.open_time <= t1:
                    filled = True
                    break
            (after_fill if filled else after_none)[s].append(gap)

    for s in ("EARLY", "LATE"):
        for lab, v in (("gap right AFTER a fill ", after_fill[s]),
                       ("gap with NO fill before", after_none[s])):
            if not v:
                print(f"  {s:<5} {lab}: none")
                continue
            v = sorted(v)
            print(f"  {s:<5} {lab}: n={len(v):<5} med={statistics.median(v):7.3f}s "
                  f"min={v[0]:6.3f} max={v[-1]:8.3f}  "
                  f">=15s: {sum(1 for x in v if x >= 15.0)}")
        print()

    # ---------------------------------------------------------------- panel B
    print("=" * 100)
    print("B. LINEAR FIT -- burst span = intercept + slope * (in-burst fills)")
    print("=" * 100)
    for s in ("EARLY", "LATE"):
        xs, ys = [], []
        for c in fin:
            if side(c.start) != s:
                continue
            b = sorted(c.burst_orders, key=lambda o: o.open_time)
            t0, t1 = b[0].open_time, b[-1].open_time
            n = 0
            for o in b:
                if o.state != "filled":
                    continue
                p = pos_by_id.get(o.order_id)
                if p and t0 <= p.open_time <= t1:
                    n += 1
            xs.append(float(n))
            ys.append((t1 - t0).total_seconds())
        if not xs:
            continue
        slope, inter = fit(xs, ys)
        resid = [y - (inter + slope * x) for x, y in zip(xs, ys)]
        print(f"  {s:<5} n={len(xs):<4} slope={slope:8.3f} s/fill   "
              f"intercept={inter:7.3f} s   "
              f"max|resid|={max(abs(r) for r in resid):6.3f}s")
        print(f"        intercept / 59 gaps = {inter/59.0*1000:.1f} ms per placement")
        print(f"        fills: {sorted(set(int(x) for x in xs))}")

    # ---------------------------------------------------------------- panel C
    print()
    print("=" * 100)
    print("C. THE 20-SECOND PACING FAMILY -- everything that flipped on 2026-07-24")
    print("=" * 100)
    rows = [
        ("close_interval_seconds", "burst @0.106 s/close (69 sweeps)",
         "paced @20.19 s/close (32 sweeps)", "20"),
        ("rearm_delay_seconds", "no floor, 42/1196 under 4.5 s",
         "floor 19.80 s, 2/581 under 19 s", "20"),
        ("restart_delay_ms", "floor 1.17 s, 64/68 under 4.5 s",
         "floor 20.91 s, 32/32 over 20.9 s", "20000"),
        ("deployment_fill_cooldown_seconds", "gap after fill 0.13 s",
         "gap after fill 20.17 s", "20"),
    ]
    print(f"  {'knob':<33} {'EARLY (Jul 14-24)':<34} {'LATE (Jul 24-30)':<34} replica")
    for k, e, l, r in rows:
        print(f"  {k:<33} {e:<34} {l:<34} {r}")
    print("\n  All four are 0 before the break and 20 after it: one operator action,")
    print("  not four coincidences.  Parity tracks LATE, so all four = 20.")


if __name__ == "__main__":
    main()
