"""Map the section structure of the dumped MT5 report CSV.

The dump is 107,932 rows because an MT5 "ReportHistory" workbook carries several
stacked tables (Positions / Orders / Deals) plus a long trailing block of chart
series data.  This prints every candidate section header and the first rows of
each so the real tables can be sliced by index.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

SECTION_WORDS = {
    "positions",
    "orders",
    "deals",
    "results",
    "summary",
    "balance",
    "working orders",
    "closed transactions",
    "open positions",
}


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "tmp/report_901018.csv")
    rows = list(csv.reader(path.open(encoding="utf-8")))
    print(f"rows={len(rows)}")
    widths = {}
    for row in rows:
        widths[len(row)] = widths.get(len(row), 0) + 1
    print("width histogram:", dict(sorted(widths.items())))
    print()
    print("--- candidate section headers (first non-empty cell matches) ---")
    for index, row in enumerate(rows):
        cells = [c.strip() for c in row if c.strip()]
        if not cells:
            continue
        first = cells[0].lower()
        if first in SECTION_WORDS or (len(cells) == 1 and len(first) < 40):
            print(f"{index:7d}  n={len(cells):2d}  {cells[:6]}")
    print()
    print("--- first 40 rows verbatim ---")
    for index, row in enumerate(rows[:40]):
        print(f"{index:5d}  {row}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
