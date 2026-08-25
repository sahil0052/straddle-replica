"""Q3i: which ledger does the target sit on?  A model-free discriminator.

At the flatten the EA liquidates at market, so the flatten's own net IS the floating
it saw.  Nothing has to be interpolated.  That splits the decision quantity into two
independently observable sums:

    realized_before  = sum of nets of positions closed BEFORE the flatten
    flatten_net      = sum of nets of the positions the flatten closed  ( = floating )

Two rival rules make opposite predictions about which of these is pinned to $30:

    H1  cycle basket:   realized_before + flatten_net  ~ 30      (CCycleDealLedger)
    H2  equity-balance: flatten_net                    ~ 30      (equity - balance,
                                                                  i.e. floating only)

On short cycles realized_before ~ 0 and the two are indistinguishable.  The LONG
cycles, where realized_before is large, are the discriminating set -- and they are
exactly the cycles that falsify H1.  So bin by realized_before and watch which
column stays pinned.
"""
from __future__ import annotations

import statistics
import sys
from collections import defaultdict

sys.path.insert(0, r"C:\websites\mt5 2")
from tools.forensics.dataset import load_all, FINAL_REGIME_START  # noqa: E402
from tools.forensics.attribution import build_exit_index, attribute  # noqa: E402


def stats(vals, label):
    if not vals:
        print(f"    {label:<26} n=0")
        return
    v = sorted(vals)
    g = lambda f: v[int(f * (len(v) - 1))]
    print(f"    {label:<26} n={len(v):<4} min={v[0]:>9.2f} p25={g(.25):>8.2f} "
          f"med={statistics.median(v):>8.2f} p75={g(.75):>8.2f} max={v[-1]:>9.2f}")


def main() -> None:
    orders, positions, deals, cycles = load_all()
    class_by_time, _, _ = build_exit_index(orders, deals)
    reason, _, _ = attribute(positions, class_by_time)

    pos_by_cycle = defaultdict(list)
    for p in positions:
        if p.cycle >= 0:
            pos_by_cycle[p.cycle].append(p)

    rows = []
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
        span = (last_close - first_close).total_seconds()

        before = [p for p in ps if not p.is_open and p.close_time
                  and p.close_time < first_close]
        realized_before = sum(p.net for p in before)
        flatten_net = sum(p.net for p in closes)
        vol_closed = sum(p.volume for p in closes)
        rows.append(dict(
            cyc=c.index, start=c.start, decision=first_close, span=span,
            realized_before=realized_before, flatten_net=flatten_net,
            total=realized_before + flatten_net,
            n_before=len(before), n_close=len(closes),
            dpp=vol_closed * 100.0,
            hrs=(first_close - c.start).total_seconds() / 3600.0,
            still_open=sum(1 for p in ps if p.is_open),
        ))

    fast = [r for r in rows if r["span"] <= 5.0 and r["still_open"] == 0]
    print(f"final-regime cycles with a flatten: {len(rows)}")
    print(f"  of which fast (<=5s) and fully closed: {len(fast)}\n")

    print("=" * 100)
    print("A.  THE TWO SUMS, OVER ALL FAST FLATTENS")
    print("=" * 100)
    stats([r["realized_before"] for r in fast], "realized_before")
    stats([r["flatten_net"] for r in fast], "flatten_net (= floating)")
    stats([r["total"] for r in fast], "H1: sum of the two")

    print("\n" + "=" * 100)
    print("B.  BINNED BY realized_before -- the discriminator")
    print("    H1 predicts the 'total' column stays pinned near 30 in every bin.")
    print("    H2 predicts the 'flatten_net' column stays pinned instead.")
    print("=" * 100)
    bins = [(-10**9, 1.0), (1.0, 25.0), (25.0, 75.0), (75.0, 200.0), (200.0, 10**9)]
    print(f"  {'realized_before bin':<22} {'n':>4} | {'med flatten_net':>16} "
          f"{'med total':>11} | {'|fn-30|':>9} {'|tot-30|':>9}")
    for lo, hi in bins:
        g = [r for r in fast if lo <= r["realized_before"] < hi]
        if not g:
            continue
        mfn = statistics.median([r["flatten_net"] for r in g])
        mt = statistics.median([r["total"] for r in g])
        efn = statistics.median([abs(r["flatten_net"] - 30.0) for r in g])
        et = statistics.median([abs(r["total"] - 30.0) for r in g])
        lab = f"[{lo if lo > -10**9 else '-inf':>6},{hi if hi < 10**9 else 'inf':>6})"
        print(f"  {lab:<22} {len(g):>4} | {mfn:>16.2f} {mt:>11.2f} | "
              f"{efn:>9.2f} {et:>9.2f}")

    print("\n  same, absolute-error totals across all fast flattens:")
    e1 = [abs(r["total"] - 30.0) for r in fast]
    e2 = [abs(r["flatten_net"] - 30.0) for r in fast]
    print(f"    H1  median |total - 30|       = {statistics.median(e1):>8.2f}   "
          f"within $5: {sum(1 for x in e1 if x <= 5):>3}/{len(e1)}")
    print(f"    H2  median |flatten_net - 30| = {statistics.median(e2):>8.2f}   "
          f"within $5: {sum(1 for x in e2 if x <= 5):>3}/{len(e2)}")

    print("\n" + "=" * 100)
    print("C.  THE LONG / HEAVILY-BANKED CYCLES, ONE LINE EACH")
    print("    (realized_before >= 75 -- where the two hypotheses disagree most)")
    print("=" * 100)
    print(f"  {'cyc':>4} {'start':<17} {'decision':<17} {'hrs':>6} {'$/pt':>6} "
          f"{'nB':>4} {'nC':>3} {'real_before':>12} {'flatten_net':>12} {'H1 total':>10}")
    for r in sorted((x for x in rows if x["realized_before"] >= 75.0),
                    key=lambda r: -r["realized_before"]):
        print(f"  {r['cyc']:>4} {r['start'].strftime('%m-%d %H:%M:%S'):<17} "
              f"{r['decision'].strftime('%m-%d %H:%M:%S'):<17} {r['hrs']:>6.1f} "
              f"{r['dpp']:>6.1f} {r['n_before']:>4} {r['n_close']:>3} "
              f"{r['realized_before']:>12.2f} {r['flatten_net']:>12.2f} "
              f"{r['total']:>10.2f}")

    print("\n" + "=" * 100)
    print("D.  HISTOGRAMS, FAST FLATTENS -- which one has the sharp edge at 30?")
    print("=" * 100)
    for key, lab in (("total", "H1  realized_before + flatten_net"),
                     ("flatten_net", "H2  flatten_net alone")):
        v = sorted(r[key] for r in fast)
        print(f"\n  {lab}")
        for lo, hi in [(-10**9, -25), (-25, 0), (0, 10), (10, 20), (20, 25),
                       (25, 28), (28, 30), (30, 32), (32, 35), (35, 40),
                       (40, 60), (60, 10**9)]:
            n = sum(1 for x in v if lo <= x < hi)
            tag = f"[{lo if lo > -10**9 else '-inf':>5},{hi if hi < 10**9 else 'inf':>5})"
            print(f"    {tag:<15}{n:>4} {'#' * n}")


if __name__ == "__main__":
    main()
