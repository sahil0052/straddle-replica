"""Dump the trailing blocks of the 901018 workbook verbatim.

PART 3c left 166 IN deals with no exit deal and no row in either the closed
'Positions' table or the 'Open Positions' block.  Before attributing that to
an EA behaviour it has to be shown whether the workbook itself accounts for
them, so print the tail blocks ('Open Positions', 'Working Orders', 'Results')
exactly as exported.
"""

from __future__ import annotations

import csv
from pathlib import Path


def main() -> int:
    rows = list(csv.reader(Path("tmp/report_901018.csv").open(encoding="utf-8")))
    print(f"total rows={len(rows)}")
    for index in range(107825, len(rows)):
        cells = [c.strip() for c in rows[index]]
        while cells and not cells[-1]:
            cells.pop()
        print(f"{index:6} | " + " | ".join(cells))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
