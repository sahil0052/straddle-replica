"""Q3g / Q2 joint: does an active TREND RESCUE suspend the $30 basket target?

Cycle 252 rode from +$30 (16:08:44) to +$642 (19:14) without flattening, which
falsifies an unconditional "realized+floating >= 30".  The first >=30 print in that
cycle coincides with a 0.12-lot fill -- a 2x rescue volume.

Hypothesis: while a rescue leg is open the profit target is suspended, so only
NON-RESCUE cycles are governed by the $30 rule.

Test: split the 99 final-regime cycles on whether they ever placed a rescue-volume
order, then re-run the "pre-decision maximum must stay below T" falsification test
inside each group.  If the rule is clean in the no-rescue group and only broken in
the rescue group, the gate is identified.

Rescue volumes are 2x the tier lot: 0.02 (tier 0.01), 0.12 (tier 0.06), 0.30
(tier 0.15).
"""
from __future__ import annotations

import statistics
import sys
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict

sys.path.insert(0, r"C:\websites\mt5 2")
from tools.forensics.dataset import load_all, FINAL_REGIME_START, CONTRACT  # noqa: E402
from tools.forensics.attribution import build_exit_index, attribute  # noqa: E402

RESCUE_VOLS = {0.02, 0.12, 0.30}
TIER_VOL = {0.01, 0.06, 0.15}


def tier_lot(level: int) -> float:
    if level <= 10:
        return 0.01
    if level <= 20:
        return 0.06
    return 0.15


def stats(vals, label):
    if not vals:
        print(f"  {label:<34} n=0")
        return
    v = sorted(vals)
    g = lambda f: v[int(f * (len(v) - 1))]
    print(f"  {label:<34} n={len(v):<4} min={v[0]:>9.2f} p10={g(.1):>8.2f} "
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

        # ---- rescue inventory -------------------------------------------
        rescue_orders = [o for o in c.orders
                         if o.is_grid and o.volume in RESCUE_VOLS
                         and o.level and o.volume > tier_lot(o.level) + 1e-9]
        rescue_fills = [p for p in ps if p.volume in RESCUE_VOLS
                        and p.level and p.volume > tier_lot(p.level) + 1e-9]
        first_rescue = min((o.open_time for o in rescue_orders), default=None)
        first_rescue_fill = min((p.open_time for p in rescue_fills), default=None)

        # ---- basket total series ----------------------------------------
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
            series.append((t, realized + floating, vol * CONTRACT, mk))
        if not series:
            continue
        pre = [(t, v) for t, v, _, _ in series
               if (decision - t).total_seconds() > 25.0]
        premax = max((v for _, v in pre), default=None)
        # first time the total crossed 30 (any time in the cycle)
        cross30 = next((t for t, v, _, _ in series if v >= 30.0), None)
        # max |market-anchor| in points before the decision
        predist = max((abs(mk - c.anchor) for t, _, _, mk in series
                       if (decision - t).total_seconds() > 25.0), default=None)

        rows.append(dict(
            cyc=c.index, decision=decision, final=series[-1][1],
            dpp=series[-1][2], premax=premax, predist=predist, cross30=cross30,
            n_resc_ord=len(rescue_orders), n_resc_fill=len(rescue_fills),
            first_rescue=first_rescue, first_rescue_fill=first_rescue_fill,
            hrs=(decision - c.start).total_seconds() / 3600.0,
            anchor=c.anchor, step=c.step,
            dist_at=abs(series[-1][3] - c.anchor),
        ))

    print(f"cycles: {len(rows)}\n")

    resc = [r for r in rows if r["n_resc_fill"] > 0]
    plain = [r for r in rows if r["n_resc_fill"] == 0]
    print("=" * 100)
    print(f"SPLIT ON RESCUE ACTIVITY:  rescue-fill cycles n={len(resc)}   "
          f"plain cycles n={len(plain)}")
    print("=" * 100)
    for lab, grp in (("RESCUE", resc), ("PLAIN ", plain)):
        print(f"\n  --- {lab} ---")
        pm = [r["premax"] for r in grp if r["premax"] is not None]
        stats(pm, "pre-decision MAX total")
        stats([r["final"] for r in grp], "total at decision")
        stats([r["hrs"] for r in grp], "cycle age (h)")
        stats([r["dpp"] for r in grp], "$ per point")
        stats([r["predist"] for r in grp if r["predist"] is not None],
              "pre-decision MAX |mkt-anchor| pts")
        stats([r["dist_at"] for r in grp], "|mkt-anchor| at decision pts")
        bad = [r for r in grp if r["premax"] is not None and r["premax"] >= 32.0]
        print(f"  FALSIFIERS of total>=30 (pre-decision max >= 32): "
              f"{len(bad)}/{len(grp)}  ({100*len(bad)/max(1,len(grp)):.0f}%)")

    print("\n" + "=" * 100)
    print("EVERY FALSIFIER, WITH ITS RESCUE STATUS")
    print("=" * 100)
    bad = sorted((r for r in rows if r["premax"] is not None and r["premax"] >= 32.0),
                 key=lambda r: -r["premax"])
    print(f"  {'cyc':>4} {'premax':>9} {'final':>9} {'$/pt':>7} {'hrs':>6} "
          f"{'rescO':>6} {'rescF':>6} {'first rescue fill':<20} "
          f"{'first >=30':<20} {'predist':>8}")
    for r in bad:
        fr = (r["first_rescue_fill"].strftime("%m-%d %H:%M:%S")
              if r["first_rescue_fill"] else "-")
        c3 = r["cross30"].strftime("%m-%d %H:%M:%S") if r["cross30"] else "-"
        print(f"  {r['cyc']:>4} {r['premax']:>9.2f} {r['final']:>9.2f} "
              f"{r['dpp']:>7.1f} {r['hrs']:>6.1f} {r['n_resc_ord']:>6} "
              f"{r['n_resc_fill']:>6} {fr:<20} {c3:<20} "
              f"{r['predist'] if r['predist'] is not None else -1:>8.1f}")

    print("\n" + "=" * 100)
    print("DID THE FIRST >=30 CROSSING HAPPEN BEFORE OR AFTER THE FIRST RESCUE FILL?")
    print("  (hypothesis: rescue arms first, THEN the total is free to run past 30)")
    print("=" * 100)
    ct = Counter()
    for r in rows:
        if r["cross30"] is None:
            ct["never crossed 30"] += 1
        elif r["first_rescue_fill"] is None:
            ct["no rescue in cycle"] += 1
        elif r["cross30"] >= r["first_rescue_fill"]:
            ct["crossed 30 AFTER rescue armed"] += 1
        else:
            ct["crossed 30 BEFORE rescue armed"] += 1
    for k, n in ct.most_common():
        print(f"  {k:<34} {n}")

    print("\n" + "=" * 100
          )
    print("PLAIN CYCLES ONLY -- histogram of the pre-decision maximum")
    print("  a clean $30 threshold predicts a hard right edge just under 30")
    print("=" * 100)
    pm = sorted(r["premax"] for r in plain if r["premax"] is not None)
    for lo, hi in [(-10**9, 0), (0, 10), (10, 20), (20, 25), (25, 28), (28, 30),
                   (30, 32), (32, 40), (40, 10**9)]:
        n = sum(1 for v in pm if lo <= v < hi)
        lab = f"[{lo if lo>-10**9 else '-inf':>5},{hi if hi<10**9 else 'inf':>5})"
        print(f"    {lab:<15}{n:>4} {'#'*n}")


if __name__ == "__main__":
    main()
