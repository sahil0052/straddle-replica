"""Same-window, same-instrument Target-vs-replica comparison.  The strict version.

live_stream_parity.py measured the two streams over their FULL extents:
Target 2026-07-31..08-21, replica 2026-08-20..08-25.  Those windows share only
two days, so every difference it reported is confounded by market regime -- a
volume tier that "the Target never uses" may simply be a level price never
reached on the Target's days.  Nothing from that script may be cited as a
divergence until it survives here.

This script fixes three specific measurement faults:

  1. WINDOW.  Restrict both streams to the days on which BOTH traded.  Same
     ticks, same volatility, same session -- so a residual difference is the EA
     or its configuration, not the market.

  2. LATTICE.  The previous panel sorted every distinct price in a day and took
     successive differences.  With many overlapping cycles that measures the
     density of a day's prices, not the lattice; it is why the modal "step" came
     out at 0.20 (noise) instead of anything structural.  Correct estimator:
     differences between CONSECUTIVE-IN-TIME fills on the SAME side, which walk
     the lattice one rung at a time.

  3. MANUAL CONTAMINATION.  On 2026-08-20 21:50:52 a human pressed MT5's "Close
     All Positions" on the replica: six CLOSE_BY operations consuming position
     #10128083980 from 0.15 down to 0.10, then market-closes of the remainder.
     Our code contains no CloseBy call anywhere (grep: zero hits), so those
     fills are not the EA's behaviour and must be excised before any pacing
     claim -- five of them share one millisecond and would otherwise dominate
     the same-ms count that is the headline finding.

What survives all three corrections is a real gap.  What does not, is noise.
"""
from __future__ import annotations

import os
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
from tools.forensics.live_stream_parity import load, TARGET, REPLICA  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# The manual "Close All Positions" batch on the replica.  Bounds taken from the
# archived log: first CLOSE_BY at 21:50:52.221, last market-close 21:51:38.772.
MANUAL_LO = datetime(2026, 8, 20, 21, 50, 45)
MANUAL_HI = datetime(2026, 8, 20, 21, 52, 0)


def is_manual(d) -> bool:
    return d.acc == REPLICA and MANUAL_LO <= d.t <= MANUAL_HI


def rule(t: str) -> None:
    print()
    print("=" * 100)
    print(t)
    print("=" * 100)


def pc(a: int, b: int) -> str:
    return f"{100.0*a/b:5.1f}%" if b else "    --"


def main() -> None:
    st = load()
    tgt_all, rep_all = st[TARGET], st[REPLICA]

    td = {d.t.date() for d in tgt_all}
    rd = {d.t.date() for d in rep_all}
    both = sorted(td & rd)

    rule("0. THE SHARED WINDOW")
    print(f"  Target days  : {len(td)}  {min(td)} .. {max(td)}")
    print(f"  replica days : {len(rd)}  {min(rd)} .. {max(rd)}")
    print(f"  SHARED days  : {len(both)}  -> {[str(d) for d in both]}")
    if not both:
        print("  no overlap; nothing here can be compared fairly.")
        return

    n_manual = sum(1 for d in rep_all if is_manual(d))
    tgt = [d for d in tgt_all if d.t.date() in both]
    rep = [d for d in rep_all if d.t.date() in both and not is_manual(d)]
    print(f"  excised manual Close-All fills on the replica : {n_manual}")
    print(f"  comparable deals : Target {len(tgt)}   replica {len(rep)}")

    # ------------------------------------------------------------------ panel 1
    rule("1. VOLUME LADDER, SHARED DAYS ONLY")
    print("  Does the 0.15 / 0.30 asymmetry survive when the market is held fixed?")
    print()
    for name, ds in (("TARGET ", tgt), ("replica", rep)):
        c = Counter(d.vol for d in ds)
        n = len(ds)
        print(f"  {name}  n={n}   volume={sum(d.vol for d in ds):.2f} lots")
        for v, k in sorted(c.items()):
            print(f"      {v:>6.2f} : {k:>5}  {pc(k, n)}  {'#'*max(1,round(40.0*k/n))}")
        print()
    ct, cr = Counter(d.vol for d in tgt), Counter(d.vol for d in rep)
    only_t = sorted(set(ct) - set(cr))
    only_r = sorted(set(cr) - set(ct))
    print(f"  tiers only the TARGET used  : {only_t}")
    print(f"  tiers only the REPLICA used : {only_r}")
    print()
    print("  Per-day volume rate -- the exposure comparison that matters, because a")
    print("  basket's $/point is set by lots, not by fill count:")
    for name, ds in (("TARGET ", tgt), ("replica", rep)):
        byday = defaultdict(float)
        for d in ds:
            byday[d.t.date()] += d.vol
        for day in both:
            print(f"      {name} {day} : {byday.get(day,0.0):>6.2f} lots"
                  f"   ({sum(1 for d in ds if d.t.date()==day)} fills)")

    # ------------------------------------------------------------------ panel 2
    rule("2. LATTICE STEP -- consecutive-in-time, same-side (correct estimator)")
    print("  Successive fills on one side walk the lattice.  Take |dP| between")
    print("  consecutive same-side fills that are close in time, and histogram.")
    print()
    for name, ds in (("TARGET ", tgt_all), ("replica", rep_all),
                     ("fresh  ", st.get("111638511", []))):
        if len(ds) < 4:
            continue
        gaps = []
        last = {}
        for d in ds:
            if is_manual(d):
                continue
            p = last.get(d.side)
            if p is not None:
                dt = (d.t - p.t).total_seconds()
                g = round(abs(d.price - p.price), 2)
                if 0 < dt <= 120.0 and 0.05 <= g <= 8.0:
                    gaps.append(g)
            last[d.side] = d
        if not gaps:
            print(f"  {name}: none")
            continue
        c = Counter(gaps)
        print(f"  {name}  n={len(gaps)}  median={statistics.median(gaps):.2f}"
              f"  mode={c.most_common(1)[0][0]:.2f}")
        for g, k in c.most_common(7):
            print(f"      {g:>5.2f} : {k:>5}  {pc(k, len(gaps))}"
                  f"  {'#'*max(1,round(40.0*k/len(gaps)))}")
        # cluster into 0.10-wide bins to expose a step family
        binned = Counter(round(g, 1) for g in gaps)
        top = binned.most_common(5)
        print(f"      0.1-binned top: {[(f'{a:.1f}', b) for a, b in top]}")
        print()

    # ------------------------------------------------------------------ panel 3
    rule("3. PACING, SHARED DAYS, MANUAL FILLS EXCISED")
    print("  The headline claim was 'Target 0 same-ms, replica 58'.  Does it hold")
    print("  after excising the human Close-All and equalising the market?")
    print()
    buckets = [(0.0, 0.001, "same ms"), (0.001, 0.1, "<100ms"),
               (0.1, 1.0, "0.1-1s"), (1.0, 5.0, "1-5s"), (5.0, 15.0, "5-15s"),
               (15.0, 25.0, "15-25s  <- 20s family"), (25.0, 60.0, "25-60s"),
               (60.0, 86400.0, ">1min")]
    for name, ds in (("TARGET ", tgt), ("replica", rep)):
        dl = [(b.t - a.t).total_seconds() for a, b in zip(ds, ds[1:])
              if 0.0 <= (b.t - a.t).total_seconds() <= 86400.0]
        if not dl:
            continue
        print(f"  {name}  n={len(dl)} gaps")
        for lo, hi, nm in buckets:
            k = sum(1 for x in dl if lo <= x < hi)
            print(f"      {nm:>22} : {k:>5}  {pc(k, len(dl))}"
                  f"  {'#'*round(40.0*k/len(dl))}")
        n20 = [x for x in dl if 19.0 <= x <= 21.5]
        if n20:
            print(f"      [19.0,21.5] n={len(n20)} median={statistics.median(n20):.3f}s"
                  f" mean={statistics.fmean(n20):.3f}s"
                  f" min={min(n20):.3f} max={max(n20):.3f}")
        print()

    # ------------------------------------------------------------------ panel 4
    rule("4. THE SUB-100ms CLUSTERS -- what exactly is the replica doing?")
    print("  If these are one broker tick sweeping several resting pendings, the")
    print("  cluster members will differ in PRICE and share a side, and prices will")
    print("  be one lattice step apart.  If they are the EA firing several actions")
    print("  in one tick, prices will be near-identical.  That distinction decides")
    print("  whether this is our bug or the broker's behaviour.")
    print()
    for name, ds in (("TARGET ", tgt_all), ("replica", rep_all)):
        ds = [d for d in ds if not is_manual(d)]
        clusters = []
        cur = [ds[0]]
        for a, b in zip(ds, ds[1:]):
            if (b.t - a.t).total_seconds() < 0.100:
                cur.append(b)
            else:
                if len(cur) > 1:
                    clusters.append(cur)
                cur = [b]
        if len(cur) > 1:
            clusters.append(cur)
        print(f"  {name}  {len(clusters)} sub-100ms clusters")
        if not clusters:
            print("      (none -- the stream is fully serialised)")
            print()
            continue
        sizes = Counter(len(c) for c in clusters)
        print(f"      sizes: {dict(sorted(sizes.items()))}")
        same_side = sum(1 for c in clusters if len({d.side for d in c}) == 1)
        same_px = sum(1 for c in clusters
                      if max(d.price for d in c) - min(d.price for d in c) < 0.01)
        print(f"      single-side : {same_side}/{len(clusters)}"
              f"   identical-price : {same_px}/{len(clusters)}")
        spreads = sorted(round(max(d.price for d in c) - min(d.price for d in c), 2)
                         for c in clusters)
        print(f"      intra-cluster price spread: median {statistics.median(spreads):.2f}"
              f"  max {spreads[-1]:.2f}")
        print("      first 6 clusters:")
        for c in clusters[:6]:
            desc = " | ".join(f"{d.t.strftime('%H:%M:%S.%f')[:-3]} {d.side[0]}"
                              f"{d.vol:g}@{d.price:.2f}" for d in c)
            print(f"        {c[0].t.date()}  {desc}")
        print()


if __name__ == "__main__":
    main()
