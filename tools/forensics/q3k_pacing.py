"""Q3k: is the "second exit rule" just slow-flatten bleed?

The flatten is bimodal: some cycles liquidate the whole basket in a burst (~0.1s per
position), others pace one close per 20s timer tick.  A paced flatten of 12 positions
takes ~4 minutes, and at 40 $/point a 3-point drift during that window costs $120.

So a cycle whose EXACT sweep total lands at -$108 may not be a different exit rule at
all -- it may be a $30 target that fired and then bled out during a paced liquidation.

The quantity the EA tested is realized_before + floating AT THE FIRST CLOSE.  For a
burst flatten that equals the whole sweep's net.  For a paced flatten it does not, so
mark every swept position at the FIRST close's own price -- the one price that is
known exactly at the decision instant -- and compare.
"""
from __future__ import annotations

import statistics
import sys

sys.path.insert(0, r"C:\websites\mt5 2")
from tools.forensics.dataset import load_all, FINAL_REGIME_START, CONTRACT  # noqa: E402
from tools.forensics.attribution import build_exit_index, attribute  # noqa: E402

TARGET = 30.0


def stats(vals, label):
    if not vals:
        print(f"  {label:<34} n=0")
        return
    v = sorted(vals)
    g = lambda f: v[int(f * (len(v) - 1))]
    print(f"  {label:<34} n={len(v):<4} min={v[0]:>9.2f} p10={g(.1):>8.2f} "
          f"med={statistics.median(v):>8.2f} p75={g(.75):>8.2f} max={v[-1]:>9.2f}")


def main() -> None:
    orders, positions, deals, cycles = load_all()
    class_by_time, _, _ = build_exit_index(orders, deals)
    reason, _, _ = attribute(positions, class_by_time)

    live = [p for p in positions if p.open_time >= FINAL_REGIME_START
            or (p.close_time and p.close_time >= FINAL_REGIME_START)]

    rows = []
    for c in cycles:
        if c.start < FINAL_REGIME_START:
            continue
        S = c.start
        closes = [p for p in live if not p.is_open and p.close_time
                  and p.close_time >= S
                  and reason.get(p.position_id) == "STR CLOSE"]
        if not closes:
            continue
        first_close = min(p.close_time for p in closes)
        sweep = sorted((p for p in closes
                        if (p.close_time - first_close).total_seconds() <= 1800),
                       key=lambda p: p.close_time)
        run = [sweep[0]]
        for prev, cur in zip(sweep, sweep[1:]):
            if (cur.close_time - prev.close_time).total_seconds() <= 120.0:
                run.append(cur)
            else:
                break
        sweep = run
        span = (sweep[-1].close_time - first_close).total_seconds()

        realized_before = sum(p.net for p in live if not p.is_open and p.close_time
                              and S <= p.close_time < first_close)
        sweep_net = sum(p.net for p in sweep)

        # floating at the FIRST close, every swept position marked at that price
        mk = sweep[0].close_price
        floating_at = sum(p.dir * (mk - p.open_price) * p.volume * CONTRACT
                          for p in sweep)
        rows.append(dict(cyc=c.index, span=span, n=len(sweep),
                         per=span / max(1, len(sweep) - 1) if len(sweep) > 1 else 0.0,
                         realized_before=realized_before, sweep_net=sweep_net,
                         sweep_total=realized_before + sweep_net,
                         mark_total=realized_before + floating_at,
                         floating_at=floating_at,
                         bleed=sweep_net - floating_at,
                         dpp=sum(p.volume for p in sweep) * CONTRACT,
                         hrs=(first_close - S).total_seconds() / 3600.0))

    burst = [r for r in rows if r["per"] < 5.0]
    paced = [r for r in rows if r["per"] >= 5.0]
    print(f"cycles={len(rows)}   burst flattens={len(burst)}   paced flattens={len(paced)}")
    print(f"  seconds per close: burst med "
          f"{statistics.median([r['per'] for r in burst]):.2f}"
          f"   paced med {statistics.median([r['per'] for r in paced]):.2f}\n")

    print("=" * 100)
    print("A.  TOTAL SUMMED OVER THE WHOLE SWEEP  (what I measured before)")
    print("=" * 100)
    stats([r["sweep_total"] for r in burst], "burst flattens")
    stats([r["sweep_total"] for r in paced], "paced flattens")

    print("\n" + "=" * 100)
    print("B.  TOTAL MARKED AT THE FIRST CLOSE  (what the EA saw when it decided)")
    print("=" * 100)
    stats([r["mark_total"] for r in burst], "burst flattens")
    stats([r["mark_total"] for r in paced], "paced flattens")
    stats([r["mark_total"] for r in rows], "ALL cycles")
    e = [abs(r["mark_total"] - TARGET) for r in rows]
    print(f"\n  |marked total - 30| : med {statistics.median(e):.2f}   "
          f"<=$5 {sum(1 for x in e if x <= 5)}/{len(e)}   "
          f"<=$10 {sum(1 for x in e if x <= 10)}/{len(e)}   "
          f"<=$20 {sum(1 for x in e if x <= 20)}/{len(e)}")
    print(f"  marked total >= 28 : "
          f"{sum(1 for r in rows if r['mark_total'] >= 28)}/{len(rows)}")
    print(f"  marked total >= 25 : "
          f"{sum(1 for r in rows if r['mark_total'] >= 25)}/{len(rows)}")

    print("\n" + "=" * 100)
    print("C.  BLEED DURING THE SWEEP = sweep_net - floating_at_first_close")
    print("=" * 100)
    stats([r["bleed"] for r in burst], "burst flattens")
    stats([r["bleed"] for r in paced], "paced flattens")

    print("\n" + "=" * 100)
    print("D.  HISTOGRAM OF THE MARKED TOTAL -- the edge should sit at the target")
    print("=" * 100)
    v = sorted(r["mark_total"] for r in rows)
    for lo, hi in [(-10**9, -25), (-25, 0), (0, 10), (10, 20), (20, 25), (25, 28),
                   (28, 30), (30, 32), (32, 35), (35, 40), (40, 50), (50, 75),
                   (75, 10**9)]:
        n = sum(1 for x in v if lo <= x < hi)
        tag = f"[{lo if lo > -10**9 else '-inf':>5},{hi if hi < 10**9 else 'inf':>5})"
        print(f"    {tag:<15}{n:>4} {'#' * n}")

    print("\n" + "=" * 100)
    print("E.  CYCLES STILL BELOW THE TARGET AFTER MARKING AT THE DECISION")
    print("=" * 100)
    low = sorted((r for r in rows if r["mark_total"] < 25.0),
                 key=lambda r: r["mark_total"])
    print(f"  n={len(low)}/{len(rows)}")
    print(f"  {'cyc':>4} {'n':>3} {'s/close':>8} {'$/pt':>7} {'hrs':>6} "
          f"{'real_bef':>10} {'float_at':>10} {'marked':>9} {'sweep_tot':>10}")
    for r in low:
        print(f"  {r['cyc']:>4} {r['n']:>3} {r['per']:>8.2f} {r['dpp']:>7.1f} "
              f"{r['hrs']:>6.1f} {r['realized_before']:>10.2f} "
              f"{r['floating_at']:>10.2f} {r['mark_total']:>9.2f} "
              f"{r['sweep_total']:>10.2f}")


if __name__ == "__main__":
    main()
