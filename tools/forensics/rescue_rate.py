"""Is our ZERO trend-rescue events a gap, or just 7 cycles of bad luck?

parity_scorecard panel G is the last asymmetry left in the whole comparison:
125 Target grid orders in the final regime carry DOUBLE the tier's base volume
(0.02 = 2x0.01, 0.12 = 2x0.06, 0.30 = 2x0.15), and we have none.

Those 125 do NOT carry a rescue tag -- panel E proved every STR ORB/ORS/AVB/AVS
died before the regime boundary.  They carry ordinary STR B<n>/STR S<n> comments.
So they are the trend rescue re-placing base pendings at 2x, exactly as
ProfileCatalog.mqh LATEST_30 already encodes (trend_rescue_volume_multiplier=2.0).

That reframes the question.  The branch is NOT dead on our side the way the
ORB/ORS branch is: trend_rescue_enabled=true on LATEST_30.  So the only question
is a RATE question -- how often does it fire, and is zero in our sample
surprising?  A rate question has an exact answer, so compute it instead of
arguing about it.

The test is one-sided on purpose.  If the rescue fires in a fraction f of Target
cycles, then P(zero events in n cycles) = (1-f)^n.  If that probability is large,
zero is uninformative and there is nothing to fix.  If it is small, the branch is
reachable, should have fired, and did not -- which WOULD be a real defect.
"""
from __future__ import annotations

import os
import statistics
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
import tools.forensics.dataset as DS  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TIER = ((10, 0.01), (20, 0.06), (30, 0.15))
SETS = (("TARGET 901018", os.path.join(ROOT, ".cache", "golden")),
        ("OURS   111638511", os.path.join(ROOT, ".cache", "fresh")))


def base_for(level):
    for hi, vol in TIER:
        if level is not None and level <= hi:
            return vol
    return None


def rule(t):
    print()
    print("=" * 100)
    print(t)
    print("=" * 100)


def measure(path):
    DS.GOLDEN = __import__("pathlib").Path(path)
    orders, positions, deals, cycles = DS.load_all()
    final = DS.final_regime(cycles)
    keep = {c.index for c in final}
    grid = [o for o in orders if o.is_grid and o.cycle in keep]
    dbl, base, other = [], 0, Counter()
    for o in grid:
        b = base_for(o.level)
        if b is None:
            continue
        r = o.volume / b
        if abs(r - 1.0) < 0.05:
            base += 1
        elif abs(r - 2.0) < 0.05:
            dbl.append(o)
        else:
            other[round(r, 2)] += 1
    return final, grid, base, dbl, other


out = {}
for name, path in SETS:
    final, grid, base, dbl, other = measure(path)
    by_cyc = defaultdict(list)
    for o in dbl:
        by_cyc[o.cycle].append(o)
    out[name] = (final, grid, base, dbl, other, by_cyc)

rule("2x-VOLUME GRID ORDERS IN THE FINAL REGIME  (the trend rescue's fingerprint)")
print(f"  {'stream':<18} {'cycles':>7} {'grid':>7} {'@base':>7} {'@2x':>6}"
      f" {'other':>7}  {'cycles w/ 2x':>13}  {'fired in':>10}")
for name, (final, grid, base, dbl, other, by_cyc) in out.items():
    print(f"  {name:<18} {len(final):>7} {len(grid):>7} {base:>7} {len(dbl):>6}"
          f" {sum(other.values()):>7}  {len(by_cyc):>13}"
          f"  {100.0*len(by_cyc)/max(len(final),1):>9.1f}%")
    if other:
        print(f"    other multipliers: {dict(sorted(other.items()))}")

t_final, t_grid, _, t_dbl, _, t_by = out["TARGET 901018"]
o_final, o_grid, _, o_dbl, _, o_by = out["OURS   111638511"]

rule("PER-EVENT DETAIL, TARGET  (each cycle that rescued, and how big the sweep was)")
print(f"  {'cyc':>5} {'when':<19} {'2x orders':>10} {'levels':>16} {'sides':>12}")
for ci in sorted(t_by):
    g = t_by[ci]
    lv = sorted({o.level for o in g})
    print(f"  {ci:>5} {min(o.open_time for o in g):%Y-%m-%d %H:%M:%S}"
          f" {len(g):>10} {f'L{min(lv)}..L{max(lv)}':>16}"
          f" {str(dict(Counter(o.side for o in g))):>12}")

rule("IS OUR ZERO SURPRISING?  P(zero events | Target's own per-cycle rate)")
f = len(t_by) / max(len(t_final), 1)
n = len(o_final)
p0 = (1.0 - f) ** n
print(f"  Target rate     f = {len(t_by)}/{len(t_final)} = {f:.4f} cycles per rescue event")
print(f"  Our sample      n = {n} final-regime cycles")
print(f"  P(0 | f, n)       = (1-{f:.4f})^{n} = {p0:.4f}")
print(f"  expected events   = n*f = {n*f:.2f}")
print()
if p0 > 0.05:
    print(f"  -> NOT SURPRISING.  With a {100*f:.0f}% per-cycle rate, {n} cycles produce")
    print(f"     zero rescues {100*p0:.0f}% of the time.  Zero carries no information about")
    print("     whether our branch works; it is what the Target's own rate predicts.")
    print("     The branch is also NOT dead the way STR ORB/ORS is -- ProfileCatalog")
    print("     sets trend_rescue_enabled=true for LATEST_30, with the same")
    print("     2x multiplier, 400 drawdown, 6xM15 bars, 20pt move and 3 pending")
    print("     floor the Target was measured at.  It is reachable and unexercised,")
    print("     which is a sample-size fact, not a parity defect.")
else:
    print(f"  -> SURPRISING (P={p0:.4f}).  The branch is reachable on LATEST_30 and")
    print("     should have fired in this sample.  Investigate the gate.")

rule("CROSS-CHECK: does the measured count match what ProfileCatalog claims?")
print(f"  ProfileCatalog.mqh LATEST_30 comment: 'fired in 6 of the 100 final-regime")
print(f"  cycles ... 125 rescue orders total'")
print(f"  measured here, independently:          {len(t_by)} of {len(t_final)} cycles,"
      f" {len(t_dbl)} orders")
ok = (len(t_by) == 6 and len(t_dbl) == 125)
print(f"  agree: {ok}")
