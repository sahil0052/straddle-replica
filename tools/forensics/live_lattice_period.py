"""Recover the lattice period from fill prices WITHOUT picking a mode.

Why this script exists.  live_build_epochs.py panel 2 estimates the lattice step
as the modal gap between consecutive same-side fills.  That estimator flagged
replica 2026-08-24 as running a 1.23 step against a mandated 4658/3000 = 1.55,
and it flagged four TARGET days as "wrong step" too until a mode-share gate was
added.  Both flags are suspect for the same reason: a mode is a fragile statistic
on a continuum, and consecutive same-side fills need not be adjacent rungs --
they can straddle a re-anchor, a skipped level, or a duplicate-order burst, and
every one of those injects a gap that is not a step.

So the modal estimator can be wrong in a way that MANUFACTURES a defect.  Before
touching StraddleEngine.mqh on the strength of the 1.23 reading, the reading has
to survive an estimator that shares none of its assumptions.

THE ARITHMETIC THAT MAKES 1.23 IMPOSSIBLE.  LATEST_30 sets step = anchor/3000
over 30 levels, so a cycle anchored at A can reach at most

    A + 30 * A/3000 = A * 1.01

A 1.23 step implies A = 3690, whose ladder tops out at 3727.  The 08-24 fills
happened at ~4658, which is 931 points beyond that ceiling.  So 1.23 cannot be a
step that any single consistent (anchor, step) pair ever produced.  Either the
pair was internally inconsistent -- and a grep shows it cannot be, since
SeedCycle (the one function taking anchor and step independently) has zero
callers repo-wide, and every reachable writer at StraddleEngine.mqh:634/663/1801
keeps the pair consistent -- or 1.23 is an artifact of the estimator.

THE MODE-FREE ESTIMATOR.  A static lattice puts every fill at price = A + n*s.
Then the phase

    phi(p) = 2*pi * (p mod s) / s

is IDENTICAL for every fill, whatever n is, because the anchor only sets a
constant offset.  So sweep candidate s and measure the circular concentration

    R(s) = |mean(exp(i*phi))|      in [0, 1]

R(s) ~ 1 means the prices really do sit on a lattice of period s; R(s) ~ 0 means
they do not.  This is the Rayleigh resultant, and it needs no mode, no gap, and
no assumption that consecutive fills are adjacent rungs.

TWO PROPERTIES OF R WORTH KNOWING BEFORE READING THE OUTPUT.

  Harmonics are real, not noise.  If the true period is s then s/2, s/3, ... all
  score R ~ 1, because points spaced s apart are also spaced by an integer
  number of s/k.  So the FUNDAMENTAL is the LARGEST s that scores high, and the
  peak list below will legitimately show its submultiples.  Multiples above the
  fundamental do NOT score high (points land on alternating phases and cancel),
  which is what makes "largest high-R period" well defined.

  Mixing anchors destroys R.  Two cycles with different anchors contribute two
  different constant phases, so a day containing many re-anchors will show low R
  even when each individual cycle is a perfect lattice.  That is a feature: it
  distinguishes our long-lived static lattice from the Target's constant
  re-anchoring.

RESULT OF THE FIRST RUN, AND WHY THIS SCRIPT IS WINDOWED.  Run per DAY, the scan
found no lattice anywhere -- not on one Target day, not on one replica day:

    replica POST 2026-08-24  n=675   R(1.552) = 0.162   R(1.230) = 0.211
    replica POST 2026-08-25  n=432   R(1.547) = 0.029   R(1.230) = 0.031

Both candidates score as noise, so the day-scale scan cannot adjudicate 1.23 vs
1.55 -- it rejects both.  That is the anchor-mixing property above, not a bug:
a day holds many cycles, each with its own anchor, and their phases cancel.  The
only unit on which "step = anchor/3000" is even a meaningful claim is a SINGLE
cycle, so the scan below runs over sliding windows of consecutive fills and
keeps only the windows that actually resolve a lattice.  Windows straddling a
re-anchor score low R and are discarded, which is the correct behaviour.

The statistic that comes out is the IMPLIED DIVISOR, medianprice / period.  It
is directly comparable to the profile constant anchor_divisor = 3000, and it is
comparable between the two accounts without either of them sharing a day.
"""
from __future__ import annotations

import math
import os
import statistics
import sys
from collections import defaultdict
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
from tools.forensics.live_stream_parity import load, TARGET, REPLICA, FRESH  # noqa: E402
from tools.forensics.live_build_epochs import cohorts, DIVISOR  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Sweep range and resolution.  0.60..3.20 covers anchor/3000 for gold from 1800
# to 9600, which brackets every price in the evidence by a wide margin.
S_LO, S_HI, S_STEP = 0.60, 3.20, 0.001
R_MIN = 0.55          # a period must beat this to count as a real lattice
MIN_N = 20            # fewer prices than this and R is not meaningful


def resultant(prices: list[float], s: float) -> float:
    """Rayleigh resultant length of the phases of prices modulo s."""
    k = 2.0 * math.pi / s
    c = sv = 0.0
    for p in prices:
        a = k * p
        c += math.cos(a)
        sv += math.sin(a)
    n = len(prices)
    return math.hypot(c / n, sv / n)


def scan(prices: list[float]) -> list[tuple[float, float]]:
    """Return local maxima of R(s) over the sweep, strongest first."""
    xs, rs = [], []
    s = S_LO
    while s <= S_HI + 1e-12:
        xs.append(s)
        rs.append(resultant(prices, s))
        s += S_STEP
    peaks = []
    for i in range(1, len(rs) - 1):
        if rs[i] >= rs[i - 1] and rs[i] > rs[i + 1] and rs[i] >= R_MIN:
            peaks.append((xs[i], rs[i]))
    peaks.sort(key=lambda t: -t[1])
    return peaks


def fundamental(prices: list[float]) -> tuple[float, float]:
    """Largest high-R period = the fundamental.  (0,0) if the prices aren't a lattice."""
    peaks = scan(prices)
    if not peaks:
        return 0.0, 0.0
    best = max(peaks, key=lambda t: t[0])
    return best


def rule(t: str) -> None:
    print()
    print("=" * 100)
    print(t)
    print("=" * 100)


def main() -> None:
    st = load()
    co = cohorts(st)

    rule("1. PER-DAY LATTICE PERIOD  (mode-free Rayleigh scan of price mod s)")
    print("  fund = largest period scoring R >= 0.55; R = concentration in [0,1].")
    print("  expect = medianprice/3000, the period LATEST_30 mandates.")
    print("  A cohort that re-anchors often will show low R and fund=--; that is")
    print("  information about re-anchoring, not a failure of the scan.")
    print()
    print(f"  {'cohort':>13} {'day':>11} {'n':>5} {'medpx':>7} {'expect':>7}"
          f" {'fund':>6} {'R':>5} {'err':>7}   peaks(top4)")
    verdict: dict[str, list[float]] = defaultdict(list)
    for name, ds in co:
        byday: dict[date, list[float]] = defaultdict(list)
        for d in ds:
            byday[d.t.date()].append(d.price)
        for day in sorted(byday):
            ps = byday[day]
            if len(ps) < MIN_N:
                continue
            medpx = statistics.median(ps)
            expect = medpx / DIVISOR
            f, r = fundamental(ps)
            peaks = scan(ps)[:4]
            ptxt = " ".join(f"{a:.3f}/{b:.2f}" for a, b in peaks) or "(none)"
            if f > 0.0:
                err = f"{100.0 * (f - expect) / expect:+6.1f}%"
                verdict[name].append(100.0 * (f - expect) / expect)
            else:
                err = "     --"
            print(f"  {name:>13} {str(day):>11} {len(ps):>5} {medpx:>7.0f}"
                  f" {expect:>7.2f} {f:>6.3f} {r:>5.2f} {err}   {ptxt}")

    rule("2. THE 1.23 QUESTION -- is it a lattice period at all?")
    print("  If the EA really ran a 1.23 step on 2026-08-24, then 1.23 must score a")
    print("  high R on that day's prices.  If R(1.23) is low while R(1.55) is high,")
    print("  the 1.23 mode was an artifact of the gap estimator and there is no")
    print("  defect to fix -- and no .mqh edit is warranted.")
    print()
    post = dict(co)["replica POST"] if "replica POST" in dict(co) else []
    for day in (date(2026, 8, 24), date(2026, 8, 25)):
        ps = [d.price for d in post if d.t.date() == day]
        if len(ps) < MIN_N:
            continue
        medpx = statistics.median(ps)
        print(f"  replica POST {day}   n={len(ps)}  medpx={medpx:.2f}"
              f"  anchor/3000={medpx / DIVISOR:.3f}")
        for cand in (1.23, medpx / DIVISOR, 1.55, 0.615, 3.10):
            print(f"      R({cand:.3f}) = {resultant(ps, cand):.3f}")
        print()

    rule("3. SUMMARY -- deviation of the recovered period from anchor/3000")
    for name in ("TARGET      ", "replica PRE ", "replica POST", "fresh  POST "):
        v = verdict.get(name, [])
        if not v:
            print(f"  {name}: no day produced a usable lattice period"
                  f"  (consistent with frequent re-anchoring)")
            continue
        print(f"  {name}: n={len(v)} days  median err={statistics.median(v):+.1f}%"
              f"  range {min(v):+.1f}%..{max(v):+.1f}%")


if __name__ == "__main__":
    main()
