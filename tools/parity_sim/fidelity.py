"""Phase 0 fidelity check: verify the exported broker tick stream can explain
every order fill in the Target report.

For each entry deal in the final regime, find ticks within a +/- window of the
deal timestamp and check the deal price lies inside [min(bid), max(ask)]
(+/- one tick size) over that window. Reports coverage % and lists gaps so
affected cycles can be marked "bounded" instead of "exact".

Usage:
    python fidelity.py --ticks data/ticks-xauusd-jul14-30.csv.gz \
                       --report-dir tools/parity_sim/out
"""
from __future__ import annotations

import argparse
import bisect
import csv
import gzip
from datetime import datetime, timedelta

from report import load_entry_deals

TICK_SIZE = 0.01
WINDOW = timedelta(seconds=2)


def open_maybe_gz(path: str):
    if path.endswith(".gz"):
        return gzip.open(path, "rt")
    return open(path)


def load_ticks(path: str):
    """Return (times:list[datetime], bids:list[float], asks:list[float], gaps:list[datetime])."""
    times: list[datetime] = []
    bids: list[float] = []
    asks: list[float] = []
    gaps: list[datetime] = []
    with open_maybe_gz(path) as f:
        r = csv.reader(f)
        next(r)
        for row in r:
            if row[1] == "GAP":
                gaps.append(datetime.fromtimestamp(int(row[0]) / 1000.0))
                continue
            t = datetime.fromtimestamp(int(row[0]) / 1000.0)
            bid = float(row[1]) if row[1] else 0.0
            ask = float(row[2]) if row[2] else 0.0
            if bid <= 0.0 and ask <= 0.0:
                continue
            times.append(t)
            bids.append(bid if bid > 0 else ask)
            asks.append(ask if ask > 0 else bid)
    return times, bids, asks, gaps


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticks", required=True)
    ap.add_argument("--report-dir", default="tools/parity_sim/out")
    ap.add_argument("--out", default="tools/parity_sim/out/fidelity-report.txt")
    args = ap.parse_args()

    deals = load_entry_deals(f"{args.report_dir}/deals.csv")
    times, bids, asks, gaps = load_ticks(args.ticks)
    print(f"ticks loaded: {len(times):,}  report entry deals: {len(deals):,}  export gaps: {len(gaps)}")

    ok = 0
    misses = []
    uncovered = []
    for d in deals:
        lo = bisect.bisect_left(times, d.t - WINDOW)
        hi = bisect.bisect_right(times, d.t + WINDOW)
        if lo >= hi:
            uncovered.append(d)
            continue
        wmin = min(bids[lo:hi]) - TICK_SIZE
        wmax = max(asks[lo:hi]) + TICK_SIZE
        if wmin <= d.price <= wmax:
            ok += 1
        else:
            misses.append((d, wmin, wmax))

    total = len(deals)
    lines = [
        "PHASE 0 TICK FIDELITY REPORT",
        f"entry deals checked : {total}",
        f"explained by ticks  : {ok} ({100.0 * ok / total:.2f}%)",
        f"price mismatches    : {len(misses)}",
        f"no tick coverage    : {len(uncovered)}",
        f"export GAP markers  : {len(gaps)}",
        "",
    ]
    if misses:
        lines.append("MISMATCHES (deal outside tick window range):")
        for d, wmin, wmax in misses[:50]:
            lines.append(f"  {d.t} {d.side}{d.lvl} price={d.price} window=[{wmin:.2f},{wmax:.2f}]")
    if uncovered:
        lines.append("UNCOVERED DEALS (no ticks within +/-2s — mark cycle as bounded):")
        for d in uncovered[:50]:
            lines.append(f"  {d.t} {d.side}{d.lvl} price={d.price}")
    if gaps:
        lines.append("EXPORT GAPS:")
        for g in gaps[:50]:
            lines.append(f"  {g}")

    text = "\n".join(lines)
    print(text)
    with open(args.out, "w") as f:
        f.write(text + "\n")
    print(f"\nwritten: {args.out}")


if __name__ == "__main__":
    main()
