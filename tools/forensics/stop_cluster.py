"""WHY DO OUR STOP-OUTS FIRE IN PAIRS WHEN THE TARGET'S NEVER DO?

WHERE THIS QUESTION CAME FROM.  close_burst_ab.py closed the flatten-pacing
question (both streams 100% at 20 s) and, in doing so, exposed that the
"sub-100 ms close burst" which motivated commit 6c340b5 was never in the flatten
population at all.  Over ALL closes, ours run 10.49% under 100 ms (17 of 162) and
EVERY ONE of the 17 fast pairs is (SL, SL) -- two stop-outs.  Against the correct
comparator (the Target's post-2026-07-24 pacing family) the Target is 0 of 841.
Its PRE-break family, by contrast, was 17.78% with 411 of 414 fast pairs (SL,SL).

So our behaviour resembles the Target's old regime, not its final one, and
close_interval_seconds cannot be the lever: a stop-out is executed by the server
the instant price touches the level.  The EA's only influence is WHERE it wrote
the level.  That makes the mechanism question sharp and falsifiable.

THE HYPOTHESIS UNDER TEST.  The ratchet writes desired = market - distance*step.
Two positions on the same side that have BOTH passed tighten_trigger_steps get
the same distance (1.0), so if both are written at the same market price their
stops land on the SAME price -- and one tick then takes out both, milliseconds
apart, no matter what any pacing knob says.  The defence against that is already
in the profile: max_stop_updates_per_pass=1 rate-limits the writer, so N
positions are updated across N passes at N different market prices and their
stops come out STAGGERED.  If the Target's stops are staggered and ours are
degenerate, the mechanism is the stop writer, not the close path.

THE INSTRUMENT.  Not a reconstruction.  For a position closed BY its stop the
server stamps the level that fired into the closing deal's comment ("[sl 4648.97]"
for us, "sl 4135.53" in the Target's XLSX), and dataset.py exposes it as
Position.stop_loss.  So the level under test is the broker's own attestation of
the price that executed, on both accounts, with no spread model and no mark.

WHAT WOULD FALSIFY THE HYPOTHESIS.  If our sub-100 ms (SL,SL) pairs sit at
DIFFERENT stop prices, degeneracy is not the mechanism and something else is
sweeping two separated levels in one tick -- a gap, in which case this is market
behaviour and not a parity defect at all.  If the Target's pre-break fast pairs
are NOT degenerate either, then degeneracy explains neither stream and the
hypothesis is dead.  Panel 3 measures the same quantity on all three populations
with one estimator, so it cannot come out flattering by construction.

SCOPE WARNING, LEARNED THE HARD WAY.  dataset.FINAL_REGIME_START is 2026-07-14,
but the PACING regime broke on 2026-07-24.  final_regime() therefore straddles
the break and pools two incompatible families -- that pooling is what produced a
meaningless "Target median 0.124 s" in the first run of close_burst_ab.py.  Every
population here is split at the real break instead.
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

# The PACING break, not FINAL_REGIME_START.  See the scope warning above.
PACING_BREAK = datetime(2026, 7, 24, 12, 0, 0)

FAST = 0.100          # "same tick" for practical purposes
SAME_PRICE = 0.005    # tick is 0.01 on XAUUSD, so this is sub-tick


def rule(t: str) -> None:
    print()
    print("=" * 100)
    print(t)
    print("=" * 100)


def load(path: str):
    DS.GOLDEN = Path(path)
    return DS.load_all()


def stop_closes(positions, cycles):
    """Positions closed BY their stop, grouped by cycle, in close order.

    The discriminator is the attested level: a non-empty stop_loss means the
    closing deal's comment carried "sl <price>", i.e. the server reported that
    the stop is what executed.  Basket flattens have no such text and are
    excluded -- they are the population close_burst_ab.py already closed.
    """
    cyc = {c.index: c for c in cycles}
    by_cycle: dict[int, list] = defaultdict(list)
    for p in positions:
        if p.cycle not in cyc or p.is_open or not p.close_time or not p.stop_loss:
            continue
        by_cycle[p.cycle].append(p)
    for ps in by_cycle.values():
        ps.sort(key=lambda x: x.close_time)
    return by_cycle, cyc


def consecutive(by_cycle, cyc):
    out = []
    for idx, ps in by_cycle.items():
        step = cyc[idx].step
        for a, b in zip(ps, ps[1:]):
            dsl = abs((b.stop_loss or 0.0) - (a.stop_loss or 0.0))
            out.append({
                "cycle": idx,
                "gap": (b.close_time - a.close_time).total_seconds(),
                "dsl": dsl,
                "dsl_steps": (dsl / step) if step and step > 0 else float("nan"),
                "same_side": a.side == b.side,
                "a": a, "b": b, "step": step,
            })
    return out


def degeneracy(by_cycle):
    """How many stop-closed positions share ONE attested stop price?

    Counted per (cycle, side) because a buy stop and a sell stop at the same
    number are unrelated events.  A writer that staggers its updates produces
    all-ones here; a writer that updates several positions at one market price
    produces runs of 2, 3, 4.
    """
    runs = Counter()
    biggest = []
    for idx, ps in by_cycle.items():
        groups: dict[tuple[str, float], list] = defaultdict(list)
        for p in ps:
            groups[(p.side, round(p.stop_loss, 2))].append(p)
        for (side, price), g in groups.items():
            runs[len(g)] += 1
            if len(g) >= 2:
                biggest.append((len(g), idx, side, price, g))
    return runs, sorted(biggest, key=lambda x: -x[0])


def describe(label, gaps):
    if not gaps:
        print(f"  {label:<30}      -- none --")
        return
    s = sorted(gaps)

    def q(f):
        return s[min(int(f * (len(s) - 1)), len(s) - 1)]
    fast = sum(1 for x in gaps if x < FAST)
    print(f"  {label:<30} {len(gaps):>5} {min(gaps):>9.3f} {q(0.25):>9.2f}"
          f" {statistics.median(gaps):>9.2f} {q(0.75):>9.2f} {max(gaps):>10.1f}"
          f"   {fast:>4}/{len(gaps):<5} = {100.0 * fast / len(gaps):>6.2f}%")


def main() -> None:
    t_ord, t_pos, t_deals, t_cyc = load(GOLDEN)
    o_ord, o_pos, o_deals, o_cyc = load(FRESH)

    t_old = [c for c in t_cyc
             if DS.FINAL_REGIME_START <= c.start < PACING_BREAK]
    t_new = [c for c in t_cyc if c.start >= PACING_BREAK]

    rule("SCOPE  (split at the PACING break 2026-07-24, not FINAL_REGIME_START)")
    print(f"  TARGET cycles  Jul-14..Jul-24 (old pacing) : {len(t_old)}")
    print(f"  TARGET cycles  Jul-24..              (final): {len(t_new)}")
    print(f"  OURS   cycles                              : {len(o_cyc)}")
    print(f"  population: closed positions whose closing deal attested 'sl <price>'")

    pops = [
        ("TARGET old  (Jul14-Jul24)", stop_closes(t_pos, t_old)),
        ("TARGET final (Jul24+)", stop_closes(t_pos, t_new)),
        ("OURS  111638511", stop_closes(o_pos, o_cyc)),
    ]

    rule("1. GAPS BETWEEN CONSECUTIVE STOP-OUTS  (seconds, within one cycle)")
    print(f"  {'stream':<30} {'pairs':>5} {'min':>9} {'p25':>9} {'med':>9}"
          f" {'p75':>9} {'max':>10}   {'under 100 ms':>22}")
    cons = {}
    for label, (bc, cyc) in pops:
        cons[label] = consecutive(bc, cyc)
        describe(label, [x["gap"] for x in cons[label]])

    rule("2. THE FAST PAIRS  (are the two attested stop prices the SAME price?)")
    print("  If degeneracy is the mechanism, a fast pair must be two positions whose")
    print("  stops were written to one price.  dsl = |stop_a - stop_b|.")
    print()
    print(f"  {'stream':<30} {'fast':>5} {'same price':>12} {'<0.25 step':>12}"
          f" {'med dsl':>9} {'med dsl/step':>13}  {'same side':>10}")
    for label, _ in pops:
        fast = [x for x in cons[label] if x["gap"] < FAST]
        if not fast:
            print(f"  {label:<30} {0:>5}      -- no fast pair --")
            continue
        same = sum(1 for x in fast if x["dsl"] < SAME_PRICE)
        near = sum(1 for x in fast if x["dsl_steps"] < 0.25)
        ss = sum(1 for x in fast if x["same_side"])
        print(f"  {label:<30} {len(fast):>5}"
              f" {same:>5}/{len(fast):<6}"
              f" {near:>5}/{len(fast):<6}"
              f" {statistics.median(x['dsl'] for x in fast):>9.3f}"
              f" {statistics.median(x['dsl_steps'] for x in fast):>13.3f}"
              f"  {100.0 * ss / len(fast):>9.0f}%")

    print()
    print("  CONTROL -- the same statistic on the SLOW pairs of each stream.  If")
    print("  'same price' is high on fast pairs and low on slow ones, degeneracy is")
    print("  doing the work; if it is high on both, it is not the discriminator.")
    print()
    print(f"  {'stream':<30} {'slow':>5} {'same price':>12} {'med dsl/step':>13}")
    for label, _ in pops:
        slow = [x for x in cons[label] if x["gap"] >= FAST]
        if not slow:
            continue
        same = sum(1 for x in slow if x["dsl"] < SAME_PRICE)
        print(f"  {label:<30} {len(slow):>5} {same:>5}/{len(slow):<6}"
              f" {statistics.median(x['dsl_steps'] for x in slow):>13.3f}")

    rule("3. STOP-PRICE DEGENERACY  (how many stops share one price, per cycle+side)")
    print("  A staggered writer gives all 1s.  Runs of 2+ are positions that were")
    print("  written to the same level and must therefore die together.")
    print()
    for label, (bc, _) in pops:
        runs, biggest = degeneracy(bc)
        tot = sum(runs.values())
        multi = sum(v for k, v in runs.items() if k >= 2)
        pos_in_multi = sum(k * v for k, v in runs.items() if k >= 2)
        pos_tot = sum(k * v for k, v in runs.items())
        print(f"  {label:<30} distinct levels {tot:>5}   run sizes"
              f" {dict(sorted(runs.items()))}")
        print(f"  {'':<30} levels shared by 2+ : {multi:>5}/{tot}"
              f" = {100.0 * multi / max(tot, 1):>5.1f}%"
              f"   positions involved {pos_in_multi}/{pos_tot}"
              f" = {100.0 * pos_in_multi / max(pos_tot, 1):.1f}%")

    rule("4. OUR FAST PAIRS, IN FULL  (17 lines -- read them, do not trust a median)")
    ours = sorted([x for x in cons["OURS  111638511"] if x["gap"] < FAST],
                  key=lambda x: x["a"].close_time)
    if not ours:
        print("  none.")
    print(f"  {'close time':<23} {'cyc':>3} {'A':<8} {'B':<8} {'gap ms':>7}"
          f" {'sl_A':>9} {'sl_B':>9} {'dsl':>7} {'d/step':>7}"
          f" {'entry_A':>9} {'entry_B':>9}")
    for x in ours:
        a, b = x["a"], x["b"]
        when = f"{a.close_time:%Y-%m-%d %H:%M:%S.%f}"[:23]
        print(f"  {when:<23}"
              f" {x['cycle']:>3} {a.comment or '-':<8} {b.comment or '-':<8}"
              f" {1000.0 * x['gap']:>7.0f}"
              f" {a.stop_loss:>9.2f} {b.stop_loss:>9.2f} {x['dsl']:>7.2f}"
              f" {x['dsl_steps']:>7.3f} {a.open_price:>9.2f} {b.open_price:>9.2f}")

    rule("5. THE TARGET'S OWN CLUSTERED REGIME  (12 of its 400+ fast pairs)")
    told = sorted([x for x in cons["TARGET old  (Jul14-Jul24)"] if x["gap"] < FAST],
                  key=lambda x: x["a"].close_time)
    print(f"  {len(told)} fast pairs before the break; a sample:")
    for x in told[:12]:
        a, b = x["a"], x["b"]
        when = f"{a.close_time:%Y-%m-%d %H:%M:%S.%f}"[:23]
        print(f"  {when:<23}"
              f" {x['cycle']:>3} {a.comment or '-':<8} {b.comment or '-':<8}"
              f" {1000.0 * x['gap']:>7.0f}"
              f" {a.stop_loss:>9.2f} {b.stop_loss:>9.2f} {x['dsl']:>7.2f}"
              f" {x['dsl_steps']:>7.3f}")

    rule("6. WHAT CHANGED IN THE TARGET AT THE BREAK?")
    print("  Same estimator, its two families side by side.  If degeneracy collapsed")
    print("  at the break, the Target changed its stop WRITER, and the knob that did")
    print("  it is the thing we are missing.")
    for label in ("TARGET old  (Jul14-Jul24)", "TARGET final (Jul24+)",
                  "OURS  111638511"):
        c = cons[label]
        if not c:
            continue
        same = sum(1 for x in c if x["dsl"] < SAME_PRICE)
        print(f"  {label:<30} consecutive pairs {len(c):>5}"
              f"   at an IDENTICAL level {same:>5}"
              f" = {100.0 * same / len(c):>6.2f}%")

    rule("7. VERDICT")
    o_fast = [x for x in cons["OURS  111638511"] if x["gap"] < FAST]
    t_fast = [x for x in cons["TARGET final (Jul24+)"] if x["gap"] < FAST]
    if not o_fast:
        print("  Our stream has no sub-100 ms stop-out pair in this sample.")
        return
    o_same = sum(1 for x in o_fast if x["dsl"] < SAME_PRICE)
    print(f"  ours  : {len(o_fast)} fast pairs, {o_same} of them at an identical level")
    print(f"  target: {len(t_fast)} fast pairs in its final regime")
    if o_same >= 0.8 * len(o_fast):
        print("  -> DEGENERATE STOPS.  Our ratchet writes several positions to ONE")
        print("     price, so a single tick closes them together.  The lever is the")
        print("     stop WRITER (max_stop_updates_per_pass / when the pass runs), not")
        print("     close_interval_seconds.")
    elif o_same == 0:
        print("  -> NOT degeneracy.  The paired stops sit at different prices, so one")
        print("     tick swept two separated levels: that is a price gap, i.e. market")
        print("     behaviour, and not something a parameter controls.")
    else:
        print("  -> MIXED.  Read panel 4 line by line before concluding anything.")


if __name__ == "__main__":
    main()
