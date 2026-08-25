"""Pull 111638511's FULL account history over the MT5 Python API.  READ ONLY.

WHY THIS EXISTS.  Every previous statement about 111638511 rested on one
instrument: the terminal's Trades-category log, which records FILLS ONLY -- time,
side, volume, price, deal id.  That is why three whole bodies of Target behaviour
were reported as unverifiable on this account:

  * the trailing ratchet (2695 SL-closed positions in the Target XLSX),
  * the $30.00 fixed basket target,
  * closure reasons -- a stop fill and a flatten fill look identical in a log.

None of those are actually hidden.  They are simply not in the .log file.  They
ARE in the account's trade history, and the MT5 Python API returns that history
in a richer form than the XLSX export does:

    history_deals_get  -> profit, commission, swap, position_id, comment,
                          entry (IN/OUT), and REASON (CLIENT/EXPERT/SL/TP/SO)
    history_orders_get -> sl, tp, price_open, state, and the same reason enum
    positions_get      -> the LIVE sl/tp of every open position  <- the ratchet
    orders_get         -> the resting ladder with every pending price

deal.reason == DEAL_REASON_SL is a direct, unambiguous answer to "did the stop
close this", which is strictly better than the XLSX route of pattern-matching
"sl <price>" out of the Comment column.  positions_get is better still: it is the
ratchet caught mid-flight, which no export of closed history can show.

SAFETY, because this logs in with the master password on the same account a live
VPS EA is trading:

  1. The API is used for reads only.  order_send / order_check / order_calc_* are
     never called and are not imported.  Nothing in this file can place, modify
     or close anything.
  2. The terminal HOST is D:\\MT5ReplicaObserverTerminal -- the retired
     111387094 demo install -- and NOT C:\\Program Files\\MetaTrader 5, which is
     the operator's live read-only observer on 111638511.  That observer is left
     exactly as it is.  The host was cleared first: no chart in any of its four
     profiles has an expert attached, and AllowDllImport=0, so even with the
     account switched to master mode there is no EA present that could trade.
  3. Credentials come from the environment (MT5_LOGIN / MT5_PASSWORD /
     MT5_SERVER), never from this file, so the repo never carries the password.

Everything is dumped to artifacts/live/mt5api/ so that every later analysis runs
against files on disk and no re-login is ever needed.
"""
from __future__ import annotations

import csv
import json
import os
import sys
from datetime import datetime, timedelta

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TERMINAL = r"D:\MT5ReplicaObserverTerminal\terminal64.exe"
OUTDIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "artifacts", "live", "mt5api")

# Enum decodings.  Hardcoded rather than read off the module so the dumped CSVs
# stay readable without the package installed.
DEAL_REASON = {0: "CLIENT", 1: "MOBILE", 2: "WEB", 3: "EXPERT", 4: "SL",
               5: "TP", 6: "SO", 7: "ROLLOVER", 8: "VMARGIN", 9: "SPLIT"}
ORDER_REASON = {0: "CLIENT", 1: "MOBILE", 2: "WEB", 3: "EXPERT", 4: "SL",
                5: "TP", 6: "SO"}
DEAL_TYPE = {0: "BUY", 1: "SELL", 2: "BALANCE", 3: "CREDIT", 4: "CHARGE",
             5: "CORRECTION", 6: "BONUS", 7: "COMMISSION",
             8: "COMMISSION_DAILY", 9: "COMMISSION_MONTHLY",
             10: "AGENT_DAILY", 11: "AGENT_MONTHLY", 12: "INTEREST",
             13: "BUY_CANCELED", 14: "SELL_CANCELED", 15: "DIVIDEND",
             16: "DIVIDEND_FRANKED", 17: "TAX"}
DEAL_ENTRY = {0: "IN", 1: "OUT", 2: "INOUT", 3: "OUT_BY"}
ORDER_TYPE = {0: "BUY", 1: "SELL", 2: "BUY_LIMIT", 3: "SELL_LIMIT",
              4: "BUY_STOP", 5: "SELL_STOP", 6: "BUY_STOP_LIMIT",
              7: "SELL_STOP_LIMIT", 8: "CLOSE_BY"}
ORDER_STATE = {0: "STARTED", 1: "PLACED", 2: "CANCELED", 3: "PARTIAL",
               4: "FILLED", 5: "REJECTED", 6: "EXPIRED", 7: "REQUEST_ADD",
               8: "REQUEST_MODIFY", 9: "REQUEST_CANCEL"}
POS_TYPE = {0: "BUY", 1: "SELL"}


def rule(t: str) -> None:
    print()
    print("=" * 100)
    print(t)
    print("=" * 100)


def dump(name: str, rows: list[dict]) -> str:
    """Write rows to both CSV and JSON; return the CSV path."""
    os.makedirs(OUTDIR, exist_ok=True)
    jp = os.path.join(OUTDIR, name + ".json")
    with open(jp, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, indent=1, default=str)
    cp = os.path.join(OUTDIR, name + ".csv")
    if rows:
        keys = list(rows[0].keys())
        with open(cp, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=keys)
            w.writeheader()
            w.writerows(rows)
    return cp


def main() -> None:
    login = int(os.environ["MT5_LOGIN"])
    password = os.environ["MT5_PASSWORD"]
    server = os.environ.get("MT5_SERVER", "MetaQuotes-Demo")

    import MetaTrader5 as mt5  # noqa: N813

    rule("CONNECT  (read-only session; host terminal is the retired observer)")
    print(f"  host     : {TERMINAL}")
    print(f"  account  : {login} @ {server}")
    ok = mt5.initialize(path=TERMINAL, login=login, password=password,
                        server=server, timeout=120_000, portable=False)
    if not ok:
        print(f"  FAILED: initialize -> {mt5.last_error()}")
        # A second attempt without path attaches to whatever terminal is up.
        # Only tried if the dedicated host refused, and reported loudly.
        print("  retrying by attaching to an already-running terminal ...")
        ok = mt5.initialize(login=login, password=password, server=server,
                            timeout=120_000)
        if not ok:
            print(f"  FAILED again -> {mt5.last_error()}")
            sys.exit(2)
        print("  NOTE: attached to the running terminal, not the dedicated host.")

    ti = mt5.terminal_info()
    ai = mt5.account_info()
    print(f"  terminal : build {ti.build}  connected={ti.connected}"
          f"  trade_allowed={ti.trade_allowed}  algo={ti.trade_allowed}")
    print(f"  data dir : {ti.data_path}")
    if ai is None:
        print(f"  account_info failed -> {mt5.last_error()}")
        mt5.shutdown()
        sys.exit(2)
    print(f"  login    : {ai.login}  {ai.server}  {ai.company}")
    print(f"  balance  : {ai.balance:.2f} {ai.currency}   equity {ai.equity:.2f}"
          f"   margin {ai.margin:.2f}   free {ai.margin_free:.2f}")
    print(f"  profit   : {ai.profit:.2f}   leverage 1:{ai.leverage}"
          f"   mode={'HEDGING' if ai.margin_mode == 2 else ai.margin_mode}")
    print(f"  trade_expert={ai.trade_expert}  trade_allowed={ai.trade_allowed}")
    dump("account_info", [ai._asdict()])

    # --------------------------------------------------------------- positions
    rule("OPEN POSITIONS  (sl/tp here IS the trailing ratchet, caught mid-flight)")
    pos = mt5.positions_get() or []
    rows = []
    for p in pos:
        d = p._asdict()
        d["type_name"] = POS_TYPE.get(p.type, str(p.type))
        d["time_dt"] = datetime.fromtimestamp(p.time)
        d["reason_name"] = ORDER_REASON.get(p.reason, str(p.reason))
        rows.append(d)
    rows.sort(key=lambda r: r["time_dt"])
    print(f"  {len(rows)} open position(s)")
    if rows:
        print(f"  {'ticket':>12} {'opened':>19} {'t':>4} {'vol':>6} {'open':>9}"
              f" {'sl':>9} {'tp':>9} {'cur':>9} {'profit':>9}  comment")
        for r in rows:
            print(f"  {r['ticket']:>12} {r['time_dt']:%Y-%m-%d %H:%M:%S}"
                  f" {r['type_name']:>4} {r['volume']:>6.2f} {r['price_open']:>9.2f}"
                  f" {r['sl']:>9.2f} {r['tp']:>9.2f} {r['price_current']:>9.2f}"
                  f" {r['profit']:>9.2f}  {r['comment']}")
        with_sl = sum(1 for r in rows if r["sl"] > 0.0)
        with_tp = sum(1 for r in rows if r["tp"] > 0.0)
        print(f"  positions carrying an SL: {with_sl}/{len(rows)}"
              f"   a TP: {with_tp}/{len(rows)}")
    dump("positions", rows)

    # ------------------------------------------------------------------ orders
    rule("RESTING PENDING ORDERS  (the deployed ladder, exact prices)")
    orders = mt5.orders_get() or []
    rows = []
    for o in orders:
        d = o._asdict()
        d["type_name"] = ORDER_TYPE.get(o.type, str(o.type))
        d["state_name"] = ORDER_STATE.get(o.state, str(o.state))
        d["time_setup_dt"] = datetime.fromtimestamp(o.time_setup)
        rows.append(d)
    rows.sort(key=lambda r: (r["type_name"], r["price_open"]))
    print(f"  {len(rows)} resting order(s)")
    for r in rows:
        print(f"  {r['ticket']:>12} {r['time_setup_dt']:%Y-%m-%d %H:%M:%S}"
              f" {r['type_name']:>10} {r['volume_current']:>6.2f}"
              f" @ {r['price_open']:>9.2f}  sl={r['sl']:>9.2f} tp={r['tp']:>9.2f}"
              f"  {r['comment']}")
    dump("orders", rows)

    # ------------------------------------------------------------------- deals
    rule("CLOSED DEAL HISTORY  (profit, commission, swap, position_id, REASON)")
    # The range is deliberately absurd.  history_deals_get compares against
    # SERVER time and the package converts naive datetimes, so a range that only
    # just brackets the account's life can come back empty for timezone reasons
    # alone.  2000..2035 removes that failure mode entirely.
    frm = datetime(2000, 1, 1)
    to = datetime(2035, 1, 1)
    # Immediately after login the terminal has not necessarily finished pulling
    # history from the server, and the API returns an empty tuple rather than
    # blocking.  Poll rather than believe the first answer.
    deals = ()
    for attempt in range(30):
        deals = mt5.history_deals_get(frm, to) or ()
        if deals:
            break
        import time as _t
        _t.sleep(1.0)
    print(f"  history sync: {len(deals)} deal(s) after {attempt + 1} poll(s)"
          f"   total_reported={mt5.history_deals_total(frm, to)}")
    deals = deals or []
    rows = []
    for d0 in deals:
        d = d0._asdict()
        d["time_dt"] = datetime.fromtimestamp(d0.time)
        d["time_msc_dt"] = datetime.fromtimestamp(d0.time_msc / 1000.0)
        d["type_name"] = DEAL_TYPE.get(d0.type, str(d0.type))
        d["entry_name"] = DEAL_ENTRY.get(d0.entry, str(d0.entry))
        d["reason_name"] = DEAL_REASON.get(d0.reason, str(d0.reason))
        rows.append(d)
    rows.sort(key=lambda r: r["time_msc_dt"])
    print(f"  {len(rows)} deal(s) from {frm:%Y-%m-%d} to now")
    if rows:
        print(f"  first {rows[0]['time_dt']}   last {rows[-1]['time_dt']}")
        from collections import Counter
        print("  by reason :", dict(Counter(r["reason_name"] for r in rows)))
        print("  by entry  :", dict(Counter(r["entry_name"] for r in rows)))
        print("  by type   :", dict(Counter(r["type_name"] for r in rows)))
        tp = sum(r["profit"] for r in rows)
        tc = sum(r["commission"] for r in rows)
        ts = sum(r["swap"] for r in rows)
        print(f"  profit {tp:+.2f}   commission {tc:+.2f}   swap {ts:+.2f}"
              f"   net {tp + tc + ts:+.2f}")
        cm = Counter(r["comment"].split()[0] if r["comment"] else "(blank)"
                     for r in rows)
        print("  comment first-token :", dict(cm.most_common(12)))
    print(f"  -> {dump('deals', rows)}")

    # ------------------------------------------------------------------ orders
    rule("ORDER HISTORY  (every order ever, with the SL it carried and its state)")
    hords = mt5.history_orders_get(frm, to) or []
    rows = []
    for o0 in hords:
        d = o0._asdict()
        d["time_setup_dt"] = datetime.fromtimestamp(o0.time_setup)
        d["time_done_dt"] = (datetime.fromtimestamp(o0.time_done)
                             if o0.time_done else None)
        d["type_name"] = ORDER_TYPE.get(o0.type, str(o0.type))
        d["state_name"] = ORDER_STATE.get(o0.state, str(o0.state))
        d["reason_name"] = ORDER_REASON.get(o0.reason, str(o0.reason))
        rows.append(d)
    rows.sort(key=lambda r: r["time_setup_dt"])
    print(f"  {len(rows)} historical order(s)")
    if rows:
        from collections import Counter
        print("  by state  :", dict(Counter(r["state_name"] for r in rows)))
        print("  by type   :", dict(Counter(r["type_name"] for r in rows)))
        print("  by reason :", dict(Counter(r["reason_name"] for r in rows)))
        sl_set = sum(1 for r in rows if r["sl"] > 0.0)
        print(f"  orders carrying an SL at send time: {sl_set}/{len(rows)}")
    print(f"  -> {dump('history_orders', rows)}")

    # ------------------------------------------------------------------ symbol
    rule("SYMBOL")
    mt5.symbol_select("XAUUSD", True)
    si = mt5.symbol_info("XAUUSD")
    if si is not None:
        print(f"  XAUUSD  digits={si.digits}  point={si.point}"
              f"  tick_value={si.trade_tick_value}  contract={si.trade_contract_size}")
        print(f"  stops_level={si.trade_stops_level}  freeze={si.trade_freeze_level}"
              f"  vol_min={si.volume_min} step={si.volume_step}")
        print(f"  bid={si.bid} ask={si.ask} spread={si.spread}")
        dump("symbol_xauusd", [si._asdict()])

    mt5.shutdown()
    print()
    print(f"  session closed.  artifacts in {OUTDIR}")


if __name__ == "__main__":
    main()
