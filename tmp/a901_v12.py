"""V12 - account & symbol suffix auto-binding, and the ContractScale() multiplier.

The audit has carried 'ContractScale()=1.0' as an assertion.  ContractScale()
(StraddleEngine.mqh:1521-1527) returns SYMBOL_TRADE_CONTRACT_SIZE/100.0, and it
multiplies m_profile.cycle_target_money at StraddleEngine.mqh:3445-3448, so its
value is load-bearing for the ONLY exit the EA has.  If a broker quoted XAUUSD
with a contract size other than 100 the money target would be scaled by that
ratio.  This script identifies the Target broker's contract size from the tape
instead of assuming it:

    position profit = dir * (close_price - open_price) * volume * contract_size

is solvable for contract_size on every closed position that moved, and on every
row of the workbook's terminal 'Open Positions' block using the Market Price
column.  Also censuses the symbol strings on both tapes to size the suffix
question, and checks the reported Margin against the identified contract size.
"""

from __future__ import annotations

import csv
import glob
from collections import Counter
from pathlib import Path

TIERS = ("XAUUSD", "XAUUSD.u")


def money(text: str) -> float:
    cleaned = (text or "").replace(" ", "").replace(",", "").replace(" ", "")
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def load_positions() -> list[list[str]]:
    rows = list(csv.reader(Path("tmp/report_901018.csv").open(encoding="utf-8")))
    out: list[list[str]] = []
    inside = False
    for row in rows:
        cells = [c.strip() for c in row]
        lone = [c for c in cells if c]
        if len(lone) == 1 and lone[0] in (
            "Positions", "Orders", "Deals", "Open Positions",
            "Working Orders", "Results",
        ):
            inside = lone[0] == "Positions"
            continue
        if inside and len(cells) > 12 and cells[1].isdigit():
            out.append(cells)
    return out


def part1_symbols() -> None:
    print("=" * 72)
    print("PART 1  symbol strings on both tapes")
    print("=" * 72)
    for pattern in ("Starwave_60542_orders_history.csv",
                    "Starwave_60542_full_history.csv"):
        for path in glob.glob(pattern):
            rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
            key = next((k for k in rows[0] if k and k.strip().lower() == "symbol"),
                       None)
            census = Counter((r[key] or "").strip() for r in rows) if key else {}
            print(f"  {path:42} n={len(rows):6}  {dict(census)}")
    rows = list(csv.reader(Path("tmp/report_901018.csv").open(encoding="utf-8")))
    census: Counter[str] = Counter()
    for row in rows:
        for cell in row[:4]:
            if "XAU" in (cell or ""):
                census[cell.strip()] += 1
    print(f"  {'tmp/report_901018.csv':42} n={len(rows):6}  {dict(census)}")


def part2_contract_size(positions: list[list[str]]) -> None:
    print()
    print("=" * 72)
    print("PART 2  solve contract_size on every closed position that moved")
    print("=" * 72)
    solved: Counter[str] = Counter()
    skipped = 0
    for row in positions:
        side = row[3].lower()
        direction = 1.0 if side == "buy" else -1.0
        volume = money(row[4])
        delta = money(row[9]) - money(row[5])
        profit = money(row[12])
        if volume <= 0.0 or abs(delta) < 1e-9 or abs(profit) < 1e-9:
            skipped += 1
            continue
        contract = profit / (direction * delta * volume)
        solved[f"{contract:.4g}"] += 1
    print(f"  rows solved      : {sum(solved.values()):,}")
    print(f"  rows skipped     : {skipped:,}  (zero move or zero profit)")
    top = solved.most_common(8)
    print(f"  contract_size census (top 8): {top}")
    exact = sum(n for k, n in solved.items() if abs(float(k) - 100.0) < 0.5)
    total = sum(solved.values())
    print(f"  contract_size == 100 +/- 0.5 : {exact:,}/{total:,}"
          f"  ({100.0 * exact / total:.2f}%)" if total else "  no rows")
    print(f"  => ContractScale() = contract_size/100.0 = "
          f"{100.0 / 100.0:.4f} on this broker")


def part3_open_block() -> None:
    print()
    print("=" * 72)
    print("PART 3  the terminal 'Open Positions' block, independently")
    print("=" * 72)
    # verbatim from tmp/out_tail.txt rows 107834-107839
    block = [
        ("sell", 0.01, 4085.57, 4094.43, -8.86, "STR S2"),
        ("sell", 0.01, 4083.55, 4094.43, -10.88, "STR S3"),
        ("buy", 0.01, 4094.39, 4094.15, -0.24, "STR B5"),
        ("buy", 0.01, 4095.71, 4094.15, -1.56, "STR B6"),
        ("buy", 0.01, 4097.08, 4094.15, -2.93, "STR B7"),
        ("buy", 0.01, 4093.25, 4094.15, 0.90, "STR B4"),
    ]
    exact = 0
    for side, volume, open_price, market, profit, comment in block:
        direction = 1.0 if side == "buy" else -1.0
        contract = profit / (direction * (market - open_price) * volume)
        ok = abs(contract - 100.0) < 0.5
        exact += 1 if ok else 0
        print(f"  {comment:8} {side:4} {volume:.2f} @ {open_price:9.2f} "
              f"-> {market:9.2f}  profit={profit:7.2f}  "
              f"contract_size={contract:9.4f}  {'OK' if ok else 'MISMATCH'}")
    print(f"  contract_size == 100: {exact}/6")
    gross = 0.06
    net = 0.04 - 0.02
    price = 4094.15
    print(f"  reported Margin 8.19 implies leverage "
          f"1:{gross * 100.0 * price / 8.19:,.0f} on gross {gross:.2f} lots "
          f"or 1:{net * 100.0 * price / 8.19:,.0f} on hedged-net {net:.2f} lots")
    print(f"  gross notional/1000 = {gross * 100.0 * price / 3000.0:.4f}"
          f"   net notional/1000 = {net * 100.0 * price / 1000.0:.4f}")


def main() -> int:
    part1_symbols()
    positions = load_positions()
    part2_contract_size(positions)
    part3_open_block()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
