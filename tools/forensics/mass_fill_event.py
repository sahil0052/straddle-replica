"""WHAT PUT 111638511 -2,870 FLOATING?  The 60-millisecond both-sides ladder fill.

THE OBSERVATION THAT STARTED THIS.  positions_get returns 34 open positions.  Of
those, 29 share an open timestamp inside a SIXTY MILLISECOND window
(epoch ms 1787706002487 .. 1787706002547), and their entry prices span 4627.38 to
4687.83 -- a 60.45 POINT range, on both sides of the book at once.

A straddle grid is not supposed to be able to do that.  Its buy stops rest ABOVE
the anchor and its sell stops rest BELOW it.  For price to traverse the whole
+/-20 level ladder it must walk 30 points up and 30 points down, which takes
minutes to hours.  Filling both wings simultaneously requires the SERVER to see,
in one evaluation pass, a quote that is above every resting buy stop AND below
every resting sell stop.  There is exactly one quote shape that does that: a
spread wide enough to straddle the entire ladder.  Buy stops trigger on ASK,
sell stops trigger on BID, so an ask >= 4687.83 together with a bid <= 4627.38
fires everything.  That is a 60-point spread.

SO THIS SCRIPT ASKS FOUR QUESTIONS, IN ORDER, AND LETS THE DATA ANSWER:

  Q1  Did both wings really fill in one batch?  (open-time clustering, by side)
  Q2  What was the QUOTE at that instant?  copy_ticks_range around the event is
      the only direct evidence.  If bid/ask straddled the ladder, the spread
      blowout is proven and the EA had no say in any of it -- pending-order
      triggering is server-side.  If instead the ticks show price genuinely
      walking each level, then the fills are legitimate and the loss is ordinary
      grid behaviour in a trend.
  Q3  Is the resulting book DELTA-NEUTRAL?  This decides whether the loss is
      recoverable.  If long volume ~= short volume the P&L barely responds to
      price and the number is a FIXED cost, not a floating risk.  The
      decomposition is exact and closed-form:
          P&L = 100*[ bid*Vlong - SUM(entry*vol)_long ]
              + 100*[ SUM(entry*vol)_short - ask*Vshort ]
      so d(P&L)/d(price) = 100*(Vlong - Vshort).
  Q4  DOES THE TARGET DO THIS TOO?  This is the parity question and the only one
      that matters for the mission.  If 901018's history contains the same
      both-wings-in-one-batch event, the behaviour is the strategy's known risk
      and our EA is faithfully reproducing it.  If the Target never once does
      it, we have found a real divergence.  The test is symmetric: for every
      cycle on both accounts, find fills within a 2-second window and check
      whether they contain BOTH buy and sell levels.

WHY THE EA'S SPREAD GUARD CANNOT HELP HERE.  MaxSpreadPoints gates what the EA
chooses to DO -- placing, closing, re-arming.  A resting stop order is triggered
by the broker, not by the EA, so no client-side guard can veto it.  The only
defences are structural (do not leave both wings resting through a session
reopen) and they are the operator's call, not something to change silently.

READ-ONLY.  order_send / order_check / order_calc_* are never imported.
"""
from __future__ import annotations

import csv
import os
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
API = os.path.join(ROOT, "artifacts", "live", "mt5api")
TERMINAL = r"D:\MT5ReplicaObserverTerminal\terminal64.exe"

# The 29-fill batch, from positions.csv.  Kept as an epoch so no timezone
# convention can silently shift the window.
EVENT_MS = 1787706002490
WINDOW_S = 240


def rule(t: str) -> None:
    print()
    print("=" * 100)
    print(t)
    print("=" * 100)


def read(name: str):
    with open(os.path.join(API, name + ".csv"), newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def lvl(comment: str):
    """('B',6) from 'STR B6'.  None for anything that is not a grid leg."""
    p = (comment or "").split()
    if len(p) != 2 or p[0] != "STR" or len(p[1]) < 2:
        return None
    s, n = p[1][0], p[1][1:]
    if s not in ("B", "S") or not n.isdigit():
        return None
    return s, int(n)


# --------------------------------------------------------------------------- Q1
def q1(pos):
    rule("Q1.  DID BOTH WINGS FILL IN ONE BATCH?")
    print("  Grouping the 34 open positions by open time to the millisecond.  A grid")
    print("  that filled by traversal shows one position per group, minutes apart.")
    print()
    g = defaultdict(list)
    for r in pos:
        g[int(r["time_msc"])].append(r)
    keys = sorted(g)
    batch = [k for k in keys if abs(k - EVENT_MS) <= 2000]
    rest = [k for k in keys if k not in batch]

    print(f"  {'open time (server)':<26} {'n':>3}  {'sides':<12}"
          f" {'levels':<26} {'price span':>14}")
    for k in rest:
        rs = g[k]
        sides = "/".join(sorted({r["type_name"] for r in rs}))
        pr = [float(r["price_open"]) for r in rs]
        print(f"  {datetime.utcfromtimestamp(k/1000):%Y-%m-%d %H:%M:%S.%f}"[:26].ljust(26)
              + f" {len(rs):>3}  {sides:<12}"
              f" {','.join(r['comment'].split()[-1] for r in rs):<26}"
              f" {max(pr)-min(pr):>14.2f}")

    rs = [r for k in batch for r in g[k]]
    pr = [float(r["price_open"]) for r in rs]
    lo, hi = min(batch), max(batch)
    buys = [r for r in rs if r["type_name"] == "BUY"]
    sells = [r for r in rs if r["type_name"] == "SELL"]
    print()
    print(f"  THE BATCH: {len(rs)} positions in {hi-lo} ms"
          f"  ({datetime.utcfromtimestamp(lo/1000):%H:%M:%S.%f}"
          f" .. {datetime.utcfromtimestamp(hi/1000):%H:%M:%S.%f})")
    print(f"    BUY  legs {len(buys):>3}   entries {min(float(r['price_open']) for r in buys):.2f}"
          f" .. {max(float(r['price_open']) for r in buys):.2f}"
          f"   levels {sorted(lvl(r['comment'])[1] for r in buys)}")
    print(f"    SELL legs {len(sells):>3}   entries {min(float(r['price_open']) for r in sells):.2f}"
          f" .. {max(float(r['price_open']) for r in sells):.2f}"
          f"   levels {sorted(lvl(r['comment'])[1] for r in sells)}")
    print(f"    FULL ENTRY SPAN {min(pr):.2f} .. {max(pr):.2f}  = {max(pr)-min(pr):.2f} points")
    print()
    if buys and sells:
        print("  -> BOTH WINGS, ONE BATCH.  For this to be legitimate traversal the market")
        print(f"     had to cover {max(pr)-min(pr):.2f} points inside {hi-lo} ms.  Q2 checks the quote.")
    return rs, buys, sells


# --------------------------------------------------------------------------- Q2
def q2(rs):
    rule("Q2.  WHAT WAS THE QUOTE?  (direct tick evidence -- the decisive panel)")
    print("  TIMEZONE DISCIPLINE.  copy_ticks_range interprets a NAIVE datetime bound in")
    print("  the PC's local zone (verified: a bound of 00:56 returned ticks stamped 19:26,")
    print("  exactly 5:30 earlier = IST).  Rather than trust any conversion, this panel")
    print("  requests a deliberately WIDE range and then selects on the raw epoch")
    print("  time_msc, comparing it to the position's own time_msc from positions.csv.")
    print("  Both are the same integer field from the same API, so the comparison carries")
    print("  no timezone assumption at all.")
    print()
    try:
        import MetaTrader5 as mt5
    except Exception as e:                                     # pragma: no cover
        print(f"  MetaTrader5 unavailable ({e}); cannot fetch ticks.")
        return None

    login = int(os.environ["MT5_LOGIN"])
    ok = mt5.initialize(path=TERMINAL, login=login,
                        password=os.environ["MT5_PASSWORD"],
                        server=os.environ.get("MT5_SERVER", "MetaQuotes-Demo"),
                        timeout=120_000)
    if not ok:
        ok = mt5.initialize(login=login, password=os.environ["MT5_PASSWORD"],
                            server=os.environ.get("MT5_SERVER", "MetaQuotes-Demo"),
                            timeout=120_000)
    if not ok:
        print(f"  FAILED: initialize -> {mt5.last_error()}")
        return None

    ev = datetime.fromtimestamp(EVENT_MS / 1000, tz=timezone.utc)
    a = (ev - timedelta(hours=14)).replace(tzinfo=None)
    b = (ev + timedelta(hours=14)).replace(tzinfo=None)
    ticks = mt5.copy_ticks_range("XAUUSD", a, b, mt5.COPY_TICKS_ALL)
    n = 0 if ticks is None else len(ticks)
    print(f"  wide request {a:%Y-%m-%d %H:%M} .. {b:%Y-%m-%d %H:%M}"
          f"   ticks returned: {n}")
    if not n:
        print("  no ticks; cannot answer Q2.")
        mt5.shutdown()
        return None
    print(f"  returned epoch span (as UTC) "
          f"{datetime.fromtimestamp(int(ticks[0]['time_msc'])/1000, tz=timezone.utc):%Y-%m-%d %H:%M:%S}"
          f" .. {datetime.fromtimestamp(int(ticks[-1]['time_msc'])/1000, tz=timezone.utc):%Y-%m-%d %H:%M:%S}")

    pr = [float(r["price_open"]) for r in rs]
    need_ask, need_bid = max(pr), min(pr)

    def sel(ms):
        return [t for t in ticks if abs(int(t["time_msc"]) - EVENT_MS) <= ms]

    for w in (2_000, 10_000, 60_000, 300_000, 1_800_000):
        s = sel(w)
        lab = f"+/-{w/1000:g} s"
        if s:
            bs = [t["bid"] for t in s]
            as_ = [t["ask"] for t in s]
            print(f"  {lab:<12} ticks {len(s):>5}   bid {min(bs):.2f}..{max(bs):.2f}"
                  f"   ask {min(as_):.2f}..{max(as_):.2f}"
                  f"   max spread {max(t['ask']-t['bid'] for t in s):.2f}")
        else:
            print(f"  {lab:<12} ticks {0:>5}   -- NO TICK DATA AT THE EVENT INSTANT --")

    print()
    print(f"  TO FIRE THE WHOLE BATCH the server needed, in ONE evaluation,")
    print(f"    ask >= {need_ask:.2f}  (to trip buy stop B20)")
    print(f"    bid <= {need_bid:.2f}  (to trip sell stop S19)")
    print(f"  i.e. a simultaneous spread of at least {need_ask - need_bid:.2f}"
          f" = {(need_ask-need_bid)*100:.0f} points.")
    straddle = [t for t in ticks if t["ask"] >= need_ask and t["bid"] <= need_bid]
    sp = [t["ask"] - t["bid"] for t in ticks if t["ask"] > 0 and t["bid"] > 0]
    print(f"  ticks in the ENTIRE 28-hour pull that satisfy it: {len(straddle)}")
    print(f"  widest spread anywhere in the pull: {max(sp):.2f}"
          f" = {max(sp)*100:.0f} points  (median {statistics.median(sp):.2f})")

    near = sel(3_000)
    if near:
        print()
        print(f"  every tick within +/-3 s of the batch ({len(near)}):")
        print(f"    {'epoch ms':>14} {'as UTC':<24} {'bid':>10} {'ask':>10}"
              f" {'spread':>8} {'flags':>6}")
        for t in near[:80]:
            ms = int(t["time_msc"])
            print(f"    {ms:>14}"
                  f" {datetime.fromtimestamp(ms/1000, tz=timezone.utc):%Y-%m-%d %H:%M:%S.%f}"[:39].ljust(40)
                  + f" {t['bid']:>10.2f} {t['ask']:>10.2f}"
                  f" {t['ask']-t['bid']:>8.2f} {int(t['flags']):>6}")
    else:
        print()
        print("  ** NO TICK EXISTS AT THE EVENT INSTANT. **  The tick series that the")
        print("  server itself serves has no quote for the moment 30 orders were")
        print("  triggered.  A traversal leaves a tick trail by definition; a feed")
        print("  discontinuity does not.")

    # bracket the gap: last tick before and first tick after
    before = [t for t in ticks if int(t["time_msc"]) <= EVENT_MS]
    after = [t for t in ticks if int(t["time_msc"]) > EVENT_MS]
    if before and after:
        lb, fa = before[-1], after[0]
        gap = (int(fa["time_msc"]) - int(lb["time_msc"])) / 1000.0
        print()
        print("  THE GAP THE FILLS SIT INSIDE:")
        print(f"    last tick BEFORE : {datetime.fromtimestamp(int(lb['time_msc'])/1000, tz=timezone.utc):%Y-%m-%d %H:%M:%S.%f}"
              f"  bid {lb['bid']:.2f} ask {lb['ask']:.2f}")
        print(f"    the 30 fills     : {datetime.fromtimestamp(EVENT_MS/1000, tz=timezone.utc):%Y-%m-%d %H:%M:%S.%f}"
              f"  at 4627.38 .. 4687.83")
        print(f"    first tick AFTER : {datetime.fromtimestamp(int(fa['time_msc'])/1000, tz=timezone.utc):%Y-%m-%d %H:%M:%S.%f}"
              f"  bid {fa['bid']:.2f} ask {fa['ask']:.2f}")
        print(f"    QUOTE GAP        : {gap:,.1f} s = {gap/60:,.1f} min"
              f"    price jump {fa['bid']-lb['bid']:+.2f}")
        print()
        print("  This is the mechanism, stated exactly: the feed stops, the ladder is")
        print("  left fully armed on both wings, and when quoting resumes the server")
        print("  evaluates every resting stop against the new quote in one pass.  Each")
        print("  order is filled AT ITS OWN REQUESTED PRICE (a demo server does not")
        print("  gap-fill), so the whole ladder books at once at prices spanning 60")
        print("  points -- prices the market never actually traded through.")

    rates = mt5.copy_rates_range("XAUUSD", mt5.TIMEFRAME_M1,
                                 (ev - timedelta(hours=3)).replace(tzinfo=None),
                                 (ev + timedelta(hours=3)).replace(tzinfo=None))
    if rates is not None and len(rates):
        sub = [r for r in rates if abs(int(r["time"]) - EVENT_MS // 1000) <= 900]
        if sub:
            print()
            print("  M1 bars within +/-15 min of the event (what the chart draws):")
            print(f"    {'as UTC':<20} {'open':>9} {'high':>9} {'low':>9}"
                  f" {'close':>9} {'range':>8}")
            for r in sub:
                print(f"    {datetime.fromtimestamp(int(r['time']), tz=timezone.utc):%Y-%m-%d %H:%M}".ljust(20)
                      + f" {r['open']:>9.2f} {r['high']:>9.2f} {r['low']:>9.2f}"
                      f" {r['close']:>9.2f} {r['high']-r['low']:>8.2f}")
            hi = max(r["high"] for r in sub)
            lo = min(r["low"] for r in sub)
            print()
            print(f"    M1 high/low around the event : {lo:.2f} .. {hi:.2f}")
            print(f"    batch fills required          {need_bid:.2f} .. {need_ask:.2f}")
            if hi < need_ask - 0.01 or lo > need_bid + 0.01:
                print("    -> THE BARS DO NOT REACH THE FILLS.  Positions were opened at")
                print("       prices the recorded market never printed.  Not traversal.")
    mt5.shutdown()
    return {"n": n, "need_ask": need_ask, "need_bid": need_bid,
            "straddle": len(straddle), "max_spread": max(sp),
            "near": len(near)}


# --------------------------------------------------------------------------- Q3
def q3(pos):
    rule("Q3.  IS THE LOSS STILL FLOATING, OR IS IT ALREADY FIXED?")
    ai = read("account_info")[0]
    sym = read("symbol_xauusd")[0]
    contract = float(sym["trade_contract_size"])

    # Use each position's OWN price_current -- that is the exact mark the broker
    # used for the profit it reported, so the reconciliation has no slack.
    L = [r for r in pos if r["type_name"] == "BUY"]
    S = [r for r in pos if r["type_name"] == "SELL"]
    bid = statistics.median([float(r["price_current"]) for r in L])
    ask = statistics.median([float(r["price_current"]) for r in S])

    vl = sum(float(r["volume"]) for r in L)
    vs = sum(float(r["volume"]) for r in S)
    nl = sum(float(r["price_open"]) * float(r["volume"]) for r in L)
    ns = sum(float(r["price_open"]) * float(r["volume"]) for r in S)
    swap = sum(float(r["swap"]) for r in pos)

    pl_l = contract * (bid * vl - nl)
    pl_s = contract * (ns - ask * vs)
    model = pl_l + pl_s + swap
    actual = sum(float(r["profit"]) for r in pos) + swap

    print(f"  mark: bid {bid:.2f} (buy side) / ask {ask:.2f} (sell side)"
          f"   contract {contract:.0f} oz/lot")
    print()
    print(f"  {'':<7}{'lots':>7} {'avg entry':>11} {'notional':>13} {'P&L':>12}")
    print(f"  LONG {vl:>9.2f} {nl/vl:>11.2f} {nl:>13.4f} {pl_l:>12.2f}")
    print(f"  SHORT{vs:>9.2f} {ns/vs:>11.2f} {ns:>13.4f} {pl_s:>12.2f}")
    print(f"  swap {'':>9}{'':>11} {'':>13} {swap:>12.2f}")
    print(f"  {'-'*52}")
    print(f"  MODEL{'':>9}{'':>11} {'':>13} {model:>12.2f}")
    print(f"  BROKER (sum position profit + swap){'':>5} {actual:>12.2f}")
    print(f"  account_info.profit{'':>21} {float(ai['profit']):>12.2f}")
    print(f"  residual model - broker{'':>17} {model-actual:>12.2f}")
    print()
    net = vl - vs
    print(f"  NET EXPOSURE  {net:+.2f} lots"
          f"  ->  d(P&L)/d(gold) = ${contract*net:+.2f} per $1.00 move")
    print(f"  GROSS         {vl+vs:.2f} lots  (margin ${float(ai['margin']):,.2f}"
          f" of ${float(ai['equity']):,.2f} equity"
          f" -> margin level {float(ai['margin_level']):.0f}%)")
    print()
    print("  DECOMPOSITION.  Because the wings are near-equal in size the price terms")
    print("  almost cancel and what is left is the gap between the two average entries:")
    print(f"    bought {vl:.2f} lots at an average of {nl/vl:.2f}")
    print(f"    sold   {vs:.2f} lots at an average of {ns/vs:.2f}")
    print(f"    bought {nl/vl - ns/vs:.2f} points ABOVE where it sold")
    fixed = contract * min(vl, vs) * (nl / vl - ns / vs)
    print(f"    matched size {min(vl,vs):.2f} lots x {nl/vl - ns/vs:.2f} pts"
          f" x {contract:.0f} = ${-fixed:,.2f}")
    print(f"    ... which price CANNOT recover.  Observed floating: ${actual:,.2f}")
    print()
    if abs(contract * net) < 20:
        print(f"  -> THE LOSS IS ALREADY FIXED, NOT FLOATING.  At {contract*net:+.0f}"
              f" $/point the book is")
        print("     delta-flat: gold can rally or collapse and this number barely moves.")
        print("     It is the arithmetic cost of having bought the upper wing and sold the")
        print("     lower wing in the SAME INSTANT, and nothing but closing changes it.")
        print()
        print("     COROLLARY -- THE BASKET TARGET CAN NEVER FIRE FROM HERE.  The only")
        print("     money exit is realized_since_cycle_start + floating >= $30.  With")
        print(f"     floating pinned at {actual:,.0f} and no delta to move it, that")
        print("     condition is unreachable.  The book can only be resolved by stops")
        print("     firing one at a time (32 of 34 have none yet) or by a guard.")
    else:
        print(f"  -> STILL DIRECTIONAL at {contract*net:+.0f} $/point; the number can move.")

    # the stop-loss census -- why nothing is protected
    with_sl = [r for r in pos if float(r["sl"]) > 0]
    print()
    print(f"  STOP-LOSS CENSUS: {len(with_sl)} of {len(pos)} positions carry one.")
    for r in with_sl:
        print(f"    {r['comment']:<10} {r['type_name']:<5} {float(r['volume']):.2f}"
              f" @ {float(r['price_open']):.2f}   sl {float(r['sl']):.2f}"
              f"   profit {float(r['profit']):+.2f}")
    print("  The other 32 have sl=0.00 by LAW, not by fault: StopScheduler::Calculate")
    print("  opens with `if(favorable_steps < lock_trigger_steps) return false;` and")
    print("  lock_trigger_steps = 2.0, so at step 1.55 a position must earn +3.10 in its")
    print("  favour before ANY stop is written.  A batch fill hands the EA a book where")
    print("  almost nothing is in profit, so almost nothing is protected.")
    return {"vl": vl, "vs": vs, "net": net, "actual": actual,
            "avg_l": nl / vl, "avg_s": ns / vs}


# --------------------------------------------------------------------------- Q4
def q4():
    rule("Q4.  DOES THE TARGET EA DO THIS TOO?  (the parity question)")
    print("  Symmetric test, one estimator, both accounts: inside each cycle, group")
    print("  fills into 2-second windows and ask whether any window contains BOTH a")
    print("  buy level and a sell level.  A traversal grid can fill several levels of")
    print("  ONE wing quickly; only a quote discontinuity fills both wings at once.")
    print()
    import tools.forensics.dataset as DS

    def scan(path, label):
        DS.GOLDEN = Path(path)
        _o, positions, _d, cycles = DS.load_all()
        cyc = {c.index: c for c in cycles}
        by = defaultdict(list)
        for p in positions:
            if p.cycle in cyc and p.open_time:
                by[p.cycle].append(p)
        tot = both = 0
        worst = None
        for idx, ps in by.items():
            ps.sort(key=lambda x: x.open_time)
            i = 0
            while i < len(ps):
                j = i
                while j + 1 < len(ps) and \
                        (ps[j + 1].open_time - ps[i].open_time).total_seconds() <= 2.0:
                    j += 1
                w = ps[i:j + 1]
                if len(w) >= 4:
                    tot += 1
                    sides = {x.side for x in w}
                    if len(sides) > 1:
                        both += 1
                        span = max(x.open_price for x in w) - min(x.open_price for x in w)
                        if worst is None or span > worst[0]:
                            worst = (span, idx, len(w), w[0].open_time)
                i = j + 1
        return label, len(positions), tot, both, worst

    rows = [scan(os.path.join(ROOT, ".cache", "golden"), "TARGET 901018 (XLSX)"),
            scan(os.path.join(ROOT, ".cache", "fresh"), "OURS   111638511")]
    print(f"  {'stream':<24} {'positions':>10} {'>=4-fill windows':>18}"
          f" {'BOTH sides':>12} {'worst span':>12}")
    for label, n, tot, both, worst in rows:
        ws = f"{worst[0]:.2f} pts" if worst else "--"
        print(f"  {label:<24} {n:>10} {tot:>18} {both:>12} {ws:>12}")
        if worst:
            print(f"      worst: cycle {worst[1]}  {worst[2]} fills"
                  f"  at {worst[3]:%Y-%m-%d %H:%M:%S}")
    print()
    t, o = rows[0], rows[1]
    print("  READ THE SPAN, NOT THE COUNT.  Presence of a both-wings window is the")
    print("  wrong discriminator and an earlier version of this panel got it wrong.")
    print("  Two adjacent levels either side of the anchor filling together is an")
    print("  ordinary whipsaw across the middle of the ladder -- it costs a couple of")
    print("  steps.  A batch that spans the WHOLE armed ladder requires a quote wide")
    print("  enough to sit above the top buy stop and below the bottom sell stop at")
    print("  once, and it costs (span x matched lots x contract).  Those are different")
    print("  events with the same boolean answer, so compare magnitudes.")
    print()
    if t[4] is None or o[4] is None:
        print("  -> inconclusive on this sample (a stream has no >=4-fill window).")
        return
    ts, osp = t[4][0], o[4][0]
    print(f"    TARGET worst both-wings span : {ts:>7.2f} pts   ({t[3]} such windows)")
    print(f"    OURS   worst both-wings span : {osp:>7.2f} pts   ({o[3]} such windows)")
    print(f"    ratio                        : {osp / ts:>7.2f}x")
    print()
    if osp > 4.0 * ts:
        print("  -> DIVERGENCE IN MAGNITUDE, NOT IN LOGIC.  Both EAs get both-wings")
        print("     batches, but the Target's worst is a couple of lattice steps wide")
        print("     while ours spans the entire armed ladder.  The EA does not choose")
        print("     this: a resting stop order is triggered server-side by the quote, so")
        print("     the span is set by the widest spread the VENUE prints, not by any")
        print("     EA parameter.  The Target's live broker never printed a spread wide")
        print("     enough to straddle its ladder; MetaQuotes-Demo did.  Classify this")
        print("     as a feed/venue difference and do NOT 'fix' it in the EA -- but do")
        print("     NOT treat our demo P&L as representative of the Target's either.")
    else:
        print("  -> AT PARITY IN MAGNITUDE.  Our worst both-wings batch is the same")
        print("     order of size as the Target's, i.e. ordinary whipsaw across the")
        print("     anchor rather than a ladder-wide straddle.")


def main() -> None:
    pos = read("positions")
    rs, buys, sells = q1(pos)
    q2(rs)
    q3(pos)
    try:
        q4()
    except Exception as e:
        print(f"\n  Q4 unavailable: {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
