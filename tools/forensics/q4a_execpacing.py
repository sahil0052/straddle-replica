"""Q4a: does the replica's one-action-per-timer-tick execution model reproduce the
Target EA's measured order/close/cancel pacing?

The replica architecture (StraddleEngine.mqh::OnTimer) is a single state machine
driven by EventSetMillisecondTimer(max(20, InterOrderDelayMs)) = 100 ms, and every
tick performs exactly ONE broker action:

    CYCLE_DEPLOYING  -> DeployOne()             1 PlaceStop  per tick
    CYCLE_CANCELING  -> CancelOneOrder()        1 DeleteOrder per tick   (ungated)
    CYCLE_CLOSING    -> CloseOnePosition()      1 ClosePosition per tick,
                                                gated by close_interval_seconds=20
                                                UNLESS m_halted / shadow reset
    CYCLE_RUNNING    -> UpdatePositionStops()   max_stop_updates_per_pass=1

So the model predicts three distinct observable cadences:
    deployment  ~= timer_ms                     (100 ms)
    cancelling  ~= timer_ms                     (100 ms)
    closing     ~= close_interval_seconds       (20 s), or timer_ms on the halt path

Panels A/B measure the first two against the report and pin timer_ms.
Panel C is the real question.  The Target EA's flatten closes are BIMODAL: most
sweeps burst, a minority pace at ~20 s.  The replica can only ever burst on the
safety-halt path, so if the Target bursts on ordinary basket exits the replica is
in the wrong mode most of the time.

Two competing explanations, and they are distinguishable from the WITHIN-sweep gap
structure:

  H-gate   close_interval_seconds is real; something selects burst vs paced.
           => a paced sweep's internal gaps are UNIFORMLY ~20 s.
  H-retry  there is no close interval; the EA always bursts, and 20 s gaps are
           stalls (rejected close retried on a later tick, or a tick starved).
           => a paced sweep's gaps are MIXED: clusters of ~0.1 s with occasional
              20 s jumps.

Panel C prints the gap sequence of every paced sweep so the shape decides.
Panel D checks that cancelling strictly precedes closing (cancel_before_close).
"""
from __future__ import annotations

import statistics
import sys
from collections import Counter

sys.path.insert(0, r"C:\websites\mt5 2")
from tools.forensics.dataset import load_all, FINAL_REGIME_START, CONTRACT  # noqa: E402
from tools.forensics.attribution import build_exit_index, attribute  # noqa: E402

SWEEP_GAP = 120.0      # seconds; must exceed close_interval_seconds=20 comfortably
BURST_MAX = 1.0        # median gap below this = burst mode
PACED_MIN = 10.0       # median gap above this = paced mode


def gaps(times) -> list[float]:
    return [(b - a).total_seconds() for a, b in zip(times, times[1:])]


def q(xs: list[float], p: float) -> float:
    if not xs:
        return float("nan")
    s = sorted(xs)
    return s[min(len(s) - 1, max(0, int(p * (len(s) - 1) + 0.5)))]


def group(items, keyfn, gap: float):
    """Split a time-sorted list wherever the gap between consecutive keys exceeds `gap`."""
    out, cur = [], [items[0]]
    for prev, nxt in zip(items, items[1:]):
        if (keyfn(nxt) - keyfn(prev)).total_seconds() <= gap:
            cur.append(nxt)
        else:
            out.append(cur)
            cur = [nxt]
    out.append(cur)
    return out


def main() -> None:
    orders, positions, deals, cycles = load_all()
    class_by_time, _, _ = build_exit_index(orders, deals)
    reason, _, _ = attribute(positions, class_by_time)

    # ---------------------------------------------------------------- panel A
    print("=" * 100)
    print("A. DEPLOYMENT CADENCE  (predicted: one PlaceStop per timer tick = "
          "InterOrderDelayMs)")
    print("=" * 100)
    fin = [c for c in cycles if c.start >= FINAL_REGIME_START]
    dep_all: list[float] = []
    dep_per_cycle: list[float] = []
    for c in fin:
        g = gaps([o.open_time for o in c.burst_orders])
        if not g:
            continue
        dep_all += g
        dep_per_cycle.append(statistics.median(g))
    print(f"  final-regime deployment bursts : {len(dep_per_cycle)}")
    print(f"  orders per burst               : "
          f"{statistics.median(len(c.burst_orders) for c in fin):.0f} (median)")
    print(f"  intra-burst gap, all {len(dep_all):>5} gaps : "
          f"p10={q(dep_all,0.10):.3f}s  p50={q(dep_all,0.50):.3f}s  "
          f"p90={q(dep_all,0.90):.3f}s")
    print(f"  per-burst median gap           : "
          f"median={statistics.median(dep_per_cycle):.3f}s  "
          f"min={min(dep_per_cycle):.3f}s  max={max(dep_per_cycle):.3f}s")
    print(f"  => implied timer_ms            : "
          f"{statistics.median(dep_per_cycle)*1000:.0f} ms")

    # ---------------------------------------------------------------- panel B
    print()
    print("=" * 100)
    print("B. CANCEL CADENCE  (independent estimate of the same constant; "
          "CancelOneOrder is UNGATED)")
    print("=" * 100)
    canc = sorted((o for o in orders
                   if o.is_grid and o.state == "canceled" and o.end_time
                   and o.end_time >= FINAL_REGIME_START),
                  key=lambda o: o.end_time)
    csweeps = [s for s in group(canc, lambda o: o.end_time, SWEEP_GAP) if len(s) >= 5]
    cg_all, cg_med, csize = [], [], []
    for s in csweeps:
        g = gaps([o.end_time for o in s])
        cg_all += g
        cg_med.append(statistics.median(g))
        csize.append(len(s))
    print(f"  cancel sweeps (>=5 orders)     : {len(csweeps)}")
    print(f"  orders per sweep               : median={statistics.median(csize):.0f}  "
          f"min={min(csize)}  max={max(csize)}")
    print(f"  intra-sweep gap, all {len(cg_all):>5} gaps : "
          f"p10={q(cg_all,0.10):.3f}s  p50={q(cg_all,0.50):.3f}s  "
          f"p90={q(cg_all,0.90):.3f}s")
    print(f"  per-sweep median gap           : "
          f"median={statistics.median(cg_med):.3f}s  "
          f"min={min(cg_med):.3f}s  max={max(cg_med):.3f}s")
    print(f"  => implied timer_ms            : "
          f"{statistics.median(cg_med)*1000:.0f} ms")

    # ------------------------------------------------------------ close sweeps
    live = [p for p in positions
            if (p.open_time >= FINAL_REGIME_START
                or (p.close_time and p.close_time >= FINAL_REGIME_START))]
    closers = sorted((p for p in live if not p.is_open and p.close_time
                      and reason.get(p.position_id) == "STR CLOSE"),
                     key=lambda p: p.close_time)
    sweeps = [s for s in group(closers, lambda p: p.close_time, SWEEP_GAP)
              if s[0].close_time >= FINAL_REGIME_START]

    # ---------------------------------------------------------------- panel C
    print()
    print("=" * 100)
    print("C. FLATTEN CLOSE CADENCE -- H-gate (uniform 20 s) vs H-retry (mixed)")
    print("=" * 100)
    burst, paced, mixed, single = [], [], [], []
    for s in sweeps:
        g = gaps([p.close_time for p in s])
        if not g:
            single.append((s, g))
            continue
        m = statistics.median(g)
        rec = (s, g)
        if m <= BURST_MAX:
            burst.append(rec)
        elif m >= PACED_MIN:
            paced.append(rec)
        else:
            mixed.append(rec)
    n = len(sweeps)
    print(f"  final-regime flatten sweeps    : {n}   "
          f"(single-position: {len(single)})")
    for lab, grp in (("burst  (median gap <=1s)", burst),
                     ("paced  (median gap >=10s)", paced),
                     ("between (1s..10s)", mixed)):
        if not grp:
            print(f"  {lab:<26} : 0")
            continue
        med = [statistics.median(g) for _, g in grp]
        print(f"  {lab:<26} : {len(grp):>3}/{n}   "
              f"median of per-sweep median gap = {statistics.median(med):>7.3f}s")

    print()
    print("  DECISIVE: internal gap structure of every paced sweep.")
    print("  H-gate predicts every gap ~20s.  H-retry predicts a mixture "
          "(many ~0.1s, a few ~20s).")
    print(f"  {'n':>3} {'span':>9} {'fast<1s':>8} {'~20s':>6} {'other':>6} "
          f"{'min':>7} {'p50':>7} {'max':>7}   first gaps")
    for s, g in sorted(paced, key=lambda r: -len(r[1]))[:18]:
        fast = sum(1 for x in g if x < 1.0)
        near20 = sum(1 for x in g if 15.0 <= x <= 25.0)
        other = len(g) - fast - near20
        span = (s[-1].close_time - s[0].close_time).total_seconds()
        head = " ".join(f"{x:.1f}" for x in g[:9])
        print(f"  {len(s):>3} {span:>8.0f}s {fast:>8} {near20:>6} {other:>6} "
              f"{min(g):>7.2f} {statistics.median(g):>7.2f} {max(g):>7.2f}   {head}")

    allg = [x for _, g in paced for x in g]
    if allg:
        fast = sum(1 for x in allg if x < 1.0)
        near20 = sum(1 for x in allg if 15.0 <= x <= 25.0)
        print(f"\n  ALL gaps inside paced sweeps: {len(allg)}   "
              f"<1s: {fast} ({100*fast/len(allg):.1f}%)   "
              f"15-25s: {near20} ({100*near20/len(allg):.1f}%)   "
              f"other: {len(allg)-fast-near20}")
        print("  VERDICT: ", end="")
        if fast <= 0.05 * len(allg):
            print("uniform ~20s -> H-gate. close_interval_seconds IS a real rule; "
                  "find the mode selector.")
        elif fast >= 0.30 * len(allg):
            print("MIXED -> H-retry. The 20s gaps are stalls, not pacing. "
                  "close_interval_seconds should be 0.")
        else:
            print("ambiguous; neither hypothesis dominates.")

    # what separates burst from paced?
    print()
    print("  MODE SELECTOR -- what differs between burst and paced sweeps?")
    print(f"  {'metric':<26} {'burst':>14} {'paced':>14}")

    def desc(grp, fn):
        v = [fn(s) for s, _ in grp]
        return statistics.median(v) if v else float("nan")

    for lab, fn in (
        ("positions in sweep", lambda s: float(len(s))),
        ("gross lots", lambda s: sum(p.volume for p in s)),
        ("$/pt", lambda s: sum(p.volume for p in s) * CONTRACT),
        ("sweep net $", lambda s: sum(p.net for p in s)),
        ("hour of day (UTC+n)", lambda s: float(s[0].close_time.hour)),
        ("oldest position age (h)",
         lambda s: max((s[0].close_time - p.open_time).total_seconds()
                       for p in s) / 3600.0),
    ):
        print(f"  {lab:<26} {desc(burst, fn):>14.2f} {desc(paced, fn):>14.2f}")

    for lab, grp in (("burst", burst), ("paced", paced)):
        c = Counter(s[0].close_time.strftime("%a") for s, _ in grp)
        print(f"  {lab:<6} weekday: {dict(c)}")

    # ---------------------------------------------------------------- panel D
    print()
    print("=" * 100)
    print("D. PHASE ORDER -- cancel_before_close: is the cancel sweep strictly "
          "before the first close?")
    print("=" * 100)
    cend = [s[-1].end_time for s in csweeps]
    cbeg = [s[0].end_time for s in csweeps]
    lags, overlap = [], 0
    for s in sweeps:
        first = s[0].close_time
        # the cancel sweep whose window most closely precedes this flatten
        cand = [i for i in range(len(csweeps))
                if cbeg[i] <= first and (first - cbeg[i]).total_seconds() <= 3600]
        if not cand:
            continue
        i = cand[-1]
        lags.append((first - cend[i]).total_seconds())
        if cend[i] > first:
            overlap += 1
    if lags:
        print(f"  matched flatten sweeps         : {len(lags)}")
        print(f"  seconds from LAST cancel to FIRST close : "
              f"p10={q(lags,0.10):>8.2f}  p50={q(lags,0.50):>8.2f}  "
              f"p90={q(lags,0.90):>8.2f}")
        print(f"  sweeps where a cancel happened AFTER the first close (interleaved): "
              f"{overlap}/{len(lags)}")
        print("  => strict cancel-then-close phase order is "
              + ("CONFIRMED" if overlap == 0 else "VIOLATED"))


if __name__ == "__main__":
    main()
