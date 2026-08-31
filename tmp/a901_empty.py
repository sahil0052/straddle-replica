"""Prove what the 2,732 empty-comment market orders actually DID.

Era mapping already showed they live only in the HISTORICAL_50/HISTORICAL_60
windows and that 'STR CLOSE' lives only in the divisor windows -- perfectly
complementary, which says the two are one mechanism under two builds.  The
decisive test is the deal direction: a basket close produces DEAL_ENTRY_OUT
('out'), an opening trade produces 'in'.  This cross-tabs comment family against
direction for both orders and deals, and measures how completely each empty-comment
burst flattens the book.
"""
from __future__ import annotations

import collections
import csv
import re
from datetime import datetime
from pathlib import Path


def norm(value: str | None) -> str:
    return (value or "").strip()


def stamp(text: str) -> datetime | None:
    text = norm(text)
    if not text:
        return None
    for fmt in ("%Y.%m.%d %H:%M:%S.%f", "%Y.%m.%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def family(comment: str) -> str:
    comment = norm(comment)
    if not comment:
        return "<empty>"
    if comment.startswith("STR B"):
        return "STR B#"
    if comment.startswith("STR S"):
        return "STR S#"
    if comment.startswith("[sl"):
        return "[sl]"
    if re.match(r"^#\d+ by #\d+$", comment):
        return "close-by"
    return comment


def main() -> int:
    deals = list(csv.DictReader(Path("tmp/r901018_deals.csv").open(encoding="utf-8")))
    orders = list(csv.DictReader(Path("tmp/r901018_orders.csv").open(encoding="utf-8")))
    print("deal header:", [k for k in deals[0] if k])
    print()

    print("=== deal comment family x direction ===")
    table: collections.Counter = collections.Counter()
    for deal in deals:
        table[(family(deal["Comment"]), norm(deal["Direction"]))] += 1
    fams = sorted({k[0] for k in table})
    dirs = sorted({k[1] for k in table})
    print("  family        " + "".join(f"{d:>10s}" for d in dirs))
    for fam in fams:
        print(f"  {fam:14s}" + "".join(f"{table.get((fam,d),0):10d}" for d in dirs))
    print()

    # Link empty-comment market orders to their deals to read the direction.
    by_order: dict[str, list[dict]] = collections.defaultdict(list)
    for deal in deals:
        by_order[norm(deal["Order"])].append(deal)

    print("=== empty-comment MARKET orders -> deal direction ===")
    empties = [
        row for row in orders
        if not norm(row["Comment"]) and norm(row["Type"]) in ("buy", "sell")
    ]
    dir_hist: collections.Counter = collections.Counter()
    unlinked = 0
    for row in empties:
        related = by_order.get(norm(row["Order"]), [])
        if not related:
            unlinked += 1
            continue
        for deal in related:
            dir_hist[norm(deal["Direction"])] += 1
    print(f"  orders={len(empties)} unlinked={unlinked} directions={dict(dir_hist)}")
    print()

    print("=== 'STR CLOSE' MARKET orders -> deal direction, for comparison ===")
    closes = [row for row in orders if norm(row["Comment"]) == "STR CLOSE"]
    dir_hist2: collections.Counter = collections.Counter()
    for row in closes:
        for deal in by_order.get(norm(row["Order"]), []):
            dir_hist2[norm(deal["Direction"])] += 1
    print(f"  orders={len(closes)} directions={dict(dir_hist2)}")
    print()

    print("=== ORB/ORS/AVB/AVS -> deal direction ===")
    for token in ("STR ORB", "STR ORS", "STR AVB", "STR AVS"):
        hist: collections.Counter = collections.Counter()
        for row in [r for r in orders if norm(r["Comment"]) == token]:
            for deal in by_order.get(norm(row["Order"]), []):
                hist[norm(deal["Direction"])] += 1
        print(f"  {token:9s} {dict(hist)}")
    print()

    # Burst structure: an EA basket sweep closes many positions back-to-back.
    print("=== empty-comment burst structure (gap > 2 s starts a new burst) ===")
    stamps = sorted(w for w in (stamp(r["Open Time"]) for r in empties) if w)
    bursts: list[list[datetime]] = []
    for when in stamps:
        if bursts and (when - bursts[-1][-1]).total_seconds() > 2.0:
            bursts.append([when])
        else:
            if not bursts:
                bursts.append([])
            bursts[-1].append(when)
    sizes = collections.Counter(len(b) for b in bursts)
    print(f"  bursts={len(bursts)} size histogram={dict(sorted(sizes.items()))}")
    singles = sum(1 for b in bursts if len(b) == 1)
    print(f"  single-order bursts={singles} multi-order bursts={len(bursts)-singles}")
    print(f"  legs in multi-order bursts={sum(len(b) for b in bursts if len(b) > 1)}")
    print()

    print("=== 'STR CLOSE' burst structure, for comparison ===")
    cstamps = sorted(w for w in (stamp(r["Open Time"]) for r in closes) if w)
    cbursts: list[list[datetime]] = []
    for when in cstamps:
        if cbursts and (when - cbursts[-1][-1]).total_seconds() > 2.0:
            cbursts.append([when])
        else:
            if not cbursts:
                cbursts.append([])
            cbursts[-1].append(when)
    csizes = collections.Counter(len(b) for b in cbursts)
    print(f"  bursts={len(cbursts)} size histogram={dict(sorted(csizes.items()))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
