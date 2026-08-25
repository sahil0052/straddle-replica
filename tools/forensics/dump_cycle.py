"""Dump one cycle's complete event timeline: deployment, fills, SLs, re-arms, exit."""
from __future__ import annotations

import sys

sys.path.insert(0, r"C:\websites\mt5 2")
from tools.forensics.dataset import load_all  # noqa: E402
from tools.forensics.attribution import build_exit_index, attribute  # noqa: E402


def main() -> None:
    target = int(sys.argv[1]) if len(sys.argv) > 1 else 267
    orders, positions, deals, cycles = load_all()
    class_by_time, order_by_time, _ = build_exit_index(orders, deals)
    reason, _, _ = attribute(positions, class_by_time)
    c = cycles[target]

    print(f"CYCLE {c.index}  start={c.start}  burst_end={c.burst_end}  end={c.end}")
    print(f"  anchor={c.anchor} step={c.step} levels={c.levels_per_side} "
          f"divisor={c.anchor/c.step:.2f}")
    print(f"  burst orders={len(c.burst_orders)} total orders={len(c.orders)} "
          f"positions={len(c.positions)} realized={c.realized:.2f}")

    print("\n-- deployment burst (first 12) --")
    for o in c.burst_orders[:12]:
        print(f"   {o.open_time.strftime('%H:%M:%S.%f')[:-3]} {o.order_type:<10} "
              f"{o.comment:<8} px={o.price} vol={o.volume}")

    ev = []
    for o in c.orders:
        if o.is_grid:
            ev.append((o.open_time, "PLACE", f"{o.comment:<8} {o.order_type:<10} "
                                             f"px={o.price} vol={o.volume}"))
            if o.state == "canceled" and o.end_time:
                ev.append((o.end_time, "CANCEL", f"{o.comment:<8} px={o.price}"))
        else:
            ev.append((o.open_time, "MKT", f"{str(o.comment):<20} {o.order_type:<10} "
                                           f"vol={o.volume}"))
    for p in c.positions:
        ev.append((p.open_time, "OPEN",
                   f"{p.comment:<8} {p.side:<4} vol={p.volume} @{p.open_price}"))
        if p.close_time:
            d = 1.0 if p.side == "buy" else -1.0
            lk = (d * ((p.stop_loss or p.open_price) - p.open_price) / c.step)
            ev.append((p.close_time, "CLOSE",
                       f"{p.comment:<8} {p.side:<4} @{p.close_price} "
                       f"sl={p.stop_loss} locked={lk:>6.2f}st net={p.net:>7.2f} "
                       f"[{reason.get(p.position_id)}]"))
    ev.sort(key=lambda e: (e[0], e[1]))
    print(f"\n-- full timeline ({len(ev)} events) --")
    for t, kind, txt in ev:
        print(f"   {t.strftime('%H:%M:%S.%f')[:-3]} {kind:<6} {txt}")


if __name__ == "__main__":
    main()
