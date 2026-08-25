"""Q3f: dump the basket-total time series for the cycles that falsify total>=30.

For each named cycle, print every price print with the basket decomposition
(realized so far / floating / open count / armed pendings / distance from anchor)
so the $642 pre-decision maximum in cycle 252 can be judged real or artefactual.
"""
from __future__ import annotations

import sys
from bisect import bisect_left, bisect_right
from collections import defaultdict

sys.path.insert(0, r"C:\websites\mt5 2")
from tools.forensics.dataset import load_all, CONTRACT  # noqa: E402
from tools.forensics.attribution import build_exit_index, attribute  # noqa: E402


def main() -> None:
    targets = [int(x) for x in sys.argv[1:]] or [252]
    orders, positions, deals, cycles = load_all()
    class_by_time, _, _ = build_exit_index(orders, deals)
    reason, _, _ = attribute(positions, class_by_time)

    prints = []
    for p in positions:
        prints.append((p.open_time, p.open_price))
        if p.close_time and p.close_price:
            prints.append((p.close_time, p.close_price))
    prints.sort()
    pt_t = [t for t, _ in prints]
    pt_p = [x for _, x in prints]

    pos_by_cycle = defaultdict(list)
    for p in positions:
        if p.cycle >= 0:
            pos_by_cycle[p.cycle].append(p)

    for target in targets:
        c = cycles[target]
        ps = pos_by_cycle.get(target, [])
        closes = [p for p in ps if not p.is_open and p.close_time
                  and reason.get(p.position_id) == "STR CLOSE"]
        first_close = min((p.close_time for p in closes), default=None)
        print("=" * 108)
        print(f"CYCLE {target}  start={c.start}  first_close={first_close}  "
              f"anchor={c.anchor} step={c.step:.4f}")
        print(f"  positions={len(ps)}  flatten_closes={len(closes)}  "
              f"realized={c.realized:.2f}")
        print("=" * 108)
        i0 = bisect_left(pt_t, c.start)
        i1 = bisect_right(pt_t, first_close) if first_close else len(pt_t)
        print(f"  {'time':<21} {'market':>9} {'real':>9} {'float':>10} "
              f"{'TOTAL':>10} {'op':>3} {'armed':>6} {'dist_st':>8} {'$/pt':>7}")
        prev = None
        for i in range(i0, i1):
            t, mk = pt_t[i], pt_p[i]
            realized = floating = vol = 0.0
            nopen = 0
            for p in ps:
                if p.open_time > t:
                    continue
                if not p.is_open and p.close_time and p.close_time <= t:
                    realized += p.net
                else:
                    floating += p.dir * (mk - p.open_price) * p.volume * CONTRACT
                    vol += p.volume
                    nopen += 1
            armed = sum(1 for o in c.orders
                        if o.is_grid and o.open_time <= t
                        and (o.state == "placed" or (o.end_time and o.end_time > t)))
            tot = realized + floating
            flag = ""
            if tot >= 30.0:
                flag = "  <<< TOTAL>=30"
            gap = "" if prev is None else f"  (+{(t-prev).total_seconds():.0f}s)"
            print(f"  {t.strftime('%m-%d %H:%M:%S'):<21} {mk:>9.2f} {realized:>9.2f} "
                  f"{floating:>10.2f} {tot:>10.2f} {nopen:>3} {armed:>6} "
                  f"{(mk-c.anchor)/c.step:>8.2f} {vol*CONTRACT:>7.1f}{flag}{gap}")
            prev = t
        print()


if __name__ == "__main__":
    main()
