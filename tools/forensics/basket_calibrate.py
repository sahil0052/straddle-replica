"""CALIBRATE the reconstruction against the Target's own decision instant.

Everything so far has scored my reconstruction against a threshold without ever
asking whether the reconstruction is accurate.  There is a free calibration point in
every cycle and I have not used it: at t0, the instant the Target itself chose to
flatten, its own value WAS the threshold.  So:

    value@t0 ~ 30      -> R and floating are right for that cycle.
    value@t0 >> 30     -> my R or my mark is biased HIGH there, and "eligible 5 hours
                          early" is that same bias showing up earlier in the cycle.
    value@t0 << 30     -> biased low; the sub-30 flattens are my error, not a rule.

This is the test that decides whether the gated set is a finding or an artifact,
because a bias visible at t0 cannot be blamed on the Target.

Two supporting corrections to earlier runs:

  * in_break() only found the intraday rollover (22:58-23:59), so cycle 244's
    crossing print -- gap-before 177,824 s, the Fri->Mon weekend -- passed as a
    liquid mark.  Any print separated from the previous one by a long silence is a
    gapped mark: resting stops fill at extremes on the reopen and the accumulator
    values the ENTIRE basket at that extreme.  Gap-before is the general filter and
    it subsumes both the daily break and the weekend.

  * a 0.125 half-spread leaves 66 of 99 cycles never reaching 30 at all, when the
    Target demonstrably flattened at ~30 on them.  So 0.125 is too harsh, and the
    "plateau at 8 gated cycles" was measured while the denominator collapsed from 40
    to 33 -- the gated RATE was climbing, not plateauing.  Calibration fixes the
    spread instead of guessing it: pick the half-spread that centres value@t0 on 30.
"""
from __future__ import annotations

import statistics
import sys

sys.path.insert(0, r"C:\websites\mt5 2")
from tools.forensics.dataset import load_all, FINAL_REGIME_START, CONTRACT  # noqa: E402

TARGET = 30.0
GATED = {194, 252, 187, 244, 250, 197, 219, 253, 181, 269}


def main() -> None:
    orders, positions, deals, cycles = load_all()
    fin = [c for c in cycles if c.start >= FINAL_REGIME_START]

    marks = []
    for p in positions:
        marks.append((p.open_time, p.open_price))
        if p.close_time and p.close_price:
            marks.append((p.close_time, p.close_price))
    marks.sort(key=lambda r: r[0])

    rows = []
    for c in fin:
        cl = [o.open_time for o in c.orders
              if o.comment and o.comment.strip().upper().startswith("STR CLOSE")]
        if not cl or not c.end:
            continue
        t_close = min(cl)
        acts = []
        for o in c.orders:
            if not o.is_grid:
                continue
            if o.open_time and o.open_time <= t_close:
                acts.append((o.open_time, "place"))
            if o.state == "canceled" and o.end_time and o.end_time <= t_close:
                acts.append((o.end_time, "cancel"))
        acts.sort()
        t0 = t_close
        k = len(acts) - 1
        while k >= 0 and acts[k][1] == "cancel":
            t0 = acts[k][0]
            k -= 1

        rel = [p for p in positions
               if p.open_time <= t_close and (p.is_open or
                                              (p.close_time and p.close_time >= c.start))]
        ev = []
        for p in rel:
            a = p.dir * p.volume * CONTRACT
            g = p.volume * CONTRACT
            ev.append((p.open_time, 0, a, a * p.open_price, p.swap, 0.0, g))
            if p.close_time:
                ev.append((p.close_time, 1, -a, -a * p.open_price, -p.swap,
                           p.net if p.close_time >= c.start else 0.0, -g))
        ev.sort(key=lambda r: (r[0], r[1]))

        A = B = C = R = G = 0.0
        j = 0
        trail = []          # (t, gap_before, raw_value, gross)
        prev = None
        for t, m in marks:
            if t < c.start:
                continue
            if t > t0:
                break
            while j < len(ev) and ev[j][0] <= t:
                _, _, da, db, dc, dr, dg = ev[j]
                A += da; B += db; C += dc; R += dr; G += dg
                j += 1
            trail.append((t, (t - prev).total_seconds() if prev else 1e9,
                          R + m * A - B + C, G))
            prev = t
        if not trail:
            continue
        # R at t0, split by who opened the position -- the attribution check
        r_own = sum(p.net for p in rel if p.close_time and p.close_time >= c.start
                    and p.open_time >= c.start)
        r_carry = sum(p.net for p in rel if p.close_time and p.close_time >= c.start
                      and p.open_time < c.start)
        rows.append(dict(i=c.index, t0=t0, trail=trail, final=c.realized,
                         r_own=r_own, r_carry=r_carry, start=c.start))

    # ---- A. calibrate the half-spread on value@t0 --------------------------
    print("=" * 104)
    print("A. CALIBRATION -- at the Target's OWN flatten instant, the value must be ~30")
    print("=" * 104)
    print(f"  {'half':>6} {'median@t0':>10} {'mean@t0':>9} {'in [28,34]':>11}"
          f" {'below 30':>9}")
    best, bestd = 0.0, 1e18
    for half in (0.0, 0.02, 0.04, 0.06, 0.08, 0.10, 0.125, 0.15):
        v = [r["trail"][-1][2] - half * r["trail"][-1][3] for r in rows]
        med = statistics.median(v)
        band = sum(1 for x in v if 28.0 <= x <= 34.0)
        print(f"  {half:>6.3f} {med:>10.2f} {statistics.mean(v):>9.2f}"
              f" {band:>7}/{len(v)} {sum(1 for x in v if x < 30):>9}")
        if abs(med - TARGET) < bestd:
            best, bestd = half, abs(med - TARGET)
    print(f"\n  best-centred half-spread: {best:.3f}  (median value@t0 lands on 30)")

    v0 = [r["trail"][-1][2] - best * r["trail"][-1][3] for r in rows]
    print(f"  spread of value@t0 at that setting: p10 {sorted(v0)[len(v0)//10]:.2f}"
          f"  median {statistics.median(v0):.2f}"
          f"  p90 {sorted(v0)[9*len(v0)//10]:.2f}")
    print("  -> a tight band around 30 means the reconstruction is sound; wide tails")
    print("     mean the tails of every other panel are MY error, not the Target's.")

    # ---- B. is the reconstruction biased on the gated cycles? -------------
    print()
    print("=" * 104)
    print("B. THE GATED CYCLES -- what does the calibration point say about them?")
    print("=" * 104)
    print("  If value@t0 is far above 30 on exactly these cycles, the early")
    print("  'eligibility' is the same bias, seen earlier.")
    print()
    print(f"  {'cyc':>5} {'value@t0':>9} {'R own':>9} {'R carry':>9} {'carry %':>8}"
          f" {'final':>9}  reading")
    for r in sorted((x for x in rows if x["i"] in GATED), key=lambda r: -r["trail"][-1][2]):
        vt = r["trail"][-1][2] - best * r["trail"][-1][3]
        tot = abs(r["r_own"]) + abs(r["r_carry"])
        pct = (abs(r["r_carry"]) / tot * 100.0) if tot else 0.0
        note = ("value@t0 >> 30 -> reconstruction biased HIGH" if vt > 60
                else "value@t0 ~ 30 -> reconstruction OK here" if 20 <= vt <= 45
                else "value@t0 off target")
        print(f"  {r['i']:>5} {vt:>9.2f} {r['r_own']:>9.2f} {r['r_carry']:>9.2f}"
              f" {pct:>7.1f}% {r['final']:>9.2f}  {note}")

    # ---- C. re-score with the calibrated spread AND a gap filter ----------
    print()
    print("=" * 104)
    print("C. RE-SCORE: calibrated spread + reject gapped marks")
    print("=" * 104)
    print("  A crossing only counts if the previous print was recent -- otherwise the")
    print("  mark is stale and the whole basket is being valued at a gap extreme.")
    print()
    print(f"  {'max gap':>9} {'scored':>7} {'on time':>8} {'GATED':>6} {'sub-30':>7}"
          f"   gated cycles")
    for maxgap in (1e9, 600.0, 300.0, 120.0, 60.0):
        on = gt = nv = 0
        ids = []
        for r in rows:
            hit = next(((t, v - best * g) for t, gp, v, g in r["trail"]
                        if gp <= maxgap and v - best * g >= TARGET), None)
            if hit is None:
                nv += 1
            elif (r["t0"] - hit[0]).total_seconds() > 120:
                gt += 1
                ids.append(r["i"])
            else:
                on += 1
        print(f"  {maxgap if maxgap < 1e8 else 0:>9.0f} {len(rows):>7} {on:>8} {gt:>6}"
              f" {nv:>7}   {','.join(map(str, ids))}")
    print()
    print("  gap=0 means no filter.  Watch whether the gated set shrinks as stale marks")
    print("  are excluded: an artifact does, a real rule does not.")

    # ---- D. money, with honest signs --------------------------------------
    print()
    print("=" * 104)
    print("D. MONEY -- signed both ways, no netting sleight of hand")
    print("=" * 104)
    hits = []
    for r in rows:
        hit = next(((t, v - best * g) for t, gp, v, g in r["trail"]
                    if gp <= 300.0 and v - best * g >= TARGET), None)
        if hit and (r["t0"] - hit[0]).total_seconds() > 120:
            hits.append((r, hit))
    allm = sum(abs(c.realized) for c in fin)
    net = sum(c.realized for c in fin)
    worse = sum(min(0.0, h[1] - r["final"]) for r, h in hits)
    better = sum(max(0.0, h[1] - r["final"]) for r, h in hits)
    print(f"  cycles where the replica would have exited early: {len(hits)}")
    print(f"    replica WORSE off by : ${abs(worse):,.2f}")
    print(f"    replica BETTER off by: ${better:,.2f}")
    print(f"    net effect on the replica: ${better + worse:+,.2f}")
    print(f"  gross divergence |worse|+|better| = ${abs(worse)+better:,.2f}"
          f"  = {(abs(worse)+better)/allm:.2%} of ledger |money| (${allm:,.2f})")
    print(f"  net realised over the window: ${net:,.2f}")
    print()
    print("  The gross figure is the honest bound on this rule's parity risk: it is the")
    print("  money that lands differently, regardless of which way it lands.")


if __name__ == "__main__":
    main()
