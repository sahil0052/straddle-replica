"""Q1b: separate TRAIL DISTANCE from UPDATE STARVATION.

Hypothesis from the cycle-267 dump: the EA trails each position at
market -/+ D*step, but a per-pass update budget combined with a newest-first
scan starves older positions, so their SL freezes at a stale market sample.

Consequences, all testable:
  (H1) positions updated in the same pass share an identical SL price
  (H2) implied trail D = (peak_obs - sl)/step grows with 'starvation pressure'
       (how many same-side siblings opened after it, i.e. how often it lost the
       single update slot)
  (H3) on the UNSTARVED subset -- positions that were the newest of their side
       for their whole life -- implied D collapses onto the true trail distance.

(H3) is the clean estimator of D.  (H1)/(H2) confirm the mechanism.
"""
from __future__ import annotations

import statistics
import sys
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict

sys.path.insert(0, r"C:\websites\mt5 2")
from tools.forensics.dataset import load_all, FINAL_REGIME_START  # noqa: E402
from tools.forensics.attribution import build_exit_index, attribute  # noqa: E402


def q(vals, *qs):
    v = sorted(vals)
    return [f"{v[int(x * (len(v) - 1))]:.3f}" for x in qs]


def main() -> None:
    orders, positions, deals, cycles = load_all()
    class_by_time, _, _ = build_exit_index(orders, deals)
    reason, _, _ = attribute(positions, class_by_time)
    step_by_cycle = {c.index: c.step for c in cycles}

    fr = [p for p in positions
          if p.open_time >= FINAL_REGIME_START and p.cycle >= 0
          and not p.is_open and p.stop_loss]
    print(f"final-regime closed positions with an SL on record: {len(fr)}")

    # ---------- H1: do positions share identical SL prices? ------------------
    print("\n" + "=" * 78)
    print("H1  SL SHARING: is the in-force SL per-position or per-pass?")
    print("=" * 78)
    groups = defaultdict(list)
    for p in fr:
        groups[(p.cycle, p.side, round(p.stop_loss, 5))].append(p)
    sizes = Counter(len(v) for v in groups.values())
    shared = sum(len(v) for v in groups.values() if len(v) > 1)
    print(f"distinct (cycle, side, sl) groups: {len(groups)}")
    print(f"group-size histogram: {dict(sorted(sizes.items()))}")
    print(f"positions sharing an SL price with >=1 sibling: {shared}/{len(fr)} "
          f"({100*shared/len(fr):.1f}%)")

    # if SL were a per-position function of entry, sharing would be accidental.
    # Control: how often do two same-side positions in a cycle share an ENTRY?
    egroups = defaultdict(list)
    for p in fr:
        egroups[(p.cycle, p.side, round(p.open_price, 5))].append(p)
    esh = sum(len(v) for v in egroups.values() if len(v) > 1)
    print(f"control - positions sharing an ENTRY price with a sibling: "
          f"{esh}/{len(fr)} ({100*esh/len(fr):.1f}%)")

    multi = [v for v in groups.values() if len(v) > 1]
    print(f"\nsample shared-SL groups (locked profit differs => SL not entry-based):")
    for g in sorted(multi, key=lambda g: -len(g))[:6]:
        st = step_by_cycle[g[0].cycle]
        d = 1.0 if g[0].side == "buy" else -1.0
        print(f"  cyc={g[0].cycle} {g[0].side} sl={g[0].stop_loss} n={len(g)}")
        for p in sorted(g, key=lambda p: p.open_time):
            print(f"     {p.comment:<8} entry={p.open_price:<9} "
                  f"locked={d*(p.stop_loss-p.open_price)/st:>6.2f}st "
                  f"open={p.open_time.strftime('%m-%d %H:%M:%S')} "
                  f"close={p.close_time.strftime('%H:%M:%S')}")

    # ---------- build price observations ------------------------------------
    pts = []
    for p in positions:
        pts.append((p.open_time, p.open_price))
        if p.close_time and p.close_price:
            pts.append((p.close_time, p.close_price))
    for o in orders:
        if o.state == "filled" and o.end_time and o.price is not None:
            pts.append((o.end_time, o.price))
    pts.sort()
    obs_t = [t for t, _ in pts]
    obs_p = [p for _, p in pts]

    # ---------- starvation pressure -----------------------------------------
    # For each position: how many same-side same-cycle positions OPENED strictly
    # after it while it was still alive?  Each such event hands the single update
    # slot to a newer position under a newest-first scan.
    by_side = defaultdict(list)
    for p in fr:
        by_side[(p.cycle, p.side)].append(p)
    opens_by_side = {k: sorted(x.open_time for x in v) for k, v in by_side.items()}

    rows = []
    for p in fr:
        if reason.get(p.position_id) != "sl":
            continue
        st = step_by_cycle.get(p.cycle) or 0.0
        if st <= 0 or not p.close_time:
            continue
        i = bisect_left(obs_t, p.open_time)
        j = bisect_right(obs_t, p.close_time)
        if j - i < 2:
            continue
        seg = obs_p[i:j]
        d = 1.0 if p.side == "buy" else -1.0
        peak = max(seg) if p.side == "buy" else min(seg)
        peak_steps = d * (peak - p.open_price) / st
        implied = d * (peak - p.stop_loss) / st
        locked = d * (p.stop_loss - p.open_price) / st
        ol = opens_by_side[(p.cycle, p.side)]
        newer = (bisect_right(ol, p.close_time) - bisect_right(ol, p.open_time))
        life = (p.close_time - p.open_time).total_seconds()
        rows.append(dict(p=p, step=st, peak=peak_steps, implied=implied,
                         locked=locked, newer=newer, life=life, nobs=j - i))

    print("\n" + "=" * 78)
    print("H2  STARVATION PRESSURE vs IMPLIED TRAIL DISTANCE")
    print("=" * 78)
    print(f"{'newer siblings':<16}{'n':>6}{'med D':>8}{'p90 D':>8}{'max D':>8}"
          f"{'med peak':>10}{'med life s':>12}")
    for lo, hi, lab in [(0, 1, "0"), (1, 2, "1"), (2, 3, "2"), (3, 5, "3-4"),
                        (5, 9, "5-8"), (9, 10**9, "9+")]:
        sel = [r for r in rows if lo <= r["newer"] < hi]
        if not sel:
            continue
        imp = sorted(r["implied"] for r in sel)
        print(f"{lab:<16}{len(sel):>6}{statistics.median(imp):>8.3f}"
              f"{imp[int(.9*(len(imp)-1))]:>8.3f}{max(imp):>8.3f}"
              f"{statistics.median([r['peak'] for r in sel]):>10.3f}"
              f"{statistics.median([r['life'] for r in sel]):>12.0f}")

    # ---------- H3: the unstarved subset ------------------------------------
    print("\n" + "=" * 78)
    print("H3  UNSTARVED SUBSET  (no same-side sibling opened during its life)")
    print("=" * 78)
    un = [r for r in rows if r["newer"] == 0]
    imp = sorted(r["implied"] for r in un)
    print(f"n={len(un)}  implied-D quantiles "
          f"[min,p50,p75,p90,p95,p99,max] = "
          f"{q(imp, 0, .5, .75, .9, .95, .99, 1)}")
    print(f"  > 1.02 : {sum(1 for v in imp if v > 1.02)}")
    print(f"  > 2.02 : {sum(1 for v in imp if v > 2.02)}")
    print(f"  > 2.10 : {sum(1 for v in imp if v > 2.10)}")

    print("\n  unstarved, split by observed peak (the 2-stage model predicts")
    print("  D=2 while peak<3 and D=1 once peak>=3):")
    print(f"  {'peak bucket':<14}{'n':>6}{'med D':>8}{'p90 D':>8}{'max D':>8}"
          f"{'med locked':>12}")
    for lo, hi in [(0, 2), (2, 2.5), (2.5, 3), (3, 3.5), (3.5, 4), (4, 5),
                   (5, 7), (7, 99)]:
        sel = [r for r in un if lo <= r["peak"] < hi]
        if not sel:
            continue
        s = sorted(r["implied"] for r in sel)
        print(f"  [{lo:>4.1f},{hi:>4.1f})  {len(sel):>6}{statistics.median(s):>8.3f}"
              f"{s[int(.9*(len(s)-1))]:>8.3f}{max(s):>8.3f}"
              f"{statistics.median([r['locked'] for r in sel]):>12.3f}")

    print("\n  unstarved worst 12:")
    for r in sorted(un, key=lambda r: -r["implied"])[:12]:
        p = r["p"]
        print(f"    D={r['implied']:>6.3f} peak={r['peak']:>6.2f} "
              f"locked={r['locked']:>6.2f} life={r['life']:>7.0f}s "
              f"{p.side:<4} {p.comment:<8} cyc={p.cycle} {p.open_time}")


if __name__ == "__main__":
    main()
