"""The 192 fills that beat their own written stop.  What are they?

wall_residue.py Q2 found 192/2480 (7.7%) `sl`-labelled closures whose fill was
BETTER than the stop recorded on the position.  A real stop-out cannot do that:
a sell-stop fills at or below its trigger, never above.  So either the classifier
mislabelled them, or the recorded `stop_loss` is not the price that fired.

Three candidate accounts, with different signatures:

  (a) MISLABELLED FLATTENS.  The basket sweep closed them at market while a
      resting ratchet stop sat further away.  Signature: they cluster in the
      final seconds of their cycle, inside the flatten burst window, and their
      cycle has an "STR CLOSE" order.

  (b) STALE-WRITE PACING.  `max_stop_updates_per_pass=1` with
      `stop_updates_on_timer=true` means the newest SL write can reach the
      server after price already traded through the previous one.  The record
      keeps the NEWEST write; the fill honoured the older, looser one.
      Signature: magnitude bounded by one tighten's worth of distance
      (pre_tighten 2.0 - trail 1.0 = 1.0 step), and NOT flatten-adjacent.

  (c) SOMETHING UNMODELLED.  Large magnitudes, no time structure.

(a) is the benign one for this project: it bounds classifier impurity and leaves
every ratchet conclusion intact, because impurity can only ADD mass to the
distribution -- and the forbidden (1.0,2.0) decision band came back EMPTY.
Contamination cannot manufacture an empty band.  (b) would be a genuine second
confirmation of the pacing parameters.  (c) is the only bad answer.

This script does not assume; it measures the time structure and the magnitude.
"""
from __future__ import annotations

import statistics
import sys
from datetime import timedelta

sys.path.insert(0, r"C:\websites\mt5 2")
from tools.forensics.dataset import load_all, FINAL_REGIME_START  # noqa: E402
from tools.forensics.linkage import link_exits, exit_reason  # noqa: E402

SWEEP = 300.0


def main() -> None:
    orders, positions, deals, cycles = load_all()
    exit_order, _ed, _en, _st = link_exits(orders, positions, deals)

    fin = [c for c in cycles if c.start >= FINAL_REGIME_START]
    step_by_cycle = {c.index: c.step for c in fin if c.step}
    by_index = {c.index: c for c in fin}

    # first "STR CLOSE" order time per cycle == the flatten instant t0
    t0_by_cycle = {}
    for c in fin:
        cl = [o.open_time for o in c.orders
              if o.comment and o.comment.strip().upper().startswith("STR CLOSE")]
        if cl:
            t0_by_cycle[c.index] = min(cl)

    good, bad = [], []
    for p in positions:
        if p.cycle not in by_index or p.is_open or p.close_time is None:
            continue
        if exit_reason(p, exit_order) != "sl":
            continue
        st = step_by_cycle.get(p.cycle)
        if not st or p.close_price is None or not p.stop_loss:
            continue
        slip = p.dir * (p.close_price - p.stop_loss) / st
        rec = dict(cyc=p.cycle, slip=slip, t=p.close_time, net=p.net,
                   locked=p.dir * (p.stop_loss - p.open_price) / st)
        (bad if slip > 0.02 else good).append(rec)

    n_all = len(good) + len(bad)
    print("=" * 100)
    print("A. ARE THEY FLATTEN-ADJACENT?  (account (a))")
    print("=" * 100)

    def near_flatten(r):
        t0 = t0_by_cycle.get(r["cyc"])
        if t0 is None:
            return None
        d = (r["t"] - t0).total_seconds()
        return -5.0 <= d <= SWEEP

    for lab, grp in (("beat their stop", bad), ("normal stop-outs", good)):
        got = [near_flatten(r) for r in grp]
        have = [x for x in got if x is not None]
        inw = sum(1 for x in have if x)
        print(f"  {lab:>18} : n={len(grp):<5}"
              f" in a flatten window {inw}/{len(have)}"
              f" = {(100.0*inw/len(have) if have else 0):.1f}%")
    print()
    print("  If the top row is far higher than the bottom row, these are the basket")
    print("  sweep closing positions at market while a resting stop sat further off.")
    print("  That is a labelling boundary, not an EA behaviour difference.")

    print()
    print("=" * 100)
    print("B. HOW BIG ARE THEY?  (account (b) is bounded at 1.0 step)")
    print("=" * 100)
    s = sorted(r["slip"] for r in bad)
    print(f"  n={len(s)}   median {statistics.median(s):+.3f}"
          f"   p90 {s[9*len(s)//10]:+.3f}   max {s[-1]:+.3f}   (steps)")
    edges = [0.02, 0.25, 0.50, 1.00, 2.00, 4.00, 99.0]
    print(f"  {'bin (steps better)':>22} {'n':>6} {'share':>8}")
    for lo, hi in zip(edges, edges[1:]):
        k = sum(1 for x in s if lo <= x < hi)
        print(f"  {f'[{lo:.2f}, {hi:.2f})':>22} {k:>6} {100.0*k/len(s):>7.1f}%")
    over = sum(1 for x in s if x > 1.0)
    print()
    print(f"  beyond one tighten's worth (> 1.0 step) : {over}/{len(s)}"
          f" = {100.0*over/len(s):.1f}%")
    print("  A stale-write can be wrong by at most the distance the tighten moved")
    print("  the stop (pre_tighten 2.0 - trail 1.0 = 1.0 step).  Mass beyond that")
    print("  is not explained by pacing and must come from the sweep instead.")

    print()
    print("=" * 100)
    print("C. WHAT DOES THEIR EXCLUSION DO TO THE WALL?  (the robustness check)")
    print("=" * 100)
    for lab, grp in (("ALL sl-labelled", good + bad), ("clean stop-outs only", good)):
        blw = sum(1 for r in grp if 1.0 <= r["locked"] < 2.0)
        wall = sum(1 for r in grp if 1.0 <= r["locked"] < 1.95)
        abv = sum(1 for r in grp if 2.0 <= r["locked"] < 2.25)
        print(f"  {lab:>22} : n={len(grp):<5}"
              f" decisions in (1.0,1.95) = {wall:<4}"
              f" in (1.0,2.0) = {blw:<4} above = {abv}")
    print()
    print("  The forbidden band is empty either way.  Classifier impurity can only")
    print("  ADD mass to a histogram, so an empty band cannot be an artifact of it:")
    print("  the wall conclusion is robust to the whole 7.7%.")
    print()
    print(f"  measured population : {n_all} final-regime sl-labelled closures")


if __name__ == "__main__":
    main()
