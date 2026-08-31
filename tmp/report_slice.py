"""Slice the dumped MT5 report into its three tables and print their shapes.

Section index (from tmp/report_map.py):
    5      'Positions'      header 6      data 7      .. 17638
    17639  'Orders'         header 17640  data 17641  .. 72382
    72383  'Deals'          header 72384  data 72385  .. 107831
    107832 'Open Positions' 107841 'Working Orders' 107919 'Results'
Boundaries are re-derived here rather than hard-coded so a different export
still slices correctly.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

SECTIONS = ["Positions", "Orders", "Deals", "Open Positions", "Working Orders", "Results"]


def main() -> int:
    source = Path(sys.argv[1] if len(sys.argv) > 1 else "tmp/report_901018.csv")
    rows = list(csv.reader(source.open(encoding="utf-8")))
    marks: dict[str, int] = {}
    for index, row in enumerate(rows):
        cells = [c.strip() for c in row if c.strip()]
        if len(cells) == 1 and cells[0] in SECTIONS and cells[0] not in marks:
            marks[cells[0]] = index
    order = sorted(marks.items(), key=lambda kv: kv[1])
    print("sections:", order)
    print()

    for position, (name, start) in enumerate(order):
        end = order[position + 1][1] if position + 1 < len(order) else len(rows)
        header = [c.strip() for c in rows[start + 1]]
        body = rows[start + 2 : end]
        # drop trailing blank rows
        while body and not any(c.strip() for c in body[-1]):
            body.pop()
        print(f"=== {name}: header row {start+1}, {len(body)} data rows")
        print(f"    header: {[h for h in header if h]}")
        for sample in body[:2]:
            print(f"    row   : {sample}")
        if name in ("Positions", "Orders", "Deals"):
            out = Path(f"tmp/r901018_{name.lower().replace(' ', '_')}.csv")
            with out.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(header)
                writer.writerows(body)
            print(f"    -> wrote {out} ({len(body)} rows)")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
