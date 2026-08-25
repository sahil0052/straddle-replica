"""Q3e: recover the target T by interval censoring.

If the rule is "flatten when realized+floating >= T, checked every 20s", then for
the true T and only the true T:

    lag(T) = decision_time - (first time the basket total reached T)   <=  ~20s

For T below the truth the lag is far too long (the EA would have fired much
earlier); for T above the truth the crossing never happens at all.  So sweeping T
and looking for the value that collapses lag to a single timer tick is a direct
estimator of the threshold -- and it never requires knowing the basket total
exactly, only its crossing time.

The basket total is evaluated at every price print (every fill and every close in
the whole account is a timestamped price observation).
"""
from __future__ import annotations

import statistics
import sys
from bisect import bisect_left, bisect_right
from collections import defaultdict

sys.path.insert(0, r"C:\websites\mt5 2")
from tools.forensics.dataset import load_all, FINAL_REGIME_START, CONTRACT  # noqa: E402
from tools.forensics.attribution import build_exit_index, attribute  # noqa: E402

CANDIDATES = [10.0, 15.0, 20.0, 25.0, 28.0, 29.0, 30.0, 31.0, 32.0, 35.0, 40.0, 50.0]


def main() -> None:
    orders, positions, deals, cycles = load_all()
    class_by_time, _, _ = build_exit_index(orders, deals)
    reason, _, _ = attribute(positions, class_by_time)

    prints = []
    for p in positions:
        prints.append((p.open_time, p.open_price))
        if p.close_time and p.close_price:
            prints.append((p.close_time, p.close_price))
    prints.sort()
    pt_t = [t for t, _ in prints]
    pt_p = [x for _, x in prints]

    pos_by_cycle = defaultdict(list)
    for p in positions:
        if p.cycle >= 0:
            pos_by_cycle[p.cycle].append(p)

    per_cycle = []
    for c in cycles:
        if c.start < FINAL_REGIME_START:
            continue
        ps = pos_by_cycle.get(c.index, [])
        closes = [p for p in ps if not p.is_open and p.close_time
                  and reason.get(p.position_id) == "STR CLOSE"]
        if not closes:
            continue
        first_close = min(p.close_time for p in closes)
        cans = sorted(o.end_time for o in c.orders
                      if o.is_grid and o.state == "canceled" and o.end_time
                      and o.end_time <= first_close)
        decision = first_close
        if cans:
            run = [cans[-1]]
            for a, b in zip(reversed(cans[:-1]), reversed(cans)):
                if (b - a).total_seconds() <= 30.0:
                    run.append(a)
                else:
                    break
            decision = min(run)

        # ---- basket total as a function of a print index -------------------
        i0 = bisect_left(pt_t, c.start)
        i1 = bisect_right(pt_t, decision)
        series = []
        for i in range(i0, i1):
            t, mk = pt_t[i], pt_p[i]
            realized = 0.0
            floating = 0.0
            vol = 0.0
            for p in ps:
                if p.open_time > t:
                    continue
                if not p.is_open and p.close_time and p.close_time <= t:
                    realized += p.net
                else:
                    floating += p.dir * (mk - p.open_price) * p.volume * CONTRACT
                    vol += p.volume
            series.append((t, realized + floating, vol * CONTRACT))
        if not series:
            continue
        per_cycle.append(dict(cyc=c.index, decision=decision, series=series,
                              final=series[-1][1], dpp=series[-1][2],
                              npr=len(series)))

    print(f"cycles with a reconstructable series: {len(per_cycle)}")
    print(f"price prints evaluated: {sum(r['npr'] for r in per_cycle)}\n")

    print("=" * 94)
    print("LAG(T) = decision - first crossing of T,  swept over candidate targets")
    print("=" * 94)
    print(f"  {'T':>6} {'crossed':>9} {'never':>7} | "
          f"{'med lag':>9} {'p75':>9} {'p90':>9} {'<=20s':>7} {'<=25s':>7} {'<=60s':>7}")
    best = None
    for T in CANDIDATES:
        lags = []
        never = 0
        for r in per_cycle:
            cross = next((t for t, v, _ in r["series"] if v >= T), None)
            if cross is None:
                never += 1
            else:
                lags.append((r["decision"] - cross).total_seconds())
        if not lags:
            print(f"  {T:>6.1f} {0:>9} {never:>7} |  (never crossed)")
            continue
        lags.sort()
        g = lambda f: lags[int(f * (len(lags) - 1))]
        le20 = sum(1 for x in lags if x <= 20.5)
        le25 = sum(1 for x in lags if x <= 25.0)
        le60 = sum(1 for x in lags if x <= 60.0)
        score = le20 / len(per_cycle)
        print(f"  {T:>6.1f} {len(lags):>9} {never:>7} | "
              f"{statistics.median(lags):>9.1f} {g(.75):>9.1f} {g(.9):>9.1f} "
              f"{le20:>7} {le25:>7} {le60:>7}")
        if best is None or score > best[1]:
            best = (T, score)

    print(f"\n  best T by fraction of cycles firing within one 20s tick: "
          f"{best[0]:.1f}  ({100*best[1]:.0f}%)")

    print("\n" + "=" * 94)
    print("MAXIMUM BASKET TOTAL STRICTLY BEFORE THE DECISION")
    print("   under a threshold rule this must stay BELOW T on every earlier tick,")
    print("   so its distribution has a right edge at T")
    print("=" * 94)
    maxima = []
    for r in per_cycle:
        pre = [v for t, v, _ in r["series"]
               if (r["decision"] - t).total_seconds() > 25.0]
        if pre:
            maxima.append((max(pre), r["cyc"], r["dpp"]))
    maxima.sort()
    vals = [m for m, _, _ in maxima]
    g = lambda f: vals[int(f * (len(vals) - 1))]
    print(f"  n={len(vals)}  p10={g(.1):.2f} p25={g(.25):.2f} "
          f"med={statistics.median(vals):.2f} p75={g(.75):.2f} p90={g(.9):.2f} "
          f"p95={g(.95):.2f} max={vals[-1]:.2f}")
    print(f"  below 30: {sum(1 for v in vals if v < 30)}/{len(vals)} "
          f"({100*sum(1 for v in vals if v < 30)/len(vals):.0f}%)")
    print(f"  histogram of the pre-decision maximum:")
    for lo, hi in [(-10**9, 0), (0, 10), (10, 20), (20, 25), (25, 28), (28, 30),
                   (30, 32), (32, 35), (35, 40), (40, 60), (60, 10**9)]:
        n = sum(1 for v in vals if lo <= v < hi)
        lab = f"[{lo if lo>-10**9 else '-inf':>5},{hi if hi<10**9 else 'inf':>5})"
        print(f"    {lab:<15}{n:>4} {'#'*n}")
    print("\n  cycles whose pre-decision max exceeded 32 (would falsify T=30):")
    for m, cyc, dpp in maxima[::-1][:12]:
        if m > 32:
            print(f"    cyc={cyc:<5} pre-decision max={m:>9.2f}  $/pt={dpp:>7.1f}")


if __name__ == "__main__":
    main()
