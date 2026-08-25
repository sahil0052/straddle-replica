"""Phase B: classify every entry and every closure exactly, via order comments.

MT5 records the *reason* for a closure in the comment of the synthetic market
order it creates:  "[sl 4095.97]" for a stop-loss hit, "[tp ...]" for a take
profit, and the EA's own comment ("STR CLOSE") for an EA-issued basket close.
Linking position -> closing deal -> closing order therefore yields a ground
truth closure taxonomy with no inference at all.
"""
from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, r"C:\websites\mt5 2")
from tools.forensics.dataset import load_all, FINAL_REGIME_START  # noqa: E402

SL_RE = re.compile(r"^\[sl (\d+(?:\.\d+)?)\]$")
TP_RE = re.compile(r"^\[tp (\d+(?:\.\d+)?)\]$")


def main() -> None:
    orders, positions, deals, cycles = load_all()
    order_by_id = {o.order_id: o for o in orders}

    print("=== non-grid order taxonomy (type x comment-class) ===")
    def cclass(c: str | None) -> str:
        if c is None:
            return "<none>"
        if SL_RE.fullmatch(c):
            return "[sl]"
        if TP_RE.fullmatch(c):
            return "[tp]"
        return c

    tab = Counter((o.order_type, cclass(o.comment)) for o in orders if not o.is_grid)
    for (ot, cc), n in sorted(tab.items(), key=lambda kv: -kv[1]):
        print(f"  {ot:<10} {cc:<12} {n:>6}")

    print("\n=== STR ORB/ORS/AVB/AVS detail ===")
    special = [o for o in orders
               if o.comment in ("STR ORB", "STR ORS", "STR AVB", "STR AVS")]
    print("count:", len(special))
    print("by comment x type:",
          dict(Counter((o.comment, o.order_type) for o in special)))
    print("by volume:", dict(sorted(Counter(o.volume for o in special).items())))
    print("date range:", min(o.open_time for o in special), "->",
          max(o.open_time for o in special))
    by_day = Counter(o.open_time.date() for o in special)
    print("by day:", dict(sorted(by_day.items())))
    print("in final regime:",
          sum(1 for o in special if o.open_time >= FINAL_REGIME_START))
    print("samples:")
    for o in special[:14]:
        print(f"   {o.open_time} id={o.order_id} {o.order_type:<10} "
              f"vol={o.volume} px={o.price} state={o.state} c={o.comment}")

    # ---- position -> closing order comment -------------------------------
    # Deals: entry deal (opens) and exit deal(s).  Position id == first order id
    # in MT5 hedging mode.  Match exit deals by (order_id -> order.comment).
    deals_by_order = defaultdict(list)
    for d in deals:
        if d.order_id is not None:
            deals_by_order[d.order_id].append(d)

    # Build position -> exit order via the market/close order whose comment is a
    # closure marker and whose deal profit matches.  Simpler + exact route: the
    # closing deal of a position carries the SAME position id in MT5, but the
    # xlsx Deals sheet does not expose position id.  Instead use the *orders*
    # sheet: closure orders are non-grid market orders.  Pair them to positions
    # by (time == close_time) and (volume) and (opposite side).
    close_orders = [o for o in orders if not o.is_grid and o.order_type in
                    ("buy", "sell", "close by")]
    by_time = defaultdict(list)
    for o in close_orders:
        by_time[o.open_time].append(o)

    matched = 0
    unmatched = 0
    reason = Counter()
    reason_fr = Counter()
    pos_reason: dict[int, str] = {}
    for p in positions:
        if p.is_open or p.close_time is None:
            continue
        cands = by_time.get(p.close_time, [])
        want = "sell" if p.side == "buy" else "buy"
        pick = None
        for o in cands:
            if o.order_type == want and abs(o.volume - p.volume) < 1e-9:
                pick = o
                break
        if pick is None:
            for o in cands:
                if abs(o.volume - p.volume) < 1e-9:
                    pick = o
                    break
        if pick is None:
            unmatched += 1
            continue
        matched += 1
        r = cclass(pick.comment)
        reason[r] += 1
        pos_reason[p.position_id] = r
        if p.open_time >= FINAL_REGIME_START:
            reason_fr[r] += 1

    print(f"\n=== closure reason match: matched={matched} unmatched={unmatched} ===")
    print("ALL history:", dict(reason))
    print("FINAL regime:", dict(reason_fr))

    print("\n=== final-regime closures: sign of profit by reason ===")
    for r in sorted(reason_fr):
        wins = losses = zeros = 0
        for p in positions:
            if p.is_open or p.open_time < FINAL_REGIME_START:
                continue
            if pos_reason.get(p.position_id) != r:
                continue
            if p.net > 1e-9:
                wins += 1
            elif p.net < -1e-9:
                losses += 1
            else:
                zeros += 1
        print(f"  {r:<12} wins={wins:>5} losses={losses:>5} zero={zeros:>5}")

    # Also: do SL-closed positions have close_price == stop_loss?
    print("\n=== SL closure: close_price vs recorded stop_loss ===")
    diffs = []
    nosl = 0
    for p in positions:
        if pos_reason.get(p.position_id) != "[sl]":
            continue
        if p.stop_loss is None:
            nosl += 1
            continue
        diffs.append(abs((p.close_price or 0) - p.stop_loss))
    diffs.sort()
    print(f"n={len(diffs)} no_sl_recorded={nosl} max|diff|={diffs[-1] if diffs else 0}")
    print("quantiles:", [round(diffs[int(q*(len(diffs)-1))], 4)
                         for q in (0, .5, .9, .99, 1)] if diffs else None)


if __name__ == "__main__":
    main()
