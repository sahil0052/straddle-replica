"""Q4d: pin rearm_delay_seconds, and check the basket target across the Jul-24 break.

q4c found the Jul-24 settings change did NOT touch the trail (empty band 0.9927 vs
0.9926 -- identical), the lot tiers, the step, levels_per_side, or the 100 ms
action cadence.  Two things did move:

  * re-arm delay: the "near 5 s" population is 21 EARLY / 0 LATE, while "near 20 s"
    is 15 EARLY / 47 LATE.
  * the flatten total is tighter EARLY (34/68 in [25,45]) than LATE (5/32).

A delay parameter D is not a spike, it is a FLOOR: with a 100 ms evaluation timer,
no re-arm can be observed at delay < D.  If instead the EA only *evaluates* re-arms
on a 20 s clock, delays pile up at multiples of 20.  Panel A separates those:

  floor at D, 100 ms eval   -> zero observations below D, dense spike at D
  20 s evaluation cadence   -> spikes at 20, 40, 60 ...
  neither                   -> the spike is not the delay parameter

Panel A also excludes deployment-burst orders, which are not re-arms at all and
were polluting the earlier count.
Panel B prints the flatten-total distributions so the dispersion change can be read
directly rather than through a bin count.
"""
from __future__ import annotations

import bisect
import statistics
import sys
from collections import Counter
from datetime import datetime

sys.path.insert(0, r"C:\websites\mt5 2")
from tools.forensics.dataset import load_all, FINAL_REGIME_START  # noqa: E402
from tools.forensics.attribution import build_exit_index, attribute  # noqa: E402

BREAK = datetime(2026, 7, 24, 12, 0, 0)
SWEEP_GAP = 120.0


def side(t: datetime) -> str:
    return "EARLY" if t < BREAK else "LATE"


def main() -> None:
    orders, positions, deals, cycles = load_all()
    class_by_time, _, _ = build_exit_index(orders, deals)
    reason, _, _ = attribute(positions, class_by_time)

    # ---------------------------------------------------------------- panel A
    print("=" * 100)
    print("A. RE-ARM DELAY -- is the spike a FLOOR (delay param) or a CADENCE "
          "(evaluation clock)?")
    print("=" * 100)
    burst_ids = set()
    for c in cycles:
        for o in c.burst_orders:
            burst_ids.add(o.order_id)

    pos_by_id = {p.position_id: p for p in positions}
    percyc: dict[tuple, list] = {}
    for o in orders:
        if o.is_grid and o.open_time >= FINAL_REGIME_START and o.level is not None:
            percyc.setdefault((o.cycle, o.side, o.level), []).append(o)

    delays = {"EARLY": [], "LATE": []}
    for seq in percyc.values():
        seq.sort(key=lambda o: o.open_time)
        for prev, nxt in zip(seq, seq[1:]):
            if prev.state != "filled" or nxt.order_id in burst_ids:
                continue          # only genuine mid-cycle re-arms
            p = pos_by_id.get(prev.order_id)
            if not p or p.is_open or not p.close_time:
                continue
            d = (nxt.open_time - p.close_time).total_seconds()
            if d >= 0.0:
                delays[side(nxt.open_time)].append(d)

    for lab in ("EARLY", "LATE"):
        v = sorted(delays[lab])
        if not v:
            print(f"  {lab}: none")
            continue
        print(f"\n  {lab}  n={len(v)}   min={v[0]:.2f}s  "
              f"median={statistics.median(v):.2f}s")
        print(f"    below  4.5s : {sum(1 for x in v if x < 4.5):>4}"
              f"    below 19.0s : {sum(1 for x in v if x < 19.0):>4}")
        print(f"    20 smallest : "
              + " ".join(f"{x:.2f}" for x in v[:20]))
        h = Counter()
        for x in v:
            if x < 60.0:
                h[int(x // 2) * 2] += 1
        print("    histogram to 60s (2s bins, count>=3 only):")
        for k in sorted(h):
            if h[k] >= 3:
                print(f"      {k:>3}-{k+2:<3}s {'#' * min(h[k], 60)} {h[k]}")
        mult = [sum(1 for x in v if abs(x - 20.0 * m) <= 1.5) for m in (1, 2, 3)]
        print(f"    near 20s: {mult[0]}   near 40s: {mult[1]}   near 60s: {mult[2]}")

        # A floor at D admits ~no observations below D and piles up just above it.
        # Real data has a few strays (broker gaps, clock skew), so allow <=1%
        # leakage rather than demanding exactly zero -- an all-or-nothing test
        # reports "no floor" for a floor with 2 exceptions in 581.
        # An EVALUATION CADENCE of D instead scatters uniformly over [0,D) and
        # piles at every multiple of D in comparable numbers.
        verdict = None
        for d in (5.0, 20.0):
            leak = sum(1 for x in v if x < d - 0.5)
            pile = sum(1 for x in v if d - 0.5 <= x <= d + 2.0)
            if leak <= max(1, int(0.01 * len(v))) and pile >= 0.05 * len(v):
                verdict = (f"hard FLOOR at {d:.0f}s ({leak} leak, {pile} in the pile) "
                           f"-> rearm_delay_seconds = {d:.0f}")
                break
        # A cadence needs SPIKES at the multiples, so the near-multiple counts must
        # stand well above the local background.  On a flat distribution any 3 s
        # window holds ~background by definition, which is not evidence of anything.
        under60 = sum(1 for x in v if x < 60.0)
        bg = under60 / 60.0 * 3.0
        if verdict is None and bg > 0 and mult[0] >= 2.5 * bg and mult[1] >= 2.5 * bg:
            verdict = (f"EVALUATION CADENCE at 20s: {mult[0]}/{mult[1]}/{mult[2]} "
                       f"against a {bg:.1f} background per 3s window")
        print("    => " + (verdict or
                           f"NO delay gate: {sum(1 for x in v if x < 4.5)} below 4.5s, "
                           f"{sum(1 for x in v if x < 19.0)} below 19s, "
                           f"distribution continuous from {v[0]:.2f}s"))

    # ---------------------------------------------------------------- panel B
    print()
    print("=" * 100)
    print("B. BASKET TOTAL at flatten -- did the $30 target move on Jul 24?")
    print("=" * 100)
    fin_pos = [p for p in positions
               if (p.open_time >= FINAL_REGIME_START
                   or (p.close_time and p.close_time >= FINAL_REGIME_START))]
    closers = sorted((p for p in fin_pos if not p.is_open and p.close_time
                      and reason.get(p.position_id) == "STR CLOSE"),
                     key=lambda p: p.close_time)
    sweeps, cur = [], [closers[0]]
    for prev, nxt in zip(closers, closers[1:]):
        if (nxt.close_time - prev.close_time).total_seconds() <= SWEEP_GAP:
            cur.append(nxt)
        else:
            sweeps.append(cur); cur = [nxt]
    sweeps.append(cur)
    sweeps = [s for s in sweeps if s[0].close_time >= FINAL_REGIME_START]

    others = sorted((p for p in fin_pos if not p.is_open and p.close_time
                     and reason.get(p.position_id) != "STR CLOSE"),
                    key=lambda p: p.close_time)
    otimes = [p.close_time for p in others]

    tot = {"EARLY": [], "LATE": []}
    for i in range(1, len(sweeps)):
        lo, hi = sweeps[i - 1][-1].close_time, sweeps[i][0].close_time
        a, b = bisect.bisect_right(otimes, lo), bisect.bisect_left(otimes, hi)
        realized = sum(p.net for p in others[a:b])
        tot[side(hi)].append(realized + sum(p.net for p in sweeps[i]))

    for lab in ("EARLY", "LATE"):
        v = sorted(tot[lab])
        print(f"\n  {lab}  n={len(v)}  median={statistics.median(v):.2f}")
        print("    sorted: " + " ".join(f"{x:.1f}" for x in v))
        # the burst-flatten subset is the cleanest estimator (no 20s price drift)
        print(f"    in [20,40]: {sum(1 for x in v if 20<=x<=40)}   "
              f"in [25,35]: {sum(1 for x in v if 25<=x<=35)}   "
              f"< 0: {sum(1 for x in v if x<0)}   "
              f"> 60: {sum(1 for x in v if x>60)}")

    # LATE sweeps take up to 8 minutes to complete, so the LAST position closes far
    # from the decision.  Re-estimate LATE using only the FIRST close of each sweep
    # marked at the sweep's own prices -- i.e. drop the drift the pacing introduces.
    print()
    print("  LATE re-estimated at the DECISION instant (first close of the sweep),")
    print("  marking the not-yet-closed remainder at the first close's own price:")
    est = []
    for i in range(1, len(sweeps)):
        s = sweeps[i]
        hi = s[0].close_time
        if side(hi) != "LATE":
            continue
        lo = sweeps[i - 1][-1].close_time
        a, b = bisect.bisect_right(otimes, lo), bisect.bisect_left(otimes, hi)
        realized = sum(p.net for p in others[a:b])
        mark = s[0].close_price
        floating = sum(p.dir * (mark - p.open_price) * p.volume * 100.0 + p.swap
                       for p in s)
        est.append(realized + floating)
    est.sort()
    if est:
        print("    sorted: " + " ".join(f"{x:.1f}" for x in est))
        print(f"    n={len(est)}  median={statistics.median(est):.2f}   "
              f"in [20,40]: {sum(1 for x in est if 20<=x<=40)}   "
              f"in [25,35]: {sum(1 for x in est if 25<=x<=35)}   "
              f"< 0: {sum(1 for x in est if x<0)}")


if __name__ == "__main__":
    main()
