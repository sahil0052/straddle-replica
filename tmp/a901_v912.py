"""V11 - deal ledger & async trade reconciliation, measured on 901018.

Audits the real implementation (the directive's ReconcileHistoryDeals() does
not exist in the tree):
  QueueMissingHistoryDeals()      StraddleEngine.mqh:3579-3626
  ProcessPendingDeals()           StraddleEngine.mqh:3731-3748
  ProcessSelectedDeal()           StraddleEngine.mqh:3628-3729
  CCycleDealLedger::TryRecalculate()  CycleDealLedger.mqh:17-51
"""

from __future__ import annotations

import csv
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from a901_eras import norm, parse_level, parse_volume  # noqa: E402
from a901_v4578 import build_deployments, load_orders  # noqa: E402

FOOTER_NET = 17913.29
FOOTER_GROSS_PROFIT = 56855.93
FOOTER_GROSS_LOSS = -38942.64
FOOTER_OPEN_POSITIONS = 7
CAPACITY = 256
LOOKBACK_MS = 900000
INTERVAL_MS = 1000


def ts(text: str) -> datetime | None:
    text = norm(text)
    if not text:
        return None
    for fmt in ("%Y.%m.%d %H:%M:%S.%f", "%Y.%m.%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def money(text: str) -> float:
    text = norm(text).replace(" ", "").replace(",", "")
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def load_deals() -> list[dict]:
    path = Path("tmp/r901018_deals.csv")
    return list(csv.DictReader(path.open(encoding="utf-8")))


def load_positions() -> list[list[str]]:
    """Positions CSV has duplicate 'Time'/'Price' headers - index by column."""
    path = Path("tmp/r901018_positions.csv")
    rows = list(csv.reader(path.open(encoding="utf-8")))
    return [r for r in rows[1:] if len(r) >= 13 and norm(r[1]).isdigit()]


def pct(num: int, den: int) -> str:
    return "n/a" if den == 0 else f"{100.0 * num / den:.2f}%"


def part1_census(deals, positions, orders):
    print("=" * 72)
    print("PART 1  census and section integrity")
    print("=" * 72)
    print(f"deal rows            : {len(deals)}")
    print(f"position rows        : {len(positions)}")
    print(f"order rows           : {len(orders)}")

    tickets = Counter(norm(d["Deal"]) for d in deals)
    dupes = [t for t, c in tickets.items() if c > 1 and t]
    print(f"distinct deal tickets: {len(tickets)}  duplicated={len(dupes)}")

    xau = [d for d in deals if norm(d["Symbol"]) == "XAUUSD"]
    other = [d for d in deals if norm(d["Symbol"]) != "XAUUSD"]
    print(f"XAUUSD deals         : {len(xau)}   non-XAUUSD rows={len(other)}")
    for row in other:
        print(
            f"   non-XAUUSD: {norm(row['Time']):23} {norm(row['Type']):8}"
            f" profit={money(row['Profit']):>12,.2f} '{norm(row['Comment'])}'"
        )
    print(f"balance-row profit sum: {sum(money(r['Profit']) for r in other):,.2f}")
    entries = Counter(norm(d["Direction"]) for d in xau)
    print(f"XAUUSD direction census: {sorted(entries.items())}")
    return xau, other


def part2_money(xau):
    print()
    print("=" * 72)
    print("PART 2  money formula vs the report footer")
    print("     ProcessSelectedDeal()  StraddleEngine.mqh:3685-3691")
    print("     TryRecalculate()       CycleDealLedger.mqh:45-48")
    print("=" * 72)
    exits = [d for d in xau if norm(d["Direction"]) in ("out", "out by")]
    ins = [d for d in xau if norm(d["Direction"]) == "in"]
    print(f"exit deals (out|out by): {len(exits)}      in deals: {len(ins)}")

    terms = {}
    for key in ("Profit", "Swap", "Commission", "Fee"):
        terms[key] = (
            sum(1 for d in xau if money(d[key]) != 0.0),
            sum(money(d[key]) for d in xau),
        )
        print(f"   {key:11} nonzero={terms[key][0]:>6}  sum={terms[key][1]:>14,.2f}")

    four = sum(
        money(d["Profit"]) + money(d["Swap"]) + money(d["Commission"]) + money(d["Fee"])
        for d in xau
    )
    print(f"four-term sum over XAUUSD deals : {four:>14,.2f}")
    print(f"report footer Net               : {FOOTER_NET:>14,.2f}")
    print(f"delta                          : {four - FOOTER_NET:>14,.2f}")
    print(f"IDENTITY: {'MATCH' if abs(four - FOOTER_NET) < 0.005 else 'MISMATCH'}")

    gp = sum(v for v in (money(d["Profit"]) for d in xau) if v > 0)
    gl = sum(v for v in (money(d["Profit"]) for d in xau) if v < 0)
    print(f"deal-level gross profit/loss   : {gp:>12,.2f} / {gl:>12,.2f}")
    print(f"footer  gross profit/loss      : "
          f"{FOOTER_GROSS_PROFIT:>12,.2f} / {FOOTER_GROSS_LOSS:>12,.2f}")
    print(f"   gp delta={gp - FOOTER_GROSS_PROFIT:,.2f}"
          f"   gl delta={gl - FOOTER_GROSS_LOSS:,.2f}")
    unexercised = [k for k, (n, _) in terms.items() if n == 0]
    print(f"UNEXERCISED terms on this tape : {unexercised}")
    print(f"inout deals (DEAL_ENTRY_INOUT) : "
          f"{sum(1 for d in xau if norm(d['Direction']) == 'in/out')}")
    return exits, ins


def part3_fanout(xau, positions, exits, ins):
    print()
    print("=" * 72)
    print("PART 3  order -> deal fan-out (partial fills) and the position gap")
    print("     ledger is keyed on DEAL ticket  StraddleEngine.mqh:667")
    print("=" * 72)
    per_order = defaultdict(list)
    for row in xau:
        per_order[norm(row["Order"])].append(row)
    fan = Counter(len(v) for v in per_order.values())
    print(f"distinct order tickets in deals : {len(per_order)}")
    print(f"deals-per-order histogram       : {sorted(fan.items())}")
    extra = sum((n - 1) * c for n, c in fan.items())
    print(f"extra deals from multi-deal orders: {extra}")

    extra_in = sum(
        len(v) - 1 for v in per_order.values()
        if len(v) > 1 and all(norm(d["Direction"]) == "in" for d in v)
    )
    extra_out = sum(
        len(v) - 1 for v in per_order.values()
        if len(v) > 1 and all(norm(d["Direction"]) in ("out", "out by") for d in v)
    )
    mixed = sum(
        1 for v in per_order.values()
        if len(v) > 1 and len({norm(d["Direction"]) == "in" for d in v}) > 1
    )
    print(f"   extra IN  deals (partial fills)  : {extra_in}")
    print(f"   extra OUT deals (partial closes) : {extra_out}")
    print(f"   mixed-direction orders           : {mixed}")

    multi = {t for t, v in per_order.items() if len(v) > 1}
    outby = {norm(d["Order"]) for d in xau if norm(d["Direction"]) == "out by"}
    print(f"   'out by' deals={sum(1 for d in xau if norm(d['Direction']) == 'out by')}"
          f"  distinct orders={len(outby)}"
          f"  == the multi-deal orders? {outby == multi}")
    print("   -> a close-by order emits one deal per closed position, so a"
          " 2-deal order closes 2 positions (no extra exit).")

    print(f"closed positions (report)       : {len(positions)}")
    print(f"exit deals                      : {len(exits)}")
    print(f"   exits - closed positions     : {len(exits) - len(positions)}"
          f"   (predicted by extra_out={extra_out})")
    print(f"in deals                        : {len(ins)}")
    print(f"   in - closed - open({FOOTER_OPEN_POSITIONS})        : "
          f"{len(ins) - len(positions) - FOOTER_OPEN_POSITIONS}"
          f"   (predicted by extra_in={extra_in})")
    return per_order


def part4_bijection(xau, orders, per_order):
    print()
    print("=" * 72)
    print("PART 4  order <-> deal bijection integrity")
    print("=" * 72)
    order_index = {norm(o["Order"]): o for o in orders}
    print(f"orders in order section         : {len(order_index)}")
    orphan_deals = [t for t in per_order if t and t not in order_index]
    print(f"deal.Order not in order section : {len(orphan_deals)}"
          f"  {orphan_deals[:5]}")

    filled = [
        o for o in orders
        if norm(o["State"]).lower().startswith("filled")
        and norm(o["Symbol"]) == "XAUUSD"
    ]
    no_deal = [o for o in filled if norm(o["Order"]) not in per_order]
    print(f"filled orders                   : {len(filled)}")
    print(f"filled orders with zero deals   : {len(no_deal)}  "
          f"{[norm(o['Order']) for o in no_deal][:5]}")

    vol_bad = []
    for ticket, rows in per_order.items():
        order = order_index.get(ticket)
        if order is None:
            continue
        want = parse_volume(order["Volume"])
        got = sum(money(r["Volume"]) for r in rows)
        if abs(want - got) > 1e-9:
            vol_bad.append((ticket, want, got))
    print(f"volume(order.filled) == sum(deal.volume): "
          f"{len(per_order) - len(vol_bad)}/{len(per_order)}"
          f"  mismatches={len(vol_bad)}")
    for ticket, want, got in vol_bad[:5]:
        print(f"   mismatch order={ticket} filled={want} deals={got}")


def part2b_positions(positions):
    print()
    print("-" * 72)
    print("PART 2b  does the footer's gross split include swap? (position level)")
    print("-" * 72)
    vals = [money(r[12]) for r in positions]
    withswap = [money(r[12]) + money(r[11]) + money(r[10]) for r in positions]
    for label, series in (("profit only", vals), ("profit+swap+comm", withswap)):
        gp = sum(v for v in series if v > 0)
        gl = sum(v for v in series if v < 0)
        print(f"   {label:17} gp={gp:>12,.2f}  gl={gl:>12,.2f}"
              f"  net={gp + gl:>12,.2f}"
              f"  gp_delta={gp - FOOTER_GROSS_PROFIT:>9,.2f}"
              f"  gl_delta={gl - FOOTER_GROSS_LOSS:>9,.2f}")
    print(f"   position count {len(positions)}"
          f"   sum(profit+swap+comm)={sum(withswap):,.2f}"
          f"   footer Net={FOOTER_NET:,.2f}")


def part3b_join(xau, positions):
    print()
    print("-" * 72)
    print("PART 3b  IN-deal order ticket -> position ticket join")
    print("     MT5 hedging: POSITION_IDENTIFIER == opening order ticket")
    print("-" * 72)
    pos_tickets = {norm(r[1]) for r in positions}
    ins = [d for d in xau if norm(d["Direction"]) == "in"]
    matched = [d for d in ins if norm(d["Order"]) in pos_tickets]
    unmatched = [d for d in ins if norm(d["Order"]) not in pos_tickets]
    print(f"IN deals {len(ins)}   matched a closed position {len(matched)}"
          f"   unmatched {len(unmatched)}")
    print(f"position tickets never seen as an IN order: "
          f"{len(pos_tickets - {norm(d['Order']) for d in ins})}")
    if unmatched:
        times = sorted(ts(d["Time"]) for d in unmatched if ts(d["Time"]))
        print(f"unmatched IN span {times[0]} -> {times[-1]}")
        by_month = Counter(t.strftime("%Y-%m-%d") for t in times)
        print(f"unmatched IN by day (top 8): {by_month.most_common(8)}")
        lvl = Counter(norm(d["Comment"]) for d in unmatched)
        print(f"unmatched IN comments (top 6): {lvl.most_common(6)}")
        print("last 6 unmatched IN deals:")
        for d in sorted(unmatched, key=lambda r: ts(r["Time"]) or datetime.min)[-6:]:
            print(f"   {norm(d['Time']):23} deal={norm(d['Deal'])}"
                  f" order={norm(d['Order'])} vol={norm(d['Volume'])}"
                  f" '{norm(d['Comment'])}'")


def load_report_section(name: str) -> list[list[str]]:
    """Slice a named section out of the full dumped report."""
    path = Path("tmp/report_901018.csv")
    if not path.exists():
        return []
    rows = list(csv.reader(path.open(encoding="utf-8")))
    marks = []
    for index, row in enumerate(rows):
        cells = [c.strip() for c in row if c.strip()]
        if len(cells) == 1 and cells[0] in (
            "Positions", "Orders", "Deals",
            "Open Positions", "Working Orders", "Results",
        ):
            marks.append((cells[0], index))
    for position, (label, index) in enumerate(marks):
        if label != name:
            continue
        stop = marks[position + 1][1] if position + 1 < len(marks) else len(rows)
        body = rows[index + 1:stop]
        return [r for r in body if len(r) > 1 and norm(r[1]).isdigit()]
    return []


def part3c_open(xau, positions):
    print()
    print("-" * 72)
    print("PART 3c  volume conservation and the 'Open Positions' section")
    print("-" * 72)
    ins = [d for d in xau if norm(d["Direction"]) == "in"]
    exits = [d for d in xau if norm(d["Direction"]) in ("out", "out by")]
    vin = sum(money(d["Volume"]) for d in ins)
    vout = sum(money(d["Volume"]) for d in exits)
    print(f"volume in={vin:,.2f}  out={vout:,.2f}  residual={vin - vout:,.2f}")

    pos_tickets = {norm(r[1]) for r in positions}
    unmatched = [d for d in ins if norm(d["Order"]) not in pos_tickets]
    print(f"unmatched IN volume            : "
          f"{sum(money(d['Volume']) for d in unmatched):,.2f}"
          f"   (n={len(unmatched)})")

    openpos = load_report_section("Open Positions")
    print(f"'Open Positions' section rows  : {len(openpos)}")
    open_tickets = {norm(r[1]) for r in openpos}
    hit = [d for d in unmatched if norm(d["Order"]) in open_tickets]
    print(f"   of which matched an unmatched IN deal: {len(hit)}")
    for row in openpos:
        print(f"   open: {norm(row[0]):23} pos={norm(row[1])} {norm(row[3]):5}"
              f" vol={norm(row[4])} price={norm(row[5])} sl={norm(row[6])}")
    print(f"still unexplained IN deals     : {len(unmatched) - len(hit)}")

    order_index = {norm(o["Order"]): o for o in load_orders()}
    print("sample unexplained IN deals with their order row:")
    for deal in sorted(unmatched, key=lambda r: ts(r["Time"]) or datetime.min)[:6]:
        order = order_index.get(norm(deal["Order"]), {})
        print(f"   deal={norm(deal['Deal'])} {norm(deal['Time']):23}"
              f" vol={norm(deal['Volume'])} '{norm(deal['Comment'])}'"
              f" | order state='{norm(order.get('State', ''))}'"
              f" vol='{norm(order.get('Volume', ''))}'"
              f" placed={norm(order.get('Open Time', ''))}")


def part5_ordering(xau):
    print()
    print("=" * 72)
    print("PART 5  arrival ordering: is the count-monotone guard load-bearing?")
    print("     recompute-preferred guard  StraddleEngine.mqh:3678  (strict >)")
    print("=" * 72)
    rows = []
    for row in xau:
        when = ts(row["Time"])
        ticket = norm(row["Deal"])
        if when is None or not ticket.isdigit():
            continue
        rows.append((when, int(ticket), norm(row["Direction"])))
    rows.sort(key=lambda item: item[0])
    inversions = sum(
        1 for a, b in zip(rows, rows[1:])
        if b[0] > a[0] and b[1] < a[1]
    )
    print(f"deals with parsable time+ticket : {len(rows)}")
    print(f"time-ascending ticket inversions: {inversions}  "
          f"({pct(inversions, max(len(rows) - 1, 1))})")

    per_ms = Counter(item[0] for item in rows)
    ties = Counter(v for v in per_ms.values())
    print(f"deals-per-millisecond histogram : {sorted(ties.items())}")
    multi = sum(c for n, c in ties.items() if n > 1)
    print(f"milliseconds carrying >1 deal   : {multi}"
          f"   deals involved={sum(n * c for n, c in ties.items() if n > 1)}")
    exit_ms = Counter(item[0] for item in rows if item[2] in ("out", "out by"))
    exit_ties = Counter(v for v in exit_ms.values())
    print(f"EXIT deals-per-ms histogram     : {sorted(exit_ties.items())}")
    print("   -> simultaneous exits are the case where an incremental-only")
    print("      ledger would be order-sensitive; the absolute recompute is not.")


def part6_capacity(xau, deployments):
    print()
    print("=" * 72)
    print("PART 6  per-cycle deal load vs STR_PENDING_DEAL_CAPACITY / lookback")
    print("     capacity 256   interval 1000 ms   lookback 900000 ms")
    print("=" * 72)
    starts = [c["when"] for c in deployments]
    bounds = list(zip(starts, starts[1:] + [datetime(2099, 1, 1)]))
    rows = sorted(
        (ts(d["Time"]), norm(d["Direction"])) for d in xau if ts(d["Time"])
    )
    counts, exit_counts, spans = [], [], []
    for lo, hi in bounds:
        window = [r for r in rows if lo <= r[0] < hi]
        counts.append(len(window))
        exit_counts.append(sum(1 for r in window if r[1] in ("out", "out by")))
        if window:
            spans.append((window[-1][0] - lo).total_seconds())
    print(f"cycles                          : {len(bounds)}")
    print(f"deals per cycle   max={max(counts)}  p50={statistics.median(counts):.0f}"
          f"  over capacity({CAPACITY})={sum(1 for c in counts if c > CAPACITY)}")
    print(f"exits per cycle   max={max(exit_counts)}"
          f"  p50={statistics.median(exit_counts):.0f}")
    print(f"cycle deal-span s max={max(spans):,.1f}  p50={statistics.median(spans):,.1f}"
          f"  over lookback({LOOKBACK_MS // 1000}s)="
          f"{sum(1 for s in spans if s > LOOKBACK_MS / 1000.0)}")
    print(f"scans per second in-window      : {LOOKBACK_MS // INTERVAL_MS}x")


def part7_boundary(xau, deployments):
    print()
    print("=" * 72)
    print("PART 7  cycle-boundary second-flooring exposure")
    print("     m_cycle_started_msc=(long)m_cycle_started_at*1000"
          "  StraddleEngine.mqh:1869/2031")
    print("=" * 72)
    exits = sorted(
        ts(d["Time"]) for d in xau
        if norm(d["Direction"]) in ("out", "out by") and ts(d["Time"])
    )
    gaps, same_second = [], 0
    for cluster in deployments:
        start = cluster["when"]
        prior = [e for e in exits if e < start]
        if not prior:
            continue
        gap = (start - prior[-1]).total_seconds()
        gaps.append(gap)
        if prior[-1].replace(microsecond=0) == start.replace(microsecond=0):
            same_second += 1
    print(f"cycle starts with a prior exit  : {len(gaps)}")
    print(f"gap last-exit -> next start (s) : min={min(gaps):.3f}"
          f"  p50={statistics.median(gaps):.3f}  max={max(gaps):,.1f}")
    print(f"under 1.000 s                   : {sum(1 for g in gaps if g < 1.0)}")
    print(f"SAME WHOLE SECOND (leak window) : {same_second}"
          f"  ({pct(same_second, len(gaps))})")


def main() -> int:
    orders = load_orders()
    deals = load_deals()
    positions = load_positions()
    deployments = build_deployments(orders)
    xau, _ = part1_census(deals, positions, orders)
    exits, ins = part2_money(xau)
    part2b_positions(positions)
    per_order = part3_fanout(xau, positions, exits, ins)
    part3b_join(xau, positions)
    part3c_open(xau, positions)
    part4_bijection(xau, orders, per_order)
    part5_ordering(xau)
    part6_capacity(xau, deployments)
    part7_boundary(xau, deployments)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
