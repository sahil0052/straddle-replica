"""Are AGGRESSIVE_30's 9-of-29 negative locks real, or did the stale field make them?

The V4 audit reported that on the 901018 tape the AGGRESSIVE_30 era put 9 of its
29 measurable positions at a NEGATIVE locked distance -- an armed stop on the
LOSING side of the entry -- with a minimum of -7.18 steps.  Re-measured on the
Starwave tape with the broker's attested price, negatives are 1 of 1,311 (0.08%).
31% versus 0.08% is a three-order-of-magnitude disagreement, so one of the two
numbers is an artifact.

`StopScheduler::Calculate()` cannot write a losing stop.  The proof is short
enough to state in full, because it is what makes this a falsifiable test rather
than a fishing trip:

    the gate (StopScheduler.mqh:153-154) requires favorable_steps >= 2.0, where
    favorable_steps = dir*(market - entry)/step;

    the activation branch writes market - dir*pre_tighten*step, i.e.
    entry + dir*(favorable - 2.0)*step, which is >= entry because favorable >= 2;

    the trail branch writes market - dir*D*step with D in {1.0, 2.0}, i.e.
    entry + dir*(favorable - D)*step, again >= entry because favorable >= 2 >= D;

    the ratchet return only admits desired > current_sl (buys) / < (sells), so a
    stop can never loosen once written.

The single escape hatch is the broker clamp
`desired = MathMin(desired, bid - stops_level*point)` (180-188), which pushes the
stop BELOW entry only when stops_level*point > favorable*step -- and since
favorable >= 2, only when the minimum stop distance exceeds two full steps.  On
XAUUSD point = 0.01, so a 50-point stops_level is 0.50 in price, and 2*step >
0.50 for every step above 0.25.  AGGRESSIVE_30's measured step is 0.68, so the
clamp is 1.36 away from binding and cannot be the cause.

So a negative attested lock in that era would be a genuine third behaviour, and
a negative that exists ONLY on the position field is correction (C)'s estimator
reading a stale column -- exactly the defect attested_stop.py already proved for
the 192 "fills that beat their stop".  This script measures all three instruments
side by side, per era, on the same population.
"""
from __future__ import annotations

import collections
import statistics
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.forensics.dataset import load_all  # noqa: E402
from tools.forensics.linkage import SL_RE, exit_reason, link_exits  # noqa: E402

# Era boundaries, from the verified 285-deployment cut (V1/V2/V9 re-score).
ERAS = [
    ("HISTORICAL_50", datetime(2026, 6, 23, 16, 17, 27), datetime(2026, 7, 2, 15, 24, 57)),
    ("HISTORICAL_60", datetime(2026, 7, 2, 15, 24, 57), datetime(2026, 7, 13, 11, 2, 45)),
    ("AGGRESSIVE_30", datetime(2026, 7, 13, 11, 2, 45), datetime(2026, 7, 13, 12, 32, 29)),
    ("LOW_RISK_30", datetime(2026, 7, 13, 12, 32, 29), datetime(2026, 7, 13, 15, 59, 39)),
    ("STARWAVE_30", datetime(2026, 7, 13, 15, 59, 39), datetime(2027, 1, 1)),
]


def era_of(when):
    for name, start, end in ERAS:
        if start <= when < end:
            return name
    return "?"


def main() -> int:
    orders, positions, deals, cycles = load_all()
    exit_order, _ed, _en, _st = link_exits(orders, positions, deals)
    step_by_cycle = {c.index: c.step for c in cycles if c.step}
    era_by_cycle = {c.index: era_of(c.start) for c in cycles}

    rows = []
    for position in positions:
        if position.is_open or position.close_time is None:
            continue
        if exit_reason(position, exit_order) != "sl":
            continue
        step = step_by_cycle.get(position.cycle)
        if not step or position.close_price is None:
            continue
        order = exit_order.get(position.position_id)
        match = SL_RE.fullmatch((order.comment or "") if order else "")
        direction = position.dir
        rows.append({
            "era": era_by_cycle.get(position.cycle, "?"),
            "cycle": position.cycle,
            "ticket": position.position_id,
            "side": position.side,
            "level": position.level,
            "step": step,
            "open": position.open_price,
            "attested": float(match.group(1)) if match else None,
            "field": position.stop_loss if position.stop_loss else None,
            "fill": position.close_price,
            "att": (direction * (float(match.group(1)) - position.open_price) / step
                    if match else None),
            "fld": (direction * (position.stop_loss - position.open_price) / step
                    if position.stop_loss else None),
            "fil": direction * (position.close_price - position.open_price) / step,
            "opened": position.open_time,
        })

    print("=== 901018 tape: SL-labelled closures with a recoverable step ===")
    print(f"    total {len(rows)}   with an attested [sl X] price "
          f"{sum(1 for r in rows if r['att'] is not None)}   "
          f"with a position field {sum(1 for r in rows if r['fld'] is not None)}")
    print()

    print("=== part 1: negative locks per era, on each of the three instruments ===")
    print("    a negative lock = an armed stop on the LOSING side of the entry.")
    print("    StopScheduler::Calculate() cannot produce one (see docstring), so any")
    print("    era-instrument cell that is non-zero is either a third behaviour or a")
    print("    measurement defect -- and the three columns discriminate between them.")
    print()
    print(f"    {'era':16s} {'n(att)':>7} {'neg att':>8} {'n(fld)':>7} {'neg fld':>8} "
          f"{'n(fil)':>7} {'neg fil':>8}")
    order = [name for name, _s, _e in ERAS]
    per_era = collections.defaultdict(list)
    for row in rows:
        per_era[row["era"]].append(row)
    for era in order + [k for k in per_era if k not in order]:
        if era not in per_era:
            continue
        group = per_era[era]
        cells = []
        for key in ("att", "fld", "fil"):
            values = [r[key] for r in group if r[key] is not None]
            negative = sum(1 for v in values if v < -0.005)
            cells.append((len(values), negative))
        print(f"    {era:16s} " + " ".join(
            f"{n:>7d} {neg:>8d}" for n, neg in cells))
    print()

    print("=== part 2: every AGGRESSIVE_30 measurement, all three instruments ===")
    aggressive = sorted(per_era.get("AGGRESSIVE_30", []),
                        key=lambda r: (r["fld"] if r["fld"] is not None else 0.0))
    print(f"    n = {len(aggressive)}   [the V4 audit reported 9 of 29 negative, "
          f"min -7.18]")
    print("      ticket     side lvl cyc  step   open      attested   field      fill    "
          "  att      fld      fil")
    for row in aggressive:
        attested = f"{row['attested']:9.2f}" if row["attested"] is not None else "        -"
        field = f"{row['field']:9.2f}" if row["field"] is not None else "        -"
        att = f"{row['att']:+8.3f}" if row["att"] is not None else "       -"
        fld = f"{row['fld']:+8.3f}" if row["fld"] is not None else "       -"
        print(f"      {row['ticket']:10d} {row['side']:4s} "
              f"{(row['level'] if row['level'] else 0):3d} {row['cycle']:3d} "
              f"{row['step']:5.2f} {row['open']:9.2f} {attested} {field} "
              f"{row['fill']:9.2f}  {att} {fld} {row['fil']:+8.3f}")
    print()

    print("=== part 3: does the attested price rescue the field's negatives? ===")
    print("    a field-negative whose attested price is NON-negative is proof that the")
    print("    field was a stale write and the EA never armed a losing stop.")
    both = [r for r in rows if r["att"] is not None and r["fld"] is not None]
    field_negative = [r for r in both if r["fld"] < -0.005]
    rescued = [r for r in field_negative if r["att"] >= -0.005]
    print(f"    positions measurable on BOTH instruments: {len(both)}")
    print(f"    negative on the FIELD: {len(field_negative)}")
    print(f"    of those, NON-negative on the attested price: {len(rescued)} "
          f"({100.0*len(rescued)/max(1,len(field_negative)):.1f}%)")
    still = [r for r in field_negative if r["att"] < -0.005]
    print(f"    still negative on the attested price: {len(still)}")
    if still:
        print("      ticket     era              side  step   open      attested    att")
        for row in sorted(still, key=lambda r: r["att"])[:25]:
            print(f"      {row['ticket']:10d} {row['era']:16s} {row['side']:5s} "
                  f"{row['step']:5.2f} {row['open']:9.2f} {row['attested']:9.2f} "
                  f"{row['att']:+8.3f}")
    print()

    print("=== part 4: the clamp escape hatch -- could stops_level explain a negative? ===")
    print("    the clamp binds only when stops_level*point > favorable*step, and")
    print("    favorable >= 2.0 at the gate, so it needs 2*step < stops_level*point.")
    print("    XAUUSD point = 0.01, so a 50-point stops_level is 0.50 in price.")
    steps = sorted({round(r["step"], 2) for r in rows})
    at_risk = [s for s in steps if 2.0 * s < 0.50]
    print(f"    distinct cycle steps on this tape: {len(steps)}  "
          f"min {steps[0]:.2f}  max {steps[-1]:.2f}")
    print(f"    steps small enough for a 0.50 clamp to bind at the gate "
          f"(2*step < 0.50): {len(at_risk)}"
          + (f"  -> {at_risk}" if at_risk else "  -> NONE, so the clamp is excluded"))
    print()

    print("=== part 5: the forbidden band per era, on the attested instrument only ===")
    print(f"    {'era':16s} {'n':>6} {'<0':>5} {'[0,1)':>7} {'[1,1.95)':>9} "
          f"{'[1.95,2)':>9} {'>=2':>7}")
    for era in order + [k for k in per_era if k not in order]:
        if era not in per_era:
            continue
        values = [r["att"] for r in per_era[era] if r["att"] is not None]
        if not values:
            continue
        buckets = [
            sum(1 for v in values if v < -0.005),
            sum(1 for v in values if -0.005 <= v < 1.0),
            sum(1 for v in values if 1.0 <= v < 1.95),
            sum(1 for v in values if 1.95 <= v < 2.0),
            sum(1 for v in values if v >= 2.0),
        ]
        print(f"    {era:16s} {len(values):>6d} " + " ".join(
            f"{b:>{w}d}" for b, w in zip(buckets, (5, 7, 9, 9, 7))))
    print()
    every = [r["att"] for r in rows if r["att"] is not None]
    if every:
        print(f"    ALL ERAS attested: n={len(every)}  median "
              f"{statistics.median(every):+.4f}  "
              f"negative {sum(1 for v in every if v < -0.005)}  "
              f"band[1,1.95) {sum(1 for v in every if 1.0 <= v < 1.95)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
