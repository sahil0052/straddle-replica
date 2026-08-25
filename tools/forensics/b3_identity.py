"""Diagnose deal/order/position identity so the linkage is exact, not heuristic."""
from __future__ import annotations

import sys
from collections import Counter, defaultdict

sys.path.insert(0, r"C:\websites\mt5 2")
from tools.forensics.dataset import load_all  # noqa: E402
from tools.forensics.linkage import SL_RE, comment_class  # noqa: E402


def main() -> None:
    orders, positions, deals, cycles = load_all()
    order_by_id = {o.order_id: o for o in orders}
    pos_by_id = {p.position_id: p for p in positions}

    print("deal directions:", dict(Counter(d.direction for d in deals)))
    print("deal types:", dict(Counter(d.deal_type for d in deals)))

    # 1. position_id == entry order id ?
    hit = miss = 0
    mismatch = []
    for p in positions:
        o = order_by_id.get(p.position_id)
        if o is None:
            miss += 1
            continue
        ok = (abs((o.price or -1) - p.open_price) < 5.0 and o.comment == p.comment)
        if ok:
            hit += 1
        else:
            mismatch.append((p, o))
    print(f"\nposition_id -> order: hit={hit} miss={miss} mismatch={len(mismatch)}")
    for p, o in mismatch[:5]:
        print("   ", p.position_id, p.comment, p.open_price, "|", o.order_type,
              o.comment, o.price)

    # 2. entry deal: deal.order_id == position_id ?
    deals_by_order = defaultdict(list)
    for d in deals:
        if d.order_id is not None:
            deals_by_order[d.order_id].append(d)
    entry_ok = 0
    for p in positions:
        ds = deals_by_order.get(p.position_id, [])
        if any(d.direction == "in" and abs(d.volume - p.volume) < 1e-9 for d in ds):
            entry_ok += 1
    print(f"entry deal via order_id==position_id: {entry_ok}/{len(positions)}")

    # 3. how many deals per exit order?  (basket close = many deals, one order?)
    exit_orders = [o for o in orders if not o.is_grid]
    per = Counter(len(deals_by_order.get(o.order_id, [])) for o in exit_orders)
    print("deals per non-grid order:", dict(sorted(per.items())))

    # 4. Does each [sl X] order's X match exactly one position's recorded SL at
    #    that timestamp?
    print("\n=== [sl X] order -> position by (time, volume, SL==X) ===")
    by_ct = defaultdict(list)
    for p in positions:
        if p.close_time:
            by_ct[p.close_time].append(p)
    exact = ambiguous = none = 0
    time_off = Counter()
    for o in exit_orders:
        m = SL_RE.fullmatch(o.comment or "")
        if not m:
            continue
        x = float(m.group(1))
        # exit order's time vs the position close time
        best = None
        for dt_off in (0,):
            cands = [p for p in by_ct.get(o.open_time, [])
                     if p.stop_loss is not None and abs(p.stop_loss - x) < 1e-6
                     and abs(p.volume - o.volume) < 1e-9
                     and ((p.side == "buy") == (o.order_type == "sell"))]
            if cands:
                best = cands
                break
        if best is None:
            none += 1
        elif len(best) == 1:
            exact += 1
        else:
            ambiguous += 1
    print(f"exact={exact} ambiguous={ambiguous} unmatched={none}")

    # 5. exit order open_time vs position close_time offset distribution
    print("\n=== exit-order time vs deal time ===")
    offs = Counter()
    for o in exit_orders:
        ds = deals_by_order.get(o.order_id, [])
        for d in ds:
            offs[round((d.time - o.open_time).total_seconds(), 3)] += 1
    print(dict(sorted(offs.items())[:12]), "...", dict(sorted(offs.items())[-6:]))

    # 6. Do positions' close_time equal their exit DEAL time? Use order_id chain:
    #    for each non-grid order, its deals are the exits it produced.
    print("\n=== non-grid order -> which positions did it close? ===")
    multi = [o for o in exit_orders if len(deals_by_order.get(o.order_id, [])) > 1]
    print("orders producing >1 deal:", len(multi))
    for o in multi[:5]:
        print("   ", o.order_id, o.comment, o.volume,
              [(d.deal_id, d.volume, d.price, d.profit)
               for d in deals_by_order[o.order_id]])


if __name__ == "__main__":
    main()
