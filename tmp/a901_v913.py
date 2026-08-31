"""PART 3d - adjudicate the 166 IN deals that match no position row.

The workbook tail (tmp/out_tail.txt) shows the account block:
    Balance 19673.02   Margin 8.19   Floating P/L -23.57   Equity 19649.45
and an 'Open Positions' block of exactly 6 rows totalling 0.06 lots / -23.57.

So the 166 unmatched IN deals carry 14.13 lots that are neither closed
(no row in 'Positions') nor open (not in 'Open Positions', not in Margin).
Two scenarios remain:
  (a) their exit deals are ABSENT from the Deals block, or
  (b) their exits ARE among the 17,638 exit deals and the Positions block is
      missing 166 rows.
Sum of closed-position volume decides: if it equals total exit volume, every
exit deal is consumed by a listed position and (b) is refuted.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from a901_eras import norm  # noqa: E402
from a901_v912 import load_deals, load_positions, money, ts  # noqa: E402


def main() -> int:
    positions = load_positions()
    xau = [d for d in load_deals() if norm(d["Symbol"]) == "XAUUSD"]
    ins = [d for d in xau if norm(d["Direction"]) == "in"]
    exits = [d for d in xau if norm(d["Direction"]) in ("out", "out by")]

    pos_vol = sum(money(r[4]) for r in positions)
    out_vol = sum(money(d["Volume"]) for d in exits)
    in_vol = sum(money(d["Volume"]) for d in ins)
    print("=" * 72)
    print("PART 3d  is any exit deal unconsumed by a listed closed position?")
    print("=" * 72)
    print(f"closed positions   n={len(positions):6}  volume={pos_vol:10,.2f}")
    print(f"exit deals         n={len(exits):6}  volume={out_vol:10,.2f}")
    print(f"IN deals           n={len(ins):6}  volume={in_vol:10,.2f}")
    print(f"exit - closed volume delta         : {out_vol - pos_vol:,.4f}")
    print(f"VERDICT: {'every exit deal is consumed by a listed position'
                     if abs(out_vol - pos_vol) < 1e-9
                     else 'exit volume exceeds listed positions - (b) alive'}")

    pos_tickets = {norm(r[1]) for r in positions}
    open_tickets = {"20961468", "20961470", "20961473", "20961475",
                    "20961477", "20961723"}
    ghosts = [
        d for d in ins
        if norm(d["Order"]) not in pos_tickets
        and norm(d["Order"]) not in open_tickets
    ]
    print()
    print(f"ghost IN deals (no closed row, not open): {len(ghosts)}")
    print(f"   volume                              : "
          f"{sum(money(d['Volume']) for d in ghosts):,.2f}")
    for key in ("Profit", "Swap", "Commission", "Fee"):
        nz = sum(1 for d in ghosts if money(d[key]) != 0.0)
        print(f"   {key:11} nonzero={nz:>4}"
              f"  sum={sum(money(d[key]) for d in ghosts):>10,.2f}")

    print()
    print("ghost volume tiers  :",
          sorted(Counter(norm(d["Volume"]) for d in ghosts).items()))
    print("ghost side census   :",
          sorted(Counter(norm(d["Type"]) for d in ghosts).items()))
    print("ghost per-day count :",
          sorted(Counter((ts(d["Time"]) or "").strftime("%Y-%m-%d")
                         for d in ghosts).items()))

    print()
    print("does the Balance column move across a ghost row? (balance is only")
    print("written by realised deals, so a ghost must leave it unchanged)")
    rows = sorted(
        ((ts(d["Time"]), norm(d["Deal"]), norm(d["Direction"]),
          money(d["Balance"]) if "Balance" in d else 0.0) for d in xau
         if ts(d["Time"])),
        key=lambda item: item[0],
    )
    ghost_ids = {norm(d["Deal"]) for d in ghosts}
    moved = 0
    for previous, current in zip(rows, rows[1:]):
        if current[1] in ghost_ids and abs(current[3] - previous[3]) > 1e-9:
            moved += 1
    print(f"   ghost rows that moved Balance    : {moved} of {len(ghosts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
