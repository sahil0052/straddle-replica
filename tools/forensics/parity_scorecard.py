"""ONE table, TWO accounts, IDENTICAL code: the Target EA against 111638511.

WHAT MAKES THIS DIFFERENT FROM EVERY EARLIER COMPARISON IN THIS DIRECTORY.

Until the master-password API session, our own account could only be observed
through the terminal's Trades-category log -- fills, and nothing else.  Three
whole bodies of Target behaviour were therefore declared unverifiable on our
side: the trailing ratchet, the $30 basket exit, and closure attribution.  Every
"parity" claim about those three rested on reading our .mqh source and asserting
that it implemented the Target's confirmed law.  Source inspection is not
measurement.

fresh_to_golden.py removed that limit by rewriting our API history into the
Target's own CSV schema, and dataset.py now honours GOLDEN_DIR.  So this script
can do the thing that was previously impossible: run the SAME function over BOTH
datasets and print the two answers on adjacent lines.  No per-account branch
exists anywhere below.  If a number differs, the behaviour differs -- it cannot
be an artifact of two different estimators, because there is only one estimator.

WHAT EACH PANEL DECIDES, and what would falsify parity:

  A  CLOSURE MIX.  What fraction of positions the stop closes rather than the
     basket flatten.  This is the single most compressive summary of the whole
     strategy: it is set jointly by the trail distance, the activation threshold
     and the basket target, so it cannot be matched by accident.

  B  RATCHET, LOCKED PROFIT.  profit_steps = (sl - entry)*dir/step at the instant
     the stop fires.  The Target's law -- phase 1 activates at 2.0 favorable
     steps and trails 2.0 behind the peak; phase 2 tightens to a 1.0-step trail
     once 3.0 favorable steps are seen -- forces a very specific and very odd
     shape: mass in [0,1), mass in [2,inf), and a HOLE in (1,2).  The hole is the
     fingerprint.  A 1.0-step trail throughout would fill it; a fixed breakeven
     stop would collapse everything onto 0.  Any implementation that merely
     "trails a stop" fails this panel.

  C  RATCHET, TRAIL DISTANCE, independently.  For every stopped position,
     sl >= peak_true - D*step >= peak_obs - D*step, so D >= (peak_obs - sl)/step
     for every position without exception.  This is one-sided and falsifiable and
     uses no assumption from panel B.  peak_obs is built from the other account's
     own fill prices, so it is a lower bound on the true peak.

  D  BASKET EXIT.  realized + floating at the first STR CLOSE of each cycle.  If
     the $30 net target is the rule, the median pins near 30 on both.

  E  RESCUE LEGS.  STR ORS / STR ORB / STR AVS / STR AVB.  Counting them is how we
     tell "the branch agrees" from "the branch never ran" from "the behaviour was
     retired".  The count alone cannot distinguish those, so the panel prints the
     in-scope count, the whole-history count, and the FIRST and LAST date each tag
     was ever emitted.  All 120 of the Target's fall before the regime boundary and
     carry the retired volume ladder, so the in-scope count is zero on both sides;
     an earlier draft filtered but did not re-run, and reported the 120 as though
     they were in scope.  Print both columns, always.

  F  STOP DISCIPLINE AT SEND.  Does a pending ever carry an SL when it is placed?
     The Target: never.  This is what makes the ratchet a post-fill amendment
     rather than an order property, and it is checkable on every order ever sent.

  G  LATTICE.  step vs anchor/3000, and the tier boundaries.

  H  PER-POSITION P&L.  The economic outcome per trade, which is what the two
     preceding mechanisms exist to produce.

SAMPLE ASYMMETRY, stated once and not repeated.  The Target has 13 days and ~3450
closed positions in its final regime; 111638511 has one 7-hour session and 149.
Medians and shares are therefore comparable; tail extremes are not, and any
divergence confined to a far quantile is sample length, not law.  Panels print n
on every line so this stays visible.
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
from tools.forensics import dataset as DS  # noqa: E402
from tools.forensics.attribution import build_exit_index, attribute  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[2]
SETS = (("TARGET 901018", ROOT / ".cache" / "golden", True),
        ("OURS 111638511", ROOT / ".cache" / "fresh", False))
DIVISOR = 3000.0


def rule(t: str) -> None:
    print()
    print("=" * 100)
    print(t)
    print("=" * 100)


def q(vals, p) -> float:
    v = sorted(vals)
    if not v:
        return float("nan")
    return v[min(len(v) - 1, max(0, int(round(p * (len(v) - 1)))))]


def pc(a, b) -> str:
    return f"{100.0 * a / b:5.1f}%" if b else "    --"


class Snap:
    """Everything panel A..H needs, computed once per dataset."""

    def __init__(self, name: str, path: Path, final_only: bool):
        self.name = name
        DS.GOLDEN = path                      # the only switch in this file
        orders, positions, deals, cycles = DS.load_all()
        self.orders, self.positions, self.deals = orders, positions, deals
        self.cycles = (DS.final_regime(cycles) if final_only else cycles)
        keep = {c.index for c in self.cycles}
        self.step = {c.index: c.step for c in self.cycles}
        self.pos = [p for p in positions
                    if p.cycle in keep and not p.is_open and p.close_time]
        cls_by_t, _, _ = build_exit_index(orders, deals)
        self.reason, _, _ = attribute(positions, cls_by_t)

        # ---- panel B: locked profit in steps, stop-closed positions only
        self.locked, self.sl_pos = [], []
        for p in self.pos:
            if self.reason.get(p.position_id) != "sl":
                continue
            s = self.step.get(p.cycle)
            if not s or p.stop_loss is None:
                continue
            self.locked.append((p.stop_loss - p.open_price) * p.dir / s)
            self.sl_pos.append(p)

        # ---- panel C: peak excursion from the account's own fill prices
        marks = sorted((d.time, d.price) for d in deals
                       if d.price and d.time is not None)
        self.bound = []
        times = [m[0] for m in marks]
        from bisect import bisect_left, bisect_right
        for p in self.sl_pos:
            s = self.step[p.cycle]
            lo = bisect_left(times, p.open_time)
            hi = bisect_right(times, p.close_time)
            if hi - lo < 2:
                continue
            seg = [pr for _, pr in marks[lo:hi]]
            peak = max(seg) if p.dir > 0 else min(seg)
            self.bound.append((peak - p.stop_loss) * p.dir / s)

        # ---- panel D: realized + floating at each cycle's first STR CLOSE
        by_cycle = defaultdict(list)
        for p in positions:
            if p.cycle in keep:
                by_cycle[p.cycle].append(p)
        self.trigger = []
        for ci, ps in by_cycle.items():
            fl = [p for p in ps
                  if not p.is_open and self.reason.get(p.position_id) == "STR CLOSE"]
            if not fl:
                continue
            t0 = min(p.close_time for p in fl)
            mark = [p.close_price for p in fl if p.close_time == t0]
            if not mark:
                continue
            mk = statistics.median(mark)
            realized = sum(p.net for p in ps
                           if not p.is_open and p.close_time < t0)
            openp = [p for p in ps
                     if p.is_open or (p.close_time and p.close_time >= t0)]
            floating = sum((mk - p.open_price) * p.dir * p.volume * DS.CONTRACT
                           for p in openp)
            self.trigger.append((realized + floating, len(openp)))

        # ---- panels E/F/G
        # FULL comment, never the first token: "STR CLOSE", "STR ORS" and
        # "STR ORB" all begin with "STR", so splitting on whitespace silently
        # merges the basket flatten with the two rescue tags and reports a false
        # zero for both rescue counts.  The [sl <price>] forms are folded into
        # one key because the price varies per position.
        def _tag(c: str | None) -> str:
            if not c:
                return "(blank)"
            return "[sl ...]" if c.lower().lstrip("[").startswith("sl ") else c
        self.exit_comments = Counter(_tag(o.comment) for o in orders
                                     if not o.is_grid and o.cycle in keep)
        # The SAME census over the WHOLE history, plus the last date each tag was
        # ever seen.  This exists because the in-scope filter above was once added
        # without re-running the script, and panel E printed the unfiltered counts
        # as though they were final-regime counts -- reporting 92 Target rescue
        # legs that the final regime does not contain.  Printing both columns side
        # by side, with the last-seen date, makes that class of mistake visible in
        # the output instead of hiding it in a filter one line above.
        self.exit_all = Counter(_tag(o.comment) for o in orders if not o.is_grid)
        self.tag_last: dict[str, datetime] = {}
        self.tag_first: dict[str, datetime] = {}
        for o in orders:
            if o.is_grid or not o.open_time:
                continue
            k = _tag(o.comment)
            if k not in self.tag_first or o.open_time < self.tag_first[k]:
                self.tag_first[k] = o.open_time
            if k not in self.tag_last or o.open_time > self.tag_last[k]:
                self.tag_last[k] = o.open_time
        # dataset.Order deliberately does not carry stop_loss -- the loader drops
        # the column.  Read it straight off the CSV rather than widening a
        # dataclass that seventy other scripts depend on.
        self.sl_at_send, self.grid_orders = 0, 0
        import csv
        for fn in ("orders.csv", "working_orders.csv"):
            with (path / fn).open(newline="", encoding="utf-8") as fh:
                for r in csv.DictReader(fh):
                    if not DS.GRID_RE.fullmatch(r["comment"] or ""):
                        continue
                    self.grid_orders += 1
                    if (r["stop_loss"] or "").strip() not in ("", "0", "0.0"):
                        self.sl_at_send += 1
        # Restricted to the cycles in scope.  Unfiltered, the Target's whole
        # order history leaks its PRE-July-14 volume ladder (0.02/0.03/0.05)
        # into the census and manufactures a tier divergence that does not
        # exist in the regime we are matching.
        self.vol_tier = defaultdict(Counter)
        for o in orders:
            if o.is_grid and o.level and o.cycle in keep:
                band = "L1-10" if o.level <= 10 else (
                    "L11-20" if o.level <= 20 else "L21-30")
                self.vol_tier[band][round(o.volume, 2)] += 1

        # ---- panel H
        self.pnl = [p.net for p in self.pos]

    @property
    def mix(self):
        c = Counter(self.reason.get(p.position_id, "?") for p in self.pos)
        return c, len(self.pos)


def main() -> None:
    snaps = [Snap(n, p, f) for n, p, f in SETS]
    if any(not s.pos for s in snaps):
        for s in snaps:
            print(f"  {s.name}: {len(s.pos)} closed positions")
        print("  a dataset is empty -- run fresh_to_golden.py")
        return

    rule("SCOPE")
    for s in snaps:
        d = sorted({p.open_time.date() for p in s.pos})
        print(f"  {s.name:>15}  cycles {len(s.cycles):>4}"
              f"  closed positions {len(s.pos):>5}"
              f"  {len(d)} day(s) {d[0]}..{d[-1]}")

    # ---------------------------------------------------------------- panel A
    rule("A. CLOSURE MIX  (which mechanism ends a position)")
    print("  Set jointly by trail distance, activation threshold and basket")
    print("  target, so it cannot be matched by accident.")
    print()
    print(f"  {'stream':>15} {'n':>6} {'stop-out':>12} {'basket flat':>12} {'other':>8}")
    for s in snaps:
        c, n = s.mix
        sl, bf = c.get("sl", 0), c.get("STR CLOSE", 0)
        other = n - sl - bf
        print(f"  {s.name:>15} {n:>6} {sl:>6} {pc(sl, n)} {bf:>6} {pc(bf, n)}"
              f" {other:>8}")
    a, b = [s.mix[0].get("sl", 0) / max(s.mix[1], 1) for s in snaps]
    print(f"\n  stop-out share  TARGET {100 * a:.1f}%   OURS {100 * b:.1f}%"
          f"   -> {abs(a - b) * 100:.2f} pp apart")

    # ---------------------------------------------------------------- panel B
    rule("B. RATCHET, LOCKED PROFIT  profit_steps = (sl-entry)*dir/step")
    print("  The (1,2) HOLE is the fingerprint of a two-phase ratchet.  A single")
    print("  1.0-step trail would fill it; a breakeven-only stop collapses to 0.")
    print()
    print(f"  {'stream':>15} {'n':>6} {'median':>8} {'[0,1)':>13} {'(1,2) HOLE':>13}"
          f" {'[2,inf)':>13} {'neg':>5} {'~0':>5}")
    for s in snaps:
        v, n = s.locked, len(s.locked)
        lo = sum(1 for x in v if 0 <= x < 1.0)
        mid = sum(1 for x in v if 1.0 < x < 2.0)
        hi = sum(1 for x in v if x >= 2.0)
        print(f"  {s.name:>15} {n:>6} {statistics.median(v):>8.4f}"
              f" {lo:>6} {pc(lo, n)} {mid:>6} {pc(mid, n)}"
              f" {hi:>6} {pc(hi, n)}"
              f" {sum(1 for x in v if x < -0.02):>5}"
              f" {sum(1 for x in v if abs(x) <= 0.02):>5}")
    print()
    print("  quantile-by-quantile (the shape, not just the centre):")
    print(f"  {'stream':>15} " + " ".join(f"{int(p * 100):>7}%"
                                          for p in (.05, .15, .25, .35, .5,
                                                    .65, .75, .85, .95)))
    for s in snaps:
        print(f"  {s.name:>15} " + " ".join(
            f"{q(s.locked, p):>8.3f}" for p in (.05, .15, .25, .35, .5,
                                                .65, .75, .85, .95)))
    print()
    print("  0.25-step histogram, as a SHARE so the two n's are comparable:")
    edges = [i * 0.25 for i in range(0, 17)]
    print(f"  {'band':>14} {'TARGET':>16} {'OURS':>16}")
    for e in edges:
        row = []
        for s in snaps:
            k = sum(1 for x in s.locked if e <= x < e + 0.25)
            row.append((k, 100.0 * k / len(s.locked)))
        flag = "  <- HOLE" if 1.0 <= e < 2.0 else ""
        print(f"  [{e:>5.2f},{e + 0.25:>5.2f}) "
              f"{row[0][0]:>6} {row[0][1]:>6.1f}% {row[1][0]:>8} {row[1][1]:>6.1f}%{flag}")
    for s in snaps:
        k = sum(1 for x in s.locked if x >= 4.25)
        print(f"  {'>= 4.25':>14} {s.name}: {k} ({100.0 * k / len(s.locked):.1f}%)")

    # ---------------------------------------------------------------- panel C
    rule("C. RATCHET, TRAIL DISTANCE  D >= (peak_obs - sl)/step, one-sided")
    print("  Independent of panel B.  Uses only each account's own fill prices as")
    print("  market marks, so peak_obs <= peak_true and the bound is conservative.")
    print()
    print(f"  {'stream':>15} {'n':>6} {'p50':>7} {'p75':>7} {'p90':>7} {'p99':>7}"
          f" {'max':>7} {'>1.02':>12} {'>2.02':>12}")
    for s in snaps:
        v, n = s.bound, len(s.bound)
        if not n:
            continue
        print(f"  {s.name:>15} {n:>6} {q(v, .5):>7.3f} {q(v, .75):>7.3f}"
              f" {q(v, .9):>7.3f} {q(v, .99):>7.3f} {max(v):>7.3f}"
              f" {sum(1 for x in v if x > 1.02):>5} {pc(sum(1 for x in v if x > 1.02), n)}"
              f" {sum(1 for x in v if x > 2.02):>5} {pc(sum(1 for x in v if x > 2.02), n)}")
    print()
    print("  Reading: a population that pushes past 1.02 but clusters below ~2.1")
    print("  is a 2.0-step trail with a 1.0-step second phase.  Both streams must")
    print("  show the same ceiling, and neither may exceed it materially.")

    # ---------------------------------------------------------------- panel D
    rule("D. BASKET EXIT  realized + floating at each cycle's first STR CLOSE")
    print(f"  {'stream':>15} {'cycles':>7} {'median $':>9} {'p25':>8} {'p75':>8}"
          f" {'>=30':>12} {'in[25,45]':>12} {'<0':>10} {'open@trig':>10}")
    for s in snaps:
        v = [t for t, _ in s.trigger]
        o = [k for _, k in s.trigger]
        if not v:
            continue
        n = len(v)
        print(f"  {s.name:>15} {n:>7} {statistics.median(v):>9.2f}"
              f" {q(v, .25):>8.2f} {q(v, .75):>8.2f}"
              f" {sum(1 for x in v if x >= 30.0):>4} {pc(sum(1 for x in v if x >= 30.0), n)}"
              f" {sum(1 for x in v if 25 <= x <= 45):>4} {pc(sum(1 for x in v if 25 <= x <= 45), n)}"
              f" {sum(1 for x in v if x < 0):>3} {pc(sum(1 for x in v if x < 0), n)}"
              f" {statistics.median(o):>10.1f}")
    print()
    print("  OURS, every cycle in full (n is small enough to read):")
    for t, k in sorted(snaps[1].trigger):
        print(f"      total {t:>9.2f}   open at trigger {k}")
    tneg = [t for t, _ in snaps[0].trigger if t < 0]
    print(f"\n  TARGET's own negative closes: {len(tneg)} of {len(snaps[0].trigger)}"
          f"  -> {sorted(round(x, 1) for x in tneg)}")
    print("  A negative basket close is therefore Target behaviour, not a defect.")

    # ---------------------------------------------------------------- panel E
    rule("E. RESCUE LEGS  (STR ORS / STR ORB / STR AVS / STR AVB)")
    RESC = ("STR ORS", "STR ORB", "STR AVS", "STR AVB")
    print("  IN SCOPE = the regime being matched.  ALL = the entire exported")
    print("  history.  Both are printed because the difference between them is")
    print("  the whole answer here, and a single column invites the exact error")
    print("  that was made once already.")
    print()
    print(f"  {'stream':>15} {'scope':>7} {'STR CLOSE':>10} {'STR ORS':>8}"
          f" {'STR ORB':>8} {'STR AVS':>8} {'STR AVB':>8} {'[sl ...]':>9}"
          f" {'(blank)':>8}")
    for s in snaps:
        for lbl, c in (("IN", s.exit_comments), ("ALL", s.exit_all)):
            print(f"  {s.name:>15} {lbl:>7} {c.get('STR CLOSE', 0):>10}"
                  f" {c.get('STR ORS', 0):>8} {c.get('STR ORB', 0):>8}"
                  f" {c.get('STR AVS', 0):>8} {c.get('STR AVB', 0):>8}"
                  f" {c.get('[sl ...]', 0):>9} {c.get('(blank)', 0):>8}")
    print()
    print("  every other exit-comment form present, so nothing hides in a bucket:")
    for s in snaps:
        rest = {k: v for k, v in s.exit_comments.items()
                if k not in RESC + ("STR CLOSE", "[sl ...]", "(blank)")}
        print(f"      {s.name:>15} : {rest if rest else 'none'}")
    print()
    print("  LIFETIME of each rescue tag -- first and last time it was ever emitted,")
    print(f"  against the regime boundary {DS.FINAL_REGIME_START:%Y-%m-%d}:")
    for s in snaps:
        for t in RESC:
            if s.exit_all.get(t):
                a, b = s.tag_first[t], s.tag_last[t]
                side = "BEFORE the boundary" if b < DS.FINAL_REGIME_START else "in scope"
                print(f"      {s.name:>15} {t:<8} n={s.exit_all[t]:>3}"
                      f"  {a:%Y-%m-%d} .. {b:%Y-%m-%d}   last emission {side}")
        if not any(s.exit_all.get(t) for t in RESC):
            print(f"      {s.name:>15} none of the four tags in any era")
    print()
    o_r = sum(snaps[1].exit_comments.get(t, 0) for t in RESC)
    t_r = sum(snaps[0].exit_comments.get(t, 0) for t in RESC)
    t_all = sum(snaps[0].exit_all.get(t, 0) for t in RESC)
    print(f"  TARGET rescue legs IN SCOPE {t_r} over {len(snaps[0].cycles)} cycles"
          f" and {len(snaps[0].pos)} closed positions")
    print(f"  OURS   rescue legs IN SCOPE {o_r} over {len(snaps[1].cycles)} cycles"
          f" and {len(snaps[1].pos)} closed positions")
    if t_r == 0 and o_r == 0:
        print(f"\n  -> BOTH ZERO.  The Target retired these legs with the regime: all"
              f" {t_all} of them")
        print("     predate the boundary, and they carry the OLD volume ladder")
        print("     (0.01/0.02/0.03/0.05), not this regime's 0.01/0.06/0.15.  There is")
        print("     no rate to compare and no Poisson test to run -- the correct")
        print("     count in the regime we are matching is zero, and ours is zero.")
        print("     Our source encodes exactly this: the sole STR ORB/ORS emission")
        print("     (StraddleEngine.mqh:1366) is fenced behind IsHistoricalProfile(),")
        print("     true only for HISTORICAL_50/60, while production runs LATEST_30.")
        print("     STR AVB/AVS have no emission site at all -- they died even")
        print("     earlier.  The fence is the finding, not a defect.")
    elif t_r > 0 and o_r == 0:
        exp = t_r / max(len(snaps[0].cycles), 1) * len(snaps[1].cycles)
        print(f"\n  -> Target DOES emit these in scope.  At its rate our"
              f" {len(snaps[1].cycles)} cycles expect {exp:.1f}.")
        print("     Before calling that a gap, check whether the gate condition was")
        print("     ever reached on our side -- an unexercised branch is not a")
        print("     divergence.  Worst floating at any of our triggers: "
              f"{min([t for t, _ in snaps[1].trigger], default=0):.2f}"
              f" vs the Target's {min([t for t, _ in snaps[0].trigger], default=0):.2f}")
    else:
        print(f"\n  -> ours {o_r}, target {t_r}: compare rates directly.")

    # ---------------------------------------------------------------- panel F
    rule("F. STOP DISCIPLINE AT SEND  (does a pending ever carry an SL?)")
    for s in snaps:
        print(f"  {s.name:>15}  grid orders {s.grid_orders:>6}"
              f"   carrying an SL when placed: {s.sl_at_send}"
              f"  -> {'PARITY (never)' if s.sl_at_send == 0 else 'DIVERGENCE'}")
    print()
    print("  Zero on both means the stop is a post-fill amendment on both, which")
    print("  is the precondition for a ratchet to exist at all.")

    # ---------------------------------------------------------------- panel G
    rule("G. LATTICE  (step == anchor/3000, tiers at L10 / L20)")
    print(f"  {'stream':>15} {'cycles':>7} {'median anchor':>14} {'median step':>12}"
          f" {'anchor/3000':>12} {'err':>8}")
    for s in snaps:
        an = [c.anchor for c in s.cycles if c.anchor]
        st = [c.step for c in s.cycles if c.step]
        if not an:
            continue
        ma, ms = statistics.median(an), statistics.median(st)
        print(f"  {s.name:>15} {len(s.cycles):>7} {ma:>14.2f} {ms:>12.4f}"
              f" {ma / DIVISOR:>12.4f} {ms - ma / DIVISOR:>+8.4f}")
    print()
    for s in snaps:
        print(f"  {s.name} volume by level band:")
        for band in ("L1-10", "L11-20", "L21-30"):
            c = s.vol_tier.get(band)
            if c:
                print(f"      {band:>7} : " + "  ".join(
                    f"{v:g}x{k}" for v, k in sorted(c.items())))

    # ---------------------------------------------------------------- panel H
    rule("H. PER-POSITION P&L  (the economic outcome the mechanisms produce)")
    print(f"  {'stream':>15} {'n':>6} {'win%':>7} {'med win':>8} {'med loss':>9}"
          f" {'mean':>8} {'p05':>8} {'p95':>8}")
    for s in snaps:
        v = s.pnl
        w = [x for x in v if x > 0]
        l = [x for x in v if x <= 0]
        print(f"  {s.name:>15} {len(v):>6} {pc(len(w), len(v))}"
              f" {statistics.median(w) if w else 0:>8.2f}"
              f" {statistics.median(l) if l else 0:>9.2f}"
              f" {statistics.fmean(v):>8.3f} {q(v, .05):>8.2f} {q(v, .95):>8.2f}")


if __name__ == "__main__":
    main()
