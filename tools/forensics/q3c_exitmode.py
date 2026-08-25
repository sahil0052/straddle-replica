"""Q3c: is there ONE exit rule or TWO?

q3b showed the trigger total (ledger A) sits at med 34.77 / p25 27.92 / p75 42.42
with a hard mass just above 30 -- exactly what a $30 threshold sampled on a 20 s
timer predicts (the basket moves sum(vol)*100 dollars per point, so a $30 line is
observed at 30 + overshoot).  But 15 of 99 cycles flattened BELOW $25, some deeply
negative.  Those cannot be a profit exit.

Hypotheses for the sub-target flattens:
  (R1) forced re-centre: price ran too far from the anchor, or one side's levels
       were exhausted, so the EA flattens and redeploys at a new anchor
  (R2) drawdown / equity stop
  (R3) target is a % of balance, not a fixed $30 (cycle_target_balance_pct=0.18)

Everything is snapshotted at the DECISION instant = start of the terminal cancel
sweep, i.e. BEFORE any pending is pulled, so the lattice state is intact.
"""
from __future__ import annotations

import statistics
import sys
from bisect import bisect_left
from collections import Counter, defaultdict

sys.path.insert(0, r"C:\websites\mt5 2")
from tools.forensics.dataset import load_all, FINAL_REGIME_START, CONTRACT  # noqa: E402
from tools.forensics.attribution import build_exit_index, attribute  # noqa: E402


def stats(vals, label):
    if not vals:
        print(f"  {label:<30} n=0")
        return
    v = sorted(vals)
    g = lambda f: v[int(f * (len(v) - 1))]
    print(f"  {label:<30} n={len(v):<4} min={v[0]:>9.2f} p10={g(.1):>8.2f} "
          f"p25={g(.25):>8.2f} med={statistics.median(v):>8.2f} p75={g(.75):>8.2f} "
          f"p90={g(.9):>8.2f} max={v[-1]:>9.2f}")


def main() -> None:
    orders, positions, deals, cycles = load_all()
    class_by_time, _, _ = build_exit_index(orders, deals)
    reason, _, _ = attribute(positions, class_by_time)

    pts = []
    for p in positions:
        pts.append((p.open_time, p.open_price))
        if p.close_time and p.close_price:
            pts.append((p.close_time, p.close_price))
    pts.sort()
    obs_t = [t for t, _ in pts]
    obs_p = [p for _, p in pts]

    def market_at(t):
        i = bisect_left(obs_t, t)
        c = []
        if i < len(obs_t):
            c.append((abs((obs_t[i] - t).total_seconds()), obs_p[i]))
        if i > 0:
            c.append((abs((t - obs_t[i - 1]).total_seconds()), obs_p[i - 1]))
        return min(c)[1]

    # running balance: cumulative net of every closed position, chronological
    closed = sorted((p.close_time, p.net) for p in positions
                    if not p.is_open and p.close_time)
    bal_t = [t for t, _ in closed]
    bal_c = []
    run = 0.0
    for _, n in closed:
        run += n
        bal_c.append(run)

    def cum_at(t):
        i = bisect_left(bal_t, t)
        return bal_c[i - 1] if i else 0.0

    pos_by_cycle = defaultdict(list)
    for p in positions:
        if p.cycle >= 0:
            pos_by_cycle[p.cycle].append(p)
    anchors = {c.index: (c.anchor, c.step) for c in cycles}

    rows = []
    for c in cycles:
        if c.start < FINAL_REGIME_START:
            continue
        ps = pos_by_cycle.get(c.index, [])
        closes = [p for p in ps if not p.is_open and p.close_time
                  and reason.get(p.position_id) == "STR CLOSE"]
        if not closes:
            continue
        first_close = min(p.close_time for p in closes)
        cans = sorted(o.end_time for o in c.orders
                      if o.is_grid and o.state == "canceled" and o.end_time
                      and o.end_time <= first_close)
        decision = first_close
        if cans:
            run_ = [cans[-1]]
            for a, b in zip(reversed(cans[:-1]), reversed(cans)):
                if (b - a).total_seconds() <= 30.0:
                    run_.append(a)
                else:
                    break
            decision = min(run_)
        market = market_at(decision)

        realized = 0.0
        floating = 0.0
        openB = openS = 0
        volB = volS = 0.0
        for p in ps:
            if p.open_time > decision:
                continue
            if not p.is_open and p.close_time and p.close_time <= decision:
                realized += p.net
            else:
                d = p.dir
                floating += d * (market - p.open_price) * p.volume * CONTRACT
                if p.side == "buy":
                    openB += 1
                    volB += p.volume
                else:
                    openS += 1
                    volS += p.volume

        # lattice state at the decision instant, BEFORE the sweep
        armedB = armedS = 0
        filledB = filledS = 0
        maxlvlB = maxlvlS = 0
        for o in c.orders:
            if not o.is_grid or o.open_time > decision:
                continue
            alive = (o.state == "placed") or (o.end_time and o.end_time > decision)
            consumed = (o.state == "filled" and o.end_time
                        and o.end_time <= decision)
            if o.side == "B":
                armedB += 1 if alive else 0
                if consumed:
                    filledB += 1
                    maxlvlB = max(maxlvlB, o.level or 0)
            else:
                armedS += 1 if alive else 0
                if consumed:
                    filledS += 1
                    maxlvlS = max(maxlvlS, o.level or 0)

        anchor, step = anchors[c.index]
        rows.append(dict(
            cyc=c.index, decision=decision, market=market, anchor=anchor, step=step,
            realized=realized, floating=floating, total=realized + floating,
            openB=openB, openS=openS, volB=volB, volS=volS,
            armedB=armedB, armedS=armedS, filledB=filledB, filledS=filledS,
            maxlvlB=maxlvlB, maxlvlS=maxlvlS,
            dist_pts=abs(market - anchor), dist_st=abs(market - anchor) / step,
            signed_st=(market - anchor) / step,
            cum=cum_at(decision),
            hrs=(decision - c.start).total_seconds() / 3600.0,
            nclose=len(closes),
            dollars_per_pt=(volB + volS) * CONTRACT,
        ))

    print(f"cycles: {len(rows)}\n")

    # ---- R3: is the target a % of balance? ---------------------------------
    print("=" * 96)
    print("R3  IS THE TARGET A PERCENTAGE OF BALANCE?")
    print("=" * 96)
    cums = [r["cum"] for r in rows]
    print(f"  cumulative realized over the final regime: "
          f"{min(cums):.0f} -> {max(cums):.0f} (grew {max(cums)-min(cums):.0f})")
    early = [r["total"] for r in sorted(rows, key=lambda r: r["cum"])[:33]]
    late = [r["total"] for r in sorted(rows, key=lambda r: r["cum"])[-33:]]
    print(f"  trigger total, lowest-balance third : med={statistics.median(early):.2f}")
    print(f"  trigger total, highest-balance third: med={statistics.median(late):.2f}")
    print("  -> a fixed $ target predicts these are equal; a % target predicts")
    print("     the late third is larger in proportion to balance growth.")

    # ---- split by whether the profit target was met -------------------------
    hit = [r for r in rows if r["total"] >= 28.0]
    miss = [r for r in rows if r["total"] < 28.0]
    print("\n" + "=" * 96)
    print(f"SPLIT: total >= $28 (profit exit) n={len(hit)}   "
          f"vs total < $28 (something else) n={len(miss)}")
    print("=" * 96)
    for lab, grp in (("HIT ", hit), ("MISS", miss)):
        print(f"\n  --- {lab} ---")
        stats([r["total"] for r in grp], "total")
        stats([r["realized"] for r in grp], "realized")
        stats([r["floating"] for r in grp], "floating")
        stats([r["dist_st"] for r in grp], "|market-anchor| steps")
        stats([r["dist_pts"] for r in grp], "|market-anchor| points")
        stats([r["openB"] + r["openS"] for r in grp], "open positions")
        stats([r["armedB"] + r["armedS"] for r in grp], "armed pendings")
        stats([max(r["maxlvlB"], r["maxlvlS"]) for r in grp], "deepest level consumed")
        stats([r["dollars_per_pt"] for r in grp], "$ per point of basket")
        stats([r["hrs"] for r in grp], "cycle age (h)")

    # ---- overshoot model ---------------------------------------------------
    print("\n" + "=" * 96)
    print("OVERSHOOT MODEL: a $30 line sampled on a 20s timer")
    print("=" * 96)
    print("  If the rule is total>=30 checked every 20s, overshoot should scale")
    print("  with $/point of the open basket (how fast the total moves).")
    print(f"  {'$/pt bucket':<16}{'n':>5}{'med total':>11}{'p90 total':>11}"
          f"{'min total':>11}")
    for lo, hi in [(0, 20), (20, 40), (40, 70), (70, 120), (120, 10**9)]:
        sel = [r for r in hit if lo <= r["dollars_per_pt"] < hi]
        if not sel:
            continue
        t = sorted(r["total"] for r in sel)
        print(f"  [{lo:>4},{hi if hi<10**9 else 999:>4})    {len(sel):>5}"
              f"{statistics.median(t):>11.2f}{t[int(.9*(len(t)-1))]:>11.2f}"
              f"{t[0]:>11.2f}")

    # ---- the MISS cycles in full detail ------------------------------------
    print("\n" + "=" * 96)
    print("EVERY SUB-TARGET FLATTEN, IN FULL")
    print("=" * 96)
    print(f"  {'cyc':>4} {'decision':<20} {'total':>8} {'real':>8} {'float':>9} "
          f"{'oB':>3} {'oS':>3} {'aB':>3} {'aS':>3} {'fB':>3} {'fS':>3} "
          f"{'lvlB':>5} {'lvlS':>5} {'dist_st':>8} {'$/pt':>7} {'hrs':>6}")
    for r in sorted(miss, key=lambda r: r["total"]):
        print(f"  {r['cyc']:>4} {r['decision'].strftime('%m-%d %H:%M:%S'):<20} "
              f"{r['total']:>8.2f} {r['realized']:>8.2f} {r['floating']:>9.2f} "
              f"{r['openB']:>3} {r['openS']:>3} {r['armedB']:>3} {r['armedS']:>3} "
              f"{r['filledB']:>3} {r['filledS']:>3} "
              f"{r['maxlvlB']:>5} {r['maxlvlS']:>5} {r['signed_st']:>8.2f} "
              f"{r['dollars_per_pt']:>7.1f} {r['hrs']:>6.1f}")

    # ---- is one side fully exhausted at the miss cycles? -------------------
    print("\n" + "=" * 96)
    print("LATTICE EXHAUSTION: armed pendings remaining per side at decision")
    print("=" * 96)
    for lab, grp in (("HIT ", hit), ("MISS", miss)):
        z = Counter()
        for r in grp:
            z[("B=0" if r["armedB"] == 0 else "B>0",
               "S=0" if r["armedS"] == 0 else "S>0")] += 1
        print(f"  {lab}: {dict(z)}")


if __name__ == "__main__":
    main()
