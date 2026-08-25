"""DID THE CLOSE-PACING FIX ACTUALLY WORK?  A/B across the deploy boundary.

WHY THIS SCRIPT EXISTS.  The fix committed in 6c340b5 (CloseIntervalElapsed() +
the m_close_skip cursor + drain protection in the CYCLE_RESTARTING handler) was
written to kill one specific defect: on 111638511 the basket flatten fired runs of
2-4 market closes 39-127 ms apart, because the CYCLE_RESTARTING drain called
TryCloseOneOwnedPosition directly and therefore paced at the OnTimer period
(100 ms) instead of at close_interval_seconds (20 s).  The Target never does this.

Deploying a fix is not the same as verifying it.  This script is the verification,
and it is built so it cannot flatter the fix:

  * ONE estimator, THREE populations.  The same function measures the Target, our
    stream before the restart, and our stream after it.  A difference in a printed
    number cannot be an artifact of two measurement paths.

  * The population is the closes the pacer actually governs -- basket flattens,
    not stop-outs.  A stop-out is executed server-side the instant price touches
    the stop; the EA does not pace it and close_interval_seconds has no authority
    over it.  Mixing the two would dilute the very effect under test.  The
    discriminator is the same on both accounts: a position whose stop price was
    recovered from the closing deal's "sl <price>" text was closed BY the stop;
    one with an empty stop_loss was flattened.  That split reproduces panel A
    exactly (Target 72.2/27.8, ours 71.2/28.8), so it is not a new assumption.

  * The statistic is the gap between CONSECUTIVE flatten closes inside one cycle.
    That is the quantity close_interval_seconds is supposed to bound from below,
    stated in the units the knob is written in.

  * Both streams carry millisecond resolution (golden close_time is
    "...:34.403000"; ours comes from time_msc), so sub-100 ms clusters are
    measurable on both and the comparison is not resolution-limited on one side.

WHAT WOULD FALSIFY THE FIX.  If post-restart cycles still show consecutive
flatten gaps under 1 s, the gate is not on every path and the fix is incomplete.
If post-restart gaps sit at or above close_interval_seconds and the Target's do
too, the defect is closed.  The pre-restart column is the control: it must still
show the sub-100 ms runs, otherwise this script is not measuring what it claims
and no conclusion can be drawn from the post column either.

THE DEPLOY BOUNDARY is the systemd ActiveEnterTimestamp of
straddle-shadow-mt5.service, 2026-08-25 18:36:35 UTC, converted to server time
(UTC+3) because every timestamp in both datasets is server time.
"""
from __future__ import annotations

import os
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
import tools.forensics.dataset as DS  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GOLDEN = os.path.join(ROOT, ".cache", "golden")
FRESH = os.path.join(ROOT, ".cache", "fresh")

# systemd ActiveEnterTimestamp 2026-08-25 18:36:35 UTC -> server clock is UTC+3.
RESTART = datetime(2026, 8, 25, 21, 36, 35)

# close_interval_seconds on LATEST_30 (ProfileCatalog.mqh).
CLOSE_INTERVAL = 20.0


def rule(t: str) -> None:
    print()
    print("=" * 100)
    print(t)
    print("=" * 100)


def load(path: str):
    DS.GOLDEN = __import__("pathlib").Path(path)
    return DS.load_all()


def flatten_gaps(positions, cycles, lo=None, hi=None):
    """Gaps between consecutive basket-flatten closes inside the same cycle.

    lo/hi bound the CLOSE time, not the cycle, because the restart lands
    mid-cycle: a cycle that straddles the boundary contributes its early closes
    to the control and its later ones to the treatment, which is the correct
    attribution -- the binary in force is whichever was running at that instant.
    """
    keep = {c.index for c in cycles}
    by_cycle: dict[int, list] = defaultdict(list)
    n_considered = 0
    for p in positions:
        if p.cycle not in keep or p.is_open or not p.close_time:
            continue
        if p.stop_loss:                      # closed BY the stop -> not paced
            continue
        if lo is not None and p.close_time < lo:
            continue
        if hi is not None and p.close_time >= hi:
            continue
        n_considered += 1
        by_cycle[p.cycle].append(p)

    gaps, runs = [], []
    for idx, ps in by_cycle.items():
        ps.sort(key=lambda x: x.close_time)
        g = [(b.close_time - a.close_time).total_seconds()
             for a, b in zip(ps, ps[1:])]
        gaps.extend(g)
        runs.append((idx, ps[0].close_time, len(ps), g))
    return n_considered, gaps, runs


def describe(label, n_pos, gaps):
    if not gaps:
        print(f"  {label:<26} {n_pos:>6} {0:>6}      -- no consecutive pair --")
        return
    s = sorted(gaps)

    def q(f):
        return s[min(int(f * (len(s) - 1)), len(s) - 1)]
    sub100 = sum(1 for x in gaps if x < 0.100)
    sub1 = sum(1 for x in gaps if x < 1.0)
    ok = sum(1 for x in gaps if x >= CLOSE_INTERVAL - 1.0)
    print(f"  {label:<26} {n_pos:>6} {len(gaps):>6} "
          f"{min(gaps):>9.3f} {q(0.25):>9.3f} {statistics.median(gaps):>9.3f} "
          f"{q(0.75):>9.3f} {max(gaps):>9.1f} "
          f"{100.0 * sub100 / len(gaps):>8.1f}% {100.0 * sub1 / len(gaps):>7.1f}%"
          f" {100.0 * ok / len(gaps):>8.1f}%")


def main() -> None:
    rule("POPULATION  (basket flattens only -- the closes close_interval_seconds governs)")
    print("  A stop-out is executed server-side on price touch; the EA does not pace it,")
    print("  so it is excluded.  Discriminator: empty stop_loss => flattened.")
    print(f"  deploy boundary (server time) : {RESTART:%Y-%m-%d %H:%M:%S}")
    print(f"  close_interval_seconds        : {CLOSE_INTERVAL:.0f}")

    t_ord, t_pos, t_deals, t_cyc = load(GOLDEN)
    t_final = DS.final_regime(t_cyc)
    o_ord, o_pos, o_deals, o_cyc = load(FRESH)
    o_final = DS.final_regime(o_cyc)

    tn, tg, tr = flatten_gaps(t_pos, t_final)
    an, ag, ar = flatten_gaps(o_pos, o_final, hi=RESTART)
    bn, bg, br = flatten_gaps(o_pos, o_final, lo=RESTART)

    rule("1. CONSECUTIVE FLATTEN-CLOSE GAPS  (seconds, within one cycle)")
    print(f"  {'stream':<26} {'closes':>6} {'gaps':>6} {'min':>9} {'p25':>9}"
          f" {'med':>9} {'p75':>9} {'max':>9} {'<100ms':>9} {'<1s':>8} {'>=19s':>9}")
    describe("TARGET 901018", tn, tg)
    describe("OURS  before restart", an, ag)
    describe("OURS  after restart", bn, bg)

    rule("2. THE DEFECT UNDER TEST  (sub-100 ms runs -- the thing the fix removes)")
    for label, gaps in (("TARGET 901018", tg), ("OURS  before restart", ag),
                        ("OURS  after restart", bg)):
        if not gaps:
            print(f"  {label:<26} no data")
            continue
        n = sum(1 for x in gaps if x < 0.100)
        print(f"  {label:<26} {n:>5} / {len(gaps):<5} gaps under 100 ms"
              f"  = {100.0 * n / len(gaps):>6.2f}%")

    rule("3. EVERY POST-RESTART FLATTEN SEQUENCE, IN FULL  (read it, do not trust a median)")
    if not br:
        print("  no post-restart flatten has happened yet -- the fix is deployed but")
        print("  UNEXERCISED.  Nothing here can confirm or refute it; keep it running")
        print("  until at least one basket target fires after the boundary.")
    for idx, t0, n, g in sorted(br, key=lambda x: x[1]):
        pretty = " ".join(f"{x:.2f}" for x in g) if g else "(single close)"
        print(f"  cycle {idx:>3}  first close {t0:%Y-%m-%d %H:%M:%S}  {n:>3} closes"
              f"  gaps: {pretty}")

    rule("4. PRE-RESTART CONTROL  (must still show the defect, else this test is blind)")
    for idx, t0, n, g in sorted(ar, key=lambda x: x[1]):
        pretty = " ".join(f"{x:.2f}" for x in g) if g else "(single close)"
        print(f"  cycle {idx:>3}  first close {t0:%Y-%m-%d %H:%M:%S}  {n:>3} closes"
              f"  gaps: {pretty}")

    rule("5. TARGET REFERENCE  (its own flatten sequences, for the shape of a clean one)")
    tt = sorted(tr, key=lambda x: x[1])
    print(f"  {len(tt)} flatten sequences in the final regime; showing the 12 largest")
    for idx, t0, n, g in sorted(tt, key=lambda x: -x[2])[:12]:
        s = sorted(g)
        print(f"  cycle {idx:>3}  {t0:%Y-%m-%d %H:%M:%S}  {n:>3} closes"
              f"  gap med {statistics.median(g):>7.2f}  min {min(g):>7.2f}"
              f"  max {max(g):>8.2f}  under 1s {sum(1 for x in g if x < 1.0)}")

    rule("6. VERDICT")
    if not bg:
        print("  UNEXERCISED.  The binary is verified in place (hash-identical on the")
        print("  VPS) but no post-restart basket flatten has produced a consecutive")
        print("  pair yet.  Keep it running; re-run this script after the next exit.")
        return
    bad = sum(1 for x in bg if x < 1.0)
    ctl = sum(1 for x in ag if x < 1.0) if ag else 0
    print(f"  post-restart gaps under 1 s : {bad}/{len(bg)}")
    print(f"  pre-restart  gaps under 1 s : {ctl}/{len(ag) if ag else 0}  (control)")
    tsub = sum(1 for x in tg if x < 1.0)
    print(f"  Target       gaps under 1 s : {tsub}/{len(tg)}"
          f" = {100.0 * tsub / max(len(tg), 1):.2f}%")
    if bad == 0 and ctl > 0:
        print("  -> FIX CONFIRMED.  The defect is present in the control and absent")
        print("     after the boundary, measured by one estimator on one account.")
    elif bad == 0 and ctl == 0:
        print("  -> CLEAN, but the control is clean too, so this sample cannot")
        print("     attribute it to the fix.  More pre-boundary data or more cycles.")
    else:
        print("  -> NOT CLOSED.  Sub-second flatten gaps survive the fix; a close path")
        print("     is still bypassing CloseIntervalElapsed().  Investigate before")
        print("     treating this as parity.")


if __name__ == "__main__":
    main()
