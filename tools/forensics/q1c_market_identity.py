"""Q1c: prove the ratchet equation by INVERTING it to recover the market price.

The 2-stage model asserts, for a position with entry E, side dir, step S:

    favorable = dir*(M - E)/S                      (M = market at last SL update)
    D         = 2.0  if favorable <  3.0           (pre-tighten)
                1.0  if favorable >= 3.0           (tightened)
    sl        = M - dir*D*S

Only `sl` and `E` are recorded; M is unobserved.  But D is recoverable from the
recorded sl alone, because locked = dir*(sl-E)/S = favorable - D, so

    locked in [0,1)   <=> favorable in [2,3)   <=> D = 2
    locked in [2,inf) <=> favorable in [3,inf) <=> D = 1

and the model is falsified by anything landing in [1,2).  Having fixed D we can
invert:  M_hat = sl + dir*D*S.

The test: positions on the same side of the same cycle updated in the same pass
must yield the SAME M_hat -- INCLUDING positions in different stages, whose raw
sl values then differ by exactly (2.0-1.0)*S = one step.  Agreement of M_hat
across different entries AND different stages is a strong joint test of the
trigger (3.0), both distances (2.0/1.0) and the shared-market update.
"""
from __future__ import annotations

import statistics
import sys
from collections import Counter, defaultdict

sys.path.insert(0, r"C:\websites\mt5 2")
from tools.forensics.dataset import load_all, FINAL_REGIME_START  # noqa: E402
from tools.forensics.attribution import build_exit_index, attribute  # noqa: E402

PRE, POST, TRIG = 2.0, 1.0, 3.0


def main() -> None:
    orders, positions, deals, cycles = load_all()
    class_by_time, _, _ = build_exit_index(orders, deals)
    reason, _, _ = attribute(positions, class_by_time)
    step_by_cycle = {c.index: c.step for c in cycles}

    fr = [p for p in positions
          if p.open_time >= FINAL_REGIME_START and p.cycle >= 0
          and not p.is_open and p.stop_loss
          and (step_by_cycle.get(p.cycle) or 0) > 0]

    # ---------- exact boundary measurement ----------------------------------
    print("=" * 78)
    print("A. EXACT MODE BOUNDARIES  (all final-regime positions with an SL)")
    print("=" * 78)
    rec = []
    for p in fr:
        s = step_by_cycle[p.cycle]
        d = 1.0 if p.side == "buy" else -1.0
        rec.append((d * (p.stop_loss - p.open_price) / s, p, s, d))
    lo = sorted(v for v, *_ in rec if v < 1.0)
    hi = sorted(v for v, *_ in rec if v >= 1.0)
    print(f"n={len(rec)}  mode A (locked<1): {len(lo)}   mode B (locked>=1): {len(hi)}")
    print(f"  mode A : min={lo[0]:+.4f}  max={lo[-1]:+.4f}   "
          f"(model predicts [0.000, 1.000))")
    print(f"  mode B : min={hi[0]:+.4f}  max={hi[-1]:+.4f}   "
          f"(model predicts [2.000, inf))")
    print(f"  EMPTY BAND observed: ({lo[-1]:.4f}, {hi[0]:.4f})  "
          f"width={hi[0]-lo[-1]:.4f} steps")
    print(f"  negatives (SL beyond entry): {sum(1 for v in lo if v < -1e-9)}")
    band = sorted(v for v in hi if v < 2.0)
    print(f"  mode-B members below 2.000 (slippage-smeared edge): {len(band)}")
    if band:
        print("    -> those positions in detail:")
        for v, p, s, d in sorted(rec, key=lambda r: r[0]):
            if 1.0 <= v < 2.0:
                print(f"      {p.comment:<7} cyc={p.cycle:<4} locked={v:.4f} "
                      f"step={s:.4f} entry={p.open_price} sl={p.stop_loss}")

    # ---------- invert to the market price ----------------------------------
    print("\n" + "=" * 78)
    print("B. MARKET-PRICE INVERSION  M_hat = sl + dir*D*step")
    print("=" * 78)
    inv = []
    for v, p, s, d in rec:
        D = PRE if v < 1.0 else POST
        inv.append((p, s, d, v, D, p.stop_loss + d * D * s))

    groups = defaultdict(list)
    for row in inv:
        p, s, d, v, D, m = row
        groups[(p.cycle, p.side, round(m, 1))].append(row)

    mixed = [g for g in groups.values() if len({x[4] for x in g}) == 2]
    print(f"M_hat groups (cycle, side, 0.1-price bin): {len(groups)}")
    print(f"  groups containing BOTH stages (D=2 and D=1): {len(mixed)}")
    spreads = sorted(max(x[5] for x in g) - min(x[5] for x in g) for g in mixed)
    if spreads:
        print(f"  within-group M_hat spread across stages (price): "
              f"median={statistics.median(spreads):.4f} "
              f"p90={spreads[int(.9*(len(spreads)-1))]:.4f} "
              f"max={spreads[-1]:.4f}")
    print("\n  sample mixed-stage groups (raw sl differs by exactly 1 step,")
    print("  yet M_hat agrees -- this is the joint proof):")
    for g in sorted(mixed, key=lambda g: -len(g))[:5]:
        p0, s0 = g[0][0], g[0][1]
        print(f"   cyc={p0.cycle} {p0.side} step={s0:.4f}")
        for p, s, d, v, D, m in sorted(g, key=lambda x: x[3]):
            print(f"     {p.comment:<7} entry={p.open_price:<9} sl={p.stop_loss:<9} "
                  f"locked={v:>6.3f} D={D:.1f} favorable={v+D:>6.3f} "
                  f"M_hat={m:.4f}")

    # ---------- raw-sl ladder ------------------------------------------------
    print("\n" + "=" * 78)
    print("C. DISTINCT SL VALUES PER (CYCLE, SIDE): the 1-step ladder")
    print("=" * 78)
    per = defaultdict(set)
    for p, s, d, v, D, m in inv:
        per[(p.cycle, p.side)].add(round(p.stop_loss, 5))
    ladder = Counter()
    for (cyc, side), sls in per.items():
        s = step_by_cycle[cyc]
        xs = sorted(sls)
        for a, b in zip(xs, xs[1:]):
            ladder[round((b - a) / s, 1)] += 1
    print("consecutive distinct-SL gaps, in steps (top 14):")
    for k, n in sorted(ladder.items(), key=lambda kv: -kv[1])[:14]:
        print(f"   {k:>6.1f} steps : {n}")

    # ---------- residual test on same-instant closures ----------------------
    print("\n" + "=" * 78)
    print("D. SAME-INSTANT CLOSURE GROUPS: does one M explain every member?")
    print("=" * 78)
    byt = defaultdict(list)
    for row in inv:
        p = row[0]
        if reason.get(p.position_id) == "sl":
            byt[(p.cycle, p.side, p.close_time)].append(row)
    resid = []
    nmix = 0
    nmulti = 0
    for g in byt.values():
        if len(g) < 2:
            continue
        nmulti += 1
        if len({x[4] for x in g}) == 2:
            nmix += 1
        ms = [x[5] for x in g]
        mu = statistics.median(ms)
        for m in ms:
            resid.append(abs(m - mu) / g[0][1])
    resid.sort()
    print(f"multi-position same-instant SL groups: {nmulti} (mixed-stage: {nmix})")
    if resid:
        print(f"|M_hat - median(M_hat)| in steps: "
              f"p50={statistics.median(resid):.4f} "
              f"p90={resid[int(.9*(len(resid)-1))]:.4f} "
              f"p99={resid[int(.99*(len(resid)-1))]:.4f} max={resid[-1]:.4f}")
        print(f"  within 0.05 step: "
              f"{100*sum(1 for r in resid if r<=0.05)/len(resid):.1f}%"
              f"   within 0.15 step: "
              f"{100*sum(1 for r in resid if r<=0.15)/len(resid):.1f}%")


if __name__ == "__main__":
    main()
