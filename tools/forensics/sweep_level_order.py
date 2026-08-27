"""Does the Target's flatten sweep close INNER levels first or OUTER levels first?

WHY THIS SCRIPT EXISTS.  Commit 9a0cf62 flipped TryCloseOneOwnedPosition() from a
descending index walk to an ascending one, on the stated grounds that the Target
"closes positions in ascending level order (Level 1, Level 2, Level 3...)".  But
flatten_order.py measures the Target's post-break sweeps at
rho(close order, OPEN time) = -0.994 -- strongly newest-first -- and a descending
index walk is what produces newest-first, since MT5 appends new positions to the
end of the list.  So the two claims prescribe opposite loop directions and at most
one of them can be a parity fix.

NOTE ON A WRONG INFERENCE THIS SCRIPT WAS BUILT TO TEST.  An earlier reading went
"in a trending grid the outer levels fill LAST, so newest-first means OUTER-first."
That does not follow, and the measurement below is what shows it: level is a
PER-SIDE coordinate, with each wing numbering outward from the anchor
independently, so a monotone newest = outermost chain only exists inside a
one-sided trend.  Open time is strongly ordered in the Target's sweeps; level is
not ordered at all.  Both facts are true at once.

This script decides it on the quantity actually in dispute: the grid LEVEL NUMBER
of each flattened leg, in the order the legs were closed.

    rho(close_order_index, level) strongly POSITIVE  -> inner levels first (ascending)
    rho(close_order_index, level) strongly NEGATIVE  -> outer levels first (descending)
    rho ~ 0                                          -> no level rule at all

LEVEL SOURCE.  The Target's positions DO carry per-level comments.  An earlier
version of this docstring claimed they did not, and that was simply wrong:
dataset.GRID_RE ("STR B7" / "STR S12") matches 17,515 of 17,632 Target positions
(99.3%) and 1,097 of 1,097 in the post-pacing-break regime (100.0%).  The level was
readable directly the whole time, so the comment is now the primary source on every
account, Target included.

The geometric reconstruction is kept as a cross-check and as a fallback for the
117 legs with no usable comment: each cycle's deployment burst is fitted to a
lattice in dataset._fit_lattice, and a position's level is the lattice slot whose
price is nearest its open price on the matching side.  A leg further than half a
step from every slot is dropped as unattributable rather than snapped to a wrong
level.

CAVEAT ON THE GEOMETRY -- it carries a systematic OFF-BY-ONE on Target data, and
it is worst exactly where it matters most.  Against the Target's own comments it
agrees on 86.1% of pre-break flatten legs but only 54.5% of post-break ones, and
every inspected mismatch is geo = comment + 1: the fitted anchor sits about half a
step off on Target cycles, so the nearest-slot search lands one rung out.  (An
earlier version of this note quoted 82.8% pooled across both regimes, which hid
how much worse the post-break fit is.)  It agrees 47/47 and 31/31 on OUR accounts,
where the fit is unbiased.  A uniform off-by-one is a MONOTONE transform of level,
so it cannot change a Spearman rho -- which is why the geometric verdict and the
authoritative comment-level verdict below agree on the sign and the conclusion.
Do not use level_from_lattice() for anything that needs an ABSOLUTE level on
Target data.

SWEEP CLASSIFICATION is the mechanism test from flatten_order.py, not a time
window: a position carrying a stop price was stopped out, one carrying none was
flattened.  Stop-losses keep firing while a paced flatten runs, so a time window
silently mixes them in and corrupts the ordering.
"""
from __future__ import annotations

import statistics
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.forensics import dataset as DS

PACING_BREAK = datetime(2026, 7, 24, 12, 0, 0)
SWEEP_MAX = 900.0

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / ".cache" / "golden"
FRESH = ROOT / ".cache" / "fresh"
VANTAGE = ROOT / ".cache" / "vantage"


def spearman(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 3:
        return None

    def rank(v: list[float]) -> list[float]:
        order = sorted(range(n), key=lambda i: v[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    rx, ry = rank(xs), rank(ys)
    mx, my = statistics.fmean(rx), statistics.fmean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = sum((a - mx) ** 2 for a in rx) ** 0.5
    dy = sum((b - my) ** 2 for b in ry) ** 0.5
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


def level_from_lattice(p, cyc) -> int | None:
    """Nearest lattice slot on the matching side, or None if unattributable."""
    if not cyc.lattice or not cyc.step or p.open_price is None:
        return None
    side = "B" if p.dir > 0 else "S"
    best, bestd = None, None
    for (sd, lv), price in cyc.lattice.items():
        if sd != side:
            continue
        d = abs(p.open_price - price)
        if bestd is None or d < bestd:
            best, bestd = lv, d
    if best is None or bestd is None:
        return None
    if bestd > cyc.step * 0.5:
        return None
    return best


def level_from_comment(p) -> int | None:
    m = DS.GRID_RE.match((p.comment or "").strip())
    return int(m.group(2)) if m else None


def sweeps(cycles, lo=None, hi=None):
    """Flatten sweeps of 4+ legs, classified by mechanism."""
    out = []
    for c in cycles:
        closed = [p for p in c.positions if not p.is_open and p.close_time]
        if len(closed) < 4:
            continue
        t0 = None
        for p in sorted(closed, key=lambda p: p.close_time):
            if not (p.stop_loss and p.stop_loss > 0):
                t0 = p.close_time
                break
        if t0 is None:
            continue
        if lo is not None and t0 < lo:
            continue
        if hi is not None and t0 >= hi:
            continue
        sw = [
            p
            for p in closed
            if t0 <= p.close_time <= t0 + timedelta(seconds=SWEEP_MAX)
            and not (p.stop_loss and p.stop_loss > 0)
        ]
        if len(sw) < 4:
            continue
        sw.sort(key=lambda p: p.close_time)
        out.append((c, sw))
    return out


def measure(label, dirpath, lo=None, hi=None, use_comment=False):
    DS.GOLDEN = dirpath
    orders, positions, deals, cycles = DS.load_all()
    sws = sweeps(cycles, lo, hi)

    rho_lvl, rho_open, agree, disagree, dropped, kept = [], [], 0, 0, 0, 0
    per_sweep = []
    for cyc, sw in sws:
        idx, lvls, opens = [], [], []
        for i, p in enumerate(sw):
            geo = level_from_lattice(p, cyc)
            cmt = level_from_comment(p)
            if use_comment and cmt is not None and geo is not None:
                if cmt == geo:
                    agree += 1
                else:
                    disagree += 1
            lv = cmt if (use_comment and cmt is not None) else geo
            if lv is None:
                dropped += 1
                continue
            kept += 1
            idx.append(float(i))
            lvls.append(float(lv))
            opens.append(p.open_time.timestamp())
        if len(idx) < 4:
            continue
        r = spearman(idx, lvls)
        ro = spearman(idx, opens)
        if r is not None:
            rho_lvl.append(r)
            per_sweep.append((cyc.index, len(idx), r, ro))
        if ro is not None:
            rho_open.append(ro)

    print(f"\n{label}")
    print(f"  sweeps measured {len(rho_lvl):4d}   legs kept {kept:5d}   legs unattributable {dropped:4d}")
    if use_comment:
        tot = agree + disagree
        pct = 100.0 * agree / tot if tot else 0.0
        print(f"  level cross-check (comment vs geometry): {agree}/{tot} agree = {pct:.1f}%")
    if not rho_lvl:
        print("  -- no measurable sweeps --")
        return None
    med = statistics.median(rho_lvl)
    print(f"  rho(close order, LEVEL)      median {med:+.3f}   "
          f"min {min(rho_lvl):+.3f}  max {max(rho_lvl):+.3f}")
    if rho_open:
        print(f"  rho(close order, OPEN time)  median {statistics.median(rho_open):+.3f}   "
              f"(cross-check vs flatten_order.py)")
    pos = sum(1 for r in rho_lvl if r > 0.5)
    neg = sum(1 for r in rho_lvl if r < -0.5)
    mid = len(rho_lvl) - pos - neg
    print(f"  sweeps clearly INNER-first (rho > +0.5) : {pos:4d}")
    print(f"  sweeps clearly OUTER-first (rho < -0.5) : {neg:4d}")
    print(f"  sweeps with no clear level rule         : {mid:4d}")
    verdict = ("INNER LEVELS FIRST (ascending)" if med > 0.5 else
               "OUTER LEVELS FIRST (descending)" if med < -0.5 else
               "NO LEVEL RULE -- the loop does not sort by level")
    print(f"  VERDICT: {verdict}")
    return med, per_sweep


def main() -> None:
    print("=" * 78)
    print("SWEEP ORDER BY GRID LEVEL -- does the flatten close inner or outer first?")
    print("=" * 78)
    print("  rho > +0.5  inner levels first (level 1, 2, 3 ...)  <- the 9a0cf62 claim")
    print("  rho < -0.5  outer levels first (level 30, 29, ...)")
    print("  rho ~  0    no level ordering at all")

    a = measure("TARGET 901018  pre-break  (0.1s pacing)", GOLDEN, hi=PACING_BREAK,
                use_comment=True)
    b = measure("TARGET 901018  post-break (20s pacing)", GOLDEN, lo=PACING_BREAK,
                use_comment=True)
    c = measure("OURS 111638511 (comment levels + geometry cross-check)",
                FRESH, use_comment=True)
    d = measure("OURS 25954110  (comment levels + geometry cross-check)",
                VANTAGE, use_comment=True)

    print("\n" + "=" * 78)
    print("PER-SWEEP DETAIL -- OUR live account, every sweep")
    print("=" * 78)
    if d:
        print(f"  {'cycle':>6} {'legs':>5} {'rho(level)':>11} {'rho(open)':>10}")
        for ci, n, r, ro in d[1]:
            ros = f"{ro:+.3f}" if ro is not None else "  n/a"
            print(f"  {ci:6d} {n:5d} {r:+11.3f} {ros:>10}")

    print("\n" + "=" * 78)
    print("WHAT THIS MEANS FOR COMMIT 9a0cf62")
    print("=" * 78)
    if b is None:
        print("  Target post-break unmeasurable -- cannot adjudicate.")
        return
    tmed = b[0]
    if tmed > 0.5:
        print("  The Target DOES close inner levels first.  9a0cf62 (ascending walk) is")
        print("  the correct direction and should stay.")
    elif tmed < -0.5:
        print("  The Target closes OUTER levels first.  9a0cf62 flipped the loop the WRONG")
        print("  way and should be reverted to the descending walk.")
    else:
        print(f"  The Target's median rho(close order, level) is {tmed:+.3f} -- it has NO level")
        print("  ordering rule.  Its sweep is an unsorted walk of MT5's position list, the")
        print("  same as ours.  Neither direction is 'the parity direction', because there")
        print("  is no target ordering to match: the sequence is an artifact of how MT5")
        print("  happens to index positions and how that index compacts as legs are removed.")
        print("  9a0cf62 is therefore HARMLESS but it is also NOT a parity fix, and the")
        print("  'ascending level order' evidence it cites does not reproduce.")


if __name__ == "__main__":
    main()
