"""Exact position <-> exit-deal <-> closing-order linkage.

The xlsx Deals sheet has no position id, but it does have direction (in/out),
time, volume, price and order_id.  A closed position's exit is the unique 'out'
deal with the same (time, volume, price).  Where several positions share an
instant (basket liquidation) the tuple is still unique per (volume, price)
except for genuine duplicates, which we resolve by consuming a multiset.
"""
from __future__ import annotations

import re
from collections import defaultdict

SL_RE = re.compile(r"^\[sl (\d+(?:\.\d+)?)\]$")
TP_RE = re.compile(r"^\[tp (\d+(?:\.\d+)?)\]$")
CLOSE_BY_RE = re.compile(r"^#\d+ by #\d+$")


def comment_class(c: str | None) -> str:
    if c is None:
        return "<none>"
    if SL_RE.fullmatch(c):
        return "sl"
    if TP_RE.fullmatch(c):
        return "tp"
    if CLOSE_BY_RE.fullmatch(c):
        return "close_by"
    return c


def link_exits(orders, positions, deals):
    """Return (exit_order_by_pos, exit_deal_by_pos, entry_deal_by_pos, stats)."""
    order_by_id = {o.order_id: o for o in orders}

    out_pool: dict[tuple, list] = defaultdict(list)
    in_pool: dict[tuple, list] = defaultdict(list)
    for d in deals:
        if d.deal_type == "balance":
            continue
        key = (d.time, round(d.volume, 4), round(d.price or 0.0, 5))
        if d.direction == "out":
            out_pool[key].append(d)
        elif d.direction == "in":
            in_pool[key].append(d)
        else:  # in/out (close-by) counts for both
            out_pool[key].append(d)
            in_pool[key].append(d)

    exit_order: dict[int, object] = {}
    exit_deal: dict[int, object] = {}
    entry_deal: dict[int, object] = {}
    stats = {"exit_hit": 0, "exit_miss": 0, "entry_hit": 0, "entry_miss": 0}

    for p in positions:
        ekey = (p.open_time, round(p.volume, 4), round(p.open_price, 5))
        bucket = in_pool.get(ekey)
        if bucket:
            entry_deal[p.position_id] = bucket.pop(0)
            stats["entry_hit"] += 1
        else:
            stats["entry_miss"] += 1

        if p.is_open or p.close_time is None or p.close_price is None:
            continue
        xkey = (p.close_time, round(p.volume, 4), round(p.close_price, 5))
        bucket = out_pool.get(xkey)
        if bucket:
            d = bucket.pop(0)
            exit_deal[p.position_id] = d
            stats["exit_hit"] += 1
            if d.order_id is not None and d.order_id in order_by_id:
                exit_order[p.position_id] = order_by_id[d.order_id]
        else:
            stats["exit_miss"] += 1

    return exit_order, exit_deal, entry_deal, stats


def exit_reason(p, exit_order) -> str:
    o = exit_order.get(p.position_id)
    if o is None:
        return "<unlinked>"
    return comment_class(o.comment)
