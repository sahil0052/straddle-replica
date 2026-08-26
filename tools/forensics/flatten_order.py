"""IN WHAT ORDER DOES EACH EA FLATTEN ITS BASKET -- and what does the sweep cost?

WHY THIS PANEL EXISTS.  An audit narrative arrived claiming that during a paced
flatten "profitable short legs were closed first", and attributing a cycle that
banked +$3.20 out of ~$140 peak floating to the 20-second pacing delay.  Both
halves are testable, and our own code already answers the first half:

    for(int index=PositionsTotal()-1;index>=0;index--)      StraddleEngine.mqh:2413
       ...
       if(m_gateway.ClosePosition(ticket,"STR CLOSE")) { ...; return true; }

There is NO profit comparison anywhere in that loop, and no sort.  It walks MT5's
position list from the LAST index down and closes the first owned ticket it
reaches.  MT5 appends newly-opened positions at the end of that list, so the
selection LEANS newest-first -- but only leans.  Two things break strictness: the
index list COMPACTS as each position is removed, so the surviving tickets shift
down between passes, and m_close_skip steps over a ticket whose close failed.
Measured on the live account's own sweep, rho(close order, open time) = -0.70, not
-1.00.  So "LIFO" is the right intuition and the wrong word; "index order,
newest-leaning" is exact.

Either way, "winners first" is not a policy -- it is what index order looks like
when the winners happen to be the legs that opened last, which is exactly what a
one-directional trend run produces.  Reverse the market and the identical code
holds the winners to the end instead.

So the parity question is not "does it close winners first" but:

    Q1  Is the Target's flatten order LIFO too, or FIFO, or profit-sorted?

That is measurable without any mark.  Inside one sweep, rank the closed positions
by close_time (the order the EA actually chose) and by open_time, and correlate:

        rho(close_rank, open_rank) = +1  ->  FIFO  (oldest first)
                                   = -1  ->  LIFO  (newest first)
                                   ~  0  ->  neither; some other key

Then correlate close_rank against per-position P&L to test the "winners first"
claim directly.  A profit-sorted EA shows rho ~ -1 on THAT column regardless of
open order.  Our EA must score LIFO on the open-order column and near 0 on the
profit column; if the Target scores differently, the flatten ORDER is a real
architectural divergence even though the flatten PACE (20 s) already matches.

WHY ORDER IS WORTH MONEY, NOT JUST TIDINESS.  A paced sweep is 20 s per leg, so a
12-leg basket is exposed for ~4 minutes.  Whichever legs are closed LAST carry
that exposure.  LIFO on a trend run keeps the OLDEST legs -- the ones that opened
before the move and are therefore the losers -- open longest.  That is not
automatically bad: those legs are counter-trend, so a retracement HELPS them.  It
does mean the order determines which side of the book eats the retracement, and
the sign of that effect flips with the direction of the pullback.  Panel C
measures it instead of assuming it.

    Q2  Does sweep duration actually predict a worse exit?
    Q3  What is the Target's cycle-exit distribution, and does its variance track
        sweep duration or something else?

SCOPE.  Pacing questions split at the PACING break, 2026-07-24 12:00 -- never at
dataset.FINAL_REGIME_START (2026-07-14), which straddles it and pools a 0.1 s
sweep family with a 20 s one.  That pooling has manufactured a false verdict in
this project before.

READ-ONLY.  Reads .cache/golden (Target XLSX) and .cache/fresh (ours).  No API,
no order_send.
"""
from __future__ import annotations

import os
import statistics
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
import tools.forensics.dataset as DS  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GOLDEN = os.path.join(ROOT, ".cache", "golden")
FRESH = os.path.join(ROOT, ".cache", "fresh")
# The live EA account.  Its cycle 0 IS the sweep the audit narrative describes,
# so it is measured here beside the Target rather than argued about.
VANTAGE = os.path.join(ROOT, ".cache", "vantage")

PACING_BREAK = datetime(2026, 7, 24, 12, 0, 0)
SWEEP_MAX = 900.0


def rule(t: str) -> None:
    print()
    print("=" * 100)
    print(t)
    print("=" * 100)


def spearman(a, b):
    """Rank correlation.  Ties averaged.  None when undefined."""
    n = len(a)
    if n < 3:
        return None

    def ranks(v):
        order = sorted(range(n), key=lambda i: v[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    ra, rb = ranks(a), ranks(b)
    ma, mb = sum(ra) / n, sum(rb) / n
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    da = sum((x - ma) ** 2 for x in ra) ** 0.5
    db = sum((y - mb) ** 2 for y in rb) ** 0.5
    if da == 0 or db == 0:
        return None
    return num / (da * db)


def sweeps(path: str, label: str, after_break: bool | None):
    """Every flatten sweep: the positions closed in it, in close order.

    A sweep is anchored on the cycle's first `STR CLOSE` order, which is the EA's
    own attestation that BeginClose() ran.  Positions closed within SWEEP_MAX of
    that instant belong to the sweep; anything closed earlier was a stop-out and
    is `pre` money, not sweep money.
    """
    DS.GOLDEN = Path(path)
    _o, _p, _d, cycles = DS.load_all()
    out = []
    for c in cycles:
        cl = [o.open_time for o in c.orders
              if o.comment and o.comment.strip().upper().startswith("STR CLOSE")]
        if not cl:
            continue
        t0 = min(cl)
        if after_break is not None and (t0 >= PACING_BREAK) != after_break:
            continue
        pre, sw = 0.0, []
        for p in c.positions:
            if p.is_open or not p.close_time:
                continue
            if p.close_time < t0 - timedelta(seconds=5):
                pre += p.net
            elif p.close_time <= t0 + timedelta(seconds=SWEEP_MAX):
                sw.append(p)
        if len(sw) < 4:
            continue
        sw.sort(key=lambda p: p.close_time)
        span = (sw[-1].close_time - sw[0].close_time).total_seconds()
        out.append(dict(label=label, i=c.index, t0=t0, pre=pre, sw=sw,
                        burst=sum(p.net for p in sw), span=span,
                        per=span / max(1, len(sw) - 1)))
    return out


def order_stats(rows):
    """Per-sweep rank correlations, aggregated."""
    ro, rp, rs = [], [], []
    for r in rows:
        sw = r["sw"]
        crank = list(range(len(sw)))
        rho_open = spearman(crank, [p.open_time.timestamp() for p in sw])
        rho_pl = spearman(crank, [p.net for p in sw])
        rho_side = spearman(crank, [p.dir for p in sw])
        if rho_open is not None:
            ro.append(rho_open)
        if rho_pl is not None:
            rp.append(rho_pl)
        if rho_side is not None:
            rs.append(rho_side)
    return ro, rp, rs


def qs(v, fs=(0.10, 0.25, 0.50, 0.75, 0.90)):
    s = sorted(v)
    return [s[min(int(f * (len(s) - 1)), len(s) - 1)] for f in fs]


def main() -> None:
    t_old = sweeps(GOLDEN, "TARGET pre-break", False)
    t_new = sweeps(GOLDEN, "TARGET post-break", True)
    ours = sweeps(FRESH, "OURS 111638511", None)
    vant = sweeps(VANTAGE, "OURS 25954110", None)
    pops = [("TARGET pre-break  (0.1s)", t_old),
            ("TARGET post-break (20s)", t_new),
            ("OURS  111638511   (20s)", ours),
            ("OURS  25954110    (20s)", vant)]

    rule("SCOPE -- flatten sweeps of 4+ legs")
    for lab, rows in pops:
        if not rows:
            print(f"  {lab:<26} 0 sweeps")
            continue
        print(f"  {lab:<26} {len(rows):>4} sweeps"
              f"   median {statistics.median(r['per'] for r in rows):>6.2f} s/close"
              f"   median span {statistics.median(r['span'] for r in rows):>7.1f} s"
              f"   median legs {statistics.median(len(r['sw']) for r in rows):>4.1f}")

    rule("A. FLATTEN ORDER.  rho = +1 FIFO (oldest first), -1 LIFO (newest first)")
    print("  Our loop walks PositionsTotal()-1 down to 0 and closes the first owned")
    print("  ticket, with no sort and no profit test.  MT5 appends new positions at the")
    print("  end of that list, so our predicted score is rho(open) ~ -1 and rho(P&L) ~ 0.")
    print("  If the Target scores the same, flatten ORDER is at parity.  If it scores")
    print("  +1 it flattens FIFO, and our LIFO is a real architectural divergence.")
    print()
    print(f"  {'stream':<26} {'n':>4} {'rho vs OPEN time':>32}"
          f" {'rho vs P&L':>22} {'rho vs SIDE':>14}")
    print(f"  {'':<26} {'':>4} {'med    [p25 .. p75]':>32}"
          f" {'med':>22} {'med':>14}")
    verdicts = {}
    for lab, rows in pops:
        if not rows:
            continue
        ro, rp, rs = order_stats(rows)
        if not ro:
            continue
        q = qs(ro)
        verdicts[lab] = (statistics.median(ro),
                         statistics.median(rp) if rp else float("nan"))
        print(f"  {lab:<26} {len(ro):>4}"
              f" {statistics.median(ro):>+14.3f}  [{q[1]:>+6.3f} ..{q[3]:>+7.3f}]"
              f" {statistics.median(rp) if rp else float('nan'):>+22.3f}"
              f" {statistics.median(rs) if rs else float('nan'):>+14.3f}")
    print()
    print("  How to read rho vs SIDE: our positions carry dir=+1 buy / -1 sell, so a")
    print("  strongly negative value means BUYS were closed late -- which on a downtrend")
    print("  is the losing wing, and is a CONSEQUENCE of LIFO, not a separate policy.")

    rule("B. IS ANY STREAM PROFIT-SORTED?  (the 'winners first' claim, tested)")
    print("  A profit-sorted flatten would show rho(P&L) strongly negative -- most")
    print("  profitable closed first -- INDEPENDENT of open order.  Anything near zero")
    print("  means P&L plays no part in the selection and any apparent 'winners first'")
    print("  is the market having made the newest legs the winners.")
    print()
    for lab, (ro, rp) in verdicts.items():
        tag = ("PROFIT-SORTED" if rp < -0.5 else
               "LOSERS-FIRST" if rp > 0.5 else "P&L PLAYS NO PART")
        omode = ("LIFO (newest first)" if ro < -0.5 else
                 "FIFO (oldest first)" if ro > 0.5 else "no open-order rule")
        print(f"  {lab:<26} order = {omode:<22} profit key = {tag}")

    rule("C. DOES SWEEP DURATION PREDICT A WORSE EXIT?  (the pacing-cost claim)")
    print("  If the 20 s pacing is what destroys a cycle's profit, exit value must fall")
    print("  as span rises.  Bucket by span across BOTH regimes so the label cannot")
    print("  carry the result.")
    print()
    allrows = t_old + t_new
    buckets = [("under 5 s", 0, 5), ("5 - 60 s", 5, 60),
               ("1 - 3 min", 60, 180), ("3 - 6 min", 180, 360),
               ("over 6 min", 360, 1e9)]
    print(f"  {'span bucket':>12} {'cycles':>7} {'med exit':>10} {'med pre':>10}"
          f" {'med burst':>11} {'worst exit':>11} {'exit < 0':>9}")
    for name, lo, hi in buckets:
        g = [r for r in allrows if lo <= r["span"] < hi]
        if not g:
            continue
        ex = [r["pre"] + r["burst"] for r in g]
        print(f"  {name:>12} {len(g):>7} {statistics.median(ex):>10.2f}"
              f" {statistics.median(r['pre'] for r in g):>10.2f}"
              f" {statistics.median(r['burst'] for r in g):>11.2f}"
              f" {min(ex):>11.2f} {sum(1 for x in ex if x < 0):>4}/{len(g):<4}")
    rho = spearman([r["span"] for r in allrows],
                   [r["pre"] + r["burst"] for r in allrows])
    print()
    print(f"  rho(sweep span, exit value) over {len(allrows)} Target sweeps"
          f" = {rho:+.3f}" if rho is not None else "  rho undefined")
    print("  A pacing-cost story needs this clearly negative.  Near zero means duration")
    print("  is not what sets the exit value.")

    rule("D. THE TARGET'S CYCLE-EXIT DISTRIBUTION  (audit question 3)")
    print("  exit = pre + burst = money realised in the cycle at the flatten, which is")
    print("  the same quantity the $30 rule is evaluated on.  No mark, no reconstruction.")
    print()
    bands = [("< 0", -1e9, 0), ("0 .. 15", 0, 15), ("15 .. 25", 15, 25),
             ("25 .. 35", 25, 35), ("35 .. 60", 35, 60),
             ("60 .. 150", 60, 150), ("> 150", 150, 1e9)]
    cols = [(lab, rows) for lab, rows in pops]
    hdr = "".join(f"{lab.split('(')[0].strip():>21}" for lab, _ in cols)
    print(f"  {'band ($)':>10}{hdr}")
    for name, lo, hi in bands:
        cells = []
        for _lab, rows in cols:
            ex = [r["pre"] + r["burst"] for r in rows]
            k = sum(1 for x in ex if lo <= x < hi)
            cells.append(f"{k:>4} /{100.0 * k / len(ex) if ex else 0:>6.1f}%"
                         if ex else "     --     ")
        print(f"  {name:>10}" + "".join(f"{c:>21}" for c in cells))
    print()
    print(f"  {'stat':>10}{hdr}")
    for stat, fn in (("median", statistics.median),
                     ("mean", statistics.fmean),
                     ("min", min), ("max", max)):
        cells = []
        for _lab, rows in cols:
            ex = [r["pre"] + r["burst"] for r in rows]
            cells.append(f"{fn(ex):>12.2f}" if ex else "      --    ")
        print(f"  {stat:>10}" + "".join(f"{c:>21}" for c in cells))
    print()
    print("  VARIANCE IS THE TARGET'S NORMAL STATE.  If the post-break column spreads")
    print("  across every band from negative to >150, then a cycle landing at +$3 and")
    print("  another at +$60 are the SAME rule sampling different market paths, not two")
    print("  different behaviours -- and a replica that produced only tight +$30 exits")
    print("  would be the one out of parity.")

    rule("E. THE LIVE SWEEP, LEG BY LEG  (the cycle the audit narrative describes)")
    if not vant:
        print("  no 4+ leg sweep in .cache/vantage")
    for r in vant:
        print(f"  cycle {r['i']}  flatten began {r['t0']:%Y-%m-%d %H:%M:%S}"
              f"   {len(r['sw'])} legs   span {r['span']:.1f}s"
              f"   {r['per']:.2f} s/close")
        print(f"    realised BEFORE the flatten (stop-outs) : {r['pre']:>+9.2f}")
        print(f"    the sweep itself                        : {r['burst']:>+9.2f}")
        print(f"    cycle exit                              : "
              f"{r['pre'] + r['burst']:>+9.2f}")
        print()
        print(f"    {'#':>2} {'closed':>12} {'opened':>12} {'side':>5} {'vol':>5}"
              f" {'entry':>9} {'exit':>9} {'net':>8} {'orank':>6}  comment")
        byopen = sorted(r["sw"], key=lambda p: p.open_time)
        orank = {id(p): i + 1 for i, p in enumerate(byopen)}
        for k, p in enumerate(r["sw"], start=1):
            print(f"    {k:>2} {p.close_time:%H:%M:%S.%f}"[:22]
                  + f" {p.open_time:%H:%M:%S}"[:13]
                  + f" {p.side:>5} {p.volume:>5.2f}"
                  f" {p.open_price:>9.2f} {p.close_price:>9.2f}"
                  f" {p.net:>+8.2f} {orank[id(p)]:>6}  {p.comment}")
        ro = spearman(list(range(len(r["sw"]))),
                      [p.open_time.timestamp() for p in r["sw"]])
        rp = spearman(list(range(len(r["sw"]))), [p.net for p in r["sw"]])
        print()
        print(f"    rho(close order, open time) = {ro:+.3f}"
              f"   rho(close order, P&L) = {rp:+.3f}")
        print("    Neither is -1.000.  The loop has no sort at all: it walks MT5's")
        print("    position index from the top down, and that index COMPACTS as each")
        print("    position is removed, so raw index order only leans newest-first.")


if __name__ == "__main__":
    main()
