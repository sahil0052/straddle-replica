"""Q3h: are the pre-decision excursions above $30 SUSTAINED or single-print noise?

A $30 line sampled every 20s is only falsified by an excursion that LASTS longer
than a timer tick.  A single print above 30 that immediately retraces is invisible
to the EA -- and is exactly what a mis-valued basket produces, because the whole
basket is priced off one fill print (a buy-stop fill is the ASK, a buy position is
marked at the BID, so the error is ~spread x $/point, i.e. +-$30 at $94/pt).

Two measurements per cycle:

 1. SUSTAINED EXCURSION: the longest contiguous span, ending >25s before the
    decision, over which the total stayed >= 30 + margin, where
    margin = SPREAD_PTS * $/point is the valuation error bound.

 2. VALUATION CHECK: the flatten net is the floating the EA actually saw (the
    basket is liquidated at market).  Comparing it with my interpolated floating
    at the decision measures my own error directly, with no model in between.
"""
from __future__ import annotations

import statistics
import sys
from bisect import bisect_left, bisect_right
from collections import defaultdict

sys.path.insert(0, r"C:\websites\mt5 2")
from tools.forensics.dataset import load_all, FINAL_REGIME_START, CONTRACT  # noqa: E402
from tools.forensics.attribution import build_exit_index, attribute  # noqa: E402

SPREAD_PTS = 0.35     # typical XAUUSD spread on this broker, in price points
TARGET = 30.0


def stats(vals, label):
    if not vals:
        print(f"  {label:<36} n=0")
        return
    v = sorted(vals)
    g = lambda f: v[int(f * (len(v) - 1))]
    print(f"  {label:<36} n={len(v):<4} min={v[0]:>9.2f} p10={g(.1):>8.2f} "
          f"med={statistics.median(v):>8.2f} p75={g(.75):>8.2f} "
          f"p90={g(.9):>8.2f} max={v[-1]:>9.2f}")


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

        # ---- exact reconstruction: no price interpolation -----------------
        realized_before = sum(p.net for p in ps if not p.is_open and p.close_time
                              and p.close_time < first_close)
        flatten_net = sum(p.net for p in closes)
        exact_total = realized_before + flatten_net
        span = (last_close - first_close).total_seconds()

        # ---- series + sustained excursion ---------------------------------
        i0 = bisect_left(pt_t, c.start)
        i1 = bisect_right(pt_t, decision)
        series = []
        for i in range(i0, i1):
            t, mk = pt_t[i], pt_p[i]
            realized = floating = vol = 0.0
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
        interp_floating = None
        for t, v, dpp in reversed(series):
            interp_floating = v
            break

        pre = [(t, v, dpp) for t, v, dpp in series
               if (decision - t).total_seconds() > 25.0]
        # longest contiguous run above the noise-adjusted line
        best_run = 0.0
        best_at = None
        cur_start = None
        for t, v, dpp in pre:
            margin = SPREAD_PTS * dpp
            if v >= TARGET + margin:
                if cur_start is None:
                    cur_start = t
                dur = (t - cur_start).total_seconds()
                if dur > best_run:
                    best_run, best_at = dur, cur_start
            else:
                cur_start = None
        # same but with no margin, for comparison
        best_run0 = 0.0
        cur0 = None
        for t, v, dpp in pre:
            if v >= TARGET:
                if cur0 is None:
                    cur0 = t
                best_run0 = max(best_run0, (t - cur0).total_seconds())
            else:
                cur0 = None

        rows.append(dict(cyc=c.index, decision=decision, span=span,
                         nclose=len(closes), dpp=series[-1][2],
                         realized_before=realized_before, flatten_net=flatten_net,
                         exact_total=exact_total, interp_total=series[-1][1],
                         sustained=best_run, sustained0=best_run0,
                         sust_at=best_at,
                         hrs=(decision - c.start).total_seconds() / 3600.0))

    print(f"cycles: {len(rows)}\n")

    print("=" * 104)
    print("1.  SUSTAINED EXCURSION ABOVE THE TARGET, BEFORE THE DECISION")
    print("    a 20s-sampled $30 line is only falsified by a run LONGER than one tick")
    print("=" * 104)
    for lab, key in (("no margin        ", "sustained0"),
                     ("spread-adjusted  ", "sustained")):
        v = [r[key] for r in rows]
        print(f"  {lab} : never above   {sum(1 for x in v if x == 0):>3}/{len(v)}")
        print(f"  {' ' * 17}   <=20s        {sum(1 for x in v if 0 < x <= 20):>3}")
        print(f"  {' ' * 17}   20s-5min     {sum(1 for x in v if 20 < x <= 300):>3}")
        print(f"  {' ' * 17}   5min-1h      {sum(1 for x in v if 300 < x <= 3600):>3}")
        print(f"  {' ' * 17}   >1h          {sum(1 for x in v if x > 3600):>3}")
    print()
    hard = sorted((r for r in rows if r["sustained"] > 300),
                  key=lambda r: -r["sustained"])
    print(f"  HARD FALSIFIERS (spread-adjusted excursion > 5 min): {len(hard)}/{len(rows)}")
    print(f"  {'cyc':>4} {'excursion':>11} {'began':<20} {'decision':<20} "
          f"{'$/pt':>7} {'hrs':>6} {'exact tot':>10}")
    for r in hard:
        print(f"  {r['cyc']:>4} {r['sustained']/60:>9.1f}m  "
              f"{r['sust_at'].strftime('%m-%d %H:%M:%S'):<20} "
              f"{r['decision'].strftime('%m-%d %H:%M:%S'):<20} "
              f"{r['dpp']:>7.1f} {r['hrs']:>6.1f} {r['exact_total']:>10.2f}")

    print("\n" + "=" * 104)
    print("2.  MY VALUATION ERROR, MEASURED DIRECTLY")
    print("    exact_total = realized_before + flatten_net   (no price estimated)")
    print("    interp_total = realized + floating priced off the nearest print")
    print("=" * 104)
    fast = [r for r in rows if r["span"] <= 5.0]
    stats([r["exact_total"] for r in fast], "exact total (fast flattens)")
    stats([r["interp_total"] - r["exact_total"] for r in fast],
          "interp - exact (my error)")
    err = [abs(r["interp_total"] - r["exact_total"]) for r in fast]
    print(f"\n  |error| <= 5 : {sum(1 for x in err if x <= 5):>3}/{len(err)}")
    print(f"  |error| <= 15: {sum(1 for x in err if x <= 15):>3}/{len(err)}")
    print(f"  |error| >  30: {sum(1 for x in err if x > 30):>3}/{len(err)}")

    print("\n" + "=" * 104)
    print("3.  EXACT TOTAL AT THE DECISION, FAST FLATTENS, GROUPED BY EXCURSION CLASS")
    print("=" * 104)
    clean = [r for r in fast if r["sustained"] <= 300]
    dirty = [r for r in fast if r["sustained"] > 300]
    stats([r["exact_total"] for r in clean], "clean cycles (no long excursion)")
    stats([r["exact_total"] for r in dirty], "cycles with a long excursion")
    v = sorted(r["exact_total"] for r in clean)
    print(f"\n  clean cycles: >=30 {sum(1 for x in v if x >= 30)}/{len(v)}  "
          f">=28 {sum(1 for x in v if x >= 28)}/{len(v)}  "
          f"<25 {sum(1 for x in v if x < 25)}/{len(v)}")
    print(f"  clean totals: {[f'{x:.2f}' for x in v]}")


if __name__ == "__main__":
    main()
