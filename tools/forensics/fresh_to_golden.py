"""Rewrite 111638511's API dump into the Target's golden-CSV schema.

WHY THIS EXISTS -- and why it is worth more than any bespoke comparison script.

The Target EA's entire body of evidence lives in .cache/golden/ as six CSVs, and
seventy-odd forensic scripts in this directory read them through one loader,
tools/forensics/dataset.py.  q1_trailing measures the ratchet.  q3_basket
measures the $30 exit.  ratchet_edges, attested_stop, q3o/q3p, q4a..q4f all sit
on the same foundation.  Every one of those measurements was previously
impossible on 111638511 for a single reason: the only instrument we had for our
own account was the terminal's Trades-category log, which records fills and
nothing else -- no stop-loss, no profit, no closure reason.

The master-password API session removed that limit.  artifacts/live/mt5api/ now
holds the account's full deal history with per-deal profit and a REASON enum, the
full order history with the SL each order carried, the live SL of every open
position, and the resting ladder.  That is strictly more than the Target's XLSX
export contains.

So the leverage is obvious: do not write a new comparison.  Translate our data
into the schema the existing toolchain already reads, point dataset.py at it with
one environment variable, and the whole Target-side battery runs on our account
unmodified.  One adapter unlocks seventy scripts.

THE FOUR TRANSLATIONS THAT ARE NOT MECHANICAL:

 1. POSITIONS.  The API has no position table for closed positions -- MT5 keeps
    deals.  A hedging-mode position is exactly one entry=IN deal and one
    entry=OUT deal sharing a position_id.  open_price/volume/side/comment come
    from the IN deal; close_price/close_time from the OUT deal; profit,
    commission and swap are summed over both because MT5 books them on either
    leg depending on broker.

 2. STOP LOSS, for closed positions.  Nothing in the deal record carries the
    stop price.  But when the stop is what closed the position, the server
    stamps it into the OUT deal's comment as "[sl 4648.97]" -- and 107 of our
    149 closes carry exactly that.  This is the SAME instrument the Target XLSX
    exposes ("sl 4135.53" in its Comment column), so the ratchet is measured
    from the same kind of evidence on both sides, not from two different proxies.
    A position closed by the basket flatten has no SL text and gets an empty
    stop_loss, which is honest: the stop existed but its last value is not
    recoverable from history.  positions_get is what recovers it for the ones
    still open.

 3. ORDER TYPE / STATE vocabulary.  Golden uses the XLSX's lowercase words --
    "buy stop", "sell stop", "buy", "sell", "filled", "canceled", "placed" --
    not the API's BUY_STOP / FILLED enums.  Mapping them rather than teaching
    dataset.py a second vocabulary keeps the loader untouched.

 4. TIME BASE.  The API's integer timestamps are true UTC epochs; datetime
    .fromtimestamp on this PC yields IST, which is what the terminal log shows.
    The Target's golden CSVs are in SERVER time, and server = UTC+3 (EEST).
    Since every parity statistic is either within one stream or a rate, the
    convention only affects labels -- but if the two streams are ever put on one
    axis, mismatched clocks silently corrupt the picture.  So everything is
    emitted in server time and the offset is printed, not assumed.

FILTERING.  The account's opening $20,000 credit is a deal_type=balance row with
no symbol and no position; it is carried into deals.csv exactly as the Target's
four balance rows are, and ignored everywhere else by construction.

OUTPUT.  .cache/fresh/ -- deliberately a sibling of .cache/golden/ and never a
replacement for it, so no script can read our account's data believing it to be
the Target's.
"""
from __future__ import annotations

import csv
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.environ.get("FRESH_SRC") or os.path.join(ROOT, "artifacts", "live", "mt5api")
DST = os.environ.get("FRESH_DST") or os.path.join(ROOT, ".cache", "fresh")

# ZERO, and that is a correction.  This used to be timedelta(hours=3) on the
# reasoning "server = UTC+3, and the API returns UTC".  Only the first half is
# true.  srv() below builds datetime(1970,1,1) + seconds, which is
# utcfromtimestamp -- and utcfromtimestamp of an MT5 epoch ALREADY yields the
# server wall clock, because MT5 stores server time in that integer, not UTC.
# Proof, taken from two brokers on two different server zones:
#
#   111638511  ticket 10199270833  terminal shows 2026.08.26 01:00:02
#              fromtimestamp -> 06:30:02 IST  =>  utcfromtimestamp -> 01:00:02  OK
#   25954110    ticket 1859686471  terminal shows 2026.08.26 13:27:13
#              fromtimestamp -> 18:57:13 IST  =>  utcfromtimestamp -> 13:27:13  OK
#
# Adding 3 h on top pushed every .cache/fresh timestamp 3 hours into the future.
# A constant shift leaves every interval statistic untouched, which is why it
# went unnoticed, but it corrupts any absolute-time or regime-boundary comparison
# against .cache/golden.
SERVER_OFFSET = timedelta(0)

# API enum name -> golden vocabulary.
ORDER_TYPE_WORD = {
    "BUY": "buy", "SELL": "sell",
    "BUY_STOP": "buy stop", "SELL_STOP": "sell stop",
    "BUY_LIMIT": "buy limit", "SELL_LIMIT": "sell limit",
    "CLOSE_BY": "close by",
}
ORDER_STATE_WORD = {
    "FILLED": "filled", "CANCELED": "canceled", "PLACED": "placed",
    "PARTIAL": "partial", "REJECTED": "rejected", "EXPIRED": "expired",
    "STARTED": "started",
}
DEAL_TYPE_WORD = {"BUY": "buy", "SELL": "sell", "BALANCE": "balance"}
DEAL_ENTRY_WORD = {"IN": "in", "OUT": "out", "OUT_BY": "out by", "INOUT": "in/out"}

# The server stamps the triggering stop into the closing deal's comment.  Both
# "[sl 4648.97]" and the bare "sl 4648.97" form are accepted because the two
# appear in different broker builds -- the Target XLSX uses the bare form.
RE_SL = re.compile(r"\[?\bsl\s+([0-9]+(?:\.[0-9]+)?)\]?", re.I)
RE_TP = re.compile(r"\[?\btp\s+([0-9]+(?:\.[0-9]+)?)\]?", re.I)

ORDERS_HDR = ["row", "open_time", "order_id", "symbol", "order_type", "volume",
              "filled_volume", "price", "stop_loss", "take_profit", "end_time",
              "state", "comment"]
POS_HDR = ["row", "open_time", "position_id", "symbol", "side", "volume",
           "open_price", "stop_loss", "take_profit", "close_time",
           "close_price", "commission", "swap", "profit", "comment"]
DEAL_HDR = ["row", "time", "deal_id", "symbol", "deal_type", "direction",
            "volume", "price", "order_id", "commission", "fee", "swap",
            "profit", "balance", "comment"]


def rule(t: str) -> None:
    print()
    print("=" * 100)
    print(t)
    print("=" * 100)


def rd(name: str) -> list[dict]:
    p = os.path.join(SRC, name + ".csv")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def srv(epoch: float) -> datetime:
    """MT5 epoch -> server wall clock, the base the golden CSVs are written in.

    No conversion: an MT5 timestamp interpreted as if it were UTC already IS the
    broker's server clock.  See the SERVER_OFFSET note above.
    """
    return datetime(1970, 1, 1) + timedelta(seconds=float(epoch)) + SERVER_OFFSET


def ts(dt: datetime | None) -> str:
    return "" if dt is None else dt.strftime("%Y-%m-%d %H:%M:%S.%f")


def num(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def price_or_blank(v) -> str:
    """Golden writes an unset SL/TP as an empty cell, not as 0.0."""
    f = num(v)
    return "" if f <= 0.0 else f"{f:g}"


def wr(name: str, hdr: list[str], rows: list[dict]) -> str:
    os.makedirs(DST, exist_ok=True)
    p = os.path.join(DST, name + ".csv")
    with open(p, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=hdr, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    return p


def main() -> None:
    deals = rd("deals")
    hords = rd("history_orders")
    open_pos = rd("positions")
    work_ord = rd("orders")
    if not deals:
        print(f"  no deals at {SRC}; run fresh_api_pull.py first")
        sys.exit(2)

    rule("SOURCE")
    print(f"  {SRC}")
    print(f"  deals {len(deals)}   history_orders {len(hords)}"
          f"   open positions {len(open_pos)}   resting orders {len(work_ord)}")
    t0 = srv(min(num(d['time']) for d in deals))
    t1 = srv(max(num(d['time']) for d in deals))
    print(f"  span (server time) {t0:%Y-%m-%d %H:%M:%S} .. {t1:%Y-%m-%d %H:%M:%S}")
    print("  time base: broker server clock, taken straight from the MT5 epoch"
          " (offset applied: "
          f"{int(SERVER_OFFSET.total_seconds())}s)")

    # ------------------------------------------------------------------- deals
    rule("deals.csv")
    drows = []
    running = 0.0
    for i, d in enumerate(sorted(deals, key=lambda x: num(x["time_msc"])), start=1):
        running += num(d["profit"]) + num(d["commission"]) + num(d["swap"])
        drows.append({
            "row": i,
            "time": ts(srv(num(d["time_msc"]) / 1000.0)),
            "deal_id": d["ticket"],
            "symbol": d["symbol"],
            "deal_type": DEAL_TYPE_WORD.get(d["type_name"], d["type_name"].lower()),
            "direction": DEAL_ENTRY_WORD.get(d["entry_name"], "")
                         if d["type_name"] != "BALANCE" else "",
            "volume": f"{num(d['volume']):g}",
            "price": price_or_blank(d["price"]),
            "order_id": d["order"] if d["order"] not in ("", "0") else "",
            "commission": f"{num(d['commission']):g}",
            "fee": f"{num(d['fee']):g}",
            "swap": f"{num(d['swap']):g}",
            "profit": f"{num(d['profit']):g}",
            "balance": f"{running:g}",
            "comment": d["comment"],
        })
    print(f"  {len(drows)} rows -> {wr('deals', DEAL_HDR, drows)}")
    print("  deal_type :", dict(Counter(r["deal_type"] for r in drows)))
    print("  direction :", dict(Counter(r["direction"] or "(blank)" for r in drows)))

    # --------------------------------------------------------------- positions
    rule("positions.csv  (IN deal + OUT deal joined on position_id)")
    by_pos: dict[str, list[dict]] = defaultdict(list)
    for d in deals:
        if d["type_name"] == "BALANCE":
            continue
        by_pos[d["position_id"]].append(d)

    prows, unmatched, sl_found, closed = [], 0, 0, 0
    for pid, legs in by_pos.items():
        legs.sort(key=lambda x: num(x["time_msc"]))
        ins = [x for x in legs if x["entry_name"] == "IN"]
        outs = [x for x in legs if x["entry_name"] in ("OUT", "OUT_BY")]
        if not ins:
            unmatched += 1
            continue
        a = ins[0]
        b = outs[-1] if outs else None
        stop = ""
        if b is not None:
            closed += 1
            m = RE_SL.search(b["comment"] or "")
            if m:
                stop = m.group(1)
                sl_found += 1
        prows.append({
            "row": 0,
            "open_time": ts(srv(num(a["time_msc"]) / 1000.0)),
            "position_id": pid,
            "symbol": a["symbol"],
            "side": "buy" if a["type_name"] == "BUY" else "sell",
            "volume": f"{num(a['volume']):g}",
            "open_price": f"{num(a['price']):g}",
            "stop_loss": stop,
            "take_profit": "",
            "close_time": ts(srv(num(b["time_msc"]) / 1000.0)) if b else "",
            "close_price": f"{num(b['price']):g}" if b else "",
            "commission": f"{sum(num(x['commission']) for x in legs):g}",
            "swap": f"{sum(num(x['swap']) for x in legs):g}",
            "profit": f"{sum(num(x['profit']) for x in legs):g}",
            "comment": a["comment"],
            "_reason": (b["reason_name"] if b else ""),
            "_open": b is None,
        })
    prows.sort(key=lambda r: r["open_time"])
    for i, r in enumerate(prows, start=1):
        r["row"] = i

    closed_rows = [r for r in prows if not r["_open"]]
    open_rows = [r for r in prows if r["_open"]]
    print(f"  {len(by_pos)} position_id group(s)   unmatched(no IN) {unmatched}")
    print(f"  closed {len(closed_rows)}   still open {len(open_rows)}")
    print(f"  stop price recovered from OUT-deal comment: {sl_found}/{closed}"
          f" = {100.0 * sl_found / max(closed, 1):.1f}%")
    print("  close reason :", dict(Counter(r["_reason"] for r in closed_rows)))
    print(f"  {len(closed_rows)} rows -> {wr('positions', POS_HDR, closed_rows)}")

    # ----------------------------------------------------------- open_positions
    rule("open_positions.csv  (live SL straight from positions_get -- the ratchet)")
    # These come from the LIVE table, not from deals, because that is the only
    # place the current stop of a still-open position exists.  Fall back to the
    # deal-derived row if a position is somehow missing from the live snapshot.
    live_by_id = {p["ticket"]: p for p in open_pos}
    orows = []
    for r in open_rows:
        p = live_by_id.get(r["position_id"])
        if p is not None:
            r = dict(r)
            r["stop_loss"] = price_or_blank(p["sl"])
            r["take_profit"] = price_or_blank(p["tp"])
            r["close_price"] = f"{num(p['price_current']):g}"
            r["profit"] = f"{num(p['profit']):g}"
        orows.append(r)
    orows.sort(key=lambda r: r["open_time"])
    print(f"  {len(orows)} open position(s); "
          f"{sum(1 for r in orows if r['stop_loss'])} carry an SL right now")
    for r in orows:
        print(f"    {r['open_time'][:19]}  {r['side']:>4} {r['volume']:>5}"
              f" @ {r['open_price']:>9}  sl={r['stop_loss'] or '-':>9}"
              f"  {r['comment']}")
    print(f"  -> {wr('open_positions', POS_HDR, orows)}")

    # ------------------------------------------------------------------ orders
    rule("orders.csv  (order history)")
    orders_rows = []
    for i, o in enumerate(sorted(hords, key=lambda x: num(x["time_setup_msc"])),
                          start=1):
        state = ORDER_STATE_WORD.get(o["state_name"], o["state_name"].lower())
        vi = num(o["volume_initial"])
        orders_rows.append({
            "row": i,
            "open_time": ts(srv(num(o["time_setup_msc"]) / 1000.0)),
            "order_id": o["ticket"],
            "symbol": o["symbol"],
            "order_type": ORDER_TYPE_WORD.get(o["type_name"], o["type_name"].lower()),
            "volume": f"{vi:g}",
            # Golden's filled_volume is the executed quantity: equal to volume on
            # a filled order, 0.0 on a cancel.  volume_current is the REMAINDER,
            # which is 0 for both, so it cannot be used directly.
            "filled_volume": f"{vi:g}" if state == "filled" else "0.0",
            "price": f"{num(o['price_open']):g}",
            "stop_loss": price_or_blank(o["sl"]),
            "take_profit": price_or_blank(o["tp"]),
            "end_time": (ts(srv(num(o["time_done_msc"]) / 1000.0))
                         if num(o["time_done_msc"]) > 0 else ""),
            "state": state,
            "comment": o["comment"],
        })
    print(f"  {len(orders_rows)} rows -> {wr('orders', ORDERS_HDR, orders_rows)}")
    print("  (type,state) :", dict(Counter(
        (r["order_type"], r["state"]) for r in orders_rows)))
    print("  orders carrying an SL at send time:",
          sum(1 for r in orders_rows if r["stop_loss"]), "/", len(orders_rows))

    # ---------------------------------------------------------- working_orders
    rule("working_orders.csv  (the resting ladder)")
    wrows = []
    for i, o in enumerate(sorted(work_ord, key=lambda x: num(x["price_open"])),
                          start=1):
        wrows.append({
            "row": i,
            "open_time": ts(srv(num(o["time_setup_msc"]) / 1000.0)),
            "order_id": o["ticket"],
            "symbol": o["symbol"],
            "order_type": ORDER_TYPE_WORD.get(o["type_name"], o["type_name"].lower()),
            "volume": f"{num(o['volume_initial']):g}",
            "filled_volume": "0.0",
            "price": f"{num(o['price_open']):g}",
            "stop_loss": price_or_blank(o["sl"]),
            "take_profit": price_or_blank(o["tp"]),
            "end_time": "",
            "state": "placed",
            "comment": o["comment"],
        })
    print(f"  {len(wrows)} rows -> {wr('working_orders', ORDERS_HDR, wrows)}")

    # deployments.csv is only read by scripts that never run on this account, but
    # an empty well-formed file is cheaper than a missing-file branch in each.
    dep = os.path.join(DST, "deployments.csv")
    if not os.path.exists(dep):
        with open(dep, "w", encoding="utf-8", newline="") as fh:
            fh.write("row,time,comment\n")

    rule("DONE")
    print(f"  {DST}")
    print("  run any Target-side script against it with:")
    print("     GOLDEN_DIR='.cache/fresh' .venv/Scripts/python.exe"
          " tools/forensics/q1_trailing.py")


if __name__ == "__main__":
    main()
