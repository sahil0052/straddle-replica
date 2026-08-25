"""Q1d: the SL-update timer period, measured from event quantisation.

If stops are maintained on an EA timer with max_stop_updates_per_pass=1, then:
  * consecutive SL-driven closures inside one cycle should cluster at multiples
    of the timer period (the EA moves one SL per pass; a position only stops out
    after its own SL has been advanced onto the market);
  * re-arm placements after a fill should also quantise to the timer;
  * position lifetimes should quantise to the timer.

This measures the period directly from inter-event gap histograms.
"""
from __future__ import annotations

import sys
from collections import Counter, defaultdict

sys.path.insert(0, r"C:\websites\mt5 2")
from tools.forensics.dataset import load_all, FINAL_REGIME_START  # noqa: E402
from tools.forensics.attribution import build_exit_index, attribute  # noqa: E402


def gap_hist(gaps, label, top=18, res=0.1):
    c = Counter(round(g / res) * res for g in gaps)
    print(f"\n  {label}  (n={len(gaps)})")
    for k, n in sorted(c.items(), key=lambda kv: -kv[1])[:top]:
        print(f"    {k:>8.1f}s : {n:>5}  {'#' * min(60, n // max(1, len(gaps)//600 or 1))}")


def main() -> None:
    orders, positions, deals, cycles = load_all()
    class_by_time, _, _ = build_exit_index(orders, deals)
    reason, _, _ = attribute(positions, class_by_time)

    fr_cycles = [c for c in cycles if c.start >= FINAL_REGIME_START]
    print(f"final-regime cycles: {len(fr_cycles)}")

    # ---- 1. gaps between consecutive SL closures in the same cycle ----------
    print("=" * 78)
    print("1. CONSECUTIVE SL-CLOSURE GAPS WITHIN A CYCLE")
    print("=" * 78)
    by_cycle = defaultdict(list)
    for p in positions:
        if (p.cycle >= 0 and not p.is_open and p.close_time
                and p.open_time >= FINAL_REGIME_START
                and reason.get(p.position_id) == "sl"):
            by_cycle[p.cycle].append(p.close_time)
    gaps = []
    for cyc, ts in by_cycle.items():
        ts.sort()
        gaps += [(b - a).total_seconds() for a, b in zip(ts, ts[1:])]
    small = [g for g in gaps if g <= 90]
    gap_hist(small, "gaps <= 90s, 0.1s resolution")
    print(f"\n  gaps in [19.5,20.7]s : {sum(1 for g in gaps if 19.5<=g<=20.7)}")
    print(f"  gaps in [39.5,40.7]s : {sum(1 for g in gaps if 39.5<=g<=40.7)}")
    print(f"  gaps in [59.5,60.7]s : {sum(1 for g in gaps if 59.5<=g<=60.7)}")
    print(f"  gaps < 1s            : {sum(1 for g in gaps if g < 1)}")
    print(f"  total                : {len(gaps)}")

    # ---- 2. position lifetime quantisation ---------------------------------
    print("\n" + "=" * 78)
    print("2. POSITION LIFETIME MODULO 20s")
    print("=" * 78)
    lifes = [(p.close_time - p.open_time).total_seconds()
             for p in positions
             if p.cycle >= 0 and not p.is_open and p.close_time
             and p.open_time >= FINAL_REGIME_START
             and reason.get(p.position_id) == "sl"]
    short = sorted(x for x in lifes if x <= 200)
    gap_hist(short, "lifetimes <= 200s", top=16, res=1.0)
    mod = Counter(round((x % 20.0)) for x in lifes)
    print("\n  lifetime mod 20s histogram (flat => no quantisation):")
    for k in range(20):
        n = mod.get(k, 0)
        print(f"    {k:>3}s : {n:>5} {'#'*min(60, n//4)}")

    # ---- 3. re-arm delay: fill -> replacement pending order -----------------
    print("\n" + "=" * 78)
    print("3. RE-ARM DELAY  (position close -> replacement pending order placed)")
    print("=" * 78)
    place_by_key = defaultdict(list)
    for o in orders:
        if o.is_grid and o.cycle >= 0 and o.open_time >= FINAL_REGIME_START:
            place_by_key[(o.cycle, o.comment)].append(o.open_time)
    for v in place_by_key.values():
        v.sort()
    delays = []
    from bisect import bisect_right
    for p in positions:
        if (p.cycle < 0 or p.is_open or not p.close_time
                or p.open_time < FINAL_REGIME_START):
            continue
        ts = place_by_key.get((p.cycle, p.comment))
        if not ts:
            continue
        i = bisect_right(ts, p.close_time)
        if i < len(ts):
            delays.append((ts[i] - p.close_time).total_seconds())
    d = sorted(x for x in delays if x <= 300)
    gap_hist(d, "re-arm delay <= 300s", top=16, res=1.0)
    if d:
        print(f"\n  min={d[0]:.3f}  p05={d[int(.05*len(d))]:.3f} "
              f"p25={d[int(.25*len(d))]:.3f} p50={d[len(d)//2]:.3f} "
              f"p75={d[int(.75*len(d))]:.3f}  n={len(d)}")
        print(f"  in [4.5,6.5]s (rearm_delay_seconds=5): "
              f"{sum(1 for x in d if 4.5<=x<=6.5)}")
        print(f"  in [19,22]s   (timer=20)             : "
              f"{sum(1 for x in d if 19<=x<=22)}")

    # ---- 4. burst pacing ----------------------------------------------------
    print("\n" + "=" * 78)
    print("4. DEPLOYMENT BURST PACING (order-to-order within a sweep)")
    print("=" * 78)
    bg = []
    for c in fr_cycles:
        ts = sorted(o.open_time for o in c.burst_orders)
        bg += [(b - a).total_seconds() for a, b in zip(ts, ts[1:])]
    bg = [g for g in bg if g < 5]
    gap_hist(bg, "intra-burst gaps", top=10, res=0.01)
    if bg:
        bg.sort()
        print(f"\n  median={bg[len(bg)//2]:.4f}s  "
              f"=> {60/ (bg[len(bg)//2] or 1):.1f} orders/min, "
              f"full 60-order sweep ~ {60*bg[len(bg)//2]:.1f}s")

    # ---- 5. how many distinct closure instants per cycle-second -------------
    print("\n" + "=" * 78)
    print("5. SIMULTANEITY: positions closed per distinct instant")
    print("=" * 78)
    per_instant = Counter()
    inst = defaultdict(int)
    for p in positions:
        if (p.cycle >= 0 and not p.is_open and p.close_time
                and p.open_time >= FINAL_REGIME_START):
            inst[(p.close_time, reason.get(p.position_id))] += 1
    for (t, r), n in inst.items():
        per_instant[(r, n)] += 1
    for r in ("sl", "STR CLOSE"):
        row = {n: c for (rr, n), c in per_instant.items() if rr == r}
        print(f"  {r:<12}: " + str(dict(sorted(row.items()))))


if __name__ == "__main__":
    main()
