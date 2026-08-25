"""The guard-halt class of divergence: do OUR safety limits fit the Target's actual envelope?

Every other question in this project asks "does the replica compute the same
number as the Target".  This one asks something worse: "is there a state the
Target reached in which the replica STOPS TRADING ALTOGETHER".  That is not a
1% divergence -- SafetyTriggered() calls BeginClose(reason, true), which sets
m_halted=true, flattens the basket and parks the EA in CYCLE_HALTED forever
(StraddleEngine.mqh:2838-2842, 2352-2363).  There is no automatic return.

A risk limit calibrated to the historical high-water mark is not a margin, it is
a tripwire.  So this script measures the Target's realised envelope against each
of the four guards in profiles/latest_30_real_safe.set and reports the headroom.

Two DIFFERENT behaviours share the max_gross_lots number, and they must not be
conflated:

  * ExposureAllowsRearm()  (2279-2288) : gross + volume <= limit.  Returns false
    -> the re-arm is silently NOT PLACED.  Recoverable, but it means the replica
    runs a SMALLER basket than the Target from that point in the cycle onward.
    Every subsequent fill, stop and the $30 target itself are then computed on a
    different basket.  This is a divergence generator, not a safety net.

  * SafetyTriggered()      (2331-2335) : gross > limit.  HALTS.

Because ExposureAllowsRearm gates re-arms at the same number, the halt path is
mostly reachable only through the deployment ladder and the rescue leg (see the
"max_gross_lots_rescue" reject reasons at 2149/2195).  So the FIRST thing to go
wrong SHOULD be silent basket truncation, and that is what Panel B counts exactly.

PREDICTION REFUTED, RECORDED HERE SO IT IS NOT RE-MADE.  An earlier version of
this docstring called that truncation "the largest single lever on replica
fidelity that is set by configuration rather than by code".  Panel B measures
0 of 3,441 fills refused at 2.20 -- and at 2.50, 3.00, 4.00 and 5.00 too.  It
never fires in this sample.  The real exposure is DailyLossLimit (Panel C), which
the Target walked straight through TWICE.  The loud guard was the dangerous one.

Balance comes from the deals ledger (DEAL "balance" column), so the equity-loss
percentage is measured against the real account size, not a guess.
"""
from __future__ import annotations

import statistics
import sys
from collections import defaultdict

sys.path.insert(0, r"C:\websites\mt5 2")
from tools.forensics.dataset import load_all, FINAL_REGIME_START  # noqa: E402

# profiles/latest_30_real_safe.set
LIM_GROSS = 2.20
LIM_DAILY = 500.0
LIM_EQPCT = 10.0
LIM_SPREAD = 1000.0
# mql5/include/StraddleReplicaApp.mqh compiled defaults (differ from the .set!)
DEF_GROSS, DEF_DAILY, DEF_EQPCT = 2.20, 0.0, 20.0


def main() -> None:
    _orders, positions, deals, cycles = load_all()
    fin = [c for c in cycles if c.start >= FINAL_REGIME_START]
    fin_idx = {c.index for c in fin}

    # ------------------------------------------------------------------ Panel A
    # Exposure timeline: +volume at open, -volume at close.  Ties broken so that
    # closes are applied BEFORE opens at the same timestamp -- that is the
    # conservative direction for a limit test (it lowers the running total), so
    # any peak we report is a real peak and not a tie artifact.
    ev: list[tuple] = []
    for p in positions:
        if p.cycle not in fin_idx:
            continue
        ev.append((p.open_time, 1, +p.volume, p.cycle))
        if p.close_time is not None and not p.is_open:
            ev.append((p.close_time, 0, -p.volume, p.cycle))
    ev.sort(key=lambda e: (e[0], e[1]))

    run = 0.0
    peak = 0.0
    peak_at = None
    peak_cyc = None
    per_cycle_peak: dict[int, float] = defaultdict(float)
    for t, _k, dv, cyc in ev:
        run = round(run + dv, 2)
        if run > peak:
            peak, peak_at, peak_cyc = run, t, cyc
        if run > per_cycle_peak[cyc]:
            per_cycle_peak[cyc] = run

    print("=" * 100)
    print("A. MaxGrossLots -- PEAK SIMULTANEOUS OPEN VOLUME")
    print("=" * 100)
    print(f"  guard in profiles/latest_30_real_safe.set : {LIM_GROSS:.2f} lots")
    print(f"  Target's peak simultaneous open volume    : {peak:.2f} lots"
          f"   (cycle {peak_cyc}, {peak_at})")
    head = LIM_GROSS - peak
    print(f"  headroom                                  : {head:+.2f} lots"
          f" = {100.0*head/LIM_GROSS:+.1f}% of the limit")
    pk = sorted(per_cycle_peak.values())
    print()
    print(f"  per-cycle peaks (n={len(pk)}) : median {statistics.median(pk):.2f}"
          f"   p90 {pk[9*len(pk)//10]:.2f}   max {pk[-1]:.2f}")
    for thr in (0.50, 0.25, 0.10, 0.00):
        k = sum(1 for v in pk if LIM_GROSS - v <= thr)
        print(f"    cycles whose peak came within {thr:.2f} lots of the limit :"
              f" {k:>3} / {len(pk)} = {100.0*k/len(pk):.0f}%")
    print()
    print("  A limit the Target's own history brushes against is a tripwire, not a")
    print("  margin.  Every lot of headroom here is a basket leg the replica is")
    print("  allowed to add that the Target added.")

    # ------------------------------------------------------------------ Panel B
    # How many of the Target's ACTUAL fills would ExposureAllowsRearm have
    # refused?  Replay the exposure timeline and, at each open, ask the guard's
    # own question: gross_before + volume <= limit ?
    print()
    print("=" * 100)
    print("B. ExposureAllowsRearm -- FILLS THE REPLICA WOULD HAVE SILENTLY REFUSED")
    print("=" * 100)
    for lim in (LIM_GROSS, 2.50, 3.00, 4.00, 5.00):
        run = 0.0
        refused = 0
        refused_cyc: set[int] = set()
        first_refusal_cycle_share = []
        n_open = 0
        for t, k, dv, cyc in ev:
            if k == 0:
                run = round(run + dv, 2)
                continue
            n_open += 1
            if round(run + dv, 2) > lim + 1e-7:
                refused += 1
                refused_cyc.add(cyc)
            run = round(run + dv, 2)
        tag = "  <- CURRENT" if abs(lim - LIM_GROSS) < 1e-9 else ""
        print(f"  limit {lim:.2f} lots : {refused:>4} of {n_open} fills refused"
              f" = {100.0*refused/n_open:5.2f}%"
              f"   affecting {len(refused_cyc):>3} cycles{tag}")
        _ = first_refusal_cycle_share
    print()
    print("  A refused leg is not a blocked loss -- it is a DIFFERENT BASKET.  The")
    print("  $30 target, the ratchet population and the flatten instant are all")
    print("  computed over whatever legs exist, so one missing leg changes the whole")
    print("  cycle's outcome.  That is why this was worth counting.")
    print()
    print("  But the count is ZERO at the current limit and at every larger one, so")
    print("  the mechanism I expected to dominate DOES NOT FIRE in this sample.  Do")
    print("  not cite silent truncation as the leading configuration risk -- Panel C")
    print("  is.  The 0.10 lots of headroom in Panel A is still the thing to fix,")
    print("  because it is one 0.15 leg away from the HALTING branch, not this one.")

    # ------------------------------------------------------------------ Panel C
    print()
    print("=" * 100)
    print("C. DailyLossLimit -- WORST *INTRADAY RUNNING* REALISED TOTAL")
    print("=" * 100)
    print("  TodayOwnedProfit() (2290-2315) sums DEAL_PROFIT+SWAP+COMMISSION+FEE for")
    print("  the magic+symbol from server midnight to now, and SafetyTriggered tests")
    print("  it on EVERY timer tick.  So the binding number is the worst running")
    print("  intraday value, not the day's closing P&L.  A day that ends +200 but")
    print("  dips to -600 mid-session still halts the EA permanently.")
    print()
    by_day: dict[object, list] = defaultdict(list)
    for d in deals:
        if d.time is None or d.time < FINAL_REGIME_START:
            continue
        if d.deal_type.lower() not in ("buy", "sell"):
            continue
        by_day[d.time.date()].append(d)
    rows = []
    for day, ds in sorted(by_day.items()):
        ds.sort(key=lambda d: (d.time, d.deal_id))
        acc = 0.0
        worst = 0.0
        for d in ds:
            acc += d.profit + d.swap + d.commission + d.fee
            worst = min(worst, acc)
        rows.append((day, worst, acc, len(ds)))
    print(f"  {'day':>12} {'worst running':>16} {'closed at':>12} {'deals':>7}")
    for day, worst, acc, n in rows:
        flag = "   <-- WOULD HALT" if worst <= -LIM_DAILY else ""
        print(f"  {str(day):>12} {worst:>16.2f} {acc:>12.2f} {n:>7}{flag}")
    ws = sorted(r[1] for r in rows)
    print()
    print(f"  guard in the .set file : {LIM_DAILY:.2f}"
          f"   (compiled default is {DEF_DAILY:.2f} = DISABLED)")
    print(f"  worst intraday running realised : {ws[0]:.2f}"
          f"   headroom {LIM_DAILY + ws[0]:+.2f}")
    trip = sum(1 for w in ws if w <= -LIM_DAILY)
    print(f"  days that would have halted the replica : {trip} / {len(ws)}")

    # Reconciliation with AGENTS.md SS.H, which recorded "-$499.78 (2026-07-06)"
    # -- a $0.22 near-miss.  That date is BEFORE FINAL_REGIME_START (2026-07-14),
    # so it came from the whole dataset, and it is the day's CLOSING total rather
    # than the running intraday minimum.  Both statistics are computed here so the
    # two figures can never look like a contradiction again.
    print()
    print("  --- reconciliation: two different statistics, two different windows ---")
    allday: dict[object, list] = defaultdict(list)
    for d in deals:
        if d.time is None or d.deal_type.lower() not in ("buy", "sell"):
            continue
        allday[d.time.date()].append(d)
    close_worst = (None, 0.0)
    run_worst = (None, 0.0)
    for day, ds in sorted(allday.items()):
        ds.sort(key=lambda d: (d.time, d.deal_id))
        acc = 0.0
        w = 0.0
        for d in ds:
            acc += d.profit + d.swap + d.commission + d.fee
            w = min(w, acc)
        if acc < close_worst[1]:
            close_worst = (day, acc)
        if w < run_worst[1]:
            run_worst = (day, w)
    print(f"  ALL-TIME worst day by CLOSING total   : {close_worst[1]:>9.2f}"
          f"  on {close_worst[0]}")
    print(f"  ALL-TIME worst day by RUNNING minimum : {run_worst[1]:>9.2f}"
          f"  on {run_worst[0]}")
    print(f"  FINAL-REGIME worst by RUNNING minimum : {ws[0]:>9.2f}")
    print("  The guard is polled every timer tick, so the RUNNING minimum is the one")
    print("  that binds.  A closing-total measurement understates the tripwire and")
    print("  must not be used to size this guard.")

    # ------------------------------------------------------------------ Panel D
    print()
    print("=" * 100)
    print("D. MaxEquityLossPercent -- REALISED DRAWDOWN, AND WHY THIS GUARD IS UNADJUDICATED")
    print("=" * 100)
    print("  The guard is 100*(cycle_start_balance - equity)/cycle_start_balance, and")
    print("  equity = balance + FLOATING.  An earlier version of this panel argued that")
    print("  running realised alone OVERSTATES the drawdown 'because floating is positive")
    print("  while the winner runs'.  That reasoning is WRONG and the number below must")
    print("  not be read as a bound.  In a straddle basket the dangerous instant is right")
    print("  after deployment, when MANY legs are underwater simultaneously and realised")
    print("  is still exactly zero -- floating is then large and negative, so true equity")
    print("  drawdown EXCEEDS realised drawdown.  This report carries no bid/ask series,")
    print("  so floating cannot be reconstructed and this guard cannot be adjudicated")
    print("  here.  AGENTS.md SS.H carries the mark-based figure ($1,043.86, cycle 253),")
    print("  which is the binding one and is WORSE than anything below -- consistent,")
    print("  since a mark-based peak can exceed the sum of settled losses.  SS.H also")
    print("  called it 'already exceeded at a $10k balance'; the balance actually")
    print("  observed at the worst cycles is $15.6k-$17.6k, so on the real account it")
    print("  is ~6-7%, i.e. UNDER the 10% limit.  Still unadjudicated, but not breached.")
    print()
    bal_ev = [(d.time, d.balance) for d in deals
              if d.time is not None and d.balance]
    bal_ev.sort()

    def balance_at(t) -> float | None:
        lo, hi = 0, len(bal_ev)
        while lo < hi:
            mid = (lo + hi) // 2
            if bal_ev[mid][0] <= t:
                lo = mid + 1
            else:
                hi = mid
        return bal_ev[lo - 1][1] if lo else None

    worst_rows = []
    for c in fin:
        cl = sorted((p for p in c.positions if p.close_time and not p.is_open),
                    key=lambda p: p.close_time)
        if not cl:
            continue
        b0 = balance_at(c.start)
        acc = 0.0
        worst = 0.0
        for p in cl:
            acc += p.net
            worst = min(worst, acc)
        # Every leg simultaneously at its own worst settled value.  Loose, and NOT
        # a strict bound (a flattened leg may have been worse mid-life than at its
        # close), but it is the right ORDER OF MAGNITUDE for the floating exposure
        # a straddle basket carries, and it needs no mark.
        gross_loss = sum(-p.net for p in cl if p.net < 0)
        if b0 and b0 > 0:
            worst_rows.append((c.index, worst, gross_loss, b0,
                               100.0 * (-worst) / b0, 100.0 * gross_loss / b0))
    worst_rows.sort(key=lambda r: -r[5])
    print(f"  {'cycle':>7} {'worst realised':>15} {'gross loss':>12}"
          f" {'balance':>11} {'real %':>8} {'gross %':>9}")
    for cyc, worst, gl, b0, pct, gpct in worst_rows[:8]:
        flag = "  <-- >limit" if gpct >= LIM_EQPCT else ""
        print(f"  {cyc:>7} {worst:>15.2f} {gl:>12.2f} {b0:>11.2f}"
              f" {pct:>7.2f}% {gpct:>8.2f}%{flag}")
    pcts = sorted(r[4] for r in worst_rows)
    gpcts = sorted(r[5] for r in worst_rows)
    print()
    print(f"  guard in the .set file : {LIM_EQPCT:.1f}%"
          f"   (compiled default is {DEF_EQPCT:.1f}%)")
    print(f"  worst REALISED-only drawdown   : {pcts[-1]:.2f}% of balance"
          f"   (median {statistics.median(pcts):.2f}%, n={len(pcts)})")
    print(f"  worst all-legs-at-worst figure : {gpcts[-1]:.2f}% of balance"
          f"   (median {statistics.median(gpcts):.2f}%)")
    trip = sum(1 for x in gpcts if x >= LIM_EQPCT)
    print(f"  cycles exceeding the limit on the pessimistic figure : {trip}"
          f" / {len(gpcts)}")
    if bal_ev:
        bl = [b for _t, b in bal_ev]
        print(f"  balance range over the final regime : {min(bl):.2f} .. {max(bl):.2f}")
        print()
        print("  NOTE the balance range: the account grew ~10x inside this window.")
        print("  MaxEquityLossPercent is proportional so it self-scales, but")
        print("  DailyLossLimit is ABSOLUTE -- $500 is 27% of the account at the start")
        print("  of the window and 2.5% at the end.  A fixed-dollar guard cannot be")
        print("  correctly sized across a 10x balance change.")

    print()
    print("=" * 100)
    print("E. MaxSpreadPoints")
    print("=" * 100)
    print(f"  guard : {LIM_SPREAD:.0f} points.  XAUUSD point = 0.01, so that is a"
          f" ${LIM_SPREAD*0.01:.2f} spread.")
    print("  The report carries no bid/ask series, so this is UNMEASURABLE here.")
    print("  It is also ~20-50x a normal gold spread, so it is not a live tripwire;")
    print("  it only fires in a genuine liquidity hole, which is what it is for.")
    print("  Leave it alone.  Unlike the other three, this guard is correctly sized.")


if __name__ == "__main__":
    main()
