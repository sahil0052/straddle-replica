"""Q2c: re-snapshot the rescue at the CORRECTED decision instant.

q2b Panel A exposed two errors in q2a's snapshot, and both flowed in the same
direction -- they made the replica's conditions look refuted when they are not.

  1. The dataset spells the order state "canceled" (one L).  q2b tested for
     "cancelled", so every cancel-replace fell through to a catch-all bucket.  The
     real split of the 125 rescue orders is 89 cancel-replace / 36 re-arm: the
     dominant path is CANCEL a surviving base pending, then RE-PLACE it at 2x.

  2. ProcessTrendRescue does one broker action per timer tick, and the cancels come
     FIRST (TryCancelOneTrendRescueOrder returns early until the trend side is
     clear, only then does m_trend_rescue_replacing flip and placement start).  So
     at the moment the first 2x order appears, every base pending it is replacing
     has ALREADY been pulled.  Snapshotting there reads 0 pendings by construction
     and says nothing about what was true when the EA decided.

     With close_interval/cooldown at 20 s post-break and one action per tick, the
     gap between the first cancel and the first 2x placement can be minutes.

The corrected decision instant is the moment the FIRST base pending on the trend
side was cancelled, among the slots that later received a 2x order.  That is the
first observable consequence of trend_rescue_start.

Panel A  re-snapshots all three conditions there.
Panel B  measures the cancel-sweep geometry, to confirm the decision instant really
         is the first cancel and not something earlier still.
Panel C  the falsifier hunt: what separates the 6 rescue cycles from the other 94?
         Sweeps a family of candidate gates and ranks them by (misses, falsifiers).
"""
from __future__ import annotations

import statistics
import sys
from bisect import bisect_right
from collections import Counter
from datetime import datetime, timedelta

sys.path.insert(0, r"C:\websites\mt5 2")
from tools.forensics.dataset import load_all, FINAL_REGIME_START, CONTRACT  # noqa: E402

BREAK = datetime(2026, 7, 24, 12, 0, 0)
M15 = timedelta(minutes=15)


def tier_lot(level: int) -> float:
    return 0.01 if level <= 10 else (0.06 if level <= 20 else 0.15)


def is_base(o) -> bool:
    return abs(o.volume - tier_lot(o.level)) < 1e-9


def is_rescue(o) -> bool:
    return abs(o.volume - 2.0 * tier_lot(o.level)) < 1e-9


def regime(t: datetime) -> str:
    return "EARLY" if t < BREAK else "LATE"


def m15_floor(t: datetime) -> datetime:
    return t.replace(minute=(t.minute // 15) * 15, second=0, microsecond=0)


def main() -> None:
    orders, positions, deals, cycles = load_all()

    prints: list[tuple[datetime, float]] = []
    for p in positions:
        prints.append((p.open_time, p.open_price))
        if p.close_time and p.close_price:
            prints.append((p.close_time, p.close_price))
    prints.sort(key=lambda r: r[0])
    ptimes = [t for t, _ in prints]
    pvals = [v for _, v in prints]

    def price_at(t):
        i = bisect_right(ptimes, t) - 1
        return (pvals[i], (t - ptimes[i]).total_seconds()) if i >= 0 else (None, 1e9)

    bars: dict[datetime, float] = {}
    for t, v in prints:
        bars[m15_floor(t)] = v
    bar_keys = sorted(bars)

    def prior_close(t, back=6):
        i = bisect_right(bar_keys, m15_floor(t) - back * M15) - 1
        return bars[bar_keys[i]] if i >= 0 else None

    def floating(pos, t, mark):
        return sum(p.dir * (mark - p.open_price) * p.volume * CONTRACT + p.swap
                   for p in pos
                   if p.open_time <= t and (p.close_time is None or p.close_time > t))

    fin = [c for c in cycles if c.start >= FINAL_REGIME_START]

    def base_pend(cyc, t, side):
        return sum(1 for o in cyc.orders
                   if o.is_grid and o.level is not None and o.side == side
                   and is_base(o) and o.open_time <= t
                   and (o.end_time is None or o.end_time > t))

    # ---- corrected decision instant -----------------------------------------
    events = []
    for c in fin:
        resc = sorted((o for o in c.orders
                       if o.is_grid and o.level is not None and is_rescue(o)),
                      key=lambda o: o.open_time)
        if not resc:
            continue
        slots: dict[tuple, list] = {}
        for o in c.orders:
            if o.is_grid and o.level is not None:
                slots.setdefault((o.side, o.level), []).append(o)
        for v in slots.values():
            v.sort(key=lambda o: o.open_time)

        trend = resc[0].side
        cancels = []
        kind = Counter()
        for o in resc:
            prev = [q for q in slots[(o.side, o.level)] if q.open_time < o.open_time]
            if not prev:
                kind["fresh"] += 1
                continue
            q = prev[-1]
            if q.state == "canceled":
                kind["cancel-replace"] += 1
                if q.end_time and o.side == trend:
                    cancels.append(q.end_time)
            elif q.state == "filled":
                kind["re-arm"] += 1
            else:
                kind[f"prior={q.state}"] += 1
        decision = min(cancels) if cancels else resc[0].open_time
        events.append((c, resc, trend, decision, kind, sorted(cancels)))

    # ------------------------------------------------------------------ panel A
    print("=" * 100)
    print("A. CORRECTED SNAPSHOT -- at the first cancel of a trend-side base pending")
    print("=" * 100)
    print(f"  {'cyc':>4} {'reg':<5} {'tr':>3} {'floating':>9} {'move':>7} "
          f"{'pendTREND':>9} {'pendOPP':>8} {'realized':>9} {'age':>6}  {'decision':<19} "
          f"{'lag to 1st 2x':>13}")
    snap = []
    for c, resc, trend, dec, kind, cancels in events:
        mark, age = price_at(dec)
        pc = prior_close(dec)
        fl = floating(c.positions, dec, mark)
        move = (mark - pc) if pc else float("nan")
        pt = base_pend(c, dec, trend)
        po = base_pend(c, dec, "S" if trend == "B" else "B")
        realized = sum(p.net for p in c.positions
                       if p.close_time and p.close_time <= dec)
        lag = (resc[0].open_time - dec).total_seconds()
        snap.append((c.index, fl, move, pt, po, trend))
        print(f"  {c.index:>4} {regime(dec):<5} {trend:>3} {fl:>9.2f} {move:>7.2f} "
              f"{pt:>9} {po:>8} {realized:>9.2f} {age:>6.0f}s  {str(dec)[:19]:<19} "
              f"{lag:>12.0f}s")

    print()
    print("  replica gate                     measured                       verdict")
    fls = [r[1] for r in snap]
    mvs = [abs(r[2]) for r in snap]
    pts = [r[3] for r in snap]
    print(f"  floating <= -400                 range {min(fls):.0f} .. {max(fls):.0f}"
          f"{'':<12} {'PASS' if max(fls) <= -400 else 'FAIL -- blocks ' + str(sum(1 for x in fls if x > -400)) + '/6'}")
    print(f"  |move| >= 20 (M15, 6 bars)       min {min(mvs):.2f}"
          f"{'':<21} {'PASS' if min(mvs) >= 19.5 else 'FAIL'}")
    print(f"  base pendings on trend side >= 3  min {min(pts)}, values "
          f"{','.join(str(x) for x in pts):<12} "
          f"{'PASS' if min(pts) >= 3 else 'FAIL -- blocks ' + str(sum(1 for x in pts if x < 3)) + '/6'}")

    # ------------------------------------------------------------------ panel B
    print()
    print("=" * 100)
    print("B. CANCEL SWEEP GEOMETRY -- one action per tick, cancels before placements")
    print("=" * 100)
    for c, resc, trend, dec, kind, cancels in events:
        print(f"  cycle {c.index:<4} trend={trend}  "
              + "  ".join(f"{k}={n}" for k, n in kind.most_common()))
        if len(cancels) > 1:
            gaps = [(b - a).total_seconds() for a, b in zip(cancels, cancels[1:])]
            print(f"       {len(cancels)} trend-side cancels over "
                  f"{(cancels[-1]-cancels[0]).total_seconds():.0f}s   "
                  f"gap median={statistics.median(gaps):.2f}s  "
                  f"min={min(gaps):.2f}  max={max(gaps):.2f}")

    # ------------------------------------------------------------------ panel C
    print()
    print("=" * 100)
    print("C. FALSIFIER HUNT -- what separates the 6 rescue cycles from the other 94?")
    print("=" * 100)
    fired = {c.index for c, *_ in events}

    # per-cycle worst-case feature vector, evaluated on the cycle's own print grid
    feats = {}
    for c in fin:
        grid = sorted({p.open_time for p in c.positions} |
                      {p.close_time for p in c.positions if p.close_time})
        best = None
        for g in grid:
            m, _ = price_at(g)
            pc = prior_close(g)
            if m is None or pc is None:
                continue
            mv = m - pc
            if abs(mv) < 20.0:
                continue
            trend = "B" if mv > 0 else "S"
            fl = floating(c.positions, g, m)
            pt = base_pend(c, g, trend)
            # rank candidate moments by how deep the drawdown is
            if best is None or fl < best[1]:
                best = (g, fl, abs(mv), pt, trend)
        feats[c.index] = best

    hit = [i for i in feats if feats[i]]
    print(f"  cycles where |move|>=20 ever held: {len(hit)} of {len(fin)}")
    print(f"  of those, rescue fired in {len(fired & set(hit))} "
          f"(all 6 present: {fired <= set(hit)})")
    print()
    print("  deepest floating at a |move|>=20 moment:")
    r_fl = sorted(feats[i][1] for i in fired if feats[i])
    n_fl = sorted(feats[i][1] for i in hit if i not in fired)
    print(f"    rescue cycles   n={len(r_fl):<3} " + " ".join(f"{x:.0f}" for x in r_fl))
    print(f"    non-rescue      n={len(n_fl):<3} min={n_fl[0]:.0f} "
          f"p10={n_fl[len(n_fl)//10]:.0f} median={statistics.median(n_fl):.0f}")
    print(f"    non-rescue cycles below the rescue max ({max(r_fl):.0f}): "
          f"{sum(1 for x in n_fl if x <= max(r_fl))}")

    print()
    print("  candidate gates conjoined with |move| >= 20, ranked by (misses, falsifiers):")
    cands = []
    for x in (0.0, 75.0, 150.0, 200.0, 250.0, 300.0, 350.0, 400.0):
        for k in (0, 3, 5, 8, 12, 99):
            ok = {i for i in hit
                  if feats[i][1] <= -x and feats[i][3] >= (k if k < 99 else 0)}
            cands.append((len(fired - ok), len(ok - fired),
                          f"floating<=-{x:.0f} AND pendTrend>={k if k<99 else 0}"))
    cands.sort()
    for miss, fals, lab in cands[:14]:
        print(f"    miss={miss}  falsifiers={fals:>3}   {lab}")


if __name__ == "__main__":
    main()
