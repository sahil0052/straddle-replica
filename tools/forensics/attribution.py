"""Exact closure attribution v2.

Established identities (verified in b3_identity.py):
  * position_id == ticket of the entry order           (17,638 / 17,638)
  * every non-grid order produces exactly one deal     (except 12 'close by')
  * the deal fires 0-8 ms after its order              (so match on DEAL time)

Attribution strategy: group exit orders by their deal time and check whether a
timestamp ever mixes closure classes.  If it does not, the class of a timestamp
determines the class of every position closing at that instant -- exact, with no
bipartite matching required.
"""
from __future__ import annotations

from collections import defaultdict

from tools.forensics.linkage import comment_class


def build_exit_index(orders, deals):
    """Return (class_by_time, order_by_time, deal_by_order)."""
    deal_by_order: dict[int, list] = defaultdict(list)
    for d in deals:
        if d.order_id is not None:
            deal_by_order[d.order_id].append(d)

    order_by_time: dict[object, list] = defaultdict(list)
    for o in orders:
        if o.is_grid:
            continue
        for d in deal_by_order.get(o.order_id, []):
            order_by_time[d.time].append((o, d))

    class_by_time: dict[object, set[str]] = {}
    for t, items in order_by_time.items():
        class_by_time[t] = {comment_class(o.comment) for o, _ in items}
    return class_by_time, order_by_time, deal_by_order


def attribute(positions, class_by_time):
    """position_id -> closure class ('sl' | 'STR CLOSE' | ... | '<mixed>')."""
    out: dict[int, str] = {}
    mixed = 0
    missing = 0
    for p in positions:
        if p.is_open or p.close_time is None:
            continue
        cls = class_by_time.get(p.close_time)
        if not cls:
            missing += 1
            out[p.position_id] = "<missing>"
        elif len(cls) == 1:
            out[p.position_id] = next(iter(cls))
        else:
            mixed += 1
            out[p.position_id] = "<mixed:" + "|".join(sorted(cls)) + ">"
    return out, mixed, missing
