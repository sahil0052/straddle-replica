"""Q3j: rebuild the basket ledger with the EA's OWN scope, not mine.

The defect in every earlier test: I bucketed positions into cycles by OPEN time and
then summed within the bucket.  That is not what the EA sees.

  OwnedFloatingProfit()  iterates every position currently open with the magic
                         number -- including ones a PREVIOUS lattice opened and
                         left behind.  A deep survivor keeps dragging the basket
                         down after a re-centre.

  CCycleDealLedger       sums every exit deal whose DEAL_TIME_MSC >= cycle start,
                         regardless of when the position was OPENED.  A survivor
                         from the previous lattice banks into the NEW cycle.

So the quantity the EA actually tests is, at time t inside a cycle starting at S:

    realized(t) = sum of nets of ALL positions closed in [S, t]
    floating(t) = sum of ALL positions open at t, marked to market
    total(t)    = realized(t) + floating(t)                     >= 30 ?

Both sums are cycle-agnostic: membership is by TIME ALIVE, not by which burst
deployed the order.  This run re-applies the falsification test under that scope.
"""
from __future__ import annotations

import statistics
import sys
from bisect import bisect_left, bisect_right

sys.path.insert(0, r"C:\websites\mt5 2")
from tools.forensics.dataset import load_all, FINAL_REGIME_START, CONTRACT  # noqa: E402
from tools.forensics.attribution import build_exit_index, attribute  # noqa: E402

TARGET = 30.0
SPREAD_PTS = 0.35


def stats(vals, label):
    if not vals:
        print(f"  {label:<32} n=0")
        return
    v = sorted(vals)
    g = lambda f: v[int(f * (len(v) - 1))]
    print(f"  {label:<32} n={len(v):<4} min={v[0]:>9.2f} p10={g(.1):>8.2f} "
          f"med={statistics.median(v):>8.2f} p75={g(.75):>8.2f} "
          f"p90={g(.9):>8.2f} max={v[-1]:>9.2f}")


def main() -> None:
    orders, positions, deals, cycles = load_all()
    class_by_time, _, _ = build_exit_index(orders, deals)
    reason, _, _ = attribute(positions, class_by_time)

    # every position in the final regime, regardless of cycle assignment
    live = [p for p in positions if p.open_time >= FINAL_REGIME_START
            or (p.close_time and p.close_time >= FINAL_REGIME_START)]
    live.sort(key=lambda p: p.open_time)
    open_times = [p.open_time for p in live]

    prints = []
    for p in live:
        prints.append((p.open_time, p.open_price))
        if p.close_time and p.close_price:
            prints.append((p.close_time, p.close_price))
    prints.sort()
    pt_t = [t for t, _ in prints]
    pt_p = [x for _, x in prints]

    def snapshot(t, S):
        """EA-scope ledger at time t for a cycle that started at S."""
        realized = floating = vol = 0.0
        nopen = 0
        hi = bisect_right(open_times, t)
        for p in live[:hi]:
            if not p.is_open and p.close_time and p.close_time <= t:
                if p.close_time >= S:
                    realized += p.net
            else:
                nopen += 1
                vol += p.volume
        return realized, floating, vol, nopen

    rows = []
    for c in cycles:
        if c.start < FINAL_REGIME_START:
            continue
        S = c.start
        # the flatten sweep, cycle-agnostic: STR CLOSE exits after S
        closes = [p for p in live if not p.is_open and p.close_time
                  and p.close_time >= S
                  and reason.get(p.position_id) == "STR CLOSE"]
        if not closes:
            continue
        first_close = min(p.close_time for p in closes)
        # keep only the sweep contiguous with the first close (<=120s gaps)
        sweep = sorted((p for p in closes
                        if (p.close_time - first_close).total_seconds() <= 1800),
                       key=lambda p: p.close_time)
        run = [sweep[0]]
        for prev, cur in zip(sweep, sweep[1:]):
            if (cur.close_time - prev.close_time).total_seconds() <= 120.0:
                run.append(cur)
            else:
                break
        sweep = run
        last_close = max(p.close_time for p in sweep)
        span = (last_close - first_close).total_seconds()

        realized_before = sum(p.net for p in live
                              if not p.is_open and p.close_time
                              and S <= p.close_time < first_close)
        flatten_net = sum(p.net for p in sweep)
        exact_total = realized_before + flatten_net

        i0 = bisect_left(pt_t, S)
        i1 = bisect_right(pt_t, first_close)
        series = []
        hi_cache = 0
        for i in range(i0, i1):
            t, mk = pt_t[i], pt_p[i]
            realized = floating = vol = 0.0
            nopen = 0
            hi = bisect_right(open_times, t)
            for p in live[:hi]:
                if not p.is_open and p.close_time and p.close_time <= t:
                    if p.close_time >= S:
                        realized += p.net
                else:
                    floating += p.dir * (mk - p.open_price) * p.volume * CONTRACT
                    vol += p.volume
                    nopen += 1
            series.append((t, realized, floating, vol * CONTRACT, nopen))
        if not series:
            continue

        pre = [(t, r + f, dpp) for t, r, f, dpp, _ in series
               if (first_close - t).total_seconds() > 25.0]
        premax = max((v for _, v, _ in pre), default=None)
        best_run = 0.0
        cur = None
        for t, v, dpp in pre:
            if v >= TARGET + SPREAD_PTS * dpp:
                if cur is None:
                    cur = t
                best_run = max(best_run, (t - cur).total_seconds())
            else:
                cur = None

        rows.append(dict(cyc=c.index, start=S, decision=first_close, span=span,
                         realized_before=realized_before, flatten_net=flatten_net,
                         exact_total=exact_total, premax=premax,
                         sustained=best_run, n_sweep=len(sweep),
                         dpp=series[-1][3], nopen=series[-1][4],
                         interp=series[-1][1] + series[-1][2],
                         hrs=(first_close - S).total_seconds() / 3600.0))

    print(f"final-regime cycles: {len(rows)}\n")
    print("=" * 100)
    print("A.  EXACT TOTAL AT THE DECISION, EA SCOPE  (no price interpolated)")
    print("=" * 100)
    fast = [r for r in rows if r["span"] <= 5.0]
    stats([r["exact_total"] for r in rows], "all cycles")
    stats([r["exact_total"] for r in fast], "fast flattens (span<=5s)")
    stats([r["realized_before"] for r in fast], "  realized_before")
    stats([r["flatten_net"] for r in fast], "  flatten_net (= floating)")
    e = [abs(r["exact_total"] - TARGET) for r in fast]
    print(f"\n  |total - 30| : med {statistics.median(e):.2f}   "
          f"<=$5 {sum(1 for x in e if x <= 5)}/{len(e)}   "
          f"<=$10 {sum(1 for x in e if x <= 10)}/{len(e)}   "
          f"<=$20 {sum(1 for x in e if x <= 20)}/{len(e)}")

    print("\n" + "=" * 100)
    print("B.  FALSIFICATION TEST UNDER EA SCOPE")
    print("    pre-decision maximum must stay BELOW the target on every earlier tick")
    print("=" * 100)
    pm = sorted(r["premax"] for r in rows if r["premax"] is not None)
    g = lambda f: pm[int(f * (len(pm) - 1))]
    print(f"  pre-decision max: n={len(pm)} p25={g(.25):.2f} "
          f"med={statistics.median(pm):.2f} p75={g(.75):.2f} p90={g(.9):.2f} "
          f"max={pm[-1]:.2f}")
    print(f"  below 30: {sum(1 for v in pm if v < 30)}/{len(pm)}  "
          f"below 32: {sum(1 for v in pm if v < 32)}/{len(pm)}")
    for lo, hi in [(-10**9, 0), (0, 10), (10, 20), (20, 25), (25, 28), (28, 30),
                   (30, 32), (32, 40), (40, 10**9)]:
        n = sum(1 for v in pm if lo <= v < hi)
        lab = f"[{lo if lo > -10**9 else '-inf':>5},{hi if hi < 10**9 else 'inf':>5})"
        print(f"    {lab:<15}{n:>4} {'#' * n}")

    sus = [r for r in rows if r["sustained"] > 300]
    print(f"\n  SUSTAINED excursions >5min (spread-adjusted): {len(sus)}/{len(rows)}")
    if sus:
        print(f"  {'cyc':>4} {'excursion':>10} {'decision':<18} {'$/pt':>7} "
              f"{'op':>3} {'hrs':>6} {'real_bef':>10} {'flat_net':>10} {'total':>9}")
        for r in sorted(sus, key=lambda r: -r["sustained"]):
            print(f"  {r['cyc']:>4} {r['sustained']/60:>8.1f}m  "
                  f"{r['decision'].strftime('%m-%d %H:%M:%S'):<18} {r['dpp']:>7.1f} "
                  f"{r['nopen']:>3} {r['hrs']:>6.1f} {r['realized_before']:>10.2f} "
                  f"{r['flatten_net']:>10.2f} {r['exact_total']:>9.2f}")

    print("\n" + "=" * 100)
    print("C.  BELOW-TARGET EXITS -- the second rule")
    print("    cycles that flattened with an exact total well under the target")
    print("=" * 100)
    low = sorted((r for r in rows if r["exact_total"] < 20.0),
                 key=lambda r: r["exact_total"])
    print(f"  n={len(low)}/{len(rows)}")
    print(f"  {'cyc':>4} {'decision':<18} {'hrs':>6} {'$/pt':>7} {'op':>3} "
          f"{'nSweep':>7} {'real_bef':>10} {'flat_net':>10} {'total':>9} {'premax':>9}")
    for r in low:
        print(f"  {r['cyc']:>4} {r['decision'].strftime('%m-%d %H:%M:%S'):<18} "
              f"{r['hrs']:>6.1f} {r['dpp']:>7.1f} {r['nopen']:>3} {r['n_sweep']:>7} "
              f"{r['realized_before']:>10.2f} {r['flatten_net']:>10.2f} "
              f"{r['exact_total']:>9.2f} "
              f"{r['premax'] if r['premax'] is not None else -1:>9.2f}")


if __name__ == "__main__":
    main()
