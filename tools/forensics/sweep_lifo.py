"""Is the flatten sweep ordered by OPEN TIME (LIFO) rather than by grid level?

sweep_level_order.py established that the Target has NO level ordering rule:
median rho(close order, level) = -0.086 across 217 pre-break sweeps and -0.207
across 29 post-break sweeps, with inner-first and outer-first sweeps roughly
balanced (53 vs 61, and 4 vs 11).  That kills the "ascending level order" premise
behind commit 9a0cf62.

But rho(close order, OPEN time) is -0.994 post-break -- an extremely strong and
consistent signal.  So the sweep IS ordered; it is ordered by open time, newest
first, i.e. LIFO.  Level and open time are decoupled in a straddle because level
is a PER-SIDE coordinate: the buy wing and the sell wing each number outward from
the anchor independently, and price visits the two wings in whatever order it
happens to move.  A single monotone "newest = outermost" chain only exists in a
one-sided trend.  That decoupling is why "newest-first" did not imply
"outer-level-first", and it is the step that was wrong in the earlier reasoning.

This script tests LIFO non-parametrically, without correlation coefficients:

  EXACT REVERSE     is the close sequence exactly the reverse of the open sequence?
  INVERSION RATE    of all leg pairs (i,j) with i closed before j, what fraction
                    had i opened AFTER j?  1.00 = perfect LIFO, 0.50 = random
                    order, 0.00 = perfect FIFO.

Both are computed for the Target on each side of the pacing break and for our two
accounts, so the replica's sweep discipline can be read against the Target's on the
same scale.
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


def sweeps(cycles, lo=None, hi=None):
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


def inversion_rate(sw) -> tuple[float, int]:
    """Fraction of leg pairs closed in reverse-of-open order.  1.0 = pure LIFO."""
    n = len(sw)
    inv = tot = 0
    for i in range(n):
        for j in range(i + 1, n):
            ti, tj = sw[i].open_time, sw[j].open_time
            if ti == tj:
                continue
            tot += 1
            if ti > tj:          # closed earlier but opened later -> LIFO pair
                inv += 1
    return (inv / tot if tot else 0.0), tot


def measure(label, dirpath, lo=None, hi=None):
    DS.GOLDEN = dirpath
    _o, _p, _d, cycles = DS.load_all()
    sws = sweeps(cycles, lo, hi)

    rates, exact_rev, exact_fwd, legs = [], 0, 0, []
    for _c, sw in sws:
        r, tot = inversion_rate(sw)
        if tot == 0:
            continue
        rates.append(r)
        legs.append(len(sw))
        by_open_desc = sorted(sw, key=lambda p: p.open_time, reverse=True)
        by_open_asc = sorted(sw, key=lambda p: p.open_time)
        ids = [p.open_time for p in sw]
        if ids == [p.open_time for p in by_open_desc]:
            exact_rev += 1
        if ids == [p.open_time for p in by_open_asc]:
            exact_fwd += 1

    print(f"\n{label}")
    if not rates:
        print("  -- no measurable sweeps --")
        return None
    n = len(rates)
    med = statistics.median(rates)
    strong = sum(1 for r in rates if r >= 0.90)
    print(f"  sweeps {n:4d}   median legs {statistics.median(legs):.1f}")
    print(f"  inversion rate (1.00 = pure LIFO, 0.50 = random, 0.00 = FIFO)")
    print(f"      median {med:.3f}    min {min(rates):.3f}    max {max(rates):.3f}")
    print(f"  sweeps at >= 0.90 (near-pure LIFO) : {strong:4d} / {n}  = {100.0*strong/n:5.1f}%")
    print(f"  sweeps that are EXACTLY reverse-of-open (pure LIFO) : {exact_rev:4d} / {n}")
    print(f"  sweeps that are EXACTLY open order      (pure FIFO) : {exact_fwd:4d} / {n}")
    return med, n, strong, exact_rev, exact_fwd


def main() -> None:
    print("=" * 78)
    print("IS THE FLATTEN SWEEP LIFO?  (newest position closed first)")
    print("=" * 78)

    tpre = measure("TARGET 901018  pre-break  (0.1s pacing)", GOLDEN, hi=PACING_BREAK)
    tpost = measure("TARGET 901018  post-break (20s pacing)", GOLDEN, lo=PACING_BREAK)
    f = measure("OURS 111638511  (Aug 25 -- DESCENDING loop)", FRESH)
    v = measure("OURS 25954110   (Aug 26 -- DESCENDING loop, all 3 sweeps pre-9a0cf62)",
                VANTAGE)

    print("\n" + "=" * 78)
    print("READ-OUT")
    print("=" * 78)
    if tpost is None:
        print("  Target post-break unmeasurable.")
        return
    print(f"  Target post-break LIFO rate     {tpost[0]:.3f}   "
          f"({tpost[2]}/{tpost[1]} sweeps at >= 0.90, {tpost[3]} exactly reverse)")
    if tpre:
        print(f"  Target pre-break  LIFO rate     {tpre[0]:.3f}   "
              f"({tpre[2]}/{tpre[1]} sweeps at >= 0.90, {tpre[3]} exactly reverse)")
    if f:
        print(f"  Ours 111638511 (descending)     {f[0]:.3f}   "
              f"({f[2]}/{f[1]} sweeps at >= 0.90, {f[3]} exactly reverse)")
    if v:
        print(f"  Ours 25954110  (descending)     {v[0]:.3f}   "
              f"({v[2]}/{v[1]} sweeps at >= 0.90, {v[3]} exactly reverse)")

    print()
    print("  A descending index walk over MT5's position list closes the most recently")
    print("  appended position first, which is exactly LIFO in open time.  An ascending")
    print("  walk closes the oldest first, which is FIFO.  So if the Target is LIFO, the")
    print("  DESCENDING loop is the parity direction and commit 9a0cf62 inverted it.")
    print()
    print("  None of our measured sweeps ran the ascending loop: 9a0cf62 was committed")
    print("  2026-08-26 18:20:45 server time and our three sweeps began 13:20:51,")
    print("  18:03:07 and 18:20:55, the last of which predates deployment.  The ascending")
    print("  loop is therefore UNTESTED in production.")


if __name__ == "__main__":
    main()
