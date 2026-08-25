"""Q3m: re-derive cycle boundaries from FLATTEN SWEEPS, not deployment bursts.

Every earlier run keyed the ledger to a deployment burst.  That is not the EA's own
boundary.  In the engine a cycle starts at StartCycle(), which is only reachable from
CYCLE_IDLE -- and IDLE is only reached after the basket has been completely closed.
So the true reset point is the END OF A FLATTEN SWEEP.

If a re-centre deploys a fresh lattice WITHOUT flattening first (cycle 175 proves the
EA does this: 34 positions open at once, more than one lattice), then a burst-keyed
ledger starts realized over from zero mid-cycle and undercounts it.  That is exactly
the error that would make a $30 exit look like a -$170 distress exit.

So: segment the final regime by flatten sweeps, and re-run the whole test.
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
        print(f"  {label:<34} n=0")
        return
    v = sorted(vals)
    g = lambda f: v[int(f * (len(v) - 1))]
    print(f"  {label:<34} n={len(v):<4} min={v[0]:>9.2f} p10={g(.1):>8.2f} "
          f"med={statistics.median(v):>8.2f} p75={g(.75):>8.2f} max={v[-1]:>9.2f}")


def main() -> None:
    orders, positions, deals, cycles = load_all()
    class_by_time, _, _ = build_exit_index(orders, deals)
    reason, _, _ = attribute(positions, class_by_time)

    live = [p for p in positions
            if (p.open_time >= FINAL_REGIME_START
                or (p.close_time and p.close_time >= FINAL_REGIME_START))]
    live.sort(key=lambda p: p.open_time)
    open_times = [p.open_time for p in live]

    prints = sorted([(p.open_time, p.open_price) for p in live] +
                    [(p.close_time, p.close_price) for p in live
                     if p.close_time and p.close_price])
    pt_t = [t for t, _ in prints]
    pt_p = [x for _, x in prints]

    # ---- 1.  find the flatten sweeps -----------------------------------------
    closers = sorted((p for p in live if not p.is_open and p.close_time
                      and reason.get(p.position_id) == "STR CLOSE"),
                     key=lambda p: p.close_time)
    sweeps = []
    cur = [closers[0]]
    for prev, nxt in zip(closers, closers[1:]):
        if (nxt.close_time - prev.close_time).total_seconds() <= 120.0:
            cur.append(nxt)
        else:
            sweeps.append(cur)
            cur = [nxt]
    sweeps.append(cur)
    sweeps = [s for s in sweeps if s[0].close_time >= FINAL_REGIME_START]
    print(f"flatten sweeps in the final regime: {len(sweeps)}")
    print(f"  sweep sizes: med {statistics.median([len(s) for s in sweeps]):.0f}  "
          f"min {min(len(s) for s in sweeps)}  max {max(len(s) for s in sweeps)}")

    # ---- 2.  a cycle is (end of previous sweep, first close of this sweep] ----
    rows = []
    for i, sw in enumerate(sweeps):
        first_close = sw[0].close_time
        last_close = sw[-1].close_time
        S = sweeps[i - 1][-1].close_time if i > 0 else None
        if S is None:
            continue
        # was the basket genuinely flat at S?  (nothing open right after)
        open_at_S = [p for p in live if p.open_time <= S
                     and (p.is_open or (p.close_time and p.close_time > S))]
        span = (last_close - first_close).total_seconds()

        realized_before = sum(p.net for p in live if not p.is_open and p.close_time
                              and S < p.close_time < first_close)
        mk = sw[0].close_price
        floating_at = sum(p.dir * (mk - p.open_price) * p.volume * CONTRACT
                          for p in sw)
        marked = realized_before + floating_at
        sweep_total = realized_before + sum(p.net for p in sw)

        # pre-decision series under this segmentation
        i0, i1 = bisect_left(pt_t, S), bisect_right(pt_t, first_close)
        premax = None
        best_run = 0.0
        curstart = None
        for k in range(i0, i1):
            t, m = pt_t[k], pt_p[k]
            r = f = vol = 0.0
            hi = bisect_right(open_times, t)
            for p in live[:hi]:
                if not p.is_open and p.close_time and p.close_time <= t:
                    if p.close_time > S:
                        r += p.net
                else:
                    f += p.dir * (m - p.open_price) * p.volume * CONTRACT
                    vol += p.volume
            tot = r + f
            if (first_close - t).total_seconds() > 25.0:
                premax = tot if premax is None else max(premax, tot)
                if tot >= TARGET + SPREAD_PTS * vol * CONTRACT:
                    if curstart is None:
                        curstart = t
                    best_run = max(best_run, (t - curstart).total_seconds())
                else:
                    curstart = None

        rows.append(dict(idx=i, start=S, decision=first_close, span=span,
                         n=len(sw), realized_before=realized_before,
                         floating_at=floating_at, marked=marked,
                         sweep_total=sweep_total, premax=premax,
                         sustained=best_run, open_at_S=len(open_at_S),
                         dpp=sum(p.volume for p in sw) * CONTRACT,
                         hrs=(first_close - S).total_seconds() / 3600.0))

    print(f"cycles delimited by flattens: {len(rows)}")
    print(f"  cycles where the basket was NOT flat at the boundary: "
          f"{sum(1 for r in rows if r['open_at_S'] > 0)}/{len(rows)}\n")

    print("=" * 100)
    print("A.  MARKED TOTAL AT THE DECISION, FLATTEN-DELIMITED CYCLES")
    print("=" * 100)
    stats([r["realized_before"] for r in rows], "realized since last flatten")
    stats([r["floating_at"] for r in rows], "floating at first close")
    stats([r["marked"] for r in rows], "marked total")
    stats([r["sweep_total"] for r in rows], "sweep total")
    e = [abs(r["marked"] - TARGET) for r in rows]
    print(f"\n  |marked - 30| : med {statistics.median(e):.2f}   "
          f"<=$5 {sum(1 for x in e if x <= 5)}/{len(e)}   "
          f"<=$10 {sum(1 for x in e if x <= 10)}/{len(e)}   "
          f"<=$20 {sum(1 for x in e if x <= 20)}/{len(e)}")
    print(f"  marked >= 25 : {sum(1 for r in rows if r['marked'] >= 25)}/{len(rows)}")
    print(f"  marked <   0 : {sum(1 for r in rows if r['marked'] < 0)}/{len(rows)}")

    print("\n" + "=" * 100)
    print("B.  HISTOGRAM OF THE MARKED TOTAL")
    print("=" * 100)
    v = sorted(r["marked"] for r in rows)
    for lo, hi in [(-10**9, -50), (-50, -25), (-25, -10), (-10, 0), (0, 10),
                   (10, 20), (20, 25), (25, 28), (28, 30), (30, 32), (32, 35),
                   (35, 40), (40, 50), (50, 75), (75, 10**9)]:
        n = sum(1 for x in v if lo <= x < hi)
        tag = f"[{lo if lo > -10**9 else '-inf':>5},{hi if hi < 10**9 else 'inf':>5})"
        print(f"    {tag:<15}{n:>4} {'#' * n}")

    print("\n" + "=" * 100)
    print("C.  FALSIFICATION UNDER THIS SEGMENTATION")
    print("=" * 100)
    pm = sorted(r["premax"] for r in rows if r["premax"] is not None)
    g = lambda f: pm[int(f * (len(pm) - 1))]
    print(f"  pre-decision max: n={len(pm)} med={statistics.median(pm):.2f} "
          f"p75={g(.75):.2f} p90={g(.9):.2f} max={pm[-1]:.2f}")
    print(f"  below 30: {sum(1 for x in pm if x < 30)}/{len(pm)}   "
          f"below 32: {sum(1 for x in pm if x < 32)}/{len(pm)}")
    sus = [r for r in rows if r["sustained"] > 300]
    print(f"  SUSTAINED excursions > 5 min: {len(sus)}/{len(rows)}")
    for r in sorted(sus, key=lambda r: -r["sustained"]):
        print(f"    idx={r['idx']:<4} excursion={r['sustained']/60:>7.1f}m  "
              f"decision={r['decision'].strftime('%m-%d %H:%M:%S')}  "
              f"$/pt={r['dpp']:>6.1f}  hrs={r['hrs']:>6.1f}  "
              f"marked={r['marked']:>9.2f}")

    print("\n" + "=" * 100
          )
    print("D.  CYCLES STILL BELOW ZERO")
    print("=" * 100)
    low = sorted((r for r in rows if r["marked"] < 0), key=lambda r: r["marked"])
    print(f"  {'idx':>4} {'decision':<18} {'hrs':>6} {'$/pt':>7} {'n':>3} "
          f"{'openAtS':>8} {'real_bef':>10} {'float_at':>10} {'marked':>9}")
    for r in low:
        print(f"  {r['idx']:>4} {r['decision'].strftime('%m-%d %H:%M:%S'):<18} "
              f"{r['hrs']:>6.1f} {r['dpp']:>7.1f} {r['n']:>3} {r['open_at_S']:>8} "
              f"{r['realized_before']:>10.2f} {r['floating_at']:>10.2f} "
              f"{r['marked']:>9.2f}")


if __name__ == "__main__":
    main()
