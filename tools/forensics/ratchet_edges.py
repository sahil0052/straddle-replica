"""The stage-2 floor as a HARD EDGE, and breakeven activation to the tick.

parity_verdict.py panel A2 established the BANDS (density 700/755/138/799, the (1.0,2.0)
hole depleted 5.5x-5.8x).  Bands are a coarse instrument: any two-stage-ish ratchet with
roughly these numbers produces roughly these bands.  This script tests the two places
where the configured arithmetic makes an EXACT, brittle claim that a merely approximate
ratchet would fail.

  EDGE 1 -- the stage-2 floor at exactly 2.0.
      `distance = 1.0` once `favorable_steps >= 3.0`, so a runner that reaches peak P>=3.0
      closes at P-1.0 >= 2.0.  The floor is therefore not a soft tendency: it is a WALL at
      2.0.  Test: bin closes finely around 2.0.  A wall means the density immediately
      below 2.0 collapses while the density immediately above it is large.  If instead the
      distribution slides smoothly through 2.0, `trail_distance_steps` is not 1.0 and the
      tighten trigger is not 3.0.

  EDGE 2 -- activation at EXACT breakeven, to the tick.
      With `activation_uses_trailing_distance = true`, the first stop is
      `market - 2.0*step` evaluated at the moment `favorable_steps` first reaches 2.0,
      i.e. `entry + 2.0*step - 2.0*step = entry`.  Not "near" entry -- entry, up to tick
      rounding and the broker clamp.  Test: for closes in the breakeven spike, measure
      |close - open| in TICKS, not steps.  If activation used `lock_offset_price` instead,
      or a different pre-tighten distance, the spike would sit at a systematic OFFSET from
      zero rather than centred on it.

Both edges are measured from close price vs open price with the per-cycle step -- no SL
reconstruction, no marks, no spread model.  A false ratchet can imitate a histogram; it
cannot imitate a wall AND a tick-exact zero at the same time.
"""
from __future__ import annotations

import statistics
import sys
from collections import defaultdict

sys.path.insert(0, r"C:\websites\mt5 2")
from tools.forensics.dataset import load_all, FINAL_REGIME_START  # noqa: E402
from tools.forensics.linkage import link_exits, exit_reason  # noqa: E402

LOCK_TRIGGER = 2.0
PRE_TIGHTEN = 2.0
TIGHTEN_TRIGGER = 3.0
TRAIL = 1.0


def main() -> None:
    orders, positions, deals, cycles = load_all()
    exit_order, _ed, _en, _st = link_exits(orders, positions, deals)

    fin = [c for c in cycles if c.start >= FINAL_REGIME_START]
    step_by_cycle = {c.index: c.step for c in fin if c.step}
    fin_idx = {c.index for c in fin}

    locked = []          # (steps, ticks, money)
    for p in positions:
        if p.cycle not in fin_idx or p.is_open or p.close_time is None:
            continue
        if exit_reason(p, exit_order) != "sl":
            continue
        st = step_by_cycle.get(p.cycle)
        if not st or p.close_price is None:
            continue
        raw = p.dir * (p.close_price - p.open_price)
        locked.append((raw / st, raw, abs(p.net)))

    print("=" * 100)
    print("A. EDGE 1 -- IS THE STAGE-2 FLOOR A WALL AT EXACTLY 2.0, OR A SLOPE?")
    print("=" * 100)
    print(f"  configured: trail_distance_steps={TRAIL} applies at"
          f" favorable_steps>={TIGHTEN_TRIGGER}")
    print(f"  => a runner peaking at P>={TIGHTEN_TRIGGER} closes at"
          f" P-{TRAIL} >= {TIGHTEN_TRIGGER-TRAIL}.  Nothing may sit just below.")
    print()
    edges = [1.00, 1.25, 1.50, 1.75, 1.90, 1.95, 2.00,
             2.05, 2.10, 2.25, 2.50, 3.00]
    print(f"  {'bin (steps locked)':>22} {'positions':>10} {'per 0.05 step':>15}")
    for lo, hi in zip(edges, edges[1:]):
        n = sum(1 for s, _t, _m in locked if lo <= s < hi)
        print(f"  {f'[{lo:.2f}, {hi:.2f})':>22} {n:>10}"
              f" {n/((hi-lo)/0.05):>15.1f}")
    below = sum(1 for s, _t, _m in locked if 1.75 <= s < 2.00)
    above = sum(1 for s, _t, _m in locked if 2.00 <= s < 2.25)
    print()
    print(f"  immediately BELOW the wall [1.75,2.00) : {below}")
    print(f"  immediately ABOVE the wall [2.00,2.25) : {above}")
    if below:
        print(f"  ratio above:below = {above/below:.1f}x"
              "   <- a slope would give ~1x; a wall gives a large number")
    else:
        print("  ratio above:below = INFINITE (nothing below the wall at all)")

    print()
    print("=" * 100)
    print("B. EDGE 2 -- IS THE BREAKEVEN SPIKE TICK-EXACT ZERO, OR OFFSET?")
    print("=" * 100)
    print("  activation_uses_trailing_distance=true =>"
          f" first SL = market - {PRE_TIGHTEN}*step")
    print(f"  evaluated when favorable_steps first hits {LOCK_TRIGGER}"
          f" => SL = entry + ({LOCK_TRIGGER}-{PRE_TIGHTEN})*step = entry EXACTLY.")
    print()
    spike = [(s, t, m) for s, t, m in locked if -0.25 <= s < 0.25]
    if spike:
        pr = sorted(t for _s, t, _m in spike)
        print(f"  positions in the spike            : {len(spike)}")
        print(f"  price delta (close-open, signed)  : median {statistics.median(pr):+.5f}")
        print(f"                                      p10 {pr[len(pr)//10]:+.5f}"
              f"   p90 {pr[9*len(pr)//10]:+.5f}")
        print(f"  mean absolute offset              : "
              f"{statistics.mean(abs(t) for _s, t, _m in spike):.5f}")
        exact = sum(1 for _s, t, _m in spike if abs(t) < 1e-9)
        print(f"  EXACTLY zero to the cent          : {exact}/{len(spike)}"
              f" = {100.0*exact/len(spike):.0f}%")
        print()
        print("  A spike centred on zero with a large exactly-zero mass is what")
        print("  `entry + 0*step` produces.  A different activation rule (lock_offset,")
        print("  or a pre-tighten distance != lock_trigger) would centre it ELSEWHERE.")

    print()
    print("=" * 100)
    print("C. THE SAME TEST, SPLIT BY LOT TIER  (does the ratchet care about size?)")
    print("=" * 100)
    print("  The ratchet is configured per-position with no volume term, so the band")
    print("  structure must be IDENTICAL across tiers.  If the 0.15 tier behaved")
    print("  differently the rule would be volume-dependent and the replica wrong.")
    print()
    tiers: dict[float, list] = defaultdict(list)
    for p in positions:
        if p.cycle not in fin_idx or p.is_open or p.close_time is None:
            continue
        if exit_reason(p, exit_order) != "sl":
            continue
        st = step_by_cycle.get(p.cycle)
        if not st or p.close_price is None:
            continue
        tiers[round(p.volume, 2)].append(p.dir * (p.close_price - p.open_price) / st)
    print(f"  {'volume':>8} {'n':>6} {'median':>9} {'%breakeven':>11}"
          f" {'%hole 1-2':>10} {'%>=2.0':>9}")
    for v, ss in sorted(tiers.items()):
        if len(ss) < 5:
            continue
        n = len(ss)
        print(f"  {v:>8.2f} {n:>6} {statistics.median(ss):>9.3f}"
              f" {100.0*sum(1 for s in ss if -0.25 <= s < 0.25)/n:>10.0f}%"
              f" {100.0*sum(1 for s in ss if 1.0 <= s < 2.0)/n:>9.0f}%"
              f" {100.0*sum(1 for s in ss if s >= 2.0)/n:>8.0f}%")
    print()
    print("  Consistent columns across tiers = the ratchet is volume-blind, as coded.")


if __name__ == "__main__":
    main()
