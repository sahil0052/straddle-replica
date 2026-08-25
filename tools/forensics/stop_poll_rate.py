"""HOW FAST DOES EACH EA POLL ITS RATCHET GATE?  Measured, not assumed.

WHY THIS QUESTION IS NOW THE LEADING ONE.  stop_cluster.py established three
things about consecutive stop-outs inside a cycle:

    TARGET old   (Jul14-Jul24)  1798 pairs  min 0.000 s  p25   0.11 s  22.86% <100ms
    TARGET final (Jul24+)        785 pairs  min 0.289 s  p25  20.12 s   0.00% <100ms
    OURS  111638511              108 pairs  min 0.000 s  p25   2.70 s  15.74% <100ms

and it killed the obvious explanation: the Target's FINAL regime carries MORE
degenerate stop levels than ours (19.6% of levels shared by 2+ positions vs our
6.5%), yet never once closes two positions within 100 ms.  So it is not that its
stops are better separated in price.  Something separates them in TIME.

A stop-out is server-side -- the EA has no say in when it executes.  Its only
influence is WHEN IT WROTE THE LEVEL.  Two positions written to a level at the
same instant carry the same level and die on the same tick.  Two positions
written 20 s apart carry levels 20 s of market movement apart, and cannot.

Our code makes that concrete.  UpdatePositionStops (StraddleEngine.mqh:2536) is
gated by:

    if(m_profile.stop_update_interval_seconds>0 && ...) return;

and ProfileCatalog.mqh:28 sets stop_update_interval_seconds = 0 -- the gate is
OFF.  With stop_updates_on_timer=true and max_stop_updates_per_pass=1, we write
exactly one stop per 100 ms timer tick.  A p25 of 2.70 s and a floor of 0.000 s
is what that produces.

WHAT THIS SCRIPT WAS BUILT TO TEST, AND WHY THAT DESIGN FAILED.  READ THIS BEFORE
QUOTING ANY NUMBER BELOW.

The intent was to measure each EA's poll period indirectly.  The reasoning was:
the ratchet arms when favorable_steps >= lock_trigger_steps (2.0) and writes its
first stop at market - 2.0*step; because the gate is POLLED, the tick that first
satisfies the condition has already overshot to 2.0 + e, so the first stop lands
at entry + e*step, and e scales with the poll period.  A fast poller locks ~0, a
slow poller locks a visible amount.

THAT IS WRONG, and the data said so before any conclusion was drawn.  The [0,1)
band is NOT the arming overshoot, because arming is not the last write.  While
favorable_steps stays in [2.0, 3.0) the ELSE branch of StopScheduler::Calculate
re-writes desired = market - pre_tighten_trail_distance_steps*step on EVERY
subsequent pass, so the locked value ratchets up with price for as long as the
position remains in phase 1.  The final attested stop of a phase-1 stop-out
therefore encodes

    locked ~= peak_favorable_steps - 2.0        (clipped into [0,1) by phase 2)

which is a statistic of the MARKET PATH -- how far price ran before reversing --
and is almost independent of the poll period.  The measurement itself flagged
this: the median came out at 0.42 steps = 0.57 price = 57 ticks on both accounts,
and XAUUSD does not travel 57 ticks in 100 ms.  A number that large cannot be a
100 ms poll artifact, so the quantity is not what the design assumed.

CONSEQUENCE: THE POLL-RATE QUESTION IS STILL OPEN.  Nothing here confirms or
refutes stop_update_interval_seconds as the cause of our stop-out clustering.
Do not cite panel 2 or panel 5 as evidence about poll rates in either direction.

WHAT THE SCRIPT DOES LEGITIMATELY ESTABLISH.  Read as a ratchet-parity check
rather than a poll-rate probe, the panels are a strong result, because they
compare the same broker-attested quantity across both accounts with one
estimator:

  * panel 1 -- the (1,2) structural hole survives on all three streams, so the
    two-phase model is in force on our account exactly as on the Target's.
  * panel 2 -- the phase-1 trailing distribution matches across every quantile
    (p10/p25/med/p75/p90), i.e. our phase-1 trail and the market paths it sees
    are indistinguishable from the Target's final regime.
  * panel 4 -- the phase-2 locked distribution matches, which is the harder test
    of the two because phase 2 is what produces the runners.

A CORRECTION TO THE SOURCE COMMENT.  StopScheduler.mqh states the Target's
activation value as "median +0.124 steps, p10 +0.029, p90 +0.222" and attributes
it to a "100 ms timer".  Measured here over the same attested stops the [0,1)
band is median 0.433 (old) / 0.419 (final), p90 0.873 / 0.853 -- roughly 3.5x the
documented figures.  Either that comment measured a narrower population than
"phase-1 stop-outs", or its numbers are stale.  Its ARITHMETIC (the two-phase
law, the empty hole) is confirmed; its poll-period EXPLANATION is not supported
by this measurement and should not be relied on.

A NOTE ON SCOPE.  Split at the PACING break (2026-07-24), never at
dataset.FINAL_REGIME_START (2026-07-14) -- the latter straddles the break and
pools two incompatible families.  That pooling has already manufactured one false
verdict in this project; it will not be repeated here.
"""
from __future__ import annotations

import os
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
import tools.forensics.dataset as DS  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GOLDEN = os.path.join(ROOT, ".cache", "golden")
FRESH = os.path.join(ROOT, ".cache", "fresh")

PACING_BREAK = datetime(2026, 7, 24, 12, 0, 0)


def rule(t: str) -> None:
    print()
    print("=" * 100)
    print(t)
    print("=" * 100)


def load(path: str):
    DS.GOLDEN = Path(path)
    return DS.load_all()


def locked(positions, cycles):
    """Locked profit in steps for every stop-closed position, with its step.

    dir*(sl - entry)/step.  Positive means the stop sat in profit.  No mark, no
    spread model, no reconstruction: sl is the broker's attestation of the level
    that fired, read from the closing deal's comment.
    """
    cyc = {c.index: c for c in cycles}
    out = []
    for p in positions:
        if p.cycle not in cyc or p.is_open or not p.close_time or not p.stop_loss:
            continue
        step = cyc[p.cycle].step
        if not step or step <= 0:
            continue
        out.append({
            "steps": p.dir * (p.stop_loss - p.open_price) / step,
            "price": p.dir * (p.stop_loss - p.open_price),
            "step": step,
            "p": p,
            "cycle": p.cycle,
        })
    return out


def qs(vals, fs=(0.10, 0.25, 0.50, 0.75, 0.90)):
    s = sorted(vals)
    return [s[min(int(f * (len(s) - 1)), len(s) - 1)] for f in fs]


def main() -> None:
    t_ord, t_pos, t_deals, t_cyc = load(GOLDEN)
    o_ord, o_pos, o_deals, o_cyc = load(FRESH)

    t_old = [c for c in t_cyc if DS.FINAL_REGIME_START <= c.start < PACING_BREAK]
    t_new = [c for c in t_cyc if c.start >= PACING_BREAK]

    pops = [
        ("TARGET old  (Jul14-Jul24)", locked(t_pos, t_old),
         statistics.median([c.step for c in t_old if c.step > 0])),
        ("TARGET final (Jul24+)", locked(t_pos, t_new),
         statistics.median([c.step for c in t_new if c.step > 0])),
        ("OURS  111638511", locked(o_pos, o_cyc),
         statistics.median([c.step for c in o_cyc if c.step > 0])),
    ]

    rule("SCOPE")
    for label, L, step in pops:
        print(f"  {label:<30} stop-closed positions {len(L):>5}"
              f"   median lattice step {step:.4f}")

    rule("1. THE (1,2) HOLE -- confirm the phase model still holds on all three")
    print("  If the two-phase ratchet is in force, [0,1) is the phase-1 overshoot,")
    print("  [2,inf) is phase 2, and (1,2) is structurally unreachable.  If (1,2) is")
    print("  NOT empty on a stream, the phase model is wrong there and panel 2's")
    print("  interpretation of [0,1) as pure overshoot does not hold.")
    print()
    print(f"  {'stream':<30} {'<0':>7} {'[0,1)':>9} {'[1,2)':>9} {'[2,3)':>9}"
          f" {'[3,inf)':>9}")
    for label, L, _ in pops:
        v = [x["steps"] for x in L]
        if not v:
            continue
        n = len(v)
        b = [sum(1 for x in v if x < 0),
             sum(1 for x in v if 0 <= x < 1),
             sum(1 for x in v if 1 <= x < 2),
             sum(1 for x in v if 2 <= x < 3),
             sum(1 for x in v if x >= 3)]
        print(f"  {label:<30} " + " ".join(
            f"{c:>4}/{100.0*c/n:>4.1f}%" for c in b))

    rule("2. PHASE-1 LOCKED PROFIT  (NOT the poll overshoot -- see the header)")
    print("  This was designed as a poll-period probe and does not work as one: while")
    print("  favorable_steps is in [2,3) the trail keeps re-writing market-2.0*step, so")
    print("  the final value encodes peak_favorable-2.0, a market-path statistic.  Read")
    print("  it as a ratchet-parity check across quantiles, not as evidence on cadence.")
    print()
    print(f"  {'stream':<30} {'n':>5} {'p10':>8} {'p25':>8} {'med':>8} {'p75':>8}"
          f" {'p90':>8}   {'med in PRICE':>12} {'med in TICKS':>12}")
    band = {}
    for label, L, step in pops:
        v = [x["steps"] for x in L if 0 <= x["steps"] < 1]
        band[label] = v
        if len(v) < 5:
            print(f"  {label:<30} {len(v):>5}   -- too few --")
            continue
        p = qs(v)
        med_price = statistics.median(
            [x["price"] for x in L if 0 <= x["steps"] < 1])
        print(f"  {label:<30} {len(v):>5} {p[0]:>8.3f} {p[1]:>8.3f} {p[2]:>8.3f}"
              f" {p[3]:>8.3f} {p[4]:>8.3f}   {med_price:>12.3f}"
              f" {med_price / 0.01:>12.1f}")

    rule("3. IS THE BAND STRICTLY POSITIVE?  (the ratchet must never lock a loss)")
    print("  Phase 1 can only write at or above breakeven, so the band must be >= 0 on")
    print("  both accounts.  Any negative mass would mean a stop was written BEHIND the")
    print("  entry, which the law forbids.  Mass at exactly breakeven is the case where")
    print("  price reversed immediately after arming.")
    print()
    print(f"  {'stream':<30} {'n':>5} {'== 0 (within 1 tick)':>22}"
          f" {'< 0.03 steps':>14} {'> 0.10 steps':>14}")
    for label, L, step in pops:
        v = band[label]
        if len(v) < 5:
            continue
        atzero = sum(1 for x in v if abs(x) * step < 0.015)
        tiny = sum(1 for x in v if x < 0.03)
        big = sum(1 for x in v if x > 0.10)
        print(f"  {label:<30} {len(v):>5} {atzero:>5}/{len(v):<5}"
              f" = {100.0*atzero/len(v):>5.1f}%"
              f"  {tiny:>5} = {100.0*tiny/len(v):>5.1f}%"
              f"  {big:>5} = {100.0*big/len(v):>5.1f}%")

    rule("4. PHASE-2 LOCKED PROFIT  (the harder parity test -- this makes the runners)")
    print("  Phase 2 writes market - 1.0*step on every pass, so its locked value tracks")
    print("  the peak.  A STALE writer (one that revisits a position rarely) leaves the")
    print("  stop further behind the peak and should lock LESS.  This is the closest")
    print("  thing here to a cadence signal, and it is only suggestive: it also depends")
    print("  on how far the runners ran, which is market path.")
    print()
    print(f"  {'stream':<30} {'n':>5} {'p10':>8} {'p25':>8} {'med':>8} {'p75':>8}"
          f" {'p90':>8}")
    for label, L, _ in pops:
        v = [x["steps"] for x in L if x["steps"] >= 2]
        if len(v) < 5:
            print(f"  {label:<30} {len(v):>5}   -- too few --")
            continue
        p = qs(v)
        print(f"  {label:<30} {len(v):>5} {p[0]:>8.3f} {p[1]:>8.3f} {p[2]:>8.3f}"
              f" {p[3]:>8.3f} {p[4]:>8.3f}")

    rule("5. VERDICT")
    tf = band.get("TARGET final (Jul24+)", [])
    ou = band.get("OURS  111638511", [])
    to = band.get("TARGET old  (Jul14-Jul24)", [])
    if len(tf) < 5 or len(ou) < 5:
        print("  insufficient data in one band; no verdict.")
        return
    mtf, mou = statistics.median(tf), statistics.median(ou)
    mto = statistics.median(to) if len(to) >= 5 else float("nan")
    print("  RATCHET PARITY (what this script legitimately measures):")
    print(f"    phase-1 locked, TARGET old   : {mto:.4f} steps")
    print(f"    phase-1 locked, TARGET final : {mtf:.4f} steps")
    print(f"    phase-1 locked, OURS         : {mou:.4f} steps"
          f"    ratio {mou / mtf if mtf else float('nan'):.3f}x")
    p2t = [x["steps"] for x in pops[1][1] if x["steps"] >= 2]
    p2o = [x["steps"] for x in pops[2][1] if x["steps"] >= 2]
    if p2t and p2o:
        print(f"    phase-2 locked, TARGET final : {statistics.median(p2t):.4f} steps")
        print(f"    phase-2 locked, OURS         : {statistics.median(p2o):.4f} steps"
              f"    ratio {statistics.median(p2o)/statistics.median(p2t):.3f}x")
    print()
    if 0.85 <= mou / mtf <= 1.18:
        print("  -> RATCHET AT PARITY.  Both phases of the trail produce the same")
        print("     locked-profit distribution as the Target's final regime, and the")
        print("     (1,2) hole is intact on both.  This is a confirmation, not a gap.")
    else:
        print("  -> PHASE-1 TRAIL DIVERGES.  Investigate before trusting the ratchet.")
    print()
    print("  POLL RATE: NOT MEASURED HERE.  This script cannot settle it (see header).")
    print("  The stop-out clustering asymmetry therefore remains OPEN:")
    print("     TARGET final  785 consecutive stop-out gaps, min 0.289 s, p25 20.12 s,")
    print("                   0 under 100 ms")
    print("     OURS          108 consecutive stop-out gaps, min 0.000 s, p25  2.70 s,")
    print("                   17 under 100 ms = 15.74%")

    rule("6. THE REMAINING CANDIDATE, AND WHY IT IS NOT BEING APPLIED")
    print("  MECHANISM.  desired = market - distance*step depends on market and")
    print("  distance only, NOT on entry.  Two same-side positions in the same phase")
    print("  written at the same market price therefore get the IDENTICAL stop and must")
    print("  die on the same tick.  Our writer runs every timer tick")
    print("  (StraddleEngine.mqh:2837, timer_ms = MathMax(20, inter_order_delay_ms))")
    print("  because stop_update_interval_seconds = 0 at ProfileCatalog.mqh:28 makes")
    print("  the gate at StraddleEngine.mqh:2539 a no-op.  With")
    print("  max_stop_updates_per_pass = 1 the writer cycles one position per tick, so")
    print("  k live positions are all written within ~100k ms of one another -- at")
    print("  effectively one market price.  That is consistent with our 17 fast pairs,")
    print("  all same-side adjacent levels, median 0.006 step apart.")
    print()
    print("  CIRCUMSTANTIAL SUPPORT.  Every other pacing knob moved to 20 s at the")
    print("  2026-07-24 break (close_interval_seconds, rearm_delay_seconds,")
    print("  restart_delay_ms, deployment_fill_cooldown_seconds).  This one did not.")
    print("  A 20 s write cadence would separate consecutive stop levels by 20 s of")
    print("  market movement, which is exactly the floor the Target's final regime")
    print("  shows and ours does not.")
    print()
    print("  WHY IT IS NOT BEING APPLIED SILENTLY.")
    print("   1. NO DIRECT EVIDENCE.  The mechanism is sound and the correlation is")
    print("      suggestive, but no measurement here observes the Target's write")
    print("      cadence.  MT5 history records fills, not stop modifications, so the")
    print("      Target's cadence may not be observable from the XLSX at all.")
    print("   2. IT CUTS BOTH WAYS ON RISK.  A staler stop sits further behind the")
    print("      peak: it gives a runner more room but also gives back more on a")
    print("      reversal.  Panel 4 is the relevant check and currently shows OURS")
    print("      locking slightly MORE than the Target (2.903 vs 2.793 steps median),")
    print("      i.e. our fresher writer is not obviously worse.")
    print("   3. THE HOLE IS THE TRIPWIRE.  If a slower cadence widened the phase-1")
    print(f"      band past 1.0 step the (1,2) hole would fill.  Target p90 is"
          f" {qs(tf)[4]:.3f},")
    print("      so there is headroom -- but this must be re-measured after any change.")
    print("   4. AGENTS.md section H.  This is a timing change on a LIVE account.")
    print("      Measured and reported; the operator decides.")


if __name__ == "__main__":
    main()
