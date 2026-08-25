"""DECISION vs EXECUTION.  Separating what the EA chose from what the market gave it.

ratchet_edges.py found mass just below the 2.0 stage-2 floor and read it as a possible
slope.  That reading conflates two different things, and parity depends on only one of
them:

    the DECISION   -- where the EA WROTE the stop.  Recorded per position as `stop_loss`.
                      This is the EA's rule, and it is what the replica must match.

    the EXECUTION  -- where the position actually CLOSED.  Recorded as `close_price`.
                      Differs from the decision by fill slippage, which is the broker's
                      behaviour and is not reproducible by any parameter.

The distinction is testable because both fields exist in the dataset.  Predictions:

    locked_at_SL  = dir*(stop_loss  - open)/step   -> must show a HARD edge at 2.0
    locked_at_fill= dir*(close_price- open)/step   -> may smear below it via slippage

If the sub-2.0 mass is slippage, it vanishes when measured at the decision and the
2.0 wall becomes clean.  If the sub-2.0 mass survives at the decision, then the EA
really did write stops below the floor and `trail_distance_steps`/`tighten_trigger_steps`
are wrong.  Those two outcomes are not close together, so this is a real test.

The same split re-examines the (1.0,2.0) PREDICTED HOLE.  The timer-pacing account says
the hole's residents are stops written on the OLD 2.0-step trail before the tighten tick
landed -- i.e. they are genuine decisions, and should persist at the decision level.  The
slippage account says they are fills that undershot.  Measuring both tells them apart,
and the answer is not obvious in advance.
"""
from __future__ import annotations

import statistics
import sys

sys.path.insert(0, r"C:\websites\mt5 2")
from tools.forensics.dataset import load_all, FINAL_REGIME_START  # noqa: E402
from tools.forensics.linkage import link_exits, exit_reason  # noqa: E402


def profile(name: str, vals: list[float]) -> None:
    if not vals:
        print(f"  {name:>26} : no data")
        return
    s = sorted(vals)
    n = len(s)
    print(f"  {name:>26} : n={n:<5} median {statistics.median(s):>7.3f}"
          f"  p10 {s[n//10]:>7.3f}  p90 {s[9*n//10]:>7.3f}")


def main() -> None:
    orders, positions, deals, cycles = load_all()
    exit_order, _ed, _en, _st = link_exits(orders, positions, deals)

    fin = [c for c in cycles if c.start >= FINAL_REGIME_START]
    step_by_cycle = {c.index: c.step for c in fin if c.step}
    fin_idx = {c.index for c in fin}

    pairs = []      # (locked_at_SL, locked_at_fill, slip_steps, volume)
    no_sl = 0
    for p in positions:
        if p.cycle not in fin_idx or p.is_open or p.close_time is None:
            continue
        if exit_reason(p, exit_order) != "sl":
            continue
        st = step_by_cycle.get(p.cycle)
        if not st or p.close_price is None:
            continue
        if not p.stop_loss:
            no_sl += 1
            continue
        d = p.dir
        at_sl = d * (p.stop_loss - p.open_price) / st
        at_fill = d * (p.close_price - p.open_price) / st
        pairs.append((at_sl, at_fill, at_fill - at_sl, round(p.volume, 2)))

    print("=" * 100)
    print("A. THE TWO MEASUREMENTS SIDE BY SIDE")
    print("=" * 100)
    print(f"  SL-closed positions with a recorded stop_loss : {len(pairs)}")
    print(f"  SL-closed positions with stop_loss == 0       : {no_sl}"
          "   (cannot be measured at the decision)")
    print()
    profile("locked at DECISION (SL)", [a for a, _b, _c, _v in pairs])
    profile("locked at EXECUTION (fill)", [b for _a, b, _c, _v in pairs])
    profile("slippage (fill - SL)", [c for _a, _b, c, _v in pairs])
    print()
    print("  A negative median slippage means fills land WORSE than the written stop,")
    print("  which is the normal direction and is the broker's behaviour, not the EA's.")

    print("=" * 100)
    print("B. THE 2.0 WALL, MEASURED AT THE DECISION vs AT THE FILL")
    print("=" * 100)
    edges = [1.00, 1.50, 1.75, 1.90, 1.95, 2.00, 2.05, 2.10, 2.25, 2.50]
    print(f"  {'bin':>16} {'at DECISION':>13} {'at FILL':>10}"
          f"   <- per 0.05 step of width")
    for lo, hi in zip(edges, edges[1:]):
        w = (hi - lo) / 0.05
        nd = sum(1 for a, _b, _c, _v in pairs if lo <= a < hi) / w
        nf = sum(1 for _a, b, _c, _v in pairs if lo <= b < hi) / w
        print(f"  {f'[{lo:.2f},{hi:.2f})':>16} {nd:>13.1f} {nf:>10.1f}")
    for lab, sel in (("DECISION", 0), ("FILL", 1)):
        blw = sum(1 for t in pairs if 1.75 <= t[sel] < 2.00)
        abv = sum(1 for t in pairs if 2.00 <= t[sel] < 2.25)
        r = f"{abv/blw:.1f}x" if blw else "INFINITE"
        print()
        print(f"  at {lab:>8}: [1.75,2.00) = {blw:<5} [2.00,2.25) = {abv:<5}"
              f"  ratio {r}")
    print()
    print("  If the DECISION ratio is far larger than the FILL ratio, the wall is real")
    print("  and the sub-2.0 mass at the fill is slippage -- not a parity defect,")
    print("  because no parameter controls where a triggered stop actually fills.")

    print()
    print("=" * 100)
    print("C. THE PREDICTED HOLE (1.0,2.0) -- DECISIONS OR FILLS?")
    print("=" * 100)
    hd = [t for t in pairs if 1.0 <= t[0] < 2.0]
    hf = [t for t in pairs if 1.0 <= t[1] < 2.0]
    n = len(pairs)
    print(f"  in the hole at the DECISION  : {len(hd)}/{n}"
          f" = {100.0*len(hd)/n:.1f}%")
    print(f"  in the hole at the FILL      : {len(hf)}/{n}"
          f" = {100.0*len(hf)/n:.1f}%")
    print()
    print("  The timer-pacing account predicts genuine DECISIONS in the hole (stops")
    print("  written on the old 2.0-step trail before the tighten tick landed).  The")
    print("  slippage account predicts the hole is populated only at the FILL.  Both")
    print("  can be partly true; the numbers above apportion them.")
    if hd:
        print()
        print("  Do the hole's DECISIONS look like stale 2.0-trail stops?  If so their")
        print("  implied peak = locked + 2.0 must be >= 3.0, i.e. locked >= 1.0 -- true")
        print("  by construction -- and their implied peak should exceed the tighten")
        print("  trigger, which is the whole point:")
        ip = sorted(t[0] + 2.0 for t in hd)
        print(f"    implied peak under a stale 2.0 trail: median {statistics.median(ip):.3f}"
              f"  min {ip[0]:.3f}  max {ip[-1]:.3f}")
        print(f"    fraction with implied peak >= 3.0 (tighten trigger): "
              f"{100.0*sum(1 for x in ip if x >= 3.0)/len(ip):.0f}%")
        print("    A stale-trail stop MUST imply a peak past the tighten trigger,")
        print("    otherwise the tighten was never due and the stop is unexplained.")

    print()
    print("=" * 100)
    print("D. IS THERE ANY DECISION BELOW THE STAGE-1 FLOOR?  (the hard falsifier)")
    print("=" * 100)
    print("  The gate returns false below lock_trigger_steps=2.0 and activation writes")
    print("  the stop at EXACT breakeven.  So the EA must never write a stop BELOW")
    print("  entry.  One such decision falsifies the activation rule outright.")
    neg = [t for t in pairs if t[0] < -0.02]
    print()
    print(f"  decisions with locked < -0.02 steps (stop below entry) : {len(neg)}/{n}")
    if neg:
        w = sorted(neg, key=lambda t: t[0])[:6]
        for a, b, c, v in w:
            print(f"    at SL {a:+.3f}  at fill {b:+.3f}  slip {c:+.3f}  vol {v:.2f}")
        print("  ^ investigate these before claiming the activation rule holds.")
    else:
        print("  NONE.  The EA never wrote a stop below entry in the final regime.")
        print("  That is the activation rule (`entry + 0*step`) holding without")
        print("  exception across every measurable SL closure.")


if __name__ == "__main__":
    main()
