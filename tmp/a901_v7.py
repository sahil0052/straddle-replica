"""V7 adjudication: the basket money exit evaluator, on the 901018 tape.

The EA's predicate (mql5/include/BasketEvaluator.mqh) is

    net       = realized + floating
    triggered = has_traded && open_positions > 0 && target > 0 && net >= target

and the target itself is era-scoped (mql5/include/ProfileCatalog.mqh):

    HISTORICAL_50   cycle_target_balance_pct = 0.63
    HISTORICAL_60   cycle_target_balance_pct = 0.42
    AGGRESSIVE_30   inherits the default        0.18
    LOW_RISK_30     inherits the default        0.18
    STARWAVE_30     cycle_target_money       = 26.50   <-- under adjudication
    LATEST_30       cycle_target_money       = 30.00   <-- the rival reading

Four questions, each with its own instrument:

  (0) INSTRUMENT BIAS.  tmp/a901_v4578.py sums row["profit"] only.  The EA sums
      deal_profit + deal_swap + deal_commission + deal_fee
      (StraddleEngine.mqh:3685-3691).  The positions table carries Commission
      (col 10) and Swap (col 11) separately, so the bias is measurable, and it
      matters: every threshold estimate below is a sum over 6-54 legs.

  (1..4) WHICH LAW.  A percent-of-balance target and a flat-money target are
      distinguishable whenever the balance MOVED inside an era: under the pct
      law the money banked at the exit scales with the balance and the implied
      pct is flat; under the flat law the money is flat and the implied pct
      falls as the balance climbs.  Both are one-sided (overshoot is unbounded,
      undershoot is not), so the LOWER ENVELOPE -- not the median -- is the
      estimator that tracks the threshold.

  (5) THE GATE.  open_positions>0 is proved POSITIVELY, not by absence: find
      instants inside a live cycle where the open count returns to zero while
      the money already banked exceeds that cycle's target, and the cycle did
      NOT liquidate.  Without the gate, net = realized + 0 >= target would have
      fired BeginClose there and the cycle would have ended.

  (6) THE RESET.  A cumulative m_cycle_realized has a sharp signature: once any
      cycle banks more than the target, every later cycle trips on its first
      fill, so every later terminal sweep is a SINGLETON and the realized
      series is monotone non-decreasing.  Both are checked.
"""
from __future__ import annotations

import collections
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from a901_eras import norm, stamp  # noqa: E402
from a901_v4578 import (  # noqa: E402
    build_deployments, build_sweeps, cancel_times, classify_sweeps, eras_present,
    is_sl_exit, load_deals, load_orders, pct,
)

# ProfileCatalog.mqh, verbatim.  None = no configured law for that era.
TARGET_PCT = {
    "HISTORICAL_50": 0.63,   # ProfileCatalog.mqh:71
    "HISTORICAL_60": 0.42,   # ProfileCatalog.mqh:143
    "AGGRESSIVE_30": 0.18,   # inherited default, ProfileCatalog.mqh:29
    "LOW_RISK_30": 0.18,     # inherited default, ProfileCatalog.mqh:29
}
TARGET_MONEY = {
    "STARWAVE_30": 26.50,    # ProfileCatalog.mqh:478
}
RIVAL_MONEY = {
    "STARWAVE_30": 30.00,    # LATEST_30, ProfileCatalog.mqh:315
}


def load_positions_full():
    """Same positional read as a901_v4578.load_positions(), but keeping the
    Commission (10) and Swap (11) columns the EA's accumulator includes."""
    rows = []
    with Path("tmp/r901018_positions.csv").open(encoding="utf-8") as handle:
        reader = csv.reader(handle)
        next(reader)
        for row in reader:
            if len(row) < 13 or not norm(row[1]):
                continue
            opened, closed = stamp(row[0]), stamp(row[8])
            if opened is None or closed is None:
                continue
            profit = float(norm(row[12]))
            commission = float(norm(row[10])) if norm(row[10]) else 0.0
            swap = float(norm(row[11])) if norm(row[11]) else 0.0
            rows.append({
                "opened": opened,
                "ticket": int(norm(row[1])),
                "is_buy": norm(row[3]) == "buy",
                "volume": float(norm(row[4])),
                "open_price": float(norm(row[5])),
                "sl": float(norm(row[6])) if norm(row[6]) else 0.0,
                "closed": closed,
                "close_price": float(norm(row[9])),
                "profit": profit,
                "commission": commission,
                "swap": swap,
                "net": profit + commission + swap,
            })
    rows.sort(key=lambda item: (item["closed"], item["ticket"]))
    return rows


def balance_series(deals):
    """The broker's own running balance, (time, balance) after every deal."""
    out = []
    cash = []
    for row in deals:
        when = stamp(row["Time"])
        raw = norm(row["Balance"])
        if when is None or raw == "":
            continue
        out.append((when, float(raw)))
        if norm(row["Type"]) == "balance":
            cash.append((when, float(norm(row["Profit"]) or 0.0),
                         norm(row["Comment"])))
    out.sort(key=lambda item: item[0])
    return out, cash


def balance_at(series, when):
    """Last running balance at or before `when` -- what ACCOUNT_BALANCE would
    have returned to StartCycle()."""
    lo, hi = 0, len(series)
    while lo < hi:
        mid = (lo + hi) // 2
        if series[mid][0] <= when:
            lo = mid + 1
        else:
            hi = mid
    return series[lo - 1][1] if lo > 0 else None


def theil_sen(points, min_dx):
    """Median pairwise slope, restricted to pairs with enough x separation."""
    slopes = []
    for i in range(len(points)):
        xi, yi = points[i]
        for j in range(i + 1, len(points)):
            xj, yj = points[j]
            if abs(xj - xi) >= min_dx:
                slopes.append((yj - yi) / (xj - xi))
    if not slopes:
        return float("nan"), 0
    return pct(slopes, 0.50), len(slopes)


def main() -> int:
    orders = load_orders()
    deals = load_deals()
    positions = load_positions_full()
    deployments = build_deployments(orders)
    sweeps = build_sweeps(orders)
    terminal, interim, silent = classify_sweeps(sweeps, deployments)
    series, cash = balance_series(deals)
    print(f"deployments={len(deployments)} terminal={len(terminal)} "
          f"interim={len(interim)} silent={len(silent)} positions={len(positions)} "
          f"balance_points={len(series)} cash_events={len(cash)}")
    print()

    # ---- PART 0: the instrument bias in my own earlier probe ----------------
    print("=== PART 0: realized instrument -- profit-only vs the EA's sum ===")
    print("  EA: m_cycle_realized += deal_profit+deal_swap+deal_commission+deal_fee")
    print("      (StraddleEngine.mqh:3685-3691)")
    tot_p = sum(row["profit"] for row in positions)
    tot_c = sum(row["commission"] for row in positions)
    tot_s = sum(row["swap"] for row in positions)
    nz_c = sum(1 for row in positions if row["commission"] != 0.0)
    nz_s = sum(1 for row in positions if row["swap"] != 0.0)
    print(f"  whole tape  profit={tot_p:12.2f}  commission={tot_c:10.2f} "
          f"(nonzero {nz_c}/{len(positions)})  swap={tot_s:10.2f} "
          f"(nonzero {nz_s}/{len(positions)})")
    print(f"  net total   {tot_p + tot_c + tot_s:12.2f}   "
          f"bias per position p50={pct([r['commission'] + r['swap'] for r in positions], 0.50):+.4f}")
    print()

    # ---- PART 1: the balance trajectory ------------------------------------
    print("=== PART 1: broker running balance, and the deposits that move it ===")
    for when, amount, comment in cash:
        print(f"  {when}  {amount:+10.2f}  {comment}")
    print(f"  balance first={series[0][1]:.2f} last={series[-1][1]:.2f} "
          f"min={min(b for _, b in series):.2f} max={max(b for _, b in series):.2f}")
    print()

    # ---- build the per-sweep record ----------------------------------------
    records = collections.defaultdict(list)
    for sweep, cycle in terminal:
        if cycle is None:
            continue
        first, last = sweep[0]["when"], sweep[-1]["when"]
        era = str(cycle["assigned"])
        inside = [row for row in positions if cycle["when"] <= row["closed"] <= last]
        bal = balance_at(series, cycle["when"])
        records[era].append({
            "when": cycle["when"], "first": first, "last": last,
            "legs": len(sweep),
            "profit": sum(row["profit"] for row in inside),
            "net": sum(row["net"] for row in inside),
            "balance": bal,
        })

    # ---- PART 2: what the bias does to the threshold estimates -------------
    print("=== PART 2: realized at sweep completion, both instruments ===")
    print("  era              n   profit-only p50   EA-net p50    delta p50   "
          "delta p05    worst")
    for era in eras_present(records):
        rows = records[era]
        pr = [r["profit"] for r in rows]
        nt = [r["net"] for r in rows]
        dl = [r["net"] - r["profit"] for r in rows]
        print(f"  {era:14s}{len(rows):4d} {pct(pr, 0.50):15.2f} "
              f"{pct(nt, 0.50):13.2f} {pct(dl, 0.50):12.2f} "
              f"{pct(dl, 0.05):11.2f} {min(dl):8.2f}")
    print()

    # ---- PART 3: which law?  balance range decides the test's power --------
    print("=== PART 3: pct law vs flat law ===")
    print("  the two are only distinguishable when the balance MOVED inside the era")
    for era in eras_present(records):
        rows = [r for r in records[era] if r["balance"]]
        if len(rows) < 4:
            print(f"  {era:14s} n={len(rows)} -- too few sweeps to discriminate")
            continue
        bals = [r["balance"] for r in rows]
        lo, hi = min(bals), max(bals)
        cfg_pct = TARGET_PCT.get(era)
        cfg_money = TARGET_MONEY.get(era)
        span = hi / lo if lo > 0 else float("nan")
        print(f"  {era:14s} n={len(rows)}  balance {lo:.2f} -> {hi:.2f} "
              f"(x{span:.2f})  configured "
              f"{'pct=' + format(cfg_pct, '.2f') + '%' if cfg_pct else ''}"
              f"{'money=$' + format(cfg_money, '.2f') if cfg_money else ''}")
        imp = [100.0 * r["net"] / r["balance"] for r in rows]
        nt = [r["net"] for r in rows]
        for name, values, unit in (("money  ", nt, "$"), ("implied", imp, "%")):
            p10, p25, p50 = pct(values, 0.10), pct(values, 0.25), pct(values, 0.50)
            iqr = pct(values, 0.75) - p25
            print(f"      {name} p05={pct(values, 0.05):9.3f} p10={p10:9.3f} "
                  f"p25={p25:9.3f} p50={p50:9.3f}  IQR/p50="
                  f"{(iqr / p50 if p50 else float('nan')):6.3f}  [{unit}]")
        slope, npairs = theil_sen([(r["balance"], r["net"]) for r in rows],
                                  min_dx=0.05 * lo)
        print(f"      Theil-Sen d(money)/d(balance) = {slope:+.6f} "
              f"=> implied pct {100.0 * slope:+.4f}%  over {npairs} pairs "
              f"(pct law predicts "
              f"{format(cfg_pct, '+.4f') + '%' if cfg_pct else '+0.0000% (flat)'})")
    print()

    # ---- PART 4: threshold detection by the pile's LEFT EDGE ----------------
    print("=== PART 4: threshold detection -- histogram of money banked ===")
    print("  a floor law piles the distribution up against the target from above;")
    print("  the left edge of the pile is the threshold, the tail below it is")
    print("  sweep slippage.  1-dollar bins.")
    for era in eras_present(records):
        rows = records[era]
        if len(rows) < 4:
            continue
        cfg_money = TARGET_MONEY.get(era)
        cfg_pct = TARGET_PCT.get(era)
        print(f"  -- {era}   configured "
              f"{'$' + format(cfg_money, '.2f') if cfg_money else format(cfg_pct, '.2f') + '%'}")
        hist = collections.Counter()
        for r in rows:
            hist[int(r["net"] // 1.0)] += 1
        for edge in range(15, 45):
            n = hist.get(edge, 0)
            if n or 20 <= edge <= 36:
                print(f"      [{edge:3d},{edge + 1:3d})  {n:3d}  {'#' * n}")
        below = sum(1 for r in rows if r["net"] < 0.0)
        print(f"      n={len(rows)}  negative={below}  "
              f"<20={sum(1 for r in rows if 0 <= r['net'] < 20)}  "
              f"[20,26.5)={sum(1 for r in rows if 20 <= r['net'] < 26.5)}  "
              f"[26.5,30)={sum(1 for r in rows if 26.5 <= r['net'] < 30)}  "
              f">=30={sum(1 for r in rows if r['net'] >= 30)}")
        if cfg_money:
            rival = RIVAL_MONEY[era]
            for cand in (cfg_money, rival):
                short = [r["net"] for r in rows if 0.0 <= r["net"] < cand]
                print(f"      candidate ${cand:6.2f}: "
                      f"{len(rows) - len(short) - below}/{len(rows)} at-or-above, "
                      f"{len(short)} short-but-positive"
                      f"{'' if not short else ' (p50 shortfall ' + format(cand - pct(short, 0.50), '.2f') + ')'}")
    print()

    # ---- PART 5: POSITIVE evidence for the open_positions>0 gate -----------
    print("=== PART 5: the open_positions>0 gate, proved positively ===")
    print("  an instant inside a live cycle where the open count returns to ZERO")
    print("  while the money already banked exceeds that cycle's target, and the")
    print("  cycle did NOT liquidate.  Ungated, net=realized+0>=target fires")
    print("  BeginClose there and the cycle ends.")
    starts = [record["when"] for record in deployments]
    terminal_first = {}
    for sweep, cycle in terminal:
        if cycle is not None:
            terminal_first[cycle["when"]] = sweep[0]["when"]
    per_cycle = collections.defaultdict(list)
    for row in positions:
        index = -1
        for i, when in enumerate(starts):
            if when <= row["opened"]:
                index = i
            else:
                break
        if index >= 0:
            per_cycle[index].append(row)
    proofs = collections.Counter()
    cycles_with = collections.Counter()
    examples = []
    for index, rows in sorted(per_cycle.items()):
        cycle = deployments[index]
        era = str(cycle["assigned"])
        bal = balance_at(series, cycle["when"])
        if era in TARGET_MONEY:
            target = TARGET_MONEY[era]
        elif bal:
            target = bal * TARGET_PCT[era] / 100.0
        else:
            continue
        sweep_first = terminal_first.get(cycle["when"])
        last_open = max(r["opened"] for r in rows)
        events = []
        for r in rows:
            events.append((r["opened"], 1, 0.0))
            events.append((r["closed"], -1, r["net"]))
        events.sort(key=lambda item: (item[0], item[1]))
        count, banked, hits = 0, 0.0, 0
        for when, delta, money in events:
            count += delta
            banked += money
            if (count == 0 and delta == -1 and banked >= target
                    and when < last_open
                    and (sweep_first is None or when < sweep_first)):
                hits += 1
                if len(examples) < 12:
                    examples.append((era, index, when, banked, target))
        if hits:
            proofs[era] += hits
            cycles_with[era] += 1
    print("  era              cycles-with-proof   proof-instants   target basis")
    for era in eras_present(proofs) or eras_present(records):
        basis = ("$%.2f" % TARGET_MONEY[era]) if era in TARGET_MONEY \
            else ("%.2f%% of balance" % TARGET_PCT.get(era, 0.0))
        print(f"  {era:14s}{cycles_with.get(era, 0):15d}{proofs.get(era, 0):17d}"
              f"   {basis}")
    for era, index, when, banked, target in examples:
        print(f"      e.g. {era:14s} cycle#{index:3d} {when}  "
              f"banked {banked:9.2f} >= target {target:8.2f}  count->0, ran on")
    print()

    # ---- PART 6: the per-cycle reset ---------------------------------------
    print("=== PART 6: m_cycle_realized resets to 0.00 per cycle ===")
    print("  a CUMULATIVE accumulator has two signatures: once any cycle banks")
    print("  more than the target, every later cycle trips on its FIRST fill")
    print("  (one-leg sweeps only), and the banked series is monotone.")
    ordered = sorted(
        (r for rows in records.values() for r in rows), key=lambda r: r["when"]
    )
    running, first_breach = 0.0, None
    for i, r in enumerate(ordered):
        running += r["net"]
        if first_breach is None and running >= 6.50:
            first_breach = i
    print(f"  terminal sweeps={len(ordered)}  cumulative net over the tape="
          f"{running:.2f}")
    print(f"  the running total first exceeds the SMALLEST configured target "
          f"($6.50, STARWAVE_20) at sweep #{first_breach}")
    later = ordered[(first_breach or 0) + 1:]
    multi = [r for r in later if r["legs"] > 1]
    neg = [r for r in later if r["net"] < 0.0]
    fills = 0
    for index, rows in per_cycle.items():
        if len(rows) > 1:
            fills += 1
    print(f"  after that sweep: {len(later)} terminal sweeps, of which "
          f"{len(multi)} are MULTI-LEG and {len(neg)} banked a LOSS")
    print(f"  cycles that took more than one fill: {fills}/{len(per_cycle)}")
    decreases = sum(1 for a, b in zip(ordered, ordered[1:]) if b["net"] < a["net"])
    print(f"  banked series strict decreases: {decreases}/{len(ordered) - 1} "
          f"(a cumulative accumulator can never decrease in a winning regime)")
    print("  => every one of those is impossible without the per-cycle reset")
    print("     (StraddleEngine.mqh:1865, :2027, and the ctor at :3130)")
    print()

    # ---- PART 7: the LOWER ENVELOPE inside balance bins --------------------
    # The Theil-Sen slope above is confounded: the balance is very nearly a
    # monotone function of TIME, so regime drift in the overshoot masquerades as
    # a balance effect.  The floor is far less regime-sensitive than the median,
    # so bin by balance and watch the low quantiles.  Under the pct law the
    # MONEY floor rises with the balance and the implied-pct floor is flat;
    # under the flat law the money floor is flat and the pct floor falls.
    print("=== PART 7: lower envelope by balance tercile ===")
    for era in eras_present(records):
        rows = sorted((r for r in records[era] if r["balance"]),
                      key=lambda r: r["balance"])
        if len(rows) < 9:
            continue
        cfg_pct = TARGET_PCT.get(era)
        cfg_money = TARGET_MONEY.get(era)
        third = len(rows) // 3
        bins = [rows[:third], rows[third:2 * third], rows[2 * third:]]
        print(f"  -- {era}  configured "
              f"{format(cfg_pct, '.2f') + '%' if cfg_pct else '$' + format(cfg_money, '.2f')}")
        print("      bin  n   balance p50    money: minpos    p10    p25    p50"
              "     implied%: p10    p25    p50")
        for i, group in enumerate(bins):
            mon = [r["net"] for r in group]
            imp = [100.0 * r["net"] / r["balance"] for r in group]
            positives = [v for v in mon if v > 0.0]
            print(f"      {i + 1:3d} {len(group):3d} {pct([r['balance'] for r in group], 0.50):12.2f}"
                  f"  {(min(positives) if positives else float('nan')):12.2f}"
                  f" {pct(mon, 0.10):6.2f} {pct(mon, 0.25):6.2f} {pct(mon, 0.50):6.2f}"
                  f"          {pct(imp, 0.10):6.3f} {pct(imp, 0.25):6.3f} {pct(imp, 0.50):6.3f}")
        first, last = bins[0], bins[-1]
        rb = pct([r["balance"] for r in last], 0.50) / pct([r["balance"] for r in first], 0.50)
        for name, key in (("money p25", lambda g: pct([r["net"] for r in g], 0.25)),
                          ("money p50", lambda g: pct([r["net"] for r in g], 0.50))):
            a, b = key(first), key(last)
            print(f"      balance x{rb:.2f} across bins;  {name} x"
                  f"{(b / a if a else float('nan')):.2f}  "
                  f"(pct law predicts x{rb:.2f}, flat law predicts x1.00)")
    print()

    # ---- PART 8: the gate proof, hardened against the orphan objection ------
    # PART 5 counted only positions attributed to the cycle, so an orphan from
    # the previous cycle could in principle have kept OwnedPositionCount()>0.
    # Rebuild the same walk over the GLOBAL open set: every position on the tape,
    # whatever cycle opened it.  A global zero is unarguable.
    print("=== PART 8: gate proof over the GLOBAL open set ===")
    events = []
    for row in positions:
        events.append((row["opened"], 1, 0.0))
        events.append((row["closed"], -1, row["net"]))
    events.sort(key=lambda item: (item[0], item[1]))
    zero_instants = []
    count = 0
    for when, delta, _ in events:
        count += delta
        if count == 0 and delta == -1:
            zero_instants.append(when)
    print(f"  instants where the account held ZERO open positions: "
          f"{len(zero_instants)}")
    hard = collections.Counter()
    hard_examples = []
    for index, rows in sorted(per_cycle.items()):
        cycle = deployments[index]
        era = str(cycle["assigned"])
        bal = balance_at(series, cycle["when"])
        if era in TARGET_MONEY:
            target = TARGET_MONEY[era]
        elif bal:
            target = bal * TARGET_PCT[era] / 100.0
        else:
            continue
        sweep_first = terminal_first.get(cycle["when"])
        last_open = max(r["opened"] for r in rows)
        horizon = min(x for x in (sweep_first, last_open) if x is not None)
        for when in zero_instants:
            if not (cycle["when"] < when < horizon):
                continue
            banked = sum(r["net"] for r in rows if r["closed"] <= when)
            if banked >= target:
                hard[era] += 1
                if len(hard_examples) < 10:
                    hard_examples.append((era, index, when, banked, target))
    print("  era             proof-instants (global zero + banked>=target + ran on)")
    for era in eras_present(hard) or eras_present(records):
        print(f"  {era:14s}{hard.get(era, 0):8d}")
    for era, index, when, banked, target in hard_examples:
        print(f"      {era:14s} cycle#{index:3d} {when}  banked {banked:9.2f} "
              f">= {target:8.2f}")
    print()


    # ---- PART 9: the drift-free threshold estimator -------------------------
    # Banked-at-exit overestimates the target by the tick overshoot and
    # underestimates it by whatever the market took back WHILE the basket
    # unwound.  Isolate the cycles whose entire liquidation fitted inside one
    # tight burst (<=2 s of drift): there banked ~ target + one tick, so the low
    # quantiles bound the threshold from below almost exactly.
    print("=== PART 9: threshold from single-burst liquidations only ===")
    clean = collections.defaultdict(list)
    for sweep, cycle in terminal:
        if cycle is None:
            continue
        first, last = sweep[0]["when"], sweep[-1]["when"]
        era = str(cycle["assigned"])
        span = (last - first).total_seconds()
        window = [r for r in positions if cycle["when"] <= r["closed"] <= last]
        nonsl_all = [r for r in window if not is_sl_exit(r)]
        nonsl_burst = [r for r in nonsl_all if r["closed"] >= first]
        if span > 2.0 or len(nonsl_all) != len(nonsl_burst) or not nonsl_burst:
            continue
        clean[era].append({
            "net": sum(r["net"] for r in window),
            "pre": sum(r["net"] for r in window if r["closed"] < first),
            "legs": len(nonsl_burst),
            "span": span,
            "balance": balance_at(series, cycle["when"]),
        })
    for era in eras_present(clean):
        rows = clean[era]
        mon = [r["net"] for r in rows]
        imp = [100.0 * r["net"] / r["balance"] for r in rows if r["balance"]]
        cfg_pct = TARGET_PCT.get(era)
        cfg_money = TARGET_MONEY.get(era)
        print(f"  {era:14s} n={len(rows):4d}  span p95="
              f"{pct([r['span'] for r in rows], 0.95):5.2f}s "
              f"legs p50={pct([r['legs'] for r in rows], 0.50):3.0f}  configured "
              f"{format(cfg_pct, '.2f') + '%' if cfg_pct else '$' + format(cfg_money, '.2f')}")
        print(f"      money   p05={pct(mon, 0.05):8.2f} p10={pct(mon, 0.10):8.2f} "
              f"p25={pct(mon, 0.25):8.2f} p50={pct(mon, 0.50):8.2f} "
              f"min={min(mon):8.2f}")
        if imp:
            print(f"      implied p05={pct(imp, 0.05):8.3f} p10={pct(imp, 0.10):8.3f} "
                  f"p25={pct(imp, 0.25):8.3f} p50={pct(imp, 0.50):8.3f} "
                  f"min={min(imp):8.3f}   [%]")
        if cfg_money:
            for cand in (cfg_money, RIVAL_MONEY[era]):
                short = [v for v in mon if 0.0 <= v < cand]
                print(f"      candidate ${cand:6.2f}: {len(short)} of {len(rows)} "
                      f"short-but-positive ({100.0 * len(short) / len(rows):5.1f}%)")
    print()
    # ---- PART 10: the sharpest instrument -- lone-leg cycles ---------------
    # A cycle in which NOTHING closed before the terminal sweep began is the
    # cleanest possible read on the threshold: m_cycle_realized was 0.00 at the
    # decision instant, so net == floating, and the EA fired the tick it
    # crossed.  banked = target + one tick of overshoot - the unwind slippage of
    # k legs.  At k=1 both corrections are cents-scale on a single 0.01-0.15 lot
    # leg, so the pile IS the threshold.  Watching p50 fall as k grows MEASURES
    # the slippage bias that contaminates every other estimator here.
    print("=== PART 10: zero-prior-realized cycles, bucketed by leg count ===")
    lone = collections.defaultdict(lambda: collections.defaultdict(list))
    for sweep, cycle in terminal:
        if cycle is None:
            continue
        first, last = sweep[0]["when"], sweep[-1]["when"]
        era = str(cycle["assigned"])
        window = [r for r in positions if cycle["when"] <= r["closed"] <= last]
        if not window or any(r["closed"] < first for r in window):
            continue
        if any(is_sl_exit(r) for r in window):
            continue
        lone[era][min(len(window), 7)].append(sum(r["net"] for r in window))
    for era in eras_present(lone):
        cfg_pct = TARGET_PCT.get(era)
        cfg = (format(cfg_pct, '.2f') + '%') if cfg_pct else '$' + format(TARGET_MONEY[era], '.2f')
        total = sum(len(v) for v in lone[era].values())
        print(f"  -- {era:14s} configured {cfg}   n={total}")
        for k in sorted(lone[era]):
            vals = lone[era][k]
            label = f"k={k}" if k < 7 else "k>=7"
            print(f"      {label:5s} n={len(vals):3d}  p25={pct(vals, 0.25):8.2f} "
                  f"p50={pct(vals, 0.50):8.2f} p75={pct(vals, 0.75):8.2f} "
                  f"min={min(vals):8.2f}"
                  + (f"   all={sorted(round(v, 2) for v in vals)}" if len(vals) <= 12 else ""))
    print()
    # ---- PART 11: the decision-instant mark --------------------------------
    # Every estimator above reads the money AFTER the unwind, so each one is
    # target + overshoot - slippage with both corrections unknown.  This one
    # removes the slippage entirely: reprice the whole live basket at the
    # execution price of the FIRST leg of the sweep -- a real, executable market
    # print within milliseconds of the decision -- and add the realized already
    # banked.  That sum IS the left-hand side the EA compared to the target.
    print("=== PART 11: net marked AT the decision instant (slippage removed) ===")
    worst = 0.0
    for row in positions:
        d = 1.0 if row["is_buy"] else -1.0
        model = d * (row["close_price"] - row["open_price"]) * row["volume"] * 100.0
        worst = max(worst, abs(model - row["profit"]))
    print(f"  pricing identity dir*(close-open)*vol*100 vs reported profit: "
          f"worst residual over {len(positions)} positions = {worst:.4f}")
    cancels = cancel_times(orders)
    marked = collections.defaultdict(list)
    tight = collections.defaultdict(list)
    for sweep, cycle in terminal:
        if cycle is None:
            continue
        first, last = sweep[0]["when"], sweep[-1]["when"]
        era = str(cycle["assigned"])
        window = [r for r in positions if cycle["when"] <= r["closed"] <= last]
        mark_rows = [r for r in window if r["closed"] >= first]
        if not mark_rows:
            continue
        mkt = min(mark_rows, key=lambda r: r["closed"])["close_price"]
        realized_before = sum(r["net"] for r in window if r["closed"] < first)
        live = [r for r in positions
                if cycle["when"] <= r["opened"] <= first < r["closed"]]
        floating = sum((1.0 if r["is_buy"] else -1.0)
                       * (mkt - r["open_price"]) * r["volume"] * 100.0 for r in live)
        value = realized_before + floating
        bal = balance_at(series, cycle["when"])
        record = {"net": value, "balance": bal, "legs": len(live)}
        marked[era].append(record)
        prior = [w for w in cancels if w <= first]
        if prior and (first - prior[-1]).total_seconds() <= 0.5:
            tight[era].append(record)
    for label, table in (("ALL terminal sweeps", marked),
                         ("cancel->close handoff <=0.5 s", tight)):
        print(f"  -- {label}")
        for era in eras_present(table):
            rows = table[era]
            vals = [r["net"] for r in rows]
            if not vals:
                continue
            cfg_pct = TARGET_PCT.get(era)
            cfg = ((format(cfg_pct, '.2f') + '%') if cfg_pct
                   else '$' + format(TARGET_MONEY[era], '.2f'))
            print(f"     {era:14s} n={len(vals):4d} configured {cfg:7s} "
                  f"legs p50={pct([r['legs'] for r in rows], 0.50):3.0f}")
            print(f"        money   p05={pct(vals,0.05):8.2f} p10={pct(vals,0.10):8.2f} "
                  f"p25={pct(vals,0.25):8.2f} p50={pct(vals,0.50):8.2f} "
                  f"p75={pct(vals,0.75):8.2f} min={min(vals):8.2f}")
            imp = [100.0 * r["net"] / r["balance"] for r in rows if r["balance"]]
            if imp:
                print(f"        implied p05={pct(imp,0.05):8.3f} p25={pct(imp,0.25):8.3f} "
                      f"p50={pct(imp,0.50):8.3f} p75={pct(imp,0.75):8.3f}   [%]")
            if era in TARGET_MONEY:
                for cand in (TARGET_MONEY[era], RIVAL_MONEY[era]):
                    below = sum(1 for v in vals if v < cand)
                    print(f"        candidate ${cand:6.2f}: {below}/{len(vals)} "
                          f"({100.0*below/len(vals):5.1f}%) marked BELOW the target "
                          f"at the instant the EA decided to close")
    print()
    # ---- PART 12: two-sided decision-instant mark --------------------------
    # PART 11 marked the whole basket at ONE price, so a directionally lopsided
    # basket carries a full spread of error on its net exposure -- tens of
    # dollars, which is why it puts a third of the sweeps below their own target.
    # Fix it: buys are closed at the bid and sells at the ask, and BOTH sides
    # print inside the burst, so take the first closing buy's price as the bid
    # and the first closing sell's price as the ask.
    print("=== PART 12: two-sided decision-instant mark ===")
    resid = [abs((1.0 if r["is_buy"] else -1.0)
                 * (r["close_price"] - r["open_price"]) * r["volume"] * 100.0
                 - r["profit"]) for r in positions]
    print(f"  pricing residual: >0.005 on {sum(1 for v in resid if v > 0.005)}"
          f"/{len(resid)} rows  p95={pct(resid,0.95):.4f} p999={pct(resid,0.999):.4f} "
          f"max={max(resid):.4f}")
    two = collections.defaultdict(list)
    spreads = []
    for sweep, cycle in terminal:
        if cycle is None:
            continue
        first, last = sweep[0]["when"], sweep[-1]["when"]
        era = str(cycle["assigned"])
        inside = [r for r in positions if first <= r["closed"] <= last]
        buys = [r for r in inside if r["is_buy"]]
        sells = [r for r in inside if not r["is_buy"]]
        if not buys or not sells:
            continue
        bid_row = min(buys, key=lambda r: r["closed"])
        ask_row = min(sells, key=lambda r: r["closed"])
        skew = abs((bid_row["closed"] - ask_row["closed"]).total_seconds())
        if skew > 5.0:
            continue
        bid, ask = bid_row["close_price"], ask_row["close_price"]
        spreads.append(ask - bid)
        realized_before = sum(r["net"] for r in positions
                              if cycle["when"] <= r["closed"] < first)
        live = [r for r in positions
                if cycle["when"] <= r["opened"] <= first < r["closed"]]
        floating = sum(((bid - r["open_price"]) if r["is_buy"]
                        else (r["open_price"] - ask)) * r["volume"] * 100.0
                       + r["swap"] for r in live)
        two[era].append({"net": realized_before + floating,
                         "balance": balance_at(series, cycle["when"]),
                         "legs": len(live)})
    print(f"  implied ask-bid at the decision instant: n={len(spreads)} "
          f"p05={pct(spreads,0.05):7.3f} p50={pct(spreads,0.50):7.3f} "
          f"p95={pct(spreads,0.95):7.3f}")
    for era in eras_present(two):
        rows = two[era]
        vals = [r["net"] for r in rows]
        cfg_pct = TARGET_PCT.get(era)
        cfg = ((format(cfg_pct, '.2f') + '%') if cfg_pct
               else '$' + format(TARGET_MONEY[era], '.2f'))
        print(f"  {era:14s} n={len(vals):4d} configured {cfg:7s} "
              f"legs p50={pct([r['legs'] for r in rows],0.50):3.0f}")
        print(f"      money   p05={pct(vals,0.05):8.2f} p10={pct(vals,0.10):8.2f} "
              f"p25={pct(vals,0.25):8.2f} p50={pct(vals,0.50):8.2f} "
              f"p75={pct(vals,0.75):8.2f} min={min(vals):8.2f}")
        imp = [100.0 * r["net"] / r["balance"] for r in rows if r["balance"]]
        if imp:
            print(f"      implied p05={pct(imp,0.05):8.3f} p25={pct(imp,0.25):8.3f} "
                  f"p50={pct(imp,0.50):8.3f} p75={pct(imp,0.75):8.3f}   [%]")
        if era in TARGET_MONEY:
            for cand in (TARGET_MONEY[era], RIVAL_MONEY[era]):
                below = sum(1 for v in vals if v < cand)
                print(f"      candidate ${cand:6.2f}: {below}/{len(vals)} "
                      f"({100.0*below/len(vals):5.1f}%) BELOW target at the decision")
    print()
    # ---- PART 13: the decision is the FIRST close of the cycle's drain ------
    # PARTS 11-12 still put ~40% of the sweeps below their own target, and the
    # reason is the burst grouper, not the predicate: a 2 s gap splits ONE paced
    # liquidation into several "bursts", so the terminal burst's first close can
    # be minutes after BeginClose() fired.  STARWAVE_30 has 284 interim bursts
    # over 103 cycles, 279 of them singletons -- exactly the signature of a paced
    # drain being cut up.  Mark at the FIRST close of the cycle's whole drain.
    print("=== PART 13: mark at the FIRST close of the cycle's entire drain ===")
    drains = collections.defaultdict(list)
    for burst, cycle in list(terminal) + list(interim):
        if cycle is None:
            continue
        drains[cycle["when"]].append((burst, cycle))
    third = collections.defaultdict(list)
    spans = collections.defaultdict(list)
    for key in sorted(drains):
        bursts = sorted(drains[key], key=lambda item: item[0][0]["when"])
        cycle = bursts[0][1]
        era = str(cycle["assigned"])
        decision = bursts[0][0][0]["when"]
        end = bursts[-1][0][-1]["when"]
        spans[era].append((end - decision).total_seconds())
        drained = [r for r in positions if decision <= r["closed"] <= end]
        buys = [r for r in drained if r["is_buy"]]
        sells = [r for r in drained if not r["is_buy"]]
        if not buys or not sells:
            continue
        bid = min(buys, key=lambda r: r["closed"])
        ask = min(sells, key=lambda r: r["closed"])
        if abs((bid["closed"] - ask["closed"]).total_seconds()) > 5.0:
            continue
        realized_before = sum(r["net"] for r in positions
                              if cycle["when"] <= r["closed"] < decision)
        live = [r for r in positions
                if cycle["when"] <= r["opened"] <= decision < r["closed"]]
        floating = sum(((bid["close_price"] - r["open_price"]) if r["is_buy"]
                        else (r["open_price"] - ask["close_price"]))
                       * r["volume"] * 100.0 + r["swap"] for r in live)
        third[era].append({"net": realized_before + floating,
                           "balance": balance_at(series, cycle["when"]),
                           "legs": len(live)})
    for era in eras_present(spans):
        s = spans[era]
        print(f"  {era:14s} drain span s: n={len(s):4d} p50={pct(s,0.50):8.2f} "
              f"p95={pct(s,0.95):9.2f} max={max(s):9.2f}   bursts/cycle p50="
              f"{pct([len(drains[k]) for k in drains if str(drains[k][0][1]['assigned']) == era], 0.50):3.0f}")
    for era in eras_present(third):
        rows = third[era]
        vals = [r["net"] for r in rows]
        cfg_pct = TARGET_PCT.get(era)
        cfg = ((format(cfg_pct, '.2f') + '%') if cfg_pct
               else '$' + format(TARGET_MONEY[era], '.2f'))
        print(f"  {era:14s} n={len(vals):4d} configured {cfg:7s} "
              f"legs p50={pct([r['legs'] for r in rows],0.50):3.0f}")
        print(f"      money   p05={pct(vals,0.05):8.2f} p10={pct(vals,0.10):8.2f} "
              f"p25={pct(vals,0.25):8.2f} p50={pct(vals,0.50):8.2f} "
              f"p75={pct(vals,0.75):8.2f} min={min(vals):8.2f}")
        imp = [100.0 * r["net"] / r["balance"] for r in rows if r["balance"]]
        if imp:
            print(f"      implied p05={pct(imp,0.05):8.3f} p25={pct(imp,0.25):8.3f} "
                  f"p50={pct(imp,0.50):8.3f} p75={pct(imp,0.75):8.3f}   [%]")
        if era in TARGET_MONEY:
            for cand in (TARGET_MONEY[era], RIVAL_MONEY[era]):
                below = sum(1 for v in vals if v < cand)
                print(f"      candidate ${cand:6.2f}: {below}/{len(vals)} "
                      f"({100.0*below/len(vals):5.1f}%) BELOW target at the decision")
    print()
    # ---- PART 14: is the shortfall cancel-run latency, or a real violation? --
    # PART 13 refuted its own premise (bursts/cycle p50 = 1 in every era, so the
    # grouper was NOT cutting up a paced drain) and left ~41% of the sweeps
    # marked below $26.50.  Two readings remain.  Either the mark is late --
    # BeginClose() fires, the bulk cancel runs, and the price mean-reverts before
    # the first close prints, which biases every mark DOWN -- or the floor law is
    # genuinely violated.  These are separable: bias predicts the shortfall grows
    # with the cancel->close latency, a violation predicts it is flat in latency.
    print("=== PART 14: shortfall vs cancel-run latency ===")
    cancels = cancel_times(orders)
    def run_start(decision, floor):
        """Start of the contiguous 2 s-gap cancel cluster that ends at `decision`."""
        window = [c for c in cancels if floor <= c <= decision]
        if not window:
            return None
        start = window[-1]
        for earlier in reversed(window[:-1]):
            if (start - earlier).total_seconds() > 2.0:
                break
            start = earlier
        return start
    buckets = collections.defaultdict(lambda: collections.defaultdict(list))
    slope_points = collections.defaultdict(list)
    for key in sorted(drains):
        bursts = sorted(drains[key], key=lambda item: item[0][0]["when"])
        cycle = bursts[0][1]
        era = str(cycle["assigned"])
        decision = bursts[0][0][0]["when"]
        end = bursts[-1][0][-1]["when"]
        drained = [r for r in positions if decision <= r["closed"] <= end]
        buys = [r for r in drained if r["is_buy"]]
        sells = [r for r in drained if not r["is_buy"]]
        if not buys or not sells:
            continue
        bid = min(buys, key=lambda r: r["closed"])
        ask = min(sells, key=lambda r: r["closed"])
        if abs((bid["closed"] - ask["closed"]).total_seconds()) > 5.0:
            continue
        began = run_start(decision, cycle["when"])
        if began is None:
            continue
        latency = (decision - began).total_seconds()
        realized_before = sum(r["net"] for r in positions
                              if cycle["when"] <= r["closed"] < began)
        live = [r for r in positions
                if cycle["when"] <= r["opened"] <= began < r["closed"]]
        net = realized_before + sum(
            ((bid["close_price"] - r["open_price"]) if r["is_buy"]
             else (r["open_price"] - ask["close_price"]))
            * r["volume"] * 100.0 + r["swap"] for r in live)
        label = ("a <1s" if latency < 1.0 else "b 1-3s" if latency < 3.0
                 else "c 3-6s" if latency < 6.0 else "d >=6s")
        buckets[era][label].append(net)
        slope_points[era].append((latency, net))
    for era in eras_present(buckets):
        cfg_pct = TARGET_PCT.get(era)
        cfg = ((format(cfg_pct, '.2f') + '%') if cfg_pct
               else '$' + format(TARGET_MONEY.get(era, 0.0), '.2f'))
        print(f"  -- {era:14s} configured {cfg}")
        for label in sorted(buckets[era]):
            vals = buckets[era][label]
            extra = ""
            if era in TARGET_MONEY:
                below = sum(1 for v in vals if v < TARGET_MONEY[era])
                extra = (f"  below ${TARGET_MONEY[era]:.2f}: {below}/{len(vals)}"
                         f" ({100.0*below/len(vals):5.1f}%)")
            print(f"      {label}  n={len(vals):4d} p25={pct(vals,0.25):8.2f} "
                  f"p50={pct(vals,0.50):8.2f} p75={pct(vals,0.75):8.2f}{extra}")
        slope, pairs = theil_sen(slope_points[era], 0.5)
        print(f"      Theil-Sen d(net)/d(latency) = {slope:+9.3f} $/s "
              f"over {pairs} pairs   (bias predicts a NEGATIVE slope, "
              f"a real violation predicts ~0)")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
