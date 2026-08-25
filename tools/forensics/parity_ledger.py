"""Money-weighted parity ledger, and a hunt for the UNAUDITED surface.

"Is the replica 99.9% the same as the Target EA?" is not answerable by counting
parameters.  Parameters are not equally weighted: `trail_distance_steps` governs
every one of 2,695 SL closures while `trend_rescue_bars` governs 6 events in 100
cycles.  A parity claim has to be weighted by the money and the decision volume
each rule actually controls.

Part 1 does that.  Every final-regime dollar is attributed to the rule that
produced it, and each rule carries the confidence label the audit earned:

    EXACT     reproduced to the tick on both sides of the Jul-24 regime break
    BOUNDED   the mechanism is proven, the constant has residual error
    UNKNOWN   no rule reproduces it

Part 2 is the more important half, and it is the reason "99.9%" cannot be
asserted.  Every audit so far has been driven by a question I already knew to
ask (ratchet, rescue, basket, queue).  The risk to a parity claim is not the
residual inside an audited rule -- it is a rule the Target EA has that I never
thought to look for.  So this half enumerates the behavioural surface that has
NEVER been tested against the report and tests it:

    B1  session / time-of-day gating on cycle starts
    B2  flatten -> redeploy latency vs restart_delay_ms = 20 s
    B3  weekday coverage: Friday-close flatten?  Sunday-open deploy?
    B4  non-grid (manual / non-STR) trading in the final regime
    B5  volume exceptions outside the confirmed tier + rescue set
    B6  lattice geometry stability (levels_per_side, anchor divisor)
    B7  SL-model residual: how many SL closures does the ratchet NOT explain?
    B8  concurrent-cycle overlap (positions surviving past the next deployment)
"""
from __future__ import annotations

import statistics
import sys
from collections import Counter, defaultdict
from datetime import timedelta

sys.path.insert(0, r"C:\websites\mt5 2")
from tools.forensics.dataset import load_all, FINAL_REGIME_START  # noqa: E402

TIERS = {0.01, 0.02, 0.06, 0.12, 0.15, 0.30}
SL_TOL = 0.60          # points; XAUUSD step is ~1.33 so this is <0.5 step
FLATTEN_WINDOW = 300.0  # seconds: closes within this of the LAST close = one sweep


def bar(frac: float, width: int = 34) -> str:
    n = int(round(frac * width))
    return "#" * n + "." * (width - n)


def main() -> None:
    orders, positions, deals, cycles = load_all()
    fin = [c for c in cycles if c.start >= FINAL_REGIME_START]

    # ================================================================== PART 1
    print("=" * 100)
    print("PART 1.  MONEY-WEIGHTED PARITY LEDGER  (final regime, Jul 14-30)")
    print("=" * 100)

    buckets: dict[str, list[float]] = defaultdict(list)
    counts: Counter[str] = Counter()
    anomalous_cycles: list[tuple[int, float, int]] = []

    for c in fin:
        closed = [p for p in c.positions if not p.is_open]
        if not closed:
            continue
        last = max(p.close_time for p in closed)
        sweep_cut = last - timedelta(seconds=FLATTEN_WINDOW)

        cyc_flatten_money = 0.0
        for p in closed:
            at_sl = (p.stop_loss is not None and p.close_price is not None
                     and abs(p.close_price - p.stop_loss) <= SL_TOL)
            in_sweep = p.close_time >= sweep_cut
            if at_sl and not in_sweep:
                key = "sl_ratchet"
            elif at_sl and in_sweep:
                key = "sl_in_sweep"
            elif in_sweep:
                key = "basket_flatten"
                cyc_flatten_money += p.net
            else:
                key = "other_close"
            buckets[key].append(p.net)
            counts[key] += 1

        net_exit = cyc_flatten_money
        if net_exit < -25.0:
            anomalous_cycles.append((c.index, net_exit,
                                     sum(1 for p in closed
                                         if p.close_time >= sweep_cut)))

    total_money = sum(sum(v) for v in buckets.values())
    total_pos = sum(counts.values())

    print()
    print(f"  {'bucket':<18} {'positions':>10} {'net $':>12} {'|$| share':>10}  "
          f"{'rule':<26} confidence")
    absall = sum(abs(x) for v in buckets.values() for x in v)
    labels = {
        "sl_ratchet":     ("2-stage trailing ratchet", "EXACT"),
        "sl_in_sweep":    ("ratchet (SL hit in sweep)", "EXACT"),
        "basket_flatten": ("$30 net basket target", "EXACT*"),
        "other_close":    ("no rule reproduces this", "UNKNOWN"),
    }
    for k in ("sl_ratchet", "sl_in_sweep", "basket_flatten", "other_close"):
        v = buckets.get(k, [])
        share = sum(abs(x) for x in v) / absall if absall else 0.0
        rule, conf = labels[k]
        print(f"  {k:<18} {len(v):>10} {sum(v):>12.2f} {share:>9.1%}  "
              f"{rule:<26} {conf}")
    print(f"  {'-'*96}")
    print(f"  {'TOTAL':<18} {total_pos:>10} {total_money:>12.2f}")

    print()
    print("  * the $30 target is EXACT as a rule, but 6 of 100 cycles exit far below")
    print("    it with no discoverable trigger.  Those cycles' money is the real")
    print("    exposure, so it is broken out separately:")
    print()
    an_money = sum(m for _, m, _ in anomalous_cycles)
    print(f"  {'cyc':>5} {'exit net $':>12} {'positions in sweep':>20}")
    for i, m, n in anomalous_cycles:
        print(f"  {i:>5} {m:>12.2f} {n:>20}")
    print(f"  {'-'*40}")
    print(f"  {len(anomalous_cycles):>5} cycles {an_money:>10.2f} total at risk")
    if absall:
        print(f"\n  unexplained share of |money| = "
              f"{(sum(abs(x) for x in buckets.get('other_close', [])) + abs(an_money)) / absall:.2%}")

    # ================================================================== PART 2
    print()
    print("=" * 100)
    print("PART 2.  THE UNAUDITED SURFACE  -- rules I never thought to look for")
    print("=" * 100)

    # ---- B1 session gating ------------------------------------------------
    print()
    print("B1. CYCLE-START HOUR  (a session filter the replica does not have?)")
    hh = Counter(c.start.hour for c in fin)
    for h in range(24):
        n = hh.get(h, 0)
        print(f"    {h:02d}:00  {n:>3}  {bar(n / max(hh.values()) if hh else 0)}")
    empty = [h for h in range(24) if hh.get(h, 0) == 0]
    print(f"    hours with ZERO starts: {empty if empty else 'none'}")
    print(f"    -> {'SUSPECT session gate' if len(empty) >= 6 else 'no session gate evident'}")

    # ---- B2 restart latency ----------------------------------------------
    print()
    print("B2. FLATTEN -> NEXT DEPLOYMENT LATENCY  (restart_delay_ms = 20 s)")
    lat = []
    for c in fin:
        if c.end and c.flat_time:
            lat.append(((c.end - c.flat_time).total_seconds(), c.index,
                        c.flat_time, c.end))
    lat.sort()
    near = [x for x, *_ in lat if 15.0 <= x <= 40.0]
    print(f"    n={len(lat)}  median={statistics.median([x for x,*_ in lat]):.1f}s  "
          f"min={lat[0][0]:.1f}s  max={lat[-1][0]:.1f}s")
    print(f"    within [15,40] s of the 20 s floor: {len(near)}/{len(lat)} "
          f"= {len(near)/len(lat):.0%}")
    print(f"    the {min(6, len(lat))} SHORTEST (a sub-20 s restart would refute the floor):")
    for x, i, ft, st in lat[:6]:
        print(f"      cyc {i:>4}  {x:>9.1f}s   flat {str(ft)[:19]} -> deploy {str(st)[:19]}")
    print(f"    the {min(8, len(lat))} LONGEST (long gaps need a non-timer explanation):")
    for x, i, ft, st in lat[-8:]:
        wd = ft.strftime("%a")
        print(f"      cyc {i:>4}  {x/3600:>7.2f}h   flat {str(ft)[:19]} ({wd}) "
              f"-> deploy {str(st)[:19]} ({st.strftime('%a')})")

    # ---- B3 weekday coverage ---------------------------------------------
    print()
    print("B3. WEEKDAY COVERAGE of deployments and of the last close")
    wd_start = Counter(c.start.strftime("%a") for c in fin)
    wd_flat = Counter(c.flat_time.strftime("%a") for c in fin if c.flat_time)
    for d in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"):
        print(f"    {d}  deploys {wd_start.get(d,0):>3}   flattens {wd_flat.get(d,0):>3}")

    # ---- B4 non-grid trading ---------------------------------------------
    print()
    print("B4. NON-GRID ACTIVITY in the final regime (manual / other EA)")
    fin_pos = [p for c in fin for p in c.positions]
    ng = [p for p in fin_pos if p.grid_side is None]
    print(f"    positions: {len(fin_pos)} total, {len(ng)} non-STR "
          f"({len(ng)/max(1,len(fin_pos)):.2%})")
    if ng:
        print(f"    non-STR net $ = {sum(p.net for p in ng):.2f}")
        for cm, n in Counter(p.comment or "<blank>" for p in ng).most_common(8):
            print(f"      {n:>5}x  {cm!r}")
    fin_ord = [o for c in fin for o in c.orders]
    ngo = [o for o in fin_ord if not o.is_grid]
    print(f"    orders: {len(fin_ord)} total, {len(ngo)} non-STR")
    for cm, n in Counter((o.comment or "<blank>")[:40] for o in ngo).most_common(8):
        print(f"      {n:>5}x  {cm!r}")

    # ---- B5 volume exceptions -------------------------------------------
    print()
    print("B5. VOLUME EXCEPTIONS outside {0.01,0.02,0.06,0.12,0.15,0.30}")
    vex = Counter(o.volume for o in fin_ord if o.is_grid and o.volume not in TIERS)
    print(f"    grid orders off-tier: {sum(vex.values())}   {dict(vex) if vex else '(none)'}")
    mis = 0
    for o in fin_ord:
        if not o.is_grid or o.level is None:
            continue
        base = 0.01 if o.level <= 10 else (0.06 if o.level <= 20 else 0.15)
        if abs(o.volume - base) > 1e-9 and abs(o.volume - 2 * base) > 1e-9:
            mis += 1
    print(f"    grid orders that are neither 1x nor 2x their tier: {mis}")

    # ---- B6 geometry stability ------------------------------------------
    print()
    print("B6. LATTICE GEOMETRY stability across the 100 cycles")
    lv = Counter(c.levels_per_side for c in fin)
    div = [c.anchor / c.step for c in fin if c.step]
    print(f"    levels_per_side: {dict(lv)}")
    print(f"    anchor/step: median={statistics.median(div):.2f}  "
          f"min={min(div):.2f}  max={max(div):.2f}  "
          f"stdev={statistics.pstdev(div):.2f}")
    off = [c.index for c in fin if c.step and abs(c.anchor / c.step - 3000.0) > 25.0]
    print(f"    cycles more than 25 off a 3000 divisor: {off if off else 'none'}")

    # ---- B7 SL residual --------------------------------------------------
    print()
    print("B7. SL-MODEL RESIDUAL  -- SL closures the ratchet does NOT explain")
    print("    ratchet: activate at 2.0 steps (SL=breakeven), 2.0-step trail until")
    print("    3.0 steps, then 1.0-step trail.  So SL profit/step must be either")
    print("    in [0,1) (pre-tighten) or >=2 (post-tighten).  The GAP is (1,2).")
    sl = []
    for c in fin:
        if not c.step:
            continue
        for p in c.positions:
            if p.is_open or p.stop_loss is None or p.close_price is None:
                continue
            if abs(p.close_price - p.stop_loss) > SL_TOL:
                continue
            steps = (p.dir * (p.close_price - p.open_price)) / c.step
            sl.append((steps, c.index, p.position_id))
    inband = sum(1 for s, *_ in sl if 1.0 < s < 2.0)
    neg = sum(1 for s, *_ in sl if s < -0.05)
    print(f"    SL closures matched: {len(sl)}")
    print(f"    profit in the FORBIDDEN (1,2)-step gap: {inband} "
          f"({inband/max(1,len(sl)):.2%})")
    print(f"    profit BELOW entry (SL under entry -- must be 0): {neg}")
    hist = Counter(min(9, int(max(0.0, s))) for s, *_ in sl)
    for k in sorted(hist):
        print(f"      [{k},{k+1}) steps  {hist[k]:>5}  "
              f"{bar(hist[k]/max(hist.values()))}")

    # ---- B8 cycle overlap ------------------------------------------------
    print()
    print("B8. CYCLE OVERLAP -- positions alive past the next deployment")
    ov = 0
    for c in fin:
        if not c.end:
            continue
        for p in c.positions:
            if p.close_time and p.close_time > c.end + timedelta(seconds=1):
                ov += 1
    print(f"    positions closing AFTER the next cycle's first pending: {ov}")
    print(f"    -> {'baskets OVERLAP; single-basket assumption is wrong' if ov else 'baskets are strictly serial (single-basket model holds)'}")


if __name__ == "__main__":
    main()
