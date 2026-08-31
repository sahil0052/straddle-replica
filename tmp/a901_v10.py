"""V10: the four non-lattice market-order families on the 901018 tape.

Our EA has exactly one market-open call site (StraddleEngine.mqh:1574, inside
PlaceLevel's crossed-price branch) and it emits STR ORB / STR ORS.  It has NO
code path that emits STR AVB / STR AVS -- those literals appear only in
EventSide()'s classifier at StraddleEngine.mqh:1193-1198.  This dumps every
occurrence of all four, plus the empty-comment market orders, so each family can
be attributed.
"""
from __future__ import annotations

import collections
import csv
from pathlib import Path


def load(name: str) -> list[dict]:
    return list(csv.DictReader(Path(f"tmp/r901018_{name}.csv").open(encoding="utf-8")))


def norm(value: str | None) -> str:
    return (value or "").strip()


def main() -> int:
    orders = load("orders")
    deals = load("deals")
    by_order = collections.defaultdict(list)
    for deal in deals:
        by_order[norm(deal["Order"])].append(deal)

    for token in ("STR ORB", "STR ORS", "STR AVB", "STR AVS"):
        hits = [row for row in orders if norm(row["Comment"]) == token]
        print(f"=== {token}: {len(hits)} orders ===")
        for row in hits:
            related = by_order.get(norm(row["Order"]), [])
            entries = ",".join(
                f"{norm(d['Direction'])}/{norm(d['Type'])}/{norm(d['Volume'])}@{norm(d['Price'])}"
                for d in related
            )
            print(
                f"  {norm(row['Open Time'])}  ord={norm(row['Order'])} "
                f"{norm(row['Type']):9s} vol={norm(row['Volume']):12s} "
                f"px={norm(row['Price']):9s} state={norm(row['State']):8s} "
                f"filled={norm(row['Time'])}  deals[{entries}]"
            )
        print()

    print("=== empty-comment orders: type/state breakdown ===")
    blanks = [row for row in orders if not norm(row["Comment"])]
    print(collections.Counter((norm(r["Type"]), norm(r["State"])) for r in blanks))
    print(f"volume histogram: {dict(sorted(collections.Counter(norm(r['Volume']) for r in blanks).items()))}")
    print("first 15:")
    for row in blanks[:15]:
        print(
            f"  {norm(row['Open Time'])} ord={norm(row['Order'])} {norm(row['Type']):5s} "
            f"vol={norm(row['Volume']):12s} px={norm(row['Price']):9s} "
            f"state={norm(row['State'])} filled={norm(row['Time'])}"
        )
    print("last 5:")
    for row in blanks[-5:]:
        print(
            f"  {norm(row['Open Time'])} ord={norm(row['Order'])} {norm(row['Type']):5s} "
            f"vol={norm(row['Volume']):12s} px={norm(row['Price']):9s} "
            f"state={norm(row['State'])} filled={norm(row['Time'])}"
        )
    print()
    daily = collections.Counter(norm(r["Open Time"])[:10] for r in blanks)
    print("empty-comment orders per day:")
    for day, count in sorted(daily.items()):
        print(f"  {day}  {count}")
    print()
    print("=== 'close by' orders ===")
    for row in [r for r in orders if norm(r["Type"]) == "close by"]:
        print(
            f"  {norm(row['Open Time'])} ord={norm(row['Order'])} vol={norm(row['Volume'])} "
            f"px={norm(row['Price'])} state={norm(row['State'])} cmt={norm(row['Comment'])!r}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
