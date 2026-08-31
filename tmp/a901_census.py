"""V10/V3 first pass: the comment vocabulary of the 901018 tape.

Everything the EA authored is fingerprinted by its order/deal comment, so the
distinct-shape census (digits collapsed to '#') is the cheapest possible test of
which code paths ever executed on this account.  In particular STR AVB/STR AVS
and STR ORB/STR ORS are the trend-rescue literals: if they are absent, the
rescue never fired here either, and JUNE_2K's trend_rescue_enabled=true is a
divergence rather than a faithful reproduction.
"""
from __future__ import annotations

import collections
import csv
import re
from pathlib import Path


def norm(value: str | None) -> str:
    return (value or "").strip()


def shape(value: str | None) -> str:
    text = norm(value)
    if not text:
        return "<empty>"
    return re.sub(r"[0-9]+", "#", text)


def main() -> int:
    orders = list(csv.DictReader(Path("tmp/r901018_orders.csv").open(encoding="utf-8")))
    deals = list(csv.DictReader(Path("tmp/r901018_deals.csv").open(encoding="utf-8")))
    positions = list(csv.DictReader(Path("tmp/r901018_positions.csv").open(encoding="utf-8")))
    print(f"orders={len(orders)} deals={len(deals)} positions={len(positions)}")
    print("order keys:", [k for k in orders[0] if k])
    print("deal  keys:", [k for k in deals[0] if k])
    print("pos   keys:", [k for k in positions[0] if k])
    print()

    for label, rowset in (("ORDERS", orders), ("DEALS", deals)):
        hist = collections.Counter(shape(row["Comment"]) for row in rowset)
        print(f"--- {label} comment shapes ({len(hist)} distinct) ---")
        for key, count in hist.most_common(40):
            print(f"  {count:7d}  {key!r}")
        print()

    print("--- trend-rescue literals ---")
    for token in ("STR AVB", "STR AVS", "STR ORB", "STR ORS"):
        in_orders = sum(1 for row in orders if token in norm(row["Comment"]))
        in_deals = sum(1 for row in deals if token in norm(row["Comment"]))
        print(f"  {token!r:10s} orders={in_orders} deals={in_deals}")
    print()

    print("--- order Type / State / filling census ---")
    for field in ("Type", "State"):
        hist = collections.Counter(norm(row[field]) for row in orders)
        print(f"  {field}: {dict(hist)}")
    print()

    print("--- order S/L and T/P occupancy (pendings must carry neither) ---")
    sl = collections.Counter(bool(norm(row["S / L"])) for row in orders)
    tp = collections.Counter(bool(norm(row["T / P"])) for row in orders)
    print(f"  S/L set: {sl[True]}  blank: {sl[False]}")
    print(f"  T/P set: {tp[True]}  blank: {tp[False]}")
    nonblank_sl = [row for row in orders if norm(row["S / L"])]
    for row in nonblank_sl[:10]:
        print(f"    SL-carrying order: {row['Order']} {row['Type']} {row['S / L']} {row['Comment']!r}")
    print()

    print("--- deal Type / Direction census ---")
    for field in ("Type", "Direction"):
        hist = collections.Counter(norm(row[field]) for row in deals)
        print(f"  {field}: {dict(hist)}")
    print()

    print("--- position volume census ---")
    hist = collections.Counter(norm(row["Volume"]) for row in positions)
    print(f"  {dict(sorted(hist.items()))}")
    print()

    print("--- position T/P occupancy (must be zero: the EA never sets TP) ---")
    tp_pos = collections.Counter(bool(norm(row["T / P"])) for row in positions)
    print(f"  T/P set: {tp_pos[True]}  blank: {tp_pos[False]}")
    print("--- position S/L occupancy ---")
    sl_pos = collections.Counter(bool(norm(row["S / L"])) for row in positions)
    print(f"  S/L set: {sl_pos[True]}  blank: {sl_pos[False]}")
    print()

    print("--- symbol census ---")
    print("  orders   :", dict(collections.Counter(norm(r["Symbol"]) for r in orders)))
    print("  positions:", dict(collections.Counter(norm(r["Symbol"]) for r in positions)))
    print("  deals    :", dict(collections.Counter(norm(r["Symbol"]) for r in deals)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
