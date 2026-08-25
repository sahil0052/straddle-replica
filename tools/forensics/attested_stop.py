"""The broker's own attestation of the stop that fired.  The cleanest ratchet instrument.

Every `sl`-labelled exit order carries the comment `[sl <price>]` -- see
linkage.SL_RE.  That price is the BROKER's record of the stop level that
triggered, written at trigger time.  It is independent of two things I have been
relying on:

  * `position.stop_loss`  -- the level on the position record.  For a RATCHETING
    stop this is the newest write, which is not necessarily the one that fired.
    beat_their_stop.py found 192/2480 fills that beat this field by a median of
    0.857 steps, up to 5.765 -- too large for pacing, and not flatten-adjacent.
    That is the signature of a STALE FIELD, not of a mislabelled exit.

  * `position.close_price` -- the fill, which includes broker slippage.

So the ordering of instrument quality for measuring the EA's DECISION is:

      comment [sl X]   >   position.stop_loss   >   close_price
      (attested at         (newest write,          (+ slippage)
       trigger)             possibly newer
                            than the trigger)

This script re-runs the two ratchet edges on the attested price, and -- more
importantly -- tests the stale-field hypothesis directly: if `stop_loss` is the
newest write and the ratchet only ever tightens, then for the 192 the attested
price must be LOOSER than the field, and never tighter.  A monotone ratchet
forbids the other direction.  That is a sharp, falsifiable prediction about a
field I have not used before, and it decides whether those 192 are an anomaly
or an artifact of reading the wrong column.
"""
from __future__ import annotations

import statistics
import sys

sys.path.insert(0, r"C:\websites\mt5 2")
from tools.forensics.dataset import load_all, FINAL_REGIME_START  # noqa: E402
from tools.forensics.linkage import link_exits, exit_reason, SL_RE  # noqa: E402


def main() -> None:
    orders, positions, deals, cycles = load_all()
    exit_order, _ed, _en, _st = link_exits(orders, positions, deals)

    fin = [c for c in cycles if c.start >= FINAL_REGIME_START]
    step_by_cycle = {c.index: c.step for c in fin if c.step}
    fin_idx = {c.index for c in fin}

    rows = []
    no_price = 0
    for p in positions:
        if p.cycle not in fin_idx or p.is_open or p.close_time is None:
            continue
        if exit_reason(p, exit_order) != "sl":
            continue
        st = step_by_cycle.get(p.cycle)
        if not st or p.close_price is None:
            continue
        o = exit_order.get(p.position_id)
        m = SL_RE.fullmatch(o.comment or "")
        if not m:
            no_price += 1
            continue
        att = float(m.group(1))
        d = p.dir
        rows.append(dict(
            cyc=p.cycle,
            att=d * (att - p.open_price) / st,
            fld=(d * (p.stop_loss - p.open_price) / st) if p.stop_loss else None,
            fil=d * (p.close_price - p.open_price) / st,
            # positive = attested stop is LOOSER (further from entry's profit
            # side) than the field, i.e. the field is a NEWER, tighter write
            loose=((d * (p.stop_loss - att) / st) if p.stop_loss else None),
            vol=round(p.volume, 2),
        ))

    print("=" * 100)
    print("A. IS THE POSITION'S stop_loss FIELD A NEWER WRITE THAN THE ONE THAT FIRED?")
    print("=" * 100)
    print(f"  sl-labelled closures with an attested price : {len(rows)}"
          f"   (no price in comment: {no_price})")
    withf = [r for r in rows if r["fld"] is not None]
    same = [r for r in withf if abs(r["loose"]) <= 0.02]
    newer = [r for r in withf if r["loose"] > 0.02]
    older = [r for r in withf if r["loose"] < -0.02]
    n = len(withf)
    print()
    print(f"    field == attested (within 0.02 step) : {len(same):>5}"
          f" = {100.0*len(same)/n:.1f}%")
    print(f"    field TIGHTER than attested          : {len(newer):>5}"
          f" = {100.0*len(newer)/n:.1f}%   <- a later ratchet write")
    print(f"    field LOOSER  than attested          : {len(older):>5}"
          f" = {100.0*len(older)/n:.1f}%   <- FORBIDDEN by monotonicity")
    print()
    print("  StopScheduler::Calculate returns desired>current_sl (buys) /"
          " desired<current_sl")
    print("  (sells), so a written stop can only ever tighten.  The third line must")
    print("  therefore be ~0.  If it is, the field is simply the newest write and the")
    print("  192 'fills that beat their stop' were me reading a newer column than the")
    print("  one the broker fired on -- an instrument error, not an EA anomaly.")
    if newer:
        g = sorted(r["loose"] for r in newer)
        print()
        print(f"  how much tighter, when tighter : median {statistics.median(g):.3f}"
              f"  p90 {g[9*len(g)//10]:.3f}  max {g[-1]:.3f}  (steps)")

    print()
    print("=" * 100)
    print("B. THE 2.0 WALL ON THE ATTESTED PRICE  (the best instrument available)")
    print("=" * 100)
    edges = [0.50, 1.00, 1.25, 1.50, 1.75, 1.90, 1.95,
             2.00, 2.05, 2.10, 2.25, 2.50, 3.00]
    print(f"  {'bin (steps locked)':>22} {'n':>7} {'per 0.05 step':>15}")
    for lo, hi in zip(edges, edges[1:]):
        k = sum(1 for r in rows if lo <= r["att"] < hi)
        print(f"  {f'[{lo:.2f}, {hi:.2f})':>22} {k:>7}"
              f" {k/((hi-lo)/0.05):>15.1f}")
    blw = sum(1 for r in rows if 1.00 <= r["att"] < 2.00)
    tail = sum(1 for r in rows if 1.00 <= r["att"] < 1.95)
    abv = sum(1 for r in rows if 2.00 <= r["att"] < 2.25)
    print()
    print(f"  attested stops in the forbidden band (1.00,2.00) : {blw}")
    print(f"  ... excluding the tick-quantisation lip [1.95,2.00) : {tail}")
    print(f"  attested stops just above the wall  [2.00,2.25)  : {abv}")

    print()
    print("=" * 100)
    print("C. BREAKEVEN ACTIVATION ON THE ATTESTED PRICE")
    print("=" * 100)
    sp = [r["att"] for r in rows if -0.25 <= r["att"] < 0.25]
    if sp:
        s = sorted(sp)
        exact = sum(1 for x in s if abs(x) < 0.005)
        print(f"  attested stops in the breakeven spike : {len(s)}")
        print(f"  locked at activation (steps)          : median"
              f" {statistics.median(s):+.4f}"
              f"   p10 {s[len(s)//10]:+.4f}   p90 {s[9*len(s)//10]:+.4f}")
        print(f"  within 0.005 steps of EXACT breakeven : {exact}/{len(s)}"
              f" = {100.0*exact/len(s):.0f}%")
        print()
        print("  activation_uses_trailing_distance=true writes"
              " market - pre_tighten*step at the")
        print("  first poll where favorable_steps >= lock_trigger.  With both equal to 2.0")
        print("  that is `entry` exactly, so this median must sit on zero, and any offset")
        print("  must be POSITIVE (the 100ms poll sees the crossing late, never early).")

    print()
    print("=" * 100)
    print("D. THE THREE INSTRUMENTS, SAME POPULATION")
    print("=" * 100)
    for lab, key in (("attested [sl X]", "att"),
                     ("position field", "fld"),
                     ("actual fill", "fil")):
        v = sorted(r[key] for r in rows if r[key] is not None)
        hole = sum(1 for x in v if 1.0 <= x < 2.0)
        print(f"  {lab:>18} : n={len(v):<5} median {statistics.median(v):>6.3f}"
              f"   in forbidden band {hole:>4} = {100.0*hole/len(v):>5.2f}%")
    print()
    print("  The forbidden band should be emptiest on the best instrument and")
    print("  fullest on the worst.  That monotone ordering is the whole argument:")
    print("  the band fills up exactly as much as the measurement degrades.")


if __name__ == "__main__":
    main()
