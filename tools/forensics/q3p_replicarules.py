"""Q3p: score the replica's OWN coded exit rules against the Target EA's behaviour.

StraddleEngine.mqh::CheckCycleTargets implements three exit paths:

  1. basket_target      net >= cycle_target_money (30)
  2. grid_recenter      trend_rescue_enabled && anchor>0 && state==RUNNING &&
                        ( dist >= 20  ||  (realized >= 50 && net >= -20 && dist >= 15) )
  3. rescue_breakeven   rescue_side != 0 && realized >= 200 && net >= -10

Rule 1 is now confirmed.  Rules 2 and 3 were written from the mission brief, never
measured.  Apply the same first-fire-time scoring to them: if either fires materially
before the Target EA actually closed, it is not parity -- it is an injected rule that
will liquidate profitable baskets early.

For each cycle report the earliest tick at which each rule would have fired, and what
the basket was worth at that moment versus what the Target EA eventually banked.
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

    fin = [c for c in cycles if c.start >= FINAL_REGIME_START]

    rows = []
    for i, sw in enumerate(sweeps):
        if i == 0:
            continue
        S, dec = sweeps[i - 1][-1].close_time, sw[0].close_time
        # anchor of the lattice deployed inside this window
        anch = [c for c in fin if S <= c.start <= dec and c.anchor]
        anchor = anch[0].anchor if anch else None
        if anchor is None:
            near = [c for c in fin if c.start <= dec and c.anchor]
            anchor = near[-1].anchor if near else None
        if anchor is None:
            continue
        mk_dec = sw[0].close_price
        r_at = sum(p.net for p in live if not p.is_open and p.close_time
                   and S < p.close_time < dec)
        f_at = sum(p.dir * (mk_dec - p.open_price) * p.volume * CONTRACT for p in sw)

        i0, i1 = bisect_left(pt_t, S), bisect_right(pt_t, dec)
        first_rc = first_bk = None
        for k in range(i0, i1):
            t, m = pt_t[k], pt_p[k]
            r = f = 0.0
            hi = bisect_right(open_times, t)
            for p in live[:hi]:
                if not p.is_open and p.close_time and p.close_time <= t:
                    if p.close_time > S:
                        r += p.net
                else:
                    f += p.dir * (m - p.open_price) * p.volume * CONTRACT
            net = r + f
            dist = abs(m - anchor)
            if first_rc is None and (dist >= 20.0
                                     or (r >= 50.0 and net >= -20.0 and dist >= 15.0)):
                first_rc = (t, net, dist, r)
            if first_bk is None and r >= 200.0 and net >= -10.0:
                first_bk = (t, net, dist, r)
            if first_rc and first_bk:
                break
        rows.append(dict(idx=i, S=S, dec=dec, marked=r_at + f_at,
                         rc=first_rc, bk=first_bk,
                         dpp=sum(p.volume for p in sw) * CONTRACT,
                         hrs=(dec - S).total_seconds() / 3600.0))

    n = len(rows)
    print(f"final-regime cycles scored: {n}\n")

    for key, name, clause in (
        ("rc", "grid_recenter",
         "dist>=20 or (realized>=50 and net>=-20 and dist>=15)"),
        ("bk", "rescue_breakeven", "realized>=200 and net>=-10"),
    ):
        hits = [r for r in rows if r[key]]
        leads = [(r["dec"] - r[key][0]).total_seconds() for r in hits]
        early = [r for r in hits
                 if (r["dec"] - r[key][0]).total_seconds() > 300.0]
        print("=" * 112)
        print(f"REPLICA RULE: {name}     {clause}")
        print("=" * 112)
        print(f"  would fire on              : {len(hits)}/{n} cycles")
        if leads:
            print(f"  median lead before the real exit : "
                  f"{statistics.median(leads):>10.1f}s  "
                  f"({statistics.median(leads)/60:.1f} min)")
            print(f"  max lead                        : {max(leads):>10.1f}s  "
                  f"({max(leads)/3600:.1f} h)")
            print(f"  fires >5 min early on           : {len(early)}/{n} cycles")
            banked = [r["marked"] for r in early]
            atfire = [r[key][1] for r in early]
            if banked:
                print(f"  on those cycles the Target EA banked a median of "
                      f"${statistics.median(banked):.2f}")
                print(f"  the replica would have closed at a median net of "
                      f"${statistics.median(atfire):.2f}")
                lost = sum(b - a for b, a in zip(banked, atfire))
                print(f"  aggregate profit destroyed over {len(early)} cycles: "
                      f"${lost:,.2f}")
        print()

    print("=" * 112)
    print("WORST OFFENDERS -- grid_recenter, sorted by profit destroyed")
    print("=" * 112)
    print(f"  {'idx':>4} {'lead':>10} {'dist@fire':>10} {'net@fire':>10} "
          f"{'real@fire':>10} {'EA banked':>11} {'destroyed':>11}")
    off = [(r["marked"] - r["rc"][1], r) for r in rows
           if r["rc"] and (r["dec"] - r["rc"][0]).total_seconds() > 300.0]
    for d, r in sorted(off, key=lambda x: -x[0])[:20]:
        lead = (r["dec"] - r["rc"][0]).total_seconds()
        print(f"  {r['idx']:>4} {lead/60:>8.1f}m {r['rc'][2]:>10.2f} "
              f"{r['rc'][1]:>10.2f} {r['rc'][3]:>10.2f} {r['marked']:>11.2f} "
              f"{d:>11.2f}")

    print("\n" + "=" * 112)
    print("WHICH CLAUSE OF grid_recenter IS THE CULPRIT?")
    print("=" * 112)
    for lab, pred in (("dist>=20 alone", lambda r, net, dist: dist >= 20.0),
                      ("realized>=50 and net>=-20 and dist>=15",
                       lambda r, net, dist: r >= 50.0 and net >= -20.0 and dist >= 15.0)):
        c = sum(1 for x in rows if x["rc"] and pred(x["rc"][3], x["rc"][1], x["rc"][2]))
        print(f"  {lab:<44} satisfied at the first-fire tick on {c:>3}/{n}")


if __name__ == "__main__":
    main()
