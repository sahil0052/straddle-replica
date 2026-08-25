"""Q3d: the exact basket total, with ZERO price interpolation.

Every previous attempt had to guess the market price at the decision instant in
order to value the open leg.  That guess is worth +/-$30 when the basket carries
$170/point.

But the EA liquidates the whole basket at market.  So the floating leg it saw is
*exactly* the net it went on to realise -- provided the liquidation is fast enough
that the market did not move during it.  Then

    total_seen  =  realized before the decision  +  net of the flatten itself
                =  the cycle's whole realized P/L        (no interpolation!)

Flatten span is bimodal (p25 0.81s, p75 120s): some flattens rip through at
0.13s/position, others are paced one position per 20s timer tick.  Restricting to
the fast ones gives an essentially exact reading of the threshold.
"""
from __future__ import annotations

import statistics
import sys
from collections import Counter, defaultdict

sys.path.insert(0, r"C:\websites\mt5 2")
from tools.forensics.dataset import load_all, FINAL_REGIME_START  # noqa: E402
from tools.forensics.attribution import build_exit_index, attribute  # noqa: E402


def stats(vals, label):
    if not vals:
        print(f"  {label:<26} n=0")
        return
    v = sorted(vals)
    g = lambda f: v[int(f * (len(v) - 1))]
    print(f"  {label:<26} n={len(v):<4} min={v[0]:>8.2f} p05={g(.05):>7.2f} "
          f"p10={g(.1):>7.2f} p25={g(.25):>7.2f} med={statistics.median(v):>7.2f} "
          f"p75={g(.75):>7.2f} p90={g(.9):>8.2f} max={v[-1]:>9.2f}")


def main() -> None:
    orders, positions, deals, cycles = load_all()
    class_by_time, _, _ = build_exit_index(orders, deals)
    reason, _, _ = attribute(positions, class_by_time)

    pos_by_cycle = defaultdict(list)
    for p in positions:
        if p.cycle >= 0:
            pos_by_cycle[p.cycle].append(p)

    rows = []
    for c in cycles:
        if c.start < FINAL_REGIME_START:
            continue
        ps = pos_by_cycle.get(c.index, [])
        closes = [p for p in ps if not p.is_open and p.close_time
                  and reason.get(p.position_id) == "STR CLOSE"]
        if not closes:
            continue
        first = min(p.close_time for p in closes)
        last = max(p.close_time for p in closes)
        span = (last - first).total_seconds()
        leftover = sum(1 for p in ps if p.is_open)
        # every position of this cycle, closed by any means
        realized_before = sum(p.net for p in ps
                              if not p.is_open and p.close_time and p.close_time < first)
        flatten_net = sum(p.net for p in closes)
        # positions stopped out DURING the flatten window (rare)
        during = [p for p in ps if not p.is_open and p.close_time
                  and first <= p.close_time <= last
                  and reason.get(p.position_id) == "sl"]
        during_net = sum(p.net for p in during)
        total = realized_before + flatten_net + during_net
        rows.append(dict(cyc=c.index, first=first, span=span, n=len(closes),
                         leftover=leftover, before=realized_before,
                         flat=flatten_net, during=during_net, nduring=len(during),
                         total=total,
                         per=span / max(1, len(closes) - 1)))

    print(f"cycles: {len(rows)}\n")
    print("=" * 92)
    print("FLATTEN PACING (bimodal: burst vs one-per-timer-tick)")
    print("=" * 92)
    per = Counter()
    for r in rows:
        per["burst (<1s/pos)" if r["per"] < 1 else
            "timer (~20s/pos)" if 15 <= r["per"] <= 25 else
            f"other ({r['per']:.0f}s/pos)"] += 1
    for k, n in per.most_common():
        print(f"  {k:<22} {n}")

    fast = [r for r in rows if r["span"] <= 5.0]
    slow = [r for r in rows if r["span"] > 5.0]

    print("\n" + "=" * 92)
    print(f"BASKET TOTAL AT THE DECISION -- FAST FLATTENS ONLY (span<=5s, n={len(fast)})")
    print("   this is an exact reconstruction: no market price is estimated")
    print("=" * 92)
    stats([r["total"] for r in fast], "total the EA saw")
    stats([r["before"] for r in fast], "  realized before")
    stats([r["flat"] for r in fast], "  net of the flatten")
    v = sorted(r["total"] for r in fast)
    print(f"\n  >=30.00 : {sum(1 for x in v if x >= 30.0):>3}/{len(v)}")
    print(f"  >=29.50 : {sum(1 for x in v if x >= 29.5):>3}/{len(v)}")
    print(f"  >=28.00 : {sum(1 for x in v if x >= 28.0):>3}/{len(v)}")
    print(f"  <28.00  : {sum(1 for x in v if x < 28.0):>3}/{len(v)}")
    print(f"\n  sorted totals:\n   {[f'{x:.2f}' for x in v]}")

    print("\n" + "=" * 92)
    print(f"SLOW / TIMER-PACED FLATTENS (span>5s, n={len(slow)})")
    print("   market drifts during liquidation, so the banked total drifts too")
    print("=" * 92)
    stats([r["total"] for x, r in enumerate(slow)], "total banked")
    stats([r["span"] for r in slow], "span (s)")
    v2 = sorted(r["total"] for r in slow)
    print(f"  >=30: {sum(1 for x in v2 if x >= 30)}/{len(v2)}   "
          f"<28: {sum(1 for x in v2 if x < 28)}/{len(v2)}")
    print(f"  sorted totals:\n   {[f'{x:.2f}' for x in v2]}")

    print("\n" + "=" * 92)
    print("PER-CYCLE, FAST FLATTENS, SORTED BY TOTAL")
    print("=" * 92)
    print(f"  {'cyc':>4} {'first close':<20} {'span':>7} {'n':>3} {'per':>6} "
          f"{'before':>9} {'flatten':>9} {'during':>8} {'TOTAL':>8} {'left':>5}")
    for r in sorted(fast, key=lambda r: r["total"]):
        print(f"  {r['cyc']:>4} {r['first'].strftime('%m-%d %H:%M:%S'):<20} "
              f"{r['span']:>7.2f} {r['n']:>3} {r['per']:>6.2f} "
              f"{r['before']:>9.2f} {r['flat']:>9.2f} {r['during']:>8.2f} "
              f"{r['total']:>8.2f} {r['leftover']:>5}")


if __name__ == "__main__":
    main()
