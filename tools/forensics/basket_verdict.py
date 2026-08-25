"""The four survivors: session breaks, or a real rule?  And what does it COST?

basket_downtime.py printed "EA WAS DOWN" seven times, and its own Panel C refutes
that reading.  Every one of the largest EA-silent windows starts near 22:xx and ends
near 00:01, and Panel A shows hour 23 with ZERO activity of any kind, account-wide,
across all 13 days.  Those are the broker's daily session break.  The two biggest
holes are Fri 22:37 -> Mon 00:01 and Fri 22:53 -> Mon 00:01: weekends.  My verdict
line called a window "market open" on the strength of ONE fill inside 86 minutes,
against a baseline near 250 fills/hour.  One fill in 86 minutes is silence.

And cycle 244 becomes eligible at exactly 2026-07-27 00:01:00 -- the same instant the
Fri->Mon weekend hole ends (00:01:21).  Its crossing is a reopen gap print.

So the discriminator has to be aliveness, proven positively, not inferred from the
absence of a break.  A PLACEMENT or a CANCEL can only come from a running EA:

    crossing print with an EA action within +/-5 min   ->  the terminal was ALIVE and
                                                           the value was >= 30.
                                                           That is a real divergence.
    crossing print with no EA action anywhere near it  ->  break, weekend, or reopen
                                                           gap.  Not a rule.

Then the part that actually answers the question being asked.  Coverage and lead time
do not tell anyone whether the replica is safe to run; money does.  For every cycle
where the divergence is real, the replica flattens at the crossing and banks roughly
the crossing value, while the Target went on to bank c.realized.  The difference,
summed and divided by the ledger's |money|, IS the parity gap in the only unit that
matters.  A divergence that is real but worth $40 is not the same finding as one
worth $4,000.
"""
from __future__ import annotations

import statistics
import sys
from collections import Counter
from datetime import timedelta

sys.path.insert(0, r"C:\websites\mt5 2")
from tools.forensics.dataset import load_all, FINAL_REGIME_START, CONTRACT  # noqa: E402

TARGET = 30.0
HALF = 0.125          # half-spread in points, from the plateau corner
ALIVE = 300.0         # seconds either side of the crossing that prove the EA ran
GATED = {194, 252, 187, 244, 250, 197, 219, 253, 181, 269}


def main() -> None:
    orders, positions, deals, cycles = load_all()
    fin = [c for c in cycles if c.start >= FINAL_REGIME_START]
    lo = min(c.start for c in fin)

    ea = sorted([o.open_time for o in orders if o.open_time and o.open_time >= lo] +
                [o.end_time for o in orders
                 if o.state == "canceled" and o.end_time and o.end_time >= lo])

    marks = []
    for p in positions:
        marks.append((p.open_time, p.open_price))
        if p.close_time and p.close_price:
            marks.append((p.close_time, p.close_price))
    marks.sort(key=lambda r: r[0])

    # ---- A. the session break, at minute resolution ------------------------
    print("=" * 104)
    print("A. THE BROKER SESSION BREAK -- measured, not assumed")
    print("=" * 104)
    per = Counter()
    for t, _ in marks:
        if t >= lo:
            per[t.hour * 60 + t.minute] += 1
    for t in ea:
        per[t.hour * 60 + t.minute] += 1
    dead = [m for m in range(1440) if per.get(m, 0) == 0]
    runs = []
    if dead:
        s = dead[0]
        for k in range(1, len(dead)):
            if dead[k] != dead[k - 1] + 1:
                runs.append((s, dead[k - 1]))
                s = dead[k]
        runs.append((s, dead[-1]))
    runs = [r for r in runs if r[1] - r[0] >= 14]
    print(f"  minutes-of-day with zero activity across all 13 days, runs >= 15 min:")
    for a, b in runs:
        print(f"    {a//60:02d}:{a%60:02d} -> {b//60:02d}:{b%60:02d}"
              f"   ({b-a+1} min dead every single day)")
    print("  -> this is the daily rollover break.  Nothing the EA does can happen here,")
    print("     and no mark exists to value the basket against.")

    def in_break(t):
        m = t.hour * 60 + t.minute
        return any(a <= m <= b for a, b in runs)

    # ---- B. score every gated cycle on proven aliveness -------------------
    print()
    print("=" * 104)
    print("B. AT THE CROSSING, WAS THE EA PROVABLY ALIVE?")
    print("=" * 104)
    print(f"  alive = a placement or a cancel within {ALIVE/60:.0f} min of the crossing print.")
    print("  Only a running terminal emits those.  Fills prove nothing: the broker")
    print("  honours resting stops with the terminal off.")
    print()

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
        raw = None          # first crossing, any print
        live = None         # first crossing with the EA provably alive
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
            v = R + m * A - B + C - HALF * G
            if v >= TARGET:
                if raw is None:
                    raw = (t, v, prev)
                if live is None and not in_break(t):
                    near = min((abs((t - x).total_seconds()) for x in ea), default=1e9)
                    if near <= ALIVE:
                        live = (t, v, near)
            prev = t
        if raw is None:
            continue
        rows.append(dict(i=c.index, t0=t0, raw=raw, live=live, start=c.start,
                         final=c.realized, nlive=sum(1 for p in rel if p.is_open or
                                                     (p.close_time and p.close_time >= t0))))

    print(f"  {'cyc':>5} {'raw lead':>9} {'crossing print':>20} {'gap before':>11}"
          f" {'break?':>7} {'EA within':>10} {'live lead':>10}")
    for r in sorted((x for x in rows if x["i"] in GATED),
                    key=lambda r: -(r["t0"] - r["raw"][0]).total_seconds()):
        t, v, prev = r["raw"]
        gap = (t - prev).total_seconds() if prev else 0.0
        near = min((abs((t - x).total_seconds()) for x in ea), default=1e9)
        ll = ((r["t0"] - r["live"][0]).total_seconds() / 60.0) if r["live"] else None
        print(f"  {r['i']:>5} {(r['t0']-t).total_seconds()/60:>7.1f}m {str(t)[:19]:>20}"
              f" {gap:>10.0f}s {'YES' if in_break(t) else '-':>7} {near:>9.0f}s"
              f" {(f'{ll:.1f}m' if ll is not None else 'never'):>10}")

    real = [r for r in rows if r["live"] and
            (r["t0"] - r["live"][0]).total_seconds() > 120]
    print()
    print(f"  cycles still gated once the crossing must be BOTH outside the break AND")
    print(f"  witnessed by a live EA: {len(real)} of {len(rows)}")

    # ---- C. the money -----------------------------------------------------
    print()
    print("=" * 104)
    print("C. WHAT DOES THE DIVERGENCE COST?  (the only unit that answers the question)")
    print("=" * 104)
    allm = sum(abs(c.realized) for c in fin)
    print("  If the replica fires at the crossing it banks ~the crossing value; the")
    print("  Target went on to bank `final`.  cost = final - crossing.")
    print()
    print(f"  {'cyc':>5} {'live lead':>10} {'crossing':>9} {'target final':>13}"
          f" {'replica cost':>13}")
    tot = 0.0
    for r in sorted(real, key=lambda r: -(r["t0"] - r["live"][0]).total_seconds()):
        t, v, near = r["live"]
        cost = r["final"] - v
        tot += cost
        print(f"  {r['i']:>5} {(r['t0']-t).total_seconds()/60:>8.1f}m {v:>9.2f}"
              f" {r['final']:>13.2f} {cost:>13.2f}")
    print(f"  {'':>5} {'':>10} {'':>9} {'TOTAL':>13} {tot:>13.2f}")
    print()
    print(f"  ledger |money| over the 100 final-regime cycles: ${allm:,.2f}")
    print(f"  divergence as a share of |money|: {abs(tot)/allm:.3%}")
    net = sum(c.realized for c in fin)
    print(f"  net realised over the window: ${net:,.2f}"
          f"   -> divergence is {abs(tot)/abs(net):.2%} of net P&L")

    # ---- D. sanity: what did the on-time population look like -------------
    print()
    print("=" * 104)
    print("D. THE HONEST HEADLINE NUMBER for the basket rule")
    print("=" * 104)
    on = [r for r in rows if (r["t0"] - r["raw"][0]).total_seconds() <= 120]
    print(f"  cycles where a crossing exists at all      : {len(rows)}")
    print(f"  fired within 2 min of the raw crossing     : {len(on)}"
          f"  = {len(on)/len(rows):.1%}")
    print(f"  gated, but crossing was in a break/no EA   : "
          f"{len([r for r in rows if r['i'] in GATED]) - len(real)}")
    print(f"  gated with a live EA witness (REAL gap)    : {len(real)}"
          f"  = {len(real)/len(rows):.1%} of scored cycles")
    if on:
        lv = [(r["t0"] - r["raw"][0]).total_seconds() for r in on]
        vv = [r["raw"][1] for r in on]
        print(f"  on-time lead: median {statistics.median(lv):.1f}s  "
              f"crossing value: median {statistics.median(vv):.2f}")
        print("  -> a median crossing value barely over 30 with a median lead of a few")
        print("     seconds is the signature of a flat $30 threshold polled continuously.")


if __name__ == "__main__":
    main()
