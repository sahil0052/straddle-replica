"""Q4e: the remaining pacing knobs, split at the Jul-24 break.

The replica's LATEST_30 profile carries four pacing constants, three already at 20:
    close_interval_seconds          = 20   confirmed by q4b (post-break)
    rearm_delay_seconds             = 20   confirmed by q4d (post-break floor)
    restart_delay_ms                = 20000
    deployment_fill_cooldown_seconds= 20

The Jul-24 change turned the first two on together, which suggests the operator
raised a family of pacing settings at once.  Test the other two the same way.

Panel A  restart_delay_ms: seconds from the LAST close of a flatten sweep to the
         FIRST pending of the next deployment burst.  In the replica this path is
         CYCLE_RESTARTING -> wait (restart_delay_ms+999)/1000 s -> CYCLE_IDLE ->
         StartCycle() + DeployOne(), so the observed gap is the floor.

Panel B  deployment_fill_cooldown_seconds: does any entry actually FILL while a
         deployment burst is still placing orders?  If none do, the constant never
         bites and is untestable.  If some do, a 20 s cooldown must appear as a 20 s
         hole in that burst -- and q4c measured the largest intra-burst gap in the
         whole final regime at 0.122 s, so the prediction is already in tension.
"""
from __future__ import annotations

import statistics
import sys
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

    fin_cycles = [c for c in cycles
                  if c.start >= FINAL_REGIME_START and c.burst_orders]
    fin_cycles.sort(key=lambda c: c.start)

    # ---------------------------------------------------------------- panel A
    print("=" * 100)
    print("A. RESTART DELAY -- last close of a flatten -> first pending of the next "
          "deployment burst")
    print("=" * 100)
    res = {"EARLY": [], "LATE": []}
    for s in sweeps:
        end = s[-1].close_time
        nxt = next((c for c in fin_cycles if c.start > end), None)
        if not nxt:
            continue
        d = (nxt.start - end).total_seconds()
        if d <= 3600.0:
            res[side(nxt.start)].append(d)
    for lab in ("EARLY", "LATE"):
        v = sorted(res[lab])
        if not v:
            print(f"  {lab}: none")
            continue
        print(f"\n  {lab}  n={len(v)}  min={v[0]:.2f}s  "
              f"median={statistics.median(v):.2f}s  max={v[-1]:.2f}s")
        print(f"    20 smallest : " + " ".join(f"{x:.2f}" for x in v[:20]))
        for lo, hi, lab2 in ((0, 4.5, "< 4.5s"), (4.5, 19.0, "4.5-19s"),
                             (19.0, 22.0, "19-22s"), (22.0, 1e9, "> 22s")):
            print(f"    {lab2:<8} {sum(1 for x in v if lo <= x < hi):>4}")

    # ---------------------------------------------------------------- panel B
    print()
    print("=" * 100)
    print("B. DEPLOYMENT FILL COOLDOWN -- do entries fill while the burst is still "
          "deploying?")
    print("=" * 100)
    pos_by_id = {p.position_id: p for p in positions}
    hits = {"EARLY": 0, "LATE": 0}
    bursts = {"EARLY": 0, "LATE": 0}
    worst = []
    for c in fin_cycles:
        b = sorted(c.burst_orders, key=lambda o: o.open_time)
        t0, t1 = b[0].open_time, b[-1].open_time
        s = side(c.start)
        bursts[s] += 1
        n = 0
        for o in b:
            if o.state != "filled":
                continue
            p = pos_by_id.get(o.order_id)
            if p and t0 <= p.open_time <= t1:
                n += 1
        if n:
            hits[s] += 1
            g = [(y.open_time - x.open_time).total_seconds()
                 for x, y in zip(b, b[1:])]
            worst.append((n, len(b), (t1 - t0).total_seconds(),
                          max(g) if g else 0.0, c.start))
    for lab in ("EARLY", "LATE"):
        print(f"  {lab:<5} bursts={bursts[lab]:<4} "
              f"bursts containing an in-burst fill = {hits[lab]}")
    if worst:
        print(f"\n  {'fills':>5} {'orders':>7} {'span':>8} {'max gap':>9}   cycle start")
        for n, ln, span, mg, st in sorted(worst, key=lambda r: -r[0])[:12]:
            print(f"  {n:>5} {ln:>7} {span:>7.1f}s {mg:>8.3f}s   {st}")
        print("\n  A 20s cooldown would force max gap >= 20s in every one of these "
              "bursts.")
        print("  => deployment_fill_cooldown_seconds = 20 is "
              + ("REFUTED" if all(r[3] < 5.0 for r in worst) else "possible"))
    else:
        print("\n  No burst contains an in-burst fill -- the constant never bites "
              "and is untestable.")


if __name__ == "__main__":
    main()
