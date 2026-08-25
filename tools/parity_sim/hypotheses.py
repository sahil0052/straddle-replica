"""Phase 2 hypothesis tests that run on the report alone (no ticks needed).

Settles/ranks the open questions the refinement loop must converge:
  H1 anchor source   — anchor vs last traded price before deployment
  H2 basket target   — fixed $30 vs percent-of-balance (balance grows in-window)
  H3 exit classification — classify all cycles by exit rule, find misfits
  H4 re-arm delay    — timer vs next-tick (delay distribution shape)
  H5 deployment pacing — burst internal pacing vs 20s cooldown values

Usage:
    python hypotheses.py --report-dir out --out out/hypotheses-report.txt
"""
from __future__ import annotations

import argparse
import bisect
import statistics as st
from collections import Counter

from report import (
    DIVISOR,
    REGIME_CUT,
    find_deployment_bursts,
    load_balance_timeline,
    load_entry_deals,
    load_orders,
    load_positions,
    segment_cycles,
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report-dir", default="out")
    ap.add_argument("--out", default="out/hypotheses-report.txt")
    args = ap.parse_args()

    positions = load_positions(f"{args.report_dir}/positions.csv")
    orders = load_orders(f"{args.report_dir}/orders.csv")
    deals = load_entry_deals(f"{args.report_dir}/deals.csv")
    balance = load_balance_timeline(f"{args.report_dir}/deals.csv")
    cycles = segment_cycles(positions)
    deployments, rearm_bursts = find_deployment_bursts(orders)

    lines = ["HYPOTHESIS TEST REPORT (report-only)", "=" * 60]

    # ---------------- H1: anchor source ----------------
    # For each deployment, compare implied anchor (mid of B1/S1) to the last
    # traded price (deal or position close) before the burst.
    price_events = [(d.t, d.price) for d in deals] + [(p.close_t, p.close_p) for p in positions]
    price_events.sort(key=lambda x: x[0])
    pe_times = [x[0] for x in price_events]
    h1 = []
    for burst in deployments:
        b1 = next((o for o in burst if o.side == "B" and o.lvl == 1 and o.price), None)
        s1 = next((o for o in burst if o.side == "S" and o.lvl == 1 and o.price), None)
        if not (b1 and s1):
            continue
        anchor = (b1.price + s1.price) / 2.0
        step = anchor / DIVISOR
        i = bisect.bisect_left(pe_times, burst[0].t)
        if i == 0:
            continue
        last_price = price_events[i - 1][1]
        age = (burst[0].t - price_events[i - 1][0]).total_seconds()
        h1.append(((anchor - last_price) / step, age))
    if h1:
        res = sorted(abs(x[0]) for x in h1)
        lines += [
            "",
            f"[H1 anchor vs last traded price] n={len(h1)}",
            f"  |anchor-last|/step: median={st.median(res):.3f} p90={res[len(res)*9//10]:.3f} max={res[-1]:.3f}",
            f"  signed median={st.median([x[0] for x in h1]):+.3f} "
            f"(0 => anchor == last price; +/-0.5 => bid/ask offset; verify vs ticks in Phase 1)",
            f"  last-price age at deploy: median={st.median([x[1] for x in h1]):.1f}s",
        ]

    # ---------------- H2: basket target formula ----------------
    bal_times = [t for t, _ in balance]
    def bal_at(t):
        i = bisect.bisect_left(bal_times, t)
        return balance[max(0, i - 1)][1]
    fixed, pct = [], []
    for cyc, _endt in cycles:
        net = sum(p.profit for p in cyc)
        if net <= 0 or len(cyc) < 8:
            continue
        b = bal_at(min(p.open_t for p in cyc))
        fixed.append(net)
        pct.append(100.0 * net / b)
    if fixed:
        cv_fixed = st.pstdev(fixed) / st.mean(fixed)
        cv_pct = st.pstdev(pct) / st.mean(pct)
        winner = "FIXED-MONEY" if cv_fixed < cv_pct else "PERCENT-OF-BALANCE"
        lines += [
            "",
            f"[H2 basket target] n={len(fixed)} positive cycles",
            f"  fixed-$ nets:   median={st.median(fixed):.2f} CV={cv_fixed:.3f}",
            f"  pct-of-balance: median={st.median(pct):.4f}% CV={cv_pct:.3f}",
            f"  lower CV wins => {winner}",
        ]

    # ---------------- H3: exit classification ----------------
    classified = Counter()
    misfits = []
    for cyc, endt in cycles:
        if len(cyc) < 8:
            classified["micro-cycle(<8 trades)"] += 1
            continue
        net = sum(p.profit for p in cyc)
        realized = sum(p.profit for p in cyc if (endt - p.close_t).total_seconds() > 90)
        start = min(p.open_t for p in cyc)
        first = [p for p in cyc if (p.open_t - start).total_seconds() < 120]
        buys = [p.open_p for p in first if p.typ == "buy"]
        sells = [p.open_p for p in first if p.typ == "sell"]
        anchor = (min(buys) + max(sells)) / 2.0 if buys and sells else (buys or sells)[0]
        finals = [p.close_p for p in cyc if (endt - p.close_t).total_seconds() <= 60]
        exitp = st.median(finals) if finals else cyc[-1].close_p
        dist = abs(exitp - anchor)
        has_rescue = any(p.vol not in (0.01, 0.06, 0.15) for p in cyc)
        if net >= 25.0 and dist < 15.0:
            classified["basket_target"] += 1
        elif dist >= 15.0:
            classified["grid_recenter"] += 1
        elif has_rescue and realized >= 150.0 and net >= -25.0:
            classified["rescue_breakeven"] += 1
        else:
            classified["UNEXPLAINED"] += 1
            misfits.append((start, len(cyc), net, dist, realized, has_rescue))
    lines += ["", f"[H3 exit classification] {dict(classified)}"]
    for m in misfits:
        lines.append(f"  UNEXPLAINED: start={m[0]} trades={m[1]} net={m[2]:.2f} dist={m[3]:.2f} realized={m[4]:.2f} rescue={m[5]}")

    # ---------------- H4: re-arm delay shape ----------------
    deltas = []
    close_times = sorted(p.close_t for p in positions)
    for burst in rearm_bursts:
        for o in burst:
            i = bisect.bisect_right(close_times, o.t)
            if i > 0:
                d = (o.t - close_times[i - 1]).total_seconds()
                if d < 600:
                    deltas.append(d)
    if deltas:
        deltas.sort()
        h = Counter(int(d // 5) * 5 for d in deltas)
        lines += [
            "",
            f"[H4 re-arm delay] n={len(deltas)} median={st.median(deltas):.1f}s "
            f"p25={deltas[len(deltas)//4]:.1f} p75={deltas[len(deltas)*3//4]:.1f}",
            f"  5s-bucket histogram (first 8): {dict(sorted(h.items())[:8])}",
            "  shape note: monotonically-decaying from 0-5s bucket => event-driven"
            " (OnTrade/next-tick after delay), not a fixed timer lattice",
        ]

    # ---------------- H5: deployment pacing ----------------
    pacing = []
    for burst in deployments:
        ts = sorted(o.t for o in burst)
        span = (ts[-1] - ts[0]).total_seconds()
        pacing.append(span)
    if pacing:
        lines += [
            "",
            f"[H5 deployment burst span] n={len(pacing)} median={st.median(pacing):.1f}s "
            f"max={max(pacing):.1f}s (60 orders per burst)",
        ]

    text = "\n".join(lines)
    print(text)
    with open(args.out, "w") as f:
        f.write(text + "\n")
    print(f"\nwritten: {args.out}")


if __name__ == "__main__":
    main()
