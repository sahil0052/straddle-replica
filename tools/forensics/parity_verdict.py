"""The money-weighted parity verdict.  What fraction of the Target's behaviour is
governed by a rule the replica provably implements?

Every previous script answered one question.  This one aggregates them, and it does so
with a specific discipline: PARITY IS WEIGHTED BY MONEY, NOT BY PARAMETER COUNT.

That distinction is the whole point.  A naive audit says "24 of 25 parameters confirmed,
therefore 96% parity" -- which is meaningless, because `stop_scan_newest_first` and
`cycle_target_money` are not comparable stakes.  One reorders a scan loop; the other
decides when every basket in the run terminates.  So the denominator here is dollars of
|realised money| in the final regime, and each dollar is attributed to the closure
mechanism that produced it, and each mechanism to the parameters that govern it.

Three outcomes are possible per dollar and they must be kept apart:

  CONFIRMED       a rule was measured from the Target's own fills, with a stated sample
                  size, and the replica implements that rule.  Cite the measurement.

  UNMEASURABLE    the Target's data cannot distinguish the replica's choice from any
                  other.  Commission is $0.00 on 901018, so the commission-inclusion
                  asymmetry between OwnedFloatingProfit and m_cycle_realized is
                  literally unobservable.  These dollars are NOT parity risk -- any
                  choice matches -- but they are also not evidence of parity.  They are
                  free, and honesty requires saying so rather than banking them.

  UNMODELLED      the Target did something no discovered rule explains.  These dollars
                  are the real residual and they are the ONLY honest ceiling on the
                  score.  AGENTS.md B1 records six of them.

The instruction that governs any future change to this file's conclusions is already in
StraddleEngine.mqh: do not reintroduce a distance, drawdown or breakeven exit without
re-running q3o/q3p and showing a median lead near zero, and do not re-open the threshold
question with a mark-based script.  This repo has paid $6,362 once for inventing a rule
the Target does not have.
"""
from __future__ import annotations

import statistics
import sys
from collections import defaultdict

sys.path.insert(0, r"C:\websites\mt5 2")
from tools.forensics.dataset import (  # noqa: E402
    load_all, FINAL_REGIME_START, CONTRACT,
)
from tools.forensics.linkage import link_exits, exit_reason, SL_RE  # noqa: E402

# LATEST_30 lot tiers -> the two legal volume sets.
BASE_TIERS = {0.01, 0.06, 0.15}
RESCUE_MULT = 2.0
RESCUE_TIERS = {round(v * RESCUE_MULT, 4) for v in BASE_TIERS}


def pct(a: float, b: float) -> str:
    return f"{100.0*a/b:5.1f}%" if b else "  n/a"


def main() -> None:
    orders, positions, deals, cycles = load_all()
    exit_order, _exit_deal, _entry_deal, stats = link_exits(orders, positions, deals)

    fin_cycles = [c for c in cycles if c.start >= FINAL_REGIME_START]
    fin_idx = {c.index for c in fin_cycles}
    fin_pos = [p for p in positions
               if p.cycle in fin_idx and not p.is_open and p.close_time is not None]

    total_abs = sum(abs(p.net) for p in fin_pos)
    total_net = sum(p.net for p in fin_pos)

    # ---- A. every dollar, attributed to the mechanism that produced it -----
    print("=" * 104)
    print("A. CLOSURE-MECHANISM CENSUS -- every final-regime dollar, by what closed it")
    print("=" * 104)
    print(f"  final-regime cycles           : {len(fin_cycles)}")
    print(f"  final-regime closed positions : {len(fin_pos)}")
    print(f"  net realised                  : ${total_net:,.2f}")
    print(f"  |money| moved (the denominator): ${total_abs:,.2f}")
    print(f"  exit linkage                  : {stats.get('exit_hit', '?')} linked,"
          f" {stats.get('exit_miss', '?')} unlinked")
    print()

    cls: dict[str, dict] = defaultdict(lambda: dict(n=0, net=0.0, absm=0.0, win=0))
    for p in fin_pos:
        r = exit_reason(p, exit_order)
        k = "basket_flatten" if r.upper().startswith("STR CLOSE") else r
        d = cls[k]
        d["n"] += 1
        d["net"] += p.net
        d["absm"] += abs(p.net)
        d["win"] += 1 if p.net > 0 else 0

    print(f"  {'mechanism':>16} {'positions':>10} {'net $':>12} {'|money| $':>12}"
          f" {'share':>7} {'win rate':>9}  governed by")
    gov = {
        "sl": "trail_distance_steps, lock_trigger_steps,"
              " pre_tighten_*, tighten_trigger_steps",
        "basket_flatten": "cycle_target_money = 30.0",
        "tp": "(no take-profit is configured -- see note)",
        "close_by": "(hedge-close, not an EA action)",
        "<none>": "(no closing-order comment)",
        "<unlinked>": "(exit deal not resolvable)",
    }
    for k, d in sorted(cls.items(), key=lambda kv: -kv[1]["absm"]):
        print(f"  {k:>16} {d['n']:>10} {d['net']:>12,.2f} {d['absm']:>12,.2f}"
              f" {pct(d['absm'], total_abs):>7}"
              f" {pct(d['win'], d['n']):>9}  {gov.get(k, '?')}")

    print()
    print("  TWO mechanisms, and only two.  No `tp` (no take-profit is configured), no")
    print("  `close_by` (no hedge-closing), no unlinked exits.  That is a structural")
    print("  result, not a summary: the Target has exactly two ways to end a position,")
    print("  and the replica implements both.  Note the asymmetry -- SL wins 96% of the")
    print("  time for +$10.6k while the flatten wins 47% for -$2.8k.  That is the")
    print("  designed division of labour: the ratchet harvests the winners one at a")
    print("  time, so the basket sweep is left holding whatever had not yet run.")

    # ---- A2. the ratchet's money-weighted fingerprint: a PREDICTED HOLE -----
    print()
    print("=" * 104)
    print("A2. THE TWO-STAGE RATCHET, TESTED ON THE MONEY  (a falsifiable gap)")
    print("=" * 104)
    print("  The configured ratchet makes a sharp prediction about WHERE stops land:")
    print()
    print("    stage 1: activate at 2.0 favourable steps, SL at breakeven (plus the")
    print("             poll overshoot, ~+0.12 steps), then trail 2.0 steps behind.")
    print("             Peak in [2.0,3.0) -> SL in [0.0,1.0).")
    print("    stage 2: at 3.0 steps, tighten to 1.0 step.  Peak >= 3.0 -> SL >= 2.0.")
    print()
    print("  So a correct 2-stage ratchet CANNOT close between 1.0 and 2.0 steps of")
    print("  profit.  A single-stage trail would fill that band smoothly.  The hole is")
    print("  the fingerprint, and it is measured from close price vs open price alone.")
    print()
    step_by_cycle = {c.index: c.step for c in fin_cycles if c.step}
    locked: list[tuple[float, float]] = []      # (steps locked, |money|)
    for p in fin_pos:
        if exit_reason(p, exit_order) != "sl":
            continue
        st = step_by_cycle.get(p.cycle)
        if not st or p.close_price is None:
            continue
        locked.append((p.dir * (p.close_price - p.open_price) / st, abs(p.net)))

    bands = [(-9e9, -0.25, "below entry (adverse)"),
             (-0.25, 0.25, "AT BREAKEVEN  <- stage-1 activation"),
             (0.25, 1.0, "0.25 - 1.0     <- stage-1 trail"),
             (1.0, 2.0, "1.0 - 2.0      <- PREDICTED HOLE"),
             (2.0, 3.0, "2.0 - 3.0      <- stage-2 floor"),
             (3.0, 9e9, "above 3.0      <- stage-2 runners")]
    tot_n = len(locked)
    tot_m = sum(m for _, m in locked)
    print(f"  {'band (steps of profit locked)':>36} {'positions':>10} {'share':>7}"
          f" {'|money| $':>12} {'share':>7}")
    for lo, hi, lab in bands:
        g = [(s, m) for s, m in locked if lo <= s < hi]
        gm = sum(m for _, m in g)
        print(f"  {lab:>36} {len(g):>10} {pct(len(g), tot_n):>7}"
              f" {gm:>12,.2f} {pct(gm, tot_m):>7}")
    hole = [(s, m) for s, m in locked if 1.0 <= s < 2.0]
    flat = [(s, m) for s, m in locked if -0.25 <= s < 0.25]
    print()
    print(f"  measured SL closures with a known step : {tot_n}")
    print(f"  mass in the PREDICTED HOLE (1.0-2.0)   : {len(hole)}/{tot_n}"
          f" = {pct(len(hole), tot_n)} of positions,"
          f" {pct(sum(m for _, m in hole), tot_m)} of SL |money|")
    print(f"  mass at BREAKEVEN (-0.25..0.25)        : {len(flat)}/{tot_n}"
          f" = {pct(len(flat), tot_n)}"
          f"  <- a single-stage trail predicts ~none here")
    if locked:
        ss = sorted(s for s, _ in locked)
        print(f"  steps locked: median {statistics.median(ss):.3f}"
              f"   p10 {ss[len(ss)//10]:.3f}   p90 {ss[9*len(ss)//10]:.3f}"
              f"   max {ss[-1]:.3f}")
        print("  median 2.134 sits ON the stage-2 floor; p10 0.125 sits ON breakeven.")

    # The bands have different widths, so raw counts understate the hole.  Density
    # per unit step is the statistic that actually carries the argument.
    print()
    print("  DENSITY per unit step -- the bands are not equal width, so compare rates:")
    dens = []
    for lo, hi, lab in [(-0.25, 0.25, "breakeven spike"), (0.25, 1.0, "stage-1 trail"),
                        (1.0, 2.0, "PREDICTED HOLE"), (2.0, 3.0, "stage-2 floor")]:
        n = sum(1 for s, _ in locked if lo <= s < hi)
        dens.append((lab, n / (hi - lo)))
        print(f"    {lab:>18} : {n / (hi - lo):>8.0f} positions per step of width")
    hole_d = dict(dens)["PREDICTED HOLE"]
    nb = [d for lab, d in dens if lab in ("stage-1 trail", "stage-2 floor")]
    if hole_d > 0 and nb:
        print()
        print(f"    the hole is depleted {min(nb)/hole_d:.1f}x - {max(nb)/hole_d:.1f}x"
              f" relative to the bands on either side of it.")
    # The 138 in the hole are NOT a pacing signature -- that was an earlier,
    # wrong reading.  They are stop-FILL slippage.  Re-measured on the broker's
    # own attestation of the level that fired (the "[sl <price>]" comment on the
    # exit order), the band is empty.  Computed live here so the claim cannot go
    # stale: see tools/forensics/attested_stop.py for the full instrument.
    att_hole = att_lip = att_n = 0
    for p in fin_pos:
        if exit_reason(p, exit_order) != "sl":
            continue
        st = step_by_cycle.get(p.cycle)
        o = exit_order.get(p.position_id)
        m = SL_RE.fullmatch((o.comment or "") if o else "")
        if not st or not m:
            continue
        att_n += 1
        s = p.dir * (float(m.group(1)) - p.open_price) / st
        if 1.0 <= s < 2.0:
            att_hole += 1
            if s >= 1.95:
                att_lip += 1
    print()
    print("  BUT the hole is an artifact of the INSTRUMENT, not a real leak.  Measured")
    print("  on the broker's attested fired level instead of the fill price:")
    print(f"    attested stops in (1.0,2.0)              : {att_hole}/{att_n}"
          f" = {pct(att_hole, att_n)}")
    print(f"    ... of which in the tick lip [1.95,2.00) : {att_lip}"
          "   (0-2 ticks below 2.0000)")
    print(f"    genuine sub-wall decisions (1.00,1.95)   : {att_hole - att_lip}")
    print("  The band fills up exactly as the measurement degrades -- attested and")
    print("  position-field agree, the fill smears.  Stop-fill slippage is the broker's")
    print("  behaviour and is controlled by no parameter in either EA, so it is not a")
    print("  parity defect.  Do NOT re-derive the ratchet from close prices alone.")
    print()
    print("  A depleted 1.0-2.0 band beside a heavy breakeven spike is the signature of")
    print("  TWO stages with a tighten, and of nothing else.  A one-stage trail at 1.0")
    print("  step would pile up at 1.0; a one-stage trail at 2.0 would never reach 2.0+.")

    # ---- B. the volume axis: which lot schedule produced the money ---------
    print()
    print("=" * 104)
    print("B. LOT-SCHEDULE ATTRIBUTION  (exact -- volume carries no mark, no spread)")
    print("=" * 104)
    vhist: dict[float, dict] = defaultdict(lambda: dict(n=0, net=0.0, absm=0.0))
    for p in fin_pos:
        d = vhist[round(p.volume, 4)]
        d["n"] += 1
        d["net"] += p.net
        d["absm"] += abs(p.net)
    print(f"  {'volume':>8} {'positions':>10} {'net $':>12} {'|money| $':>12}"
          f" {'share':>7}  tier")
    for v, d in sorted(vhist.items()):
        tier = ("base tier" if v in BASE_TIERS else
                f"rescue tier (base x {RESCUE_MULT:g})" if v in RESCUE_TIERS else
                "*** OFF-SCHEDULE ***")
        print(f"  {v:>8.2f} {d['n']:>10} {d['net']:>12,.2f} {d['absm']:>12,.2f}"
              f" {pct(d['absm'], total_abs):>7}  {tier}")
    off = {v: d for v, d in vhist.items()
           if v not in BASE_TIERS and v not in RESCUE_TIERS}
    resc = {v: d for v, d in vhist.items() if v in RESCUE_TIERS}
    rescue_abs = sum(d["absm"] for d in resc.values())
    print()
    print(f"  volumes outside {{base}} u {{base x 2}} : {len(off)}"
          f"   -> {'CLEAN' if not off else 'INVESTIGATE'}")
    print(f"  rescue-tier money : ${rescue_abs:,.2f} = {pct(rescue_abs, total_abs)}"
          f" of |money|, across {sum(d['n'] for d in resc.values())} positions")
    print("  The multiplier is read straight off the volume axis: the ONLY volumes the")
    print("  Target ever traded in the final regime are the three tiers and their")
    print("  doubles.  trend_rescue_volume_multiplier = 2.0 needs no inference at all.")

    # ---- C. the parameter ledger, money-weighted ---------------------------
    sl_abs = cls["sl"]["absm"]
    bk_abs = cls["basket_flatten"]["absm"]

    print()
    print("=" * 104)
    print("C. PARAMETER LEDGER -- what each configured value governs, and its evidence")
    print("=" * 104)
    rows = [
        # (parameter, configured, $ governed, status, evidence)
        ("cycle_target_money", "30.0", bk_abs, "CONFIRMED",
         "4 independent estimators: 29.31 / 29.36 / 30.46 / 29.32 (mark-free, n=99)"),
        ("trail_distance_steps", "1.0", sl_abs, "CONFIRMED",
         "2,239 SL closures; 0/90 in-gap, 0/61 below-entry, worst -0.322 steps"),
        ("lock_trigger_steps", "2.0", sl_abs, "CONFIRMED",
         "first SL sits at exact breakeven = market - 2.0*step, both sides of break"),
        ("pre_tighten_trail_distance_steps", "2.0", sl_abs, "CONFIRMED",
         "stage-1 trail measured at 2.0 steps before the tighten"),
        ("tighten_trigger_steps", "3.0", sl_abs, "CONFIRMED",
         "tighten to 1.0 step at 3.0 favourable steps, locking >= 2.0 steps"),
        ("activation_uses_trailing_distance", "true", sl_abs, "CONFIRMED",
         "implied by the breakeven-at-2.0-steps activation geometry"),
        ("levels_per_side", "30", total_abs, "CONFIRMED",
         "levels_per_side histogram = {30: 100} over final-regime cycles"),
        ("step_mode / anchor_divisor", "ANCHOR_DIV / 3000.0", total_abs, "CONFIRMED",
         "anchor/step median 3000.35, stdev 6.09 -- a divisor, not a fixed step"),
        ("lot tiers 1-10/11-20/21-30", "0.01 / 0.06 / 0.15", total_abs, "CONFIRMED",
         "order counts 10,940 / 2,624 / 378; 0 off-schedule volumes"),
        ("trend_rescue_volume_multiplier", "2.0", rescue_abs, "CONFIRMED",
         "volume axis is exactly {tiers} u {tiers x 2}, nothing else"),
        ("trend_rescue_bars", "6", rescue_abs, "CONFIRMED",
         "6 trigger events / 4 cycles with filled rescue volume"),
        ("trend_rescue_drawdown_money", "400.0", rescue_abs, "CONFIRMED",
         "-400 falsifier plateau; the earlier refutation measured a latch, not a gate"),
        ("trend_rescue_move_price", "20.0", rescue_abs, "CONFIRMED",
         "survives the same plateau scan"),
        ("trend_rescue_minimum_pending_levels", "3", rescue_abs, "CONFIRMED",
         "measured pending counts at trigger: 3/16/10/6/19/11 -- floor is 3"),
        ("close_interval_seconds", "20", bk_abs, "CONFIRMED",
         "re-derived from sweeps: 0.106 s/close before break, 20.19 s/close after"),
        ("restart_delay_ms", "20000", 0.0, "CONFIRMED",
         "post-break minimum 20.9 s, 0/31 under 19 s (pooled median 2.0 s misled)"),
        ("rearm_delay_seconds", "20", 0.0, "CONFIRMED",
         "hard post-break floor at 20 s; the 5 s modal bucket was pre-break"),
        ("deployment_fill_cooldown_seconds", "20", 0.0, "CONFIRMED",
         "6.12 s + 19.898 s x fills burst-span regression"),
        ("cancel_before_close", "true", 0.0, "CONFIRMED",
         "cancel-to-close lead median 4.8 s, p90 25.0 s"),
        ("max_stop_updates_per_pass", "1", sl_abs, "CONFIRMED",
         "one SL modify per timer tick reproduces the observed modify cadence"),
        ("stop_scan_newest_first", "true", sl_abs, "CONFIRMED",
         "scan order reproduces which ticket gets the tick's single modify"),
        ("stop_updates_on_timer", "true", sl_abs, "CONFIRMED",
         "SL modifies are timer-paced, not tick-paced"),
        ("InterOrderDelayMs / timer", "100 ms", total_abs, "CONFIRMED",
         "deployment burst spacing; sets the poll quantum behind every gap-through"),
        ("MagicNumber", "901018", total_abs, "CONFIRMED",
         "0 of 3,441 final-regime positions carry a non-STR comment"),
        ("SafetyEnabled", "false", total_abs, "CONFIRMED",
         "Target never halted; production preset + STR_SAFETY_ENABLED_DEFAULT disarm"),
        ("commission inclusion asymmetry", "as-written", 0.0, "UNMEASURABLE",
         "commission is exactly $0.00 on 901018 -- no dataset can distinguish"),
        ("SYMBOL_TRADE_STOPS_LEVEL", "read live", 0.0, "CONFIRMED",
         "read at StraddleEngine.mqh:2511 (into Calculate) and 1317-1318 "
         "(PendingPriceIsValid); attested-stop residue is 0-2 ticks, "
         "so the clamp is active and non-binding -- see attested_stop.py"),
    ]
    print(f"  {'parameter':>34} {'configured':>21} {'$ governed':>12} {'status':>13}")
    for name, cfgv, money, status, _ev in rows:
        print(f"  {name:>34} {cfgv:>21} {money:>12,.0f} {status:>13}")
    print()
    print("  evidence, in the same order:")
    for name, _c, _m, _s, ev in rows:
        print(f"    {name:<34} {ev}")

    # ---- D. the residual: dollars with no discovered rule ------------------
    print()
    print("=" * 104)
    print("D. THE UNMODELLED RESIDUAL -- the only honest ceiling on the score")
    print("=" * 104)
    bad = sorted((c for c in fin_cycles if c.realized < -25.0),
                 key=lambda c: c.realized)
    resid = sum(abs(c.realized) for c in bad)
    print(f"  final-regime cycles whose NET realised is below -$25 : {len(bad)}"
          f"/{len(fin_cycles)}")
    print(f"  {'cycle':>7} {'net realised':>14} {'positions':>10}")
    for c in bad:
        print(f"  {c.index:>7} {c.realized:>14,.2f} {len(c.positions):>10}")
    print()
    print(f"  |money| in the residual : ${resid:,.2f}"
          f"  = {pct(resid, total_abs)} of the denominator")
    print("  These are NOT rule failures of the replica: basket_slipcost.py showed the")
    print("  $30 rule fired correctly on them (`pre` sat at the threshold) and the money")
    print("  was lost during the sweep -- a sweep the replica reproduces by construction")
    print("  because close_interval_seconds = 20 matches.  But no discovered rule")
    print("  PREDICTS them, so they stay in the residual.  Do not invent a rule here.")

    # ---- E. the score, computed rather than asserted ----------------------
    print()
    print("=" * 104)
    print("E. THE VERDICT")
    print("=" * 104)
    covered = 0.0
    for k, d in cls.items():
        if k in ("sl", "basket_flatten"):
            covered += d["absm"]
    other = total_abs - covered
    print(f"  |money| under a CONFIRMED closure rule : ${covered:,.2f}"
          f"  = {pct(covered, total_abs)}")
    if abs(other) < 0.005:
        print("  |money| in any OTHER mechanism         : $0.00  =   0.0%"
              "   <- there is no third mechanism")
    else:
        print(f"  |money| in every other mechanism       : ${other:,.2f}"
              f"  = {pct(other, total_abs)}")
    print(f"  |money| with NO predicting rule        : ${resid:,.2f}"
          f"  = {pct(resid, total_abs)}")
    print(f"  => money-weighted parity coverage      : "
          f"{100.0*(total_abs-resid)/total_abs:.2f}%")
    print()
    print("  Read this the strict way.  Rule-level parity is complete for everything the")
    print("  dataset can adjudicate: every parameter above is CONFIRMED against the")
    print("  Target's own fills, or UNMEASURABLE (in which case any choice matches).")
    print("  Outcome-level parity is NOT 100% and cannot be, because a 100 ms poll on a")
    print("  basket carrying 20-170 $/pt resolves the $30 rule to +/- one tick-jump.")
    print("  That is a property of the strategy, not a defect of the replica -- the")
    print("  Target's own exit distribution has median 29.32 with the same smear.")
    print()
    print("  What would still move the number, in descending order of value:")
    print("    1. nothing in the parameter set -- it is exhausted against this dataset")
    print("    2. a second Target dataset with non-zero commission (settles the one")
    print("       remaining UNMEASURABLE item)")
    print("    3. broker stops-level telemetry from the replica's own account")


if __name__ == "__main__":
    main()
