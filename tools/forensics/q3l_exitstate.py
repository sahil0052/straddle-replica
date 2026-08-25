"""Q3l: characterise the exit STATE, not just the exit money.

Three groups have now separated out of the 99 final-regime cycles:

  TARGET   marked total >= 25   -- the $30 basket target fired
  MID      0 <= marked < 25     -- fired early, or bled on the way out
  DISTRESS marked < 0           -- flattened at a loss, sometimes -$170, in a burst

and 5 cycles sustained a total above the target for 6-257 minutes WITHOUT firing.

If a distance gate exists, it must show up as lattice geometry at the decision:
distance from the anchor, how deep the loaded side filled, how many pendings were
left armed, and whether the lattice was exhausted.  Measure all of it per cycle and
contrast the groups.
"""
from __future__ import annotations

import statistics
import sys
from bisect import bisect_left, bisect_right

sys.path.insert(0, r"C:\websites\mt5 2")
from tools.forensics.dataset import load_all, FINAL_REGIME_START, CONTRACT  # noqa: E402
from tools.forensics.attribution import build_exit_index, attribute  # noqa: E402


def stats(vals, label):
    if not vals:
        print(f"    {label:<30} n=0")
        return
    v = sorted(vals)
    g = lambda f: v[int(f * (len(v) - 1))]
    print(f"    {label:<30} n={len(v):<4} min={v[0]:>8.2f} p25={g(.25):>7.2f} "
          f"med={statistics.median(v):>7.2f} p75={g(.75):>7.2f} max={v[-1]:>8.2f}")


def main() -> None:
    orders, positions, deals, cycles = load_all()
    class_by_time, _, _ = build_exit_index(orders, deals)
    reason, _, _ = attribute(positions, class_by_time)

    live = [p for p in positions if p.open_time >= FINAL_REGIME_START
            or (p.close_time and p.close_time >= FINAL_REGIME_START)]

    prints = sorted([(p.open_time, p.open_price) for p in live] +
                    [(p.close_time, p.close_price) for p in live
                     if p.close_time and p.close_price])
    pt_t = [t for t, _ in prints]
    pt_p = [x for _, x in prints]

    rows = []
    for c in cycles:
        if c.start < FINAL_REGIME_START:
            continue
        S = c.start
        closes = [p for p in live if not p.is_open and p.close_time
                  and p.close_time >= S
                  and reason.get(p.position_id) == "STR CLOSE"]
        if not closes:
            continue
        first_close = min(p.close_time for p in closes)
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
        mk = sweep[0].close_price
        realized_before = sum(p.net for p in live if not p.is_open and p.close_time
                              and S <= p.close_time < first_close)
        floating_at = sum(p.dir * (mk - p.open_price) * p.volume * CONTRACT
                          for p in sweep)
        marked = realized_before + floating_at

        # ---- lattice state at the decision ------------------------------
        armed_b = armed_s = 0
        for o in c.orders:
            if not o.is_grid or o.open_time > first_close:
                continue
            still = o.state == "placed" or (o.end_time and o.end_time > first_close)
            if not still:
                continue
            if o.side == "B":
                armed_b += 1
            else:
                armed_s += 1
        filled = [p for p in live if p.level and S <= p.open_time <= first_close]
        deep_b = max((p.level for p in filled if p.dir > 0), default=0)
        deep_s = max((p.level for p in filled if p.dir < 0), default=0)
        step = c.step or 1.0
        dist_pts = abs(mk - c.anchor)
        signed_st = (mk - c.anchor) / step

        # ---- max excursion of distance before the decision --------------
        i0, i1 = bisect_left(pt_t, S), bisect_right(pt_t, first_close)
        maxdist = max((abs(pt_p[i] - c.anchor) for i in range(i0, i1)), default=0.0)

        rows.append(dict(cyc=c.index, marked=marked, hrs=(first_close - S)
                         .total_seconds() / 3600.0,
                         dist_pts=dist_pts, dist_st=abs(signed_st),
                         signed_st=signed_st, maxdist=maxdist,
                         armed_b=armed_b, armed_s=armed_s,
                         armed=armed_b + armed_s,
                         deep_b=deep_b, deep_s=deep_s,
                         deep_loaded=max(deep_b, deep_s),
                         nopen=len(sweep), step=step,
                         dpp=sum(p.volume for p in sweep) * CONTRACT))

    tgt = [r for r in rows if r["marked"] >= 25.0]
    mid = [r for r in rows if 0.0 <= r["marked"] < 25.0]
    dis = [r for r in rows if r["marked"] < 0.0]
    print(f"cycles={len(rows)}   TARGET={len(tgt)}  MID={len(mid)}  DISTRESS={len(dis)}\n")

    for lab, grp in (("TARGET  (marked >= 25)", tgt),
                     ("MID     (0 <= marked < 25)", mid),
                     ("DISTRESS(marked < 0)", dis)):
        print("=" * 96)
        print(f"{lab}   n={len(grp)}")
        print("=" * 96)
        stats([r["marked"] for r in grp], "marked total at decision")
        stats([r["dist_pts"] for r in grp], "|mkt-anchor| pts at decision")
        stats([r["dist_st"] for r in grp], "|mkt-anchor| steps at decision")
        stats([r["maxdist"] for r in grp], "max |mkt-anchor| pts in cycle")
        stats([r["armed"] for r in grp], "armed pendings left")
        stats([r["deep_loaded"] for r in grp], "deepest filled level")
        stats([r["nopen"] for r in grp], "positions in the sweep")
        stats([r["dpp"] for r in grp], "$ per point")
        stats([r["hrs"] for r in grp], "cycle age (h)")
        print()

    print("=" * 96)
    print("DISTANCE-GATE TEST:  does |mkt-anchor| >= 20 pts separate the groups?")
    print("=" * 96)
    for lab, grp in (("TARGET  ", tgt), ("MID     ", mid), ("DISTRESS", dis)):
        n20 = sum(1 for r in grp if r["dist_pts"] >= 20.0)
        n15 = sum(1 for r in grp if r["dist_pts"] >= 15.0)
        mx20 = sum(1 for r in grp if r["maxdist"] >= 20.0)
        print(f"  {lab}  dist>=20 at exit: {n20:>3}/{len(grp):<3}   "
              f"dist>=15: {n15:>3}/{len(grp):<3}   "
              f"ever reached 20 in cycle: {mx20:>3}/{len(grp)}")

    print("\n" + "=" * 96)
    print("EVERY DISTRESS EXIT, IN FULL")
    print("=" * 96)
    print(f"  {'cyc':>4} {'marked':>9} {'hrs':>6} {'$/pt':>7} {'op':>3} "
          f"{'dist_pt':>8} {'dist_st':>8} {'maxdist':>8} {'armB':>5} {'armS':>5} "
          f"{'deepB':>6} {'deepS':>6} {'step':>6}")
    for r in sorted(dis, key=lambda r: r["marked"]):
        print(f"  {r['cyc']:>4} {r['marked']:>9.2f} {r['hrs']:>6.1f} {r['dpp']:>7.1f} "
              f"{r['nopen']:>3} {r['dist_pts']:>8.2f} {r['dist_st']:>8.2f} "
              f"{r['maxdist']:>8.2f} {r['armed_b']:>5} {r['armed_s']:>5} "
              f"{r['deep_b']:>6} {r['deep_s']:>6} {r['step']:>6.3f}")

    print("\n" + "=" * 96)
    print("THE 5 CYCLES THAT SUSTAINED A TOTAL ABOVE TARGET WITHOUT FIRING")
    print("=" * 96)
    print(f"  {'cyc':>4} {'marked':>9} {'hrs':>6} {'$/pt':>7} {'op':>3} "
          f"{'dist_pt':>8} {'maxdist':>8} {'armB':>5} {'armS':>5} "
          f"{'deepB':>6} {'deepS':>6}")
    for r in rows:
        if r["cyc"] in (194, 252, 187, 244, 250):
            print(f"  {r['cyc']:>4} {r['marked']:>9.2f} {r['hrs']:>6.1f} "
                  f"{r['dpp']:>7.1f} {r['nopen']:>3} {r['dist_pts']:>8.2f} "
                  f"{r['maxdist']:>8.2f} {r['armed_b']:>5} {r['armed_s']:>5} "
                  f"{r['deep_b']:>6} {r['deep_s']:>6}")


if __name__ == "__main__":
    main()
