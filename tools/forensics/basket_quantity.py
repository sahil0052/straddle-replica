"""What EXACTLY does the Target EA's $30 basket check sum?

Panel A closed the ledger but opened a new question: 63.6% of cycles net >= +25
(median right on the target) yet 31.3% land in (-25,+25).  Cycle detection is not
the cause -- every band is 60/60 keys.  So either the rule is not $30, or the
quantity it is evaluated on is not the quantity that ends up realised.

The replica's trigger quantity is asymmetric in commission:

    m_cycle_realized  = SUM(deal_profit + deal_swap + deal_commission + deal_fee)
    OwnedFloatingProfit = SUM(POSITION_PROFIT + POSITION_SWAP)     <-- no commission
    cycle_net = m_cycle_realized + floating

On a hedging account the broker charges commission on the ENTRY deal, so an open
position already carries a paid, non-zero POSITION_COMMISSION.  Excluding it makes
the trigger optimistic by the whole open basket's entry commission -- and the
basket rule governs 64.5% of the |money| in the ledger, so a few dollars of bias
here is worth more than every rescue parameter combined.

This measures the Target's trigger quantity directly.  The flatten instant is
exact and needs no heuristic: it is the first 'STR CLOSE' order the EA sent in
that cycle.  Reconstruct, at that instant, each candidate definition and see which
one lands on 30.  The winner should sit just barely above 30 with a tight spread,
because the EA re-checks every 100 ms.

    T_profit  = R_full + F_profit                      (no swap, no commission)
    T_replica = R_full + F_profit + F_swap              (what the replica computes)
    T_all     = R_full + F_profit + F_swap + F_comm     (fully cost-loaded)

R_full is realised profit+commission+swap of everything already closed, which is
what the replica's deal ledger accumulates.
"""
from __future__ import annotations

import statistics
import sys

sys.path.insert(0, r"C:\websites\mt5 2")
from tools.forensics.dataset import load_all, FINAL_REGIME_START, CONTRACT  # noqa: E402


def main() -> None:
    orders, positions, deals, cycles = load_all()
    fin = [c for c in cycles if c.start >= FINAL_REGIME_START]

    rows = []
    no_sweep = []
    for c in fin:
        cl = [o.open_time for o in c.orders
              if o.comment and o.comment.strip().upper().startswith("STR CLOSE")]
        if not cl:
            no_sweep.append(c.index)
            continue
        t0 = min(cl)

        before = [p for p in c.positions
                  if not p.is_open and p.close_time and p.close_time < t0]
        live = [p for p in c.positions
                if p.open_time <= t0 and (p.is_open or
                                          (p.close_time and p.close_time >= t0))]
        if not live:
            no_sweep.append(c.index)
            continue

        # mark at t0: close price of the earliest-closing live position
        swept = sorted((p for p in live if p.close_time and p.close_price),
                       key=lambda p: p.close_time)
        if not swept:
            no_sweep.append(c.index)
            continue
        mark = swept[0].close_price

        r_full = sum(p.net for p in before)
        f_profit = sum(p.dir * (mark - p.open_price) * p.volume * CONTRACT
                       for p in live)
        f_swap = sum(p.swap for p in live)
        f_comm = sum(p.commission for p in live)

        rows.append(dict(
            i=c.index, n_live=len(live), n_before=len(before),
            r_full=r_full, f_profit=f_profit, f_swap=f_swap, f_comm=f_comm,
            t_profit=r_full + f_profit,
            t_replica=r_full + f_profit + f_swap,
            t_all=r_full + f_profit + f_swap + f_comm,
            final=c.realized,
            vol=sum(p.volume for p in live),
        ))

    print("=" * 104)
    print("A. WHICH QUANTITY EQUALS 30 AT THE FLATTEN INSTANT?")
    print("=" * 104)
    print(f"  cycles with a reconstructable flatten: {len(rows)}"
          f"   (skipped {len(no_sweep)}: {no_sweep})")
    print()
    print(f"  {'definition':<42} {'median':>9} {'mean':>9} {'stdev':>8} "
          f"{'>=30':>7} {'in [29,33]':>11}")
    for key, lab in (("t_profit", "R + profit                 (no swap/comm)"),
                     ("t_replica", "R + profit + swap          (REPLICA)"),
                     ("t_all", "R + profit + swap + comm   (all costs)")):
        v = [r[key] for r in rows]
        ge = sum(1 for x in v if x >= 29.995)
        band = sum(1 for x in v if 29.0 <= x <= 33.0)
        print(f"  {lab:<42} {statistics.median(v):>9.2f} "
              f"{statistics.mean(v):>9.2f} {statistics.pstdev(v):>8.2f} "
              f"{ge:>4}/{len(v)} {band:>8}/{len(v)}")

    print()
    print("  The EA re-checks every 100 ms, so the true quantity must be >= 30 and")
    print("  only barely over it.  A definition that lands BELOW 30 on most cycles is")
    print("  not the one being tested; a definition far ABOVE 30 is missing a cost.")

    # ---------------------------------------------------------------- panel B
    print()
    print("=" * 104)
    print("B. COMMISSION IS THE WHOLE STORY?  how big is the open basket's commission")
    print("=" * 104)
    cm = [-r["f_comm"] for r in rows]
    sw = [-r["f_swap"] for r in rows]
    print(f"  open-basket commission at flatten:  median ${statistics.median(cm):.2f}"
          f"   max ${max(cm):.2f}   total ${sum(cm):.2f}")
    print(f"  open-basket swap       at flatten:  median ${statistics.median(sw):.2f}"
          f"   max ${max(sw):.2f}   total ${sum(sw):.2f}")
    print()
    print("  If the replica omits commission from floating it exits when the")
    print("  cost-loaded value is only 30 - commission, i.e. it takes profit EARLY by")
    print(f"  a median of ${statistics.median(cm):.2f} per cycle, {len(rows)} cycles"
          f" = ${sum(cm):.2f} over the window.")

    # ---------------------------------------------------------------- panel C
    print()
    print("=" * 104)
    print("C. WHY DOES THE FINAL NET MISS 30?  trigger value vs what was realised")
    print("=" * 104)
    print("  slip = final cycle net - trigger value.  It is the cost of ACTUALLY")
    print("  closing: spread crossed on each market close, plus any adverse move")
    print("  during a paced 20 s/close sweep.")
    print()
    best = "t_all" if abs(statistics.median([r["t_all"] for r in rows]) - 30) < \
        abs(statistics.median([r["t_replica"] for r in rows]) - 30) else "t_replica"
    slip = [(r["final"] - r[best], r) for r in rows]
    sv = [s for s, _ in slip]
    print(f"  using {best} as the trigger value:")
    print(f"    slip: median ${statistics.median(sv):.2f}  mean ${statistics.mean(sv):.2f}"
          f"  min ${min(sv):.2f}  max ${max(sv):.2f}")
    print()
    print(f"  {'positions in sweep':<22} {'n':>4} {'median slip':>12} {'median final':>13}")
    for lo, hi in ((1, 5), (6, 10), (11, 20), (21, 40), (41, 999)):
        sub = [(s, r) for s, r in slip if lo <= r["n_live"] <= hi]
        if not sub:
            continue
        print(f"  {f'{lo}-{hi}':<22} {len(sub):>4} "
              f"{statistics.median([s for s,_ in sub]):>12.2f} "
              f"{statistics.median([r['final'] for _,r in sub]):>13.2f}")
    print()
    print("  the 12 worst slips:")
    print(f"  {'cyc':>5} {'trigger':>9} {'final':>9} {'slip':>9} {'live':>5} "
          f"{'vol':>7} {'comm':>8} {'swap':>9}")
    for s, r in sorted(slip)[:12]:
        print(f"  {r['i']:>5} {r[best]:>9.2f} {r['final']:>9.2f} {s:>9.2f} "
              f"{r['n_live']:>5} {r['vol']:>7.2f} {r['f_comm']:>8.2f} "
              f"{r['f_swap']:>9.2f}")


if __name__ == "__main__":
    main()
