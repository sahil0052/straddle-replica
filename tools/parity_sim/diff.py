"""Residual scorer: align simulated events (replay.py output) against the
Target report and produce the per-rule residual dashboard.

Alignment strategy:
  - cycles: sim cycle k <-> report cycle k (both segmented chronologically)
  - orders: within a cycle, match on (side, lvl, sequence)
  - positions: within a cycle, match closes on (side-equivalent, lvl via
    volume tier + nearest open price)

Usage:
    python diff.py --sim out/sim-events.csv --report-dir out \
                   --out out/residual-dashboard.txt
"""
from __future__ import annotations

import argparse
import csv
import statistics as st
from collections import Counter, defaultdict
from datetime import datetime

from report import DIVISOR, find_deployment_bursts, load_orders, load_positions, segment_cycles


def load_sim_events(path: str):
    events = []
    with open(path) as f:
        r = csv.DictReader(f)
        for row in r:
            row["t"] = datetime.fromisoformat(row["t"])
            events.append(row)
    return events


def fnum(x, default=None):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def fvol(x, default=None):
    """Report volumes may be formatted 'a / b' (requested vs filled; canceled
    orders show '0.06 / 0.00'). The requested volume is the max of the parts."""
    if isinstance(x, str) and "/" in x:
        parts = [fnum(p.strip(), 0.0) for p in x.split("/")]
        return max(parts)
    return fnum(str(x).strip(), default)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sim", default="out/sim-events.csv")
    ap.add_argument("--report-dir", default="out")
    ap.add_argument("--out", default="out/residual-dashboard.txt")
    args = ap.parse_args()

    sim = load_sim_events(args.sim)
    rpt_positions = load_positions(f"{args.report_dir}/positions.csv")
    rpt_orders = load_orders(f"{args.report_dir}/orders.csv")
    rpt_cycles = segment_cycles(rpt_positions)
    rpt_deployments, _ = find_deployment_bursts(rpt_orders)

    sim_by_cycle = defaultdict(list)
    for e in sim:
        sim_by_cycle[int(e["cycle"])].append(e)
    sim_cycles = sorted(sim_by_cycle)

    lines = ["PARITY RESIDUAL DASHBOARD", "=" * 60, ""]

    # ---- 1. cycle count ----
    lines.append(f"[cycles] report={len(rpt_cycles)} sim={len(sim_cycles)} "
                 f"delta={len(sim_cycles) - len(rpt_cycles)}")

    # ---- 2. anchor / lattice residual per deployment (TIME-ALIGNED) ----
    # Align each report deployment to the sim deploy event nearest in time.
    # Index alignment is wrong the moment sim and report cycle boundaries
    # diverge; time alignment keeps every comparison honest and localizes
    # divergence to the cycles where it actually happens.
    sim_deploys = sorted(
        (e for e in sim if e["kind"] == "deploy"), key=lambda e: e["t"]
    )
    sim_deploy_times = [e["t"] for e in sim_deploys]
    import bisect as _bisect

    def nearest_sim_deploy(t, tolerance_s=600.0):
        if not sim_deploys:
            return None
        i = _bisect.bisect_left(sim_deploy_times, t)
        best = None
        for j in (i - 1, i):
            if 0 <= j < len(sim_deploys):
                dt = abs((sim_deploy_times[j] - t).total_seconds())
                if best is None or dt < best[0]:
                    best = (dt, sim_deploys[j])
        return best[1] if best and best[0] <= tolerance_s else None

    anchor_res = []
    aligned_pairs = []  # (report burst, sim cycle id)
    unmatched_deployments = 0
    for burst in rpt_deployments:
        b1 = next((o for o in burst if o.side == "B" and o.lvl == 1 and o.price), None)
        s1 = next((o for o in burst if o.side == "S" and o.lvl == 1 and o.price), None)
        if not (b1 and s1):
            continue
        deploy = nearest_sim_deploy(burst[0].t)
        if deploy is None:
            unmatched_deployments += 1
            continue
        rpt_anchor = (b1.price + s1.price) / 2.0
        sim_anchor = fnum(deploy["anchor"])
        step = rpt_anchor / DIVISOR
        anchor_res.append(abs(sim_anchor - rpt_anchor) / step)
        aligned_pairs.append((burst, int(deploy["cycle"])))
    if anchor_res:
        lines.append(f"[anchor]  n={len(anchor_res)} unmatched={unmatched_deployments} residual(steps): "
                     f"median={st.median(anchor_res):.4f} max={max(anchor_res):.4f}")

    # ---- 3. order lattice price + volume residual ----
    price_res, vol_ok, vol_bad = [], 0, 0
    for burst, sim_cycle_id in aligned_pairs:
        rpt_prices = {(o.side, o.lvl): (o.price, o.vol) for o in burst if o.price}
        sim_places = {
            (e["side"], int(e["lvl"])): (fnum(e["price"]), e["vol"])
            for e in sim_by_cycle[sim_cycle_id]
            if e["kind"] == "order_place"
        }
        for key, (rp, rv) in rpt_prices.items():
            if key not in sim_places:
                continue
            sp, sv = sim_places[key]
            step = rp / DIVISOR
            price_res.append(abs(sp - rp) / step)
            if abs(fvol(sv, -1.0) - fvol(rv, -2.0)) < 1e-9:
                vol_ok += 1
            else:
                vol_bad += 1
    if price_res:
        exact = sum(1 for x in price_res if x < 0.1)
        lines.append(f"[lattice] n={len(price_res)} price residual(steps): "
                     f"median={st.median(price_res):.4f} p99={sorted(price_res)[len(price_res)*99//100]:.4f} "
                     f"exact(<0.1)={100.0*exact/len(price_res):.1f}%")
        lines.append(f"[volume]  exact={vol_ok} mismatched={vol_bad} "
                     f"({100.0*vol_ok/max(1,vol_ok+vol_bad):.2f}% exact)")

    # ---- 4. cycle net / trade count / exit reason (TIME-ALIGNED) ----
    net_res, count_res = [], []
    reasons = Counter()
    for rpt_cycle, _endt in rpt_cycles:
        start = min(p.open_t for p in rpt_cycle)
        deploy = nearest_sim_deploy(start)
        if deploy is None:
            continue
        sim_events = sim_by_cycle[int(deploy["cycle"])]
        rpt_net = sum(p.profit for p in rpt_cycle)
        sim_net = sum(fnum(e["profit"], 0.0) for e in sim_events if e["kind"] == "close")
        sim_count = sum(1 for e in sim_events if e["kind"] == "close")
        net_res.append(abs(sim_net - rpt_net))
        count_res.append(abs(sim_count - len(rpt_cycle)))
        cc = next((e for e in sim_events if e["kind"] == "cycle_close"), None)
        reasons[cc["reason"] if cc else "none"] += 1
    if net_res:
        lines.append(f"[cycle net]   |delta|$: median={st.median(net_res):.2f} "
                     f"p90={sorted(net_res)[len(net_res)*9//10]:.2f} max={max(net_res):.2f}")
        lines.append(f"[cycle count] |delta|trades: median={st.median(count_res):.1f} max={max(count_res)}")
        lines.append(f"[exit reasons] sim: {dict(reasons)}")

    # ---- 5. SL-close winner profit distribution comparison ----
    rpt_sl_wins = [
        abs(p.close_p - p.open_p) / (p.open_p / DIVISOR)
        for p in rpt_positions
        if p.profit > 0 and p.sl and abs(p.close_p - p.sl) < 1e-9
    ]
    sim_sl_wins = [
        abs(fnum(e["close_p"]) - fnum(e["open_p"])) / (fnum(e["open_p"]) / DIVISOR)
        for e in sim
        if e["kind"] == "close" and e["reason"] == "sl" and fnum(e["profit"], 0) > 0
    ]

    def dist_stats(v):
        if not v:
            return "n=0"
        v = sorted(v)
        return (f"n={len(v)} med={st.median(v):.2f} p10={v[len(v)//10]:.2f} "
                f"p90={v[len(v)*9//10]:.2f} max={v[-1]:.2f}")

    lines.append(f"[sl-winners report] {dist_stats(rpt_sl_wins)}")
    lines.append(f"[sl-winners sim]    {dist_stats(sim_sl_wins)}")
    gap_rpt = sum(1 for x in rpt_sl_wins if 1.0 < x < 2.0)
    gap_sim = sum(1 for x in sim_sl_wins if 1.0 < x < 2.0)
    lines.append(f"[sl gap(1,2)] report={gap_rpt} sim={gap_sim} (both must be ~0)")

    text = "\n".join(lines)
    print(text)
    with open(args.out, "w") as f:
        f.write(text + "\n")
    print(f"\nwritten: {args.out}")


if __name__ == "__main__":
    main()
