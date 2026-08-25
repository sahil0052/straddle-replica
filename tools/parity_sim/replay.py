"""Replay driver: feed a price stream through Engine and write the simulated
event log for diff.py.

Two price sources:
  --ticks <csv[.gz]>   real broker ticks from ExportTicks.mq5 (Phase 0/1 exact)
  --from-report        sparse price path reconstructed from report deal events
                       (works today with zero external data; between-event
                       paths are interpolated, so results are BOUNDED, not
                       exact — used to falsify/rank rule hypotheses cheaply)

Usage:
    python replay.py --from-report --report-dir out --out out/sim-events.csv
    python replay.py --ticks ../../data/ticks-xauusd-jul14-30.csv.gz \
                     --report-dir out --out out/sim-events.csv
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime

from engine import Config, Engine
from fidelity import load_ticks
from report import load_balance_timeline, load_entry_deals, load_positions, REGIME_CUT


def price_stream_from_ticks(path: str):
    times, bids, asks, _gaps = load_ticks(path)
    for i in range(len(times)):
        yield times[i], bids[i], asks[i]


def price_stream_from_report(report_dir: str, synth_spread: float = 0.15):
    """Sparse stream from every priced report event (entries + closes),
    ordered by time. Spread is synthesized (median gold ECN ~0.10-0.20)."""
    points: list[tuple[datetime, float]] = []
    for d in load_entry_deals(f"{report_dir}/deals.csv"):
        points.append((d.t, d.price))
    for p in load_positions(f"{report_dir}/positions.csv"):
        points.append((p.close_t, p.close_p))
    points.sort(key=lambda x: x[0])
    half = synth_spread / 2.0
    for t, price in points:
        yield t, price - half, price + half


def starting_balance(report_dir: str) -> float:
    bal = load_balance_timeline(f"{report_dir}/deals.csv")
    before = [b for t, b in bal if t < REGIME_CUT]
    return before[-1] if before else 10000.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticks")
    ap.add_argument("--from-report", action="store_true")
    ap.add_argument("--report-dir", default="out")
    ap.add_argument("--out", default="out/sim-events.csv")
    ap.add_argument("--anchor-source", default="mid", choices=["mid", "bid", "ask", "last"])
    args = ap.parse_args()

    if not args.ticks and not args.from_report:
        ap.error("need --ticks or --from-report")

    cfg = Config(anchor_source=args.anchor_source)
    eng = Engine(cfg, start_balance=starting_balance(args.report_dir))
    stream = (
        price_stream_from_ticks(args.ticks) if args.ticks else price_stream_from_report(args.report_dir)
    )
    n = 0
    for t, bid, ask in stream:
        eng.process_tick(t, bid, ask)
        n += 1

    with open(args.out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["kind", "t", "cycle", "side", "lvl", "vol", "price", "open_p", "close_p", "profit", "reason", "anchor", "step"])
        for e in eng.events:
            w.writerow([
                e["kind"], e["t"].isoformat(), e["cycle"],
                e.get("side", ""), e.get("lvl", ""), e.get("vol", ""), e.get("price", ""),
                e.get("open_p", ""), e.get("close_p", ""), e.get("profit", ""),
                e.get("reason", ""), e.get("anchor", ""), e.get("step", ""),
            ])
    print(f"replayed {n:,} price events -> {len(eng.events):,} sim events -> {args.out}")
    print(f"final sim balance: {eng.balance:.2f}")


if __name__ == "__main__":
    main()
