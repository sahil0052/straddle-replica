"""Phase A/B: sanity-check the cycle reconstruction and confirm regime boundaries."""
from __future__ import annotations

import statistics
import sys
from collections import Counter, defaultdict

sys.path.insert(0, r"C:\websites\mt5 2")
from tools.forensics.dataset import load_all, FINAL_REGIME_START  # noqa: E402


def main() -> None:
    orders, positions, deals, cycles = load_all()
    print(f"orders={len(orders)} positions={len(positions)} deals={len(deals)} "
          f"cycles={len(cycles)}")

    grid_orders = [o for o in orders if o.is_grid]
    print(f"grid orders={len(grid_orders)}  non-grid={len(orders)-len(grid_orders)}")
    print("non-grid comments:", Counter(
        o.comment for o in orders if not o.is_grid).most_common(12))
    print("order types:", Counter(o.order_type for o in orders).most_common())
    print("order states:", Counter(o.state for o in orders).most_common())
    print("deal types:", Counter(d.deal_type for d in deals).most_common())

    print("\n--- unassigned (pre-first-burst) ---")
    print("orders:", sum(1 for o in orders if o.cycle < 0),
          "positions:", sum(1 for p in positions if p.cycle < 0))

    print("\n--- cycle table (first 6 / last 6) ---")
    hdr = f"{'#':>4} {'start':<23} {'lvl':>4} {'step':>7} {'anchor':>9} " \
          f"{'burst':>6} {'ord':>5} {'pos':>5} {'realized':>9} {'span_pts':>8}"
    print(hdr)
    rows = []
    for c in cycles:
        prices = [p.open_price for p in c.positions]
        span = (max(prices) - min(prices)) if prices else 0.0
        rows.append((c, span))
    for c, span in rows[:6] + [(None, 0)] + rows[-6:]:
        if c is None:
            print("  ...")
            continue
        print(f"{c.index:>4} {c.start.strftime('%Y-%m-%d %H:%M:%S'):<23} "
              f"{c.levels_per_side:>4} {c.step:>7.3f} {c.anchor:>9.2f} "
              f"{len(c.burst_orders):>6} {len(c.orders):>5} {len(c.positions):>5} "
              f"{c.realized:>9.2f} {span:>8.2f}")

    print("\n--- levels_per_side over time (regime fingerprint) ---")
    by_month = defaultdict(Counter)
    for c in cycles:
        by_month[c.start.strftime("%Y-%m")][c.levels_per_side] += 1
    for k in sorted(by_month):
        print(f"  {k}: {dict(sorted(by_month[k].items()))}")

    print("\n--- lot schedule by (level tier) per half-month window ---")
    def tier(lv: int) -> str:
        if lv <= 10:
            return "L01-10"
        if lv <= 20:
            return "L11-20"
        if lv <= 30:
            return "L21-30"
        if lv <= 45:
            return "L31-45"
        return "L46-60"

    win_vol = defaultdict(Counter)
    for o in grid_orders:
        key = o.open_time.strftime("%Y-%m") + ("a" if o.open_time.day <= 14 else "b")
        win_vol[(key, tier(o.level))][o.volume] += 1
    for key in sorted(win_vol):
        print(f"  {key[0]} {key[1]}: {dict(sorted(win_vol[key].items()))}")

    print("\n--- final regime (>= %s) ---" % FINAL_REGIME_START.date())
    fr = [c for c in cycles if c.start >= FINAL_REGIME_START]
    print(f"cycles={len(fr)}")
    fr_orders = [o for o in grid_orders if o.open_time >= FINAL_REGIME_START]
    fr_pos = [p for p in positions if p.open_time >= FINAL_REGIME_START]
    print(f"grid orders={len(fr_orders)} positions={len(fr_pos)}")
    print("volume histogram:", dict(sorted(Counter(o.volume for o in fr_orders).items())))
    print("levels_per_side:", dict(sorted(Counter(c.levels_per_side for c in fr).items())))
    steps = [c.step for c in fr]
    print(f"step: median={statistics.median(steps):.4f} min={min(steps):.4f} "
          f"max={max(steps):.4f}")
    divs = [c.anchor / c.step for c in fr if c.step > 0]
    print(f"anchor/step divisor: median={statistics.median(divs):.2f} "
          f"min={min(divs):.2f} max={max(divs):.2f}")
    print("TP set count:", sum(1 for p in fr_pos if p.take_profit))


if __name__ == "__main__":
    main()
