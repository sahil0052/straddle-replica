"""Q1: the trailing-stop ratchet equation, measured on ALL SL observations.

Two independent measurements:

(1) LOCKED-PROFIT DISTRIBUTION.  For every position the report records the SL
    that was in force when it closed.  profit_steps = (sl - entry)*dir/step is
    the profit the ratchet had locked.  Its distribution discriminates between
    candidate activation/trail models.

(2) PEAK-EXCURSION BOUND (independent, one-sided, falsifiable).  Every fill and
    every close in the account is a timestamped price observation.  For a
    position open over [t0, t1] the best favourable price observed in that
    window, peak_obs, is a lower bound on the true peak.  A monotonic ratchet
    with trail distance D satisfies  sl >= peak_true - D*step >= peak_obs - D*step,
    hence  D >= (peak_obs - sl)/step  for EVERY position.  The maximum of that
    ratio over thousands of positions therefore measures D from below, and any
    position exceeding a candidate D falsifies it.
"""
from __future__ import annotations

import statistics
import sys
from bisect import bisect_left, bisect_right
from collections import Counter

sys.path.insert(0, r"C:\websites\mt5 2")
from tools.forensics.dataset import load_all, FINAL_REGIME_START  # noqa: E402
from tools.forensics.attribution import build_exit_index, attribute  # noqa: E402


def hist(vals, lo, hi, width, label):
    print(f"\n  {label}  (n={len(vals)})")
    n = int((hi - lo) / width + 0.5)
    buckets = Counter()
    for v in vals:
        if v < lo:
            buckets["<lo"] += 1
        elif v >= hi:
            buckets[">=hi"] += 1
        else:
            buckets[int((v - lo) / width)] += 1
    if "<lo" in buckets:
        print(f"    < {lo:<6.2f}      : {buckets['<lo']}")
    for i in range(n):
        c = buckets.get(i, 0)
        a, b = lo + i * width, lo + (i + 1) * width
        bar = "#" * min(70, int(c / max(1, max(buckets.values())) * 70))
        print(f"    [{a:>6.2f},{b:>6.2f}) {c:>5} {bar}")
    if ">=hi" in buckets:
        print(f"    >= {hi:<6.2f}     : {buckets['>=hi']}")


def main() -> None:
    orders, positions, deals, cycles = load_all()
    class_by_time, order_by_time, _ = build_exit_index(orders, deals)
    reason, _, _ = attribute(positions, class_by_time)
    step_by_cycle = {c.index: c.step for c in cycles}

    fr = [p for p in positions
          if p.open_time >= FINAL_REGIME_START and p.cycle >= 0]
    fr_closed = [p for p in fr if not p.is_open]

    # ---------- (1) locked-profit distribution -------------------------------
    print("=" * 78)
    print("(1) LOCKED PROFIT AT THE MOMENT OF CLOSE  (final regime)")
    print("=" * 78)

    def steps(p, price):
        st = step_by_cycle.get(p.cycle) or 0.0
        if st <= 0:
            return None
        d = 1.0 if p.side == "buy" else -1.0
        return d * (price - p.open_price) / st

    sl_pos = [p for p in fr_closed if reason.get(p.position_id) == "sl"]
    sc_pos = [p for p in fr_closed if reason.get(p.position_id) == "STR CLOSE"]
    print(f"sl-closed={len(sl_pos)}  basket-closed={len(sc_pos)} "
          f"(of which {sum(1 for p in sc_pos if p.stop_loss)} had a live SL)")

    locked = [(p, steps(p, p.stop_loss)) for p in sl_pos if p.stop_loss]
    locked = [(p, v) for p, v in locked if v is not None]
    vals = sorted(v for _, v in locked)
    print(f"\nprofit_steps of the in-force SL, n={len(vals)}")
    print(f"  min={vals[0]:.4f}  max={vals[-1]:.4f}  median={statistics.median(vals):.4f}")
    print("  quantiles:", [f"{vals[int(q*(len(vals)-1))]:.3f}"
                           for q in (0, .01, .05, .25, .5, .75, .95, .99, 1)])
    print(f"  negative (SL below entry): {sum(1 for v in vals if v < -1e-9)}")
    print(f"  exactly 0 (+-0.02 step)  : {sum(1 for v in vals if abs(v) <= 0.02)}")
    print(f"  in [0,1)                 : {sum(1 for v in vals if 0 <= v < 1)}")
    print(f"  in (1,2)  <-- claimed GAP: {sum(1 for v in vals if 1 < v < 2)}")
    print(f"  in [2,inf)               : {sum(1 for v in vals if v >= 2)}")
    hist(vals, -0.5, 4.0, 0.25, "locked profit_steps, ALL sl closures")

    # same measurement restricted to the zero-slippage subsample that produced
    # the historical "287" figure, to show the sampling bias
    zs = sorted(v for p, v in locked
                if abs((p.close_price or 0) - p.stop_loss) < 1e-9)
    print(f"\n  >>> zero-slippage subsample (the historical '287'): n={len(zs)}")
    print(f"      in [0,1)={sum(1 for v in zs if 0<=v<1)} "
          f"in (1,2)={sum(1 for v in zs if 1<v<2)} "
          f"in [2,inf)={sum(1 for v in zs if v>=2)}")
    hist(zs, -0.5, 4.0, 0.25, "locked profit_steps, zero-slippage subsample only")

    # SLs that were live but never hit (basket closed first) - also valid
    live = sorted(v for v in (steps(p, p.stop_loss) for p in sc_pos if p.stop_loss)
                  if v is not None)
    print(f"\n  live-but-unhit SLs at basket close: n={len(live)}")
    if live:
        print(f"    min={live[0]:.4f} max={live[-1]:.4f} "
              f"neg={sum(1 for v in live if v < -1e-9)} "
              f"in[0,1)={sum(1 for v in live if 0<=v<1)} "
              f"in(1,2)={sum(1 for v in live if 1<v<2)} "
              f"in[2,inf)={sum(1 for v in live if v>=2)}")
        hist(live, -0.5, 4.0, 0.25, "locked profit_steps, live-unhit SLs")

    # ---------- (2) peak excursion bound ------------------------------------
    print("\n" + "=" * 78)
    print("(2) PEAK-EXCURSION BOUND ON THE TRAIL DISTANCE")
    print("=" * 78)

    obs_t: list = []
    obs_p: list = []
    pts = []
    for p in positions:
        pts.append((p.open_time, p.open_price))
        if p.close_time and p.close_price:
            pts.append((p.close_time, p.close_price))
    for o in orders:
        if o.state == "filled" and o.end_time and o.price is not None:
            pts.append((o.end_time, o.price))
    pts.sort()
    for t, pr in pts:
        obs_t.append(t)
        obs_p.append(pr)
    print(f"price observations: {len(pts)}  "
          f"({pts[0][0]} .. {pts[-1][0]})")

    # prefix max/min via sparse table-free approach: bucket scan (windows small)
    def window(lo, hi):
        i = bisect_left(obs_t, lo)
        j = bisect_right(obs_t, hi)
        return i, j

    rows = []
    for p, lk in locked:
        st = step_by_cycle[p.cycle]
        i, j = window(p.open_time, p.close_time)
        if j - i < 2:
            continue
        seg = obs_p[i:j]
        peak = max(seg) if p.side == "buy" else min(seg)
        d = 1.0 if p.side == "buy" else -1.0
        peak_steps = d * (peak - p.open_price) / st
        implied = d * (peak - p.stop_loss) / st        # lower bound on trail D
        rows.append((p, st, peak_steps, lk, implied, j - i))

    print(f"positions with >=2 in-window observations: {len(rows)}")
    imp = sorted(r[4] for r in rows)
    print("implied trail-distance lower bound (peak_obs - sl)/step:")
    print("  quantiles:", [f"{imp[int(q*(len(imp)-1))]:.3f}"
                           for q in (0, .25, .5, .75, .9, .95, .99, 1)])
    print(f"  > 1.02 steps (falsifies a pure 1.0-step trail): "
          f"{sum(1 for v in imp if v > 1.02)}")
    print(f"  > 2.02 steps (falsifies a 2.0-step trail)     : "
          f"{sum(1 for v in imp if v > 2.02)}")
    hist(imp, -0.5, 3.0, 0.1, "implied trail lower bound, all sl positions")

    print("\n  implied trail vs observed peak bucket "
          "(model: D=2 while peak<3, D=1 once peak>=3)")
    print(f"  {'peak bucket':<14} {'n':>5} {'med D':>7} {'p90 D':>7} {'max D':>7}")
    buckets = [(2.0, 2.5), (2.5, 3.0), (3.0, 3.5), (3.5, 4.0), (4.0, 5.0),
               (5.0, 7.0), (7.0, 99.0)]
    for lo, hi in buckets:
        sel = [r[4] for r in rows if lo <= r[2] < hi]
        if not sel:
            continue
        sel.sort()
        print(f"  [{lo:>4.1f},{hi:>4.1f})    {len(sel):>5} "
              f"{statistics.median(sel):>7.3f} "
              f"{sel[int(.9*(len(sel)-1))]:>7.3f} {max(sel):>7.3f}")

    print("\n  worst 15 offenders (largest implied D):")
    for p, st, pk, lk, im, nobs in sorted(rows, key=lambda r: -r[4])[:15]:
        print(f"    D={im:>6.3f} peak={pk:>6.2f} locked={lk:>6.2f} step={st:.3f} "
              f"{p.side:<4} {p.comment:<8} cyc={p.cycle} obs={nobs} "
              f"{p.open_time}")


if __name__ == "__main__":
    main()
