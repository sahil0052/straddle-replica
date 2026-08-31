"""Cycle 169 forensics: the last 24 unexplained re-arms in ReportHistory-901018.

tmp/a901_rearm.py's part 11 leaves exactly 24 grid pendings that sit on neither
the cycle's own lattice nor a fresh one -- all inside cycle 169, all about 37
points BELOW the cycle's fitted anchor, and the market proxy at their placement
time reads ~4111.60 while their own lattice fits at ~4074.73.  A buy stop 37
points below market cannot exist, so one of the two references is wrong.  This
probe prints the raw tape for the window instead of inferring: every order in
cycle 169 in time order, and every deal either side of 10:39, so the anchor,
the market and the order prices can be read off directly.
"""

from __future__ import annotations

import collections
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.forensics.dataset import load_all  # noqa: E402
from tools.forensics.linkage import CLOSE_BY_RE  # noqa: E402

GRID = ("buy stop", "sell stop")


def main() -> int:
    orders, positions, deals, cycles = load_all()
    by_index = {c.index: c for c in cycles}
    cycle = by_index[169]
    print(f"cycle 169  start {cycle.start}  end {cycle.end}"
          f"  anchor {cycle.anchor:.2f}  step {cycle.step:.2f}"
          f"  levels_per_side {cycle.levels_per_side}")
    print()

    mine = [o for o in orders if getattr(o, "cycle", None) == 169]
    print(f"orders attributed to cycle 169: {len(mine)}")
    print("  by type: " + ", ".join(
        f"{t} {n}" for t, n in collections.Counter(o.order_type for o in mine).most_common()
    ))
    print()

    grid = sorted((o for o in mine if o.order_type in GRID), key=lambda o: o.open_time)
    if grid:
        prices = [o.price for o in grid]
        print(f"grid pendings {len(grid)}  price range {min(prices):.2f} .. {max(prices):.2f}")
        print("  first 14 and last 14 in time order:")
        for order in grid[:14] + grid[-14:]:
            print(f"    {order.open_time}  {order.order_type:<9} {order.side}{order.level:<3}"
                  f" #{order.order_id} price {order.price:>9.2f} vol {order.volume:.2f}"
                  f" state {order.state:<9} comment {order.comment!r}")
        print()

        # Where does the mass sit?  Two price clouds would prove two lattices.
        buckets = collections.Counter(int(o.price // 5) * 5 for o in grid)
        print("  price histogram (5-point buckets):")
        for bucket in sorted(buckets):
            print(f"    {bucket:>6} .. {bucket + 5:>6}  {buckets[bucket]:>4}"
                  f"  {'#' * min(60, buckets[bucket])}")
        print()

    lo = datetime(2026, 7, 13, 10, 25)
    hi = datetime(2026, 7, 13, 10, 55)
    window_deals = sorted((d for d in deals if d.price and lo <= d.time <= hi), key=lambda d: d.time)
    print(f"deals 2026-07-13 10:25..10:55: {len(window_deals)}")
    for deal in window_deals[:30]:
        print(f"    {deal.time}  {deal.deal_type:<6} price {deal.price:>9.2f}"
              f" vol {deal.volume:.2f} pos {deal.position_id}")
    if len(window_deals) > 30:
        print(f"    ... {len(window_deals) - 30} more")
    print()

    # The two clouds, if real, should each have their own deals.  Print the
    # nearest deal on each side of 10:39:29 without a 120 s cap so a stale proxy
    # shows up as a large time gap rather than a plausible-looking price.
    pivot = datetime(2026, 7, 13, 10, 39, 29)
    before = [d for d in deals if d.price and d.time <= pivot]
    after = [d for d in deals if d.price and d.time >= pivot]
    if before:
        deal = max(before, key=lambda d: d.time)
        print(f"nearest deal BEFORE {pivot}: {deal.time} price {deal.price:.2f}"
              f"  gap {(pivot - deal.time).total_seconds():.1f} s")
    if after:
        deal = min(after, key=lambda d: d.time)
        print(f"nearest deal AFTER  {pivot}: {deal.time} price {deal.price:.2f}"
              f"  gap {(deal.time - pivot).total_seconds():.1f} s")
    print()

    hand = [o for o in orders if CLOSE_BY_RE.fullmatch((o.comment or "").strip())]
    print(f"`close by` orders in the whole report: {len(hand)}")
    for order in sorted(hand, key=lambda o: o.open_time):
        print(f"    {order.open_time}  cycle {getattr(order, 'cycle', None)}"
              f" #{order.order_id} {order.order_type:<9} price {order.price:>9.2f}"
              f" comment {order.comment!r}")
    print()

    # Was cycle 169's boundary drawn across two deployments?  Print the sweep
    # gap structure: a >5 min silence inside one cycle is a restart the
    # segmenter swallowed.
    if grid:
        gaps = []
        for previous, current in zip(grid, grid[1:]):
            seconds = (current.open_time - previous.open_time).total_seconds()
            if seconds >= 60.0:
                gaps.append((previous.open_time, current.open_time, seconds))
        print(f"gaps >= 60 s between consecutive cycle-169 grid pendings: {len(gaps)}")
        for start, end, seconds in gaps[:20]:
            print(f"    {start} -> {end}   {seconds / 60.0:.1f} min")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
