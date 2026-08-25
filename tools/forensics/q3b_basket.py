"""Q3b: the basket exit condition, measured at the true DECISION instant.

Two corrections over q3_basket.py:

 1. DECISION INSTANT.  cancel_before_close=true, so the terminal pass cancels
    every armed pending BEFORE closing anything (armed-pendings-at-first-close
    was already 0).  The decision therefore happens at the first cancel of the
    terminal sweep, not at the first close.

 2. LEDGER BOUNDARY.  Cycle 175 shows 34 simultaneously-open positions -- more
    than one lattice -- so the EA re-centres (re-deploys a fresh lattice) WITHOUT
    flattening.  A deployment burst is therefore not necessarily a ledger reset.
    Two boundaries are tested:
       (A) burst  : realized accumulated since this lattice was deployed
       (B) flatten: realized accumulated since the previous basket flatten
    Whichever pins the trigger total to a constant is the EA's real ledger.

Market price at the decision instant is interpolated from the global observation
series (every fill and every close is a timestamped price print).
"""
from __future__ import annotations

import statistics
import sys
from bisect import bisect_left
from collections import defaultdict

sys.path.insert(0, r"C:\websites\mt5 2")
from tools.forensics.dataset import load_all, FINAL_REGIME_START, CONTRACT  # noqa: E402
from tools.forensics.attribution import build_exit_index, attribute  # noqa: E402


def stats(vals, label):
    if not vals:
        print(f"  {label:<32} n=0")
        return
    v = sorted(vals)
    g = lambda f: v[int(f * (len(v) - 1))]
    print(f"  {label:<32} n={len(v):<4} min={v[0]:>9.2f} p10={g(.1):>8.2f} "
          f"p25={g(.25):>8.2f} med={statistics.median(v):>8.2f} p75={g(.75):>8.2f} "
          f"p90={g(.9):>8.2f} max={v[-1]:>9.2f}")


def main() -> None:
    orders, positions, deals, cycles = load_all()
    class_by_time, _, _ = build_exit_index(orders, deals)
    reason, _, _ = attribute(positions, class_by_time)

    # ---- global price observation series -----------------------------------
    pts = []
    for p in positions:
        pts.append((p.open_time, p.open_price))
        if p.close_time and p.close_price:
            pts.append((p.close_time, p.close_price))
    pts.sort()
    obs_t = [t for t, _ in pts]
    obs_p = [p for _, p in pts]

    def market_at(t):
        i = bisect_left(obs_t, t)
        cands = []
        if i < len(obs_t):
            cands.append((abs((obs_t[i] - t).total_seconds()), obs_p[i]))
        if i > 0:
            cands.append((abs((t - obs_t[i - 1]).total_seconds()), obs_p[i - 1]))
        d, px = min(cands)
        return px, d

    pos_by_cycle = defaultdict(list)
    for p in positions:
        if p.cycle >= 0:
            pos_by_cycle[p.cycle].append(p)

    # ---- terminal cancel sweep per cycle -----------------------------------
    rows = []
    prev_flatten = {}          # cycle index -> end of previous flatten
    last_flatten_time = None
    for c in cycles:
        ps = pos_by_cycle.get(c.index, [])
        closes = [p for p in ps if not p.is_open and p.close_time
                  and reason.get(p.position_id) == "STR CLOSE"]
        prev_flatten[c.index] = last_flatten_time
        if closes:
            last_flatten_time = max(p.close_time for p in closes)

    for c in cycles:
        if c.start < FINAL_REGIME_START:
            continue
        ps = pos_by_cycle.get(c.index, [])
        closes = [p for p in ps if not p.is_open and p.close_time
                  and reason.get(p.position_id) == "STR CLOSE"]
        if not closes:
            continue
        first_close = min(p.close_time for p in closes)
        last_close = max(p.close_time for p in closes)

        # terminal cancel sweep: grid cancels in the 10 min before first_close,
        # taken as the contiguous run ending at/just before first_close
        cans = sorted(o.end_time for o in c.orders
                      if o.is_grid and o.state == "canceled" and o.end_time
                      and o.end_time <= first_close)
        sweep_start = None
        if cans:
            run = [cans[-1]]
            for a, b in zip(reversed(cans[:-1]), reversed(cans)):
                if (b - a).total_seconds() <= 30.0:
                    run.append(a)
                else:
                    break
            sweep_start = min(run)
            n_sweep = len(run)
        else:
            n_sweep = 0
        decision = sweep_start or first_close
        lag = (first_close - decision).total_seconds()

        market, obs_lag = market_at(decision)

        # ledger A: since burst start of this lattice
        # ledger B: since previous flatten completed
        bound_b = prev_flatten.get(c.index) or c.start

        def evaluate(t0, extra_positions):
            realized = 0.0
            floating = 0.0
            nopen = 0
            for p in extra_positions:
                if p.open_time > decision:
                    continue
                closed_before = (not p.is_open and p.close_time
                                 and p.close_time <= decision)
                if closed_before:
                    if p.close_time >= t0:
                        realized += p.net
                else:
                    d = 1.0 if p.side == "buy" else -1.0
                    floating += d * (market - p.open_price) * p.volume * CONTRACT
                    nopen += 1
            return realized, floating, nopen

        rA = evaluate(c.start, ps)
        # ledger B needs every position alive/closed in the window, not just
        # those tagged to this cycle
        allp = [p for p in positions
                if p.open_time <= decision
                and (p.is_open or (p.close_time and p.close_time >= bound_b))]
        rB = evaluate(bound_b, allp)

        rows.append(dict(cyc=c.index, decision=decision, lag=lag,
                         n_sweep=n_sweep, obs_lag=obs_lag, market=market,
                         step=c.step, anchor=c.anchor,
                         rA=rA[0], fA=rA[1], nA=rA[2],
                         rB=rB[0], fB=rB[1], nB=rB[2],
                         tA=rA[0] + rA[1], tB=rB[0] + rB[1],
                         nclose=len(closes),
                         span=(last_close - first_close).total_seconds()))

    print(f"cycles measured: {len(rows)}\n")
    print("=" * 100)
    print("DECISION-INSTANT QUALITY")
    print("=" * 100)
    stats([r["lag"] for r in rows], "cancel-sweep -> first close (s)")
    stats([r["n_sweep"] for r in rows], "pendings cancelled in sweep")
    stats([r["obs_lag"] for r in rows], "nearest price print (s away)")
    stats([r["span"] for r in rows], "flatten span first->last (s)")
    stats([r["span"] / max(1, r["nclose"] - 1) for r in rows if r["nclose"] > 1],
          "seconds per closed position")

    print("\n" + "=" * 100)
    print("TRIGGER QUANTITIES -- LEDGER A (since lattice deployment)")
    print("=" * 100)
    stats([r["rA"] for r in rows], "realized")
    stats([r["fA"] for r in rows], "floating")
    stats([r["tA"] for r in rows], "realized + floating")
    print("\n" + "=" * 100)
    print("TRIGGER QUANTITIES -- LEDGER B (since previous flatten)")
    print("=" * 100)
    stats([r["rB"] for r in rows], "realized")
    stats([r["fB"] for r in rows], "floating")
    stats([r["tB"] for r in rows], "realized + floating")

    for key, lab in (("tA", "A"), ("tB", "B")):
        v = [r[key] for r in rows]
        print(f"\n  ledger {lab}: >=30 {sum(1 for x in v if x >= 30):>3}/{len(v)}  "
              f"[29,32] {sum(1 for x in v if 29 <= x <= 32):>3}  "
              f"[28,34] {sum(1 for x in v if 28 <= x <= 34):>3}  "
              f"[25,40] {sum(1 for x in v if 25 <= x <= 40):>3}  "
              f"<25 {sum(1 for x in v if x < 25):>3}  "
              f"med={statistics.median(v):.2f}")

    print("\n" + "=" * 100)
    print("PER-CYCLE (sorted by ledger-A total)")
    print("=" * 100)
    print(f"  {'cyc':>4} {'decision':<20} {'lag':>6} {'sw':>3} "
          f"{'realA':>9} {'floatA':>9} {'TOTA':>8} {'nA':>3} "
          f"{'realB':>9} {'floatB':>9} {'TOTB':>8} {'nB':>3} {'ncl':>4}")
    for r in sorted(rows, key=lambda r: r["tA"]):
        print(f"  {r['cyc']:>4} {r['decision'].strftime('%Y-%m-%d %H:%M:%S'):<20} "
              f"{r['lag']:>6.1f} {r['n_sweep']:>3} "
              f"{r['rA']:>9.2f} {r['fA']:>9.2f} {r['tA']:>8.2f} {r['nA']:>3} "
              f"{r['rB']:>9.2f} {r['fB']:>9.2f} {r['tB']:>8.2f} {r['nB']:>3} "
              f"{r['nclose']:>4}")


if __name__ == "__main__":
    main()
