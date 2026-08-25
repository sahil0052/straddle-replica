"""Q3n: two tests that finish off the exit rule.

TEST 1 -- is the [0,25) group a rule, or is it valuation error?
  I mark every swept position at the FIRST close's price.  That price is one side of
  the book (bid for a long, ask for a short), so on a mixed basket the mark carries an
  error of order  spread * dollars_per_point.  At 40 $/pt and a 0.35 pt spread that is
  $14 -- easily enough to drag a genuine $30 exit down into [10,25).
  If the shortfall (30 - marked) scales with $/pt, the whole 0..75 spread is ONE rule
  blurred by mark error.  If it is flat in $/pt, it is a second threshold.

TEST 2 -- do the 6 distress exits sit at the cycle's WORST point?
  A floor on floating (or on net) must fire at, or within one timer tick of, the
  minimum.  If the decision instead comes after floating has already recovered from a
  deeper low, no floor explains it -- the EA sat through worse and then bailed.
  Reconstruct the full series per cycle and locate the decision inside it.
"""
from __future__ import annotations

import statistics
import sys
from bisect import bisect_left, bisect_right

sys.path.insert(0, r"C:\websites\mt5 2")
from tools.forensics.dataset import load_all, FINAL_REGIME_START, CONTRACT  # noqa: E402
from tools.forensics.attribution import build_exit_index, attribute  # noqa: E402

TARGET = 30.0


def main() -> None:
    orders, positions, deals, cycles = load_all()
    class_by_time, _, _ = build_exit_index(orders, deals)
    reason, _, _ = attribute(positions, class_by_time)

    live = [p for p in positions
            if (p.open_time >= FINAL_REGIME_START
                or (p.close_time and p.close_time >= FINAL_REGIME_START))]
    live.sort(key=lambda p: p.open_time)
    open_times = [p.open_time for p in live]
    prints = sorted([(p.open_time, p.open_price) for p in live] +
                    [(p.close_time, p.close_price) for p in live
                     if p.close_time and p.close_price])
    pt_t = [t for t, _ in prints]
    pt_p = [x for _, x in prints]

    closers = sorted((p for p in live if not p.is_open and p.close_time
                      and reason.get(p.position_id) == "STR CLOSE"),
                     key=lambda p: p.close_time)
    sweeps, cur = [], [closers[0]]
    for prev, nxt in zip(closers, closers[1:]):
        if (nxt.close_time - prev.close_time).total_seconds() <= 120.0:
            cur.append(nxt)
        else:
            sweeps.append(cur)
            cur = [nxt]
    sweeps.append(cur)
    sweeps = [s for s in sweeps if s[0].close_time >= FINAL_REGIME_START]

    rows = []
    for i, sw in enumerate(sweeps):
        if i == 0:
            continue
        S = sweeps[i - 1][-1].close_time
        dec = sw[0].close_time
        realized_before = sum(p.net for p in live if not p.is_open and p.close_time
                              and S < p.close_time < dec)
        mk = sw[0].close_price
        floating_at = sum(p.dir * (mk - p.open_price) * p.volume * CONTRACT for p in sw)
        dpp = sum(p.volume for p in sw) * CONTRACT
        nlong = sum(1 for p in sw if p.dir > 0)
        vlong = sum(p.volume for p in sw if p.dir > 0) * CONTRACT
        vshort = dpp - vlong

        # full reconstructed series over the cycle
        i0, i1 = bisect_left(pt_t, S), bisect_right(pt_t, dec)
        ser = []
        for k in range(i0, i1):
            t, m = pt_t[k], pt_p[k]
            r = f = v = 0.0
            hi = bisect_right(open_times, t)
            for p in live[:hi]:
                if not p.is_open and p.close_time and p.close_time <= t:
                    if p.close_time > S:
                        r += p.net
                else:
                    f += p.dir * (m - p.open_price) * p.volume * CONTRACT
                    v += p.volume
            ser.append((t, r, f, r + f, v * CONTRACT))
        rows.append(dict(idx=i, S=S, dec=dec, realized_before=realized_before,
                         floating_at=floating_at, marked=realized_before + floating_at,
                         dpp=dpp, vlong=vlong, vshort=vshort, n=len(sw),
                         nlong=nlong, ser=ser,
                         hrs=(dec - S).total_seconds() / 3600.0))

    # ---------------------------------------------------------------- TEST 1
    print("=" * 100)
    print("TEST 1.  DOES THE SHORTFALL BELOW $30 SCALE WITH $/POINT?")
    print("         mark error ~ spread * min(long$/pt, short$/pt): a one-sided price")
    print("         values BOTH legs, so only the netted exposure escapes the error")
    print("=" * 100)
    grp = [r for r in rows if r["marked"] >= -20.0]     # exclude the distress tail
    for lo, hi in [(0, 20), (20, 30), (30, 40), (40, 60), (60, 10**9)]:
        g = [r for r in grp if lo <= r["dpp"] < hi]
        if not g:
            continue
        sf = [TARGET - r["marked"] for r in g]
        below = [r for r in g if r["marked"] < 25.0]
        print(f"  $/pt [{lo:>3},{hi if hi < 10**9 else 'inf':>4})  n={len(g):>3}  "
              f"med marked={statistics.median([r['marked'] for r in g]):>7.2f}  "
              f"med shortfall={statistics.median(sf):>7.2f}  "
              f"p90 shortfall={sorted(sf)[int(.9*(len(sf)-1))]:>7.2f}  "
              f"marked<25: {len(below):>2}/{len(g)}")

    print("\n  the [0,25) group in full -- shortfall against the spread budget")
    print(f"  {'idx':>4} {'$/pt':>7} {'long$':>7} {'short$':>7} {'min-leg':>8} "
          f"{'n':>3} {'hrs':>6} {'real_bef':>9} {'float_at':>9} {'marked':>8} "
          f"{'shortfall':>10} {'/min-leg':>9}")
    for r in sorted((x for x in rows if 0.0 <= x["marked"] < 25.0),
                    key=lambda r: r["marked"]):
        leg = min(r["vlong"], r["vshort"])
        sf = TARGET - r["marked"]
        print(f"  {r['idx']:>4} {r['dpp']:>7.1f} {r['vlong']:>7.1f} "
              f"{r['vshort']:>7.1f} {leg:>8.1f} {r['n']:>3} {r['hrs']:>6.1f} "
              f"{r['realized_before']:>9.2f} {r['floating_at']:>9.2f} "
              f"{r['marked']:>8.2f} {sf:>10.2f} "
              f"{(sf / leg if leg else float('nan')):>9.3f}")

    # ---------------------------------------------------------------- TEST 2
    print("\n" + "=" * 100)
    print("TEST 2.  DO THE DISTRESS EXITS SIT AT THE CYCLE'S WORST POINT?")
    print("         a floor on floating (or on net) must fire AT the minimum")
    print("=" * 100)
    dis = sorted((r for r in rows if r["marked"] < -20.0), key=lambda r: r["marked"])
    print(f"  {'idx':>4} {'marked':>9} | {'float_at':>9} {'min_float':>10} "
          f"{'atMin?':>7} {'minAgo':>8} | {'net_at':>9} {'min_net':>9} "
          f"{'atMin?':>7} {'minAgo':>8} | {'ticks':>6}")
    for r in dis:
        ser = r["ser"]
        if not ser:
            continue
        fl = [(t, f) for t, _, f, _, _ in ser]
        nt = [(t, n) for t, _, _, n, _ in ser]
        tmf, mnf = min(fl, key=lambda x: x[1])
        tmn, mnn = min(nt, key=lambda x: x[1])
        f_at, n_at = ser[-1][2], ser[-1][3]
        print(f"  {r['idx']:>4} {r['marked']:>9.2f} | {f_at:>9.2f} {mnf:>10.2f} "
              f"{'YES' if f_at <= mnf + 1e-6 else 'no':>7} "
              f"{(r['dec']-tmf).total_seconds():>7.0f}s | "
              f"{n_at:>9.2f} {mnn:>9.2f} "
              f"{'YES' if n_at <= mnn + 1e-6 else 'no':>7} "
              f"{(r['dec']-tmn).total_seconds():>7.0f}s | {len(ser):>6}")

    print("\n  for contrast, the same columns for the 5 sustained-excursion cycles")
    print(f"  {'idx':>4} {'marked':>9} | {'float_at':>9} {'min_float':>10} "
          f"{'min_net':>9} {'max_net':>9} {'hrs':>6}")
    for r in rows:
        if r["idx"] in (21, 79, 14, 71, 77) and r["ser"]:
            fl = [f for _, _, f, _, _ in r["ser"]]
            nt = [n for _, _, _, n, _ in r["ser"]]
            print(f"  {r['idx']:>4} {r['marked']:>9.2f} | {r['ser'][-1][2]:>9.2f} "
                  f"{min(fl):>10.2f} {min(nt):>9.2f} {max(nt):>9.2f} {r['hrs']:>6.1f}")

    print("\n" + "=" * 100)
    print("TEST 3.  HOW DEEP DOES A *SURVIVING* CYCLE LET FLOATING / NET GO?")
    print("         if a floor existed at -X, no cycle may ever have gone below -X")
    print("         and lived.  Find the deepest excursion among cycles that did NOT")
    print("         exit in distress.")
    print("=" * 100)
    surv = []
    for r in rows:
        if r["marked"] < -20.0 or not r["ser"]:
            continue
        fl = [f for _, _, f, _, _ in r["ser"]]
        nt = [n for _, _, _, n, _ in r["ser"]]
        surv.append((min(fl), min(nt), r))
    surv.sort(key=lambda x: x[1])
    print(f"  deepest NET excursion among the {len(surv)} non-distress cycles:")
    print(f"  {'idx':>4} {'min_net':>9} {'min_float':>10} {'$/pt':>7} {'hrs':>6} "
          f"{'marked':>9}")
    for mnf, mnn, r in surv[:12]:
        print(f"  {r['idx']:>4} {mnn:>9.2f} {mnf:>10.2f} {r['dpp']:>7.1f} "
              f"{r['hrs']:>6.1f} {r['marked']:>9.2f}")
    dis_worst = max(min(n for _, _, _, n, _ in r["ser"]) for r in dis if r["ser"])
    print(f"\n  shallowest distress minimum   : {dis_worst:>9.2f}")
    print(f"  deepest surviving minimum     : {surv[0][1]:>9.2f}")
    print("  -> a single net floor is only viable if these do not overlap.")


if __name__ == "__main__":
    main()
