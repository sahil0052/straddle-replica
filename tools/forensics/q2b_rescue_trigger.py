"""Q2b: the trend rescue trigger under the lead-time standard.

q2a produced the decision-instant snapshot for all 6 final-regime rescue events and
it refutes two of the replica's three activation conditions outright:

    floating at the decision:  -147  -356  -759  -78  -376  -383
    base pendings on the
    side being rescued:           0     0     0    3    15     0

  * trend_rescue_drawdown_money = 400 would have BLOCKED 6 of 6.  Nothing is at
    -400.  The shallowest event fired at -$78.
  * trend_rescue_minimum_pending_levels = 3 on the trend side would have BLOCKED
    4 of 6.  The rescued side is typically EXHAUSTED (0 base pendings left), which
    is the whole reason it needs rescuing.  The 3-pending gate at StraddleEngine
    line 2211 is inside the activation guard, so it kills the rescue in exactly
    the case the rescue exists for.

Only the move condition survived: |price - iClose(M15,6)| was
40.97 / -25.73 / -29.74 / 36.37 / 21.87 / -19.85 -- all six at or above 20 with the
minimum landing 0.15 off the threshold.

n = 6, so exhaustive case inspection beats statistics.  This script dumps every
event in full, then applies the two tests that coverage cannot fake:

  A  per-event forensics: mark staleness (how stale is the reconstructed price),
     the open-position ledger, realized-so-far, and whether each rescue order was
     a CANCEL-REPLACE (a base pending existed and was pulled) or a RE-ARM (the slot
     held a position that had closed).  That distinguishes the two code paths.
  B  first-fire lead time.  lead = decision_time - first_time_condition_true.
     lead ~ 0 admissible, lead >> 0 refuted.  Swept over thresholds.
  C  the move condition: sweep the M15 lookback and the threshold.
  D  falsifier test across all 100 cycles: where the condition went true and NO
     rescue fired.  A rule that fires 6 times cannot have a precondition that goes
     true 60 times without something else gating it.
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

    def price_at(t: datetime) -> tuple[float | None, float]:
        """(last print at or before t, its age in seconds)."""
        i = bisect_right(ptimes, t) - 1
        if i < 0:
            return None, float("inf")
        return pvals[i], (t - ptimes[i]).total_seconds()

    bars: dict[datetime, float] = {}
    for t, v in prints:
        bars[m15_floor(t)] = v
    bar_keys = sorted(bars)

    def prior_close(t: datetime, back: int) -> float | None:
        i = bisect_right(bar_keys, m15_floor(t) - back * M15) - 1
        return bars[bar_keys[i]] if i >= 0 else None

    def floating(pos, t: datetime, mark: float) -> float:
        return sum(p.dir * (mark - p.open_price) * p.volume * CONTRACT + p.swap
                   for p in pos
                   if p.open_time <= t and (p.close_time is None or p.close_time > t))

    fin = [c for c in cycles if c.start >= FINAL_REGIME_START]
    events = []
    for c in fin:
        r = sorted((o for o in c.orders
                    if o.is_grid and o.level is not None and is_rescue(o)),
                   key=lambda o: o.open_time)
        if r:
            events.append((c, r))

    # ------------------------------------------------------------------ panel A
    print("=" * 100)
    print("A. PER-EVENT FORENSICS -- all 6 rescue events in full")
    print("=" * 100)
    for c, resc in events:
        t = resc[0].open_time
        mark, age = price_at(t)
        openpos = [p for p in c.positions
                   if p.open_time <= t and (p.close_time is None or p.close_time > t)]
        realized = sum(p.net for p in c.positions
                       if p.close_time and p.close_time <= t)
        fl = floating(c.positions, t, mark)

        print(f"\n  --- cycle {c.index} ({regime(t)})  step={c.step:.2f}  "
              f"anchor={c.anchor:.2f}")
        print(f"      cycle {c.start} -> {c.end}")
        print(f"      first rescue order at {t}  side={resc[0].side} "
              f"L{resc[0].level} vol={resc[0].volume} @ {resc[0].price:.2f}")
        print(f"      mark={mark:.2f} (last print {age:.1f}s old)  "
              f"floating={fl:+.2f}  realized={realized:+.2f}  "
              f"net={fl+realized:+.2f}  open={len(openpos)}")

        # per-side floating: in a trend the losing side is the one being run over
        for sd, lab in (("B", "buy "), ("S", "sell")):
            sub = [p for p in openpos if p.grid_side == sd]
            if sub:
                f = sum(p.dir * (mark - p.open_price) * p.volume * CONTRACT + p.swap
                        for p in sub)
                print(f"        {lab} open n={len(sub):<3} floating={f:+9.2f}  "
                      f"levels=" + ",".join(str(p.level) for p in sorted(
                          sub, key=lambda x: x.level or 0)))

        # classify each rescue order: cancel-replace vs re-arm
        slots: dict[tuple[str, int], list] = {}
        for o in c.orders:
            if o.is_grid and o.level is not None:
                slots.setdefault((o.side, o.level), []).append(o)
        for v in slots.values():
            v.sort(key=lambda o: o.open_time)
        kind = Counter()
        for o in resc:
            seq = slots[(o.side, o.level)]
            prev = [q for q in seq if q.open_time < o.open_time]
            if not prev:
                kind["fresh(no prior order at slot)"] += 1
                continue
            q = prev[-1]
            if q.state == "cancelled":
                dt = (o.open_time - q.end_time).total_seconds() if q.end_time else -1
                kind[f"cancel-replace (dt<=5s)" if 0 <= dt <= 5.0
                     else "cancel-replace (later)"] += 1
            elif q.state == "filled":
                kind["re-arm (prior slot order FILLED)"] += 1
            else:
                kind[f"prior state={q.state}"] += 1
        print(f"      rescue orders n={len(resc)}  "
              f"filled={sum(1 for o in resc if o.state == 'filled')}")
        for k, n in kind.most_common():
            print(f"        {n:>3}  {k}")

    # ------------------------------------------------------------------ panel B
    print()
    print("=" * 100)
    print("B. FIRST-FIRE LEAD TIME -- floating threshold")
    print("=" * 100)
    print("  lead = decision - first moment floating was at or below -X.")
    print("  A threshold the EA actually uses has lead ~ 0 (it fires on the tick the")
    print("  condition turns true).  A large lead means the condition was true long")
    print("  before and something else was really deciding.")
    print()
    print(f"  {'-X':>6} {'fires':>6} {'blocked':>8}  lead seconds per event")
    for x in (50.0, 75.0, 100.0, 150.0, 200.0, 300.0, 350.0, 400.0):
        leads, blocked = [], 0
        for c, resc in events:
            t = resc[0].open_time
            grid = sorted({p.open_time for p in c.positions if p.open_time <= t} |
                          {p.close_time for p in c.positions
                           if p.close_time and p.close_time <= t})
            first = None
            for g in grid:
                m, _ = price_at(g)
                if m is None:
                    continue
                if floating(c.positions, g, m) <= -x:
                    first = g
                    break
            if first is None:
                blocked += 1
            else:
                leads.append((t - first).total_seconds())
        print(f"  {x:>6.0f} {len(leads):>6} {blocked:>8}  "
              + " ".join(f"{v/60:.0f}m" for v in leads))

    # ------------------------------------------------------------------ panel C
    print()
    print("=" * 100)
    print("C. MOVE CONDITION -- sweep the M15 lookback")
    print("=" * 100)
    print(f"  {'bars':>5} {'min|move|':>10} {'values at the 6 decision instants'}")
    for back in (2, 4, 6, 8, 10, 12, 16, 24):
        vals = []
        for c, resc in events:
            t = resc[0].open_time
            mark, _ = price_at(t)
            pc = prior_close(t, back)
            if mark is None or pc is None:
                continue
            vals.append(mark - pc)
        mn = min(abs(v) for v in vals) if vals else float("nan")
        star = "  <== all six clear 20" if mn >= 19.5 else ""
        print(f"  {back:>5} {mn:>10.2f}  "
              + " ".join(f"{v:+7.2f}" for v in vals) + star)

    # ------------------------------------------------------------------ panel D
    print()
    print("=" * 100)
    print("D. FALSIFIER TEST -- how often did each condition go true with NO rescue?")
    print("=" * 100)
    fired = {c.index for c, _ in events}
    for x in (20.0,):
        move_true, both_true = [], []
        for c in fin:
            grid = sorted({p.open_time for p in c.positions} |
                          {p.close_time for p in c.positions if p.close_time})
            hit_move = hit_both = False
            for g in grid:
                m, _ = price_at(g)
                pc = prior_close(g, 6)
                if m is None or pc is None:
                    continue
                if abs(m - pc) >= x:
                    hit_move = True
                    if floating(c.positions, g, m) <= -75.0:
                        hit_both = True
                        break
            if hit_move:
                move_true.append(c.index)
            if hit_both:
                both_true.append(c.index)
        print(f"  |move| >= {x:.0f} alone            : true in "
              f"{len(move_true):>3} of {len(fin)} cycles, rescue fired in "
              f"{len(fired)} -> {len(set(move_true) - fired)} falsifiers")
        print(f"  |move| >= {x:.0f} AND floating<=-75 : true in "
              f"{len(both_true):>3} of {len(fin)} cycles -> "
              f"{len(set(both_true) - fired)} falsifiers")
        miss = sorted(fired - set(both_true))
        if miss:
            print(f"  cycles that FIRED but the rule never went true: {miss}")


if __name__ == "__main__":
    main()
