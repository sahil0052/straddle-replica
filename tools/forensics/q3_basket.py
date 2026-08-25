"""Q3: the exact cycle/basket exit condition.

Candidate rules for triggering the flatten:
  (a) pure net basket target:      realized + floating >= 30.0
  (b) floating only:               floating >= 30.0
  (c) realized only:               realized >= 30.0
  (d) balance-percentage target:   realized + floating >= pct * balance
  (e) distance / level gates

Measurement: for every final-regime cycle find the FIRST `STR CLOSE` instant.
The close price of the position closed at that instant is a direct observation of
the market.  With that market price we can value every position still open, so
realized / floating / total are all computable at the trigger instant.  The rule
is whichever quantity is pinned at a constant across 100 cycles.
"""
from __future__ import annotations

import statistics
import sys
from collections import Counter, defaultdict

sys.path.insert(0, r"C:\websites\mt5 2")
from tools.forensics.dataset import load_all, FINAL_REGIME_START, CONTRACT  # noqa: E402
from tools.forensics.attribution import build_exit_index, attribute  # noqa: E402


def stats(vals, label, unit="$"):
    if not vals:
        print(f"  {label:<34} n=0")
        return
    v = sorted(vals)
    print(f"  {label:<34} n={len(v):<4} min={v[0]:>9.2f} p10={v[int(.1*(len(v)-1))]:>8.2f} "
          f"med={statistics.median(v):>8.2f} p90={v[int(.9*(len(v)-1))]:>8.2f} "
          f"max={v[-1]:>9.2f} sd={statistics.pstdev(v):>7.2f}")


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
        closes = [p for p in ps
                  if not p.is_open and p.close_time
                  and reason.get(p.position_id) == "STR CLOSE"]
        if not closes:
            continue
        first = min(closes, key=lambda p: p.close_time)
        t = first.close_time
        market = first.close_price
        realized = sum(p.net for p in ps
                       if not p.is_open and p.close_time and p.close_time < t)
        open_now = [p for p in ps if p.open_time <= t
                    and (p.is_open or (p.close_time and p.close_time >= t))]
        floating = 0.0
        for p in open_now:
            d = 1.0 if p.side == "buy" else -1.0
            floating += d * (market - p.open_price) * p.volume * CONTRACT
        # count of simultaneously-open positions and pendings still armed
        pend = sum(1 for o in c.orders
                   if o.is_grid and o.open_time <= t
                   and (o.state == "placed"
                        or (o.end_time and o.end_time > t)))
        rows.append(dict(cyc=c.index, t=t, market=market, step=c.step,
                         anchor=c.anchor, realized=realized, floating=floating,
                         total=realized + floating, nopen=len(open_now),
                         npend=pend, nclose=len(closes),
                         dist=abs(market - c.anchor) / (c.step or 1),
                         dur=(t - c.start).total_seconds() / 3600.0,
                         cycle_realized=c.realized))

    print(f"final-regime cycles with a basket close: {len(rows)}\n")
    print("=" * 78)
    print("CANDIDATE TRIGGER QUANTITIES AT THE FIRST `STR CLOSE` INSTANT")
    print("=" * 78)
    stats([r["realized"] for r in rows], "(c) realized at trigger")
    stats([r["floating"] for r in rows], "(b) floating at trigger")
    stats([r["total"] for r in rows], "(a) realized + floating")
    print()
    stats([r["nopen"] for r in rows], "open positions at trigger", "")
    stats([r["npend"] for r in rows], "armed pendings at trigger", "")
    stats([r["dist"] for r in rows], "|market-anchor| in steps", "")
    stats([r["dur"] for r in rows], "cycle age at trigger (hours)", "")

    # which quantity is most tightly pinned?  coefficient of variation
    print("\n  tightness (sd / |median|, lower = more likely the rule):")
    for key in ("realized", "floating", "total"):
        v = [r[key] for r in rows]
        med = statistics.median(v)
        sd = statistics.pstdev(v)
        print(f"    {key:<10} med={med:>9.2f} sd={sd:>8.2f} "
              f"cv={abs(sd/med) if med else float('inf'):>7.3f}")

    print("\n" + "=" * 78)
    print("PER-CYCLE DETAIL (all 100)")
    print("=" * 78)
    print(f"  {'cyc':>4} {'trigger time':<20} {'realized':>9} {'floating':>9} "
          f"{'total':>9} {'open':>5} {'pend':>5} {'nclose':>7} {'dist':>7} {'hrs':>6}")
    for r in sorted(rows, key=lambda r: r["cyc"]):
        print(f"  {r['cyc']:>4} {r['t'].strftime('%Y-%m-%d %H:%M:%S'):<20} "
              f"{r['realized']:>9.2f} {r['floating']:>9.2f} {r['total']:>9.2f} "
              f"{r['nopen']:>5} {r['npend']:>5} {r['nclose']:>7} "
              f"{r['dist']:>7.2f} {r['dur']:>6.1f}")

    # ---- does the total cluster on 30? -------------------------------------
    print("\n" + "=" * 78)
    print("IS THERE A $30 TARGET?")
    print("=" * 78)
    for key in ("total", "realized", "floating"):
        v = [r[key] for r in rows]
        print(f"  {key:<10} >=30: {sum(1 for x in v if x >= 30):>3}  "
              f"in[29,35]: {sum(1 for x in v if 29 <= x <= 35):>3}  "
              f"in[25,45]: {sum(1 for x in v if 25 <= x <= 45):>3}  "
              f"<0: {sum(1 for x in v if x < 0):>3}")
    tot = sorted(r["total"] for r in rows)
    print(f"\n  sorted totals: {[f'{x:.1f}' for x in tot]}")

    # ---- cycle-level realized outcome --------------------------------------
    print("\n" + "=" * 78)
    print("WHOLE-CYCLE REALIZED P/L (what the cycle actually banked)")
    print("=" * 78)
    cr = [r["cycle_realized"] for r in rows]
    stats(cr, "cycle realized total")
    print(f"  >=30: {sum(1 for x in cr if x >= 30)}  in[29,35]: "
          f"{sum(1 for x in cr if 29 <= x <= 35)}  <0: {sum(1 for x in cr if x < 0)}")
    print(f"  sorted: {[f'{x:.1f}' for x in sorted(cr)]}")


if __name__ == "__main__":
    main()
