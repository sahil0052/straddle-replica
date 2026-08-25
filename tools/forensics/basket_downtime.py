"""Were the four surviving "gated" cycles actually EA DOWNTIME?

Where this stands.  The $30 basket rule scores a median lead of ~5 s on the cycles
it governs, and the flat threshold is already triply confirmed in-code (29.31 /
29.36 / 30.46, with a size-scaled variant refuted at 0/100).  Four cycles resist:
194, 252, 187, 244 held a reconstructed total above $30 for 80-306 minutes -- 70
consecutive prints in the case of 252 -- without flattening.  Two candidate
explanations were killed:

    starvation by pending work   REFUTED: 0/10 gated intervals were busy, and 194
                                sat idle 85.9 min with no placement and no cancel.
    a size-scaled target        REFUTED in-code at StraddleEngine.mqh:2871.

I then read "idle" as only refuting starvation.  It does more than that.  A running
one-action-per-tick EA with an idle queue reaches CheckCycleTargets on the very next
100 ms tick.  So an 85.9-minute hole with the target satisfied is not a gate at all
-- it is the EA not running.

The two classes of evidence separate cleanly, because they have different actors:

    a PLACEMENT or a CANCEL  is the EA acting.       No EA -> none of these.
    a position OPEN          is a resting stop being filled BY THE MARKET.
    a position CLOSE at SL   is a resting stop being filled BY THE MARKET.

So during a genuine downtime window, fills keep printing (the broker honours resting
orders with the terminal off) while EA actions stop dead.  That is exactly the
signature Panel B/D showed for 194: 54 prints, 29 EA actions, one 85.9-minute hole.

This measures it directly.  For each survivor's largest idle window, count ALL
account activity -- across every cycle, not just this one -- split into
market-driven and EA-driven.  Then compare against the same clock hour on other
days, so a daily market break cannot be mistaken for downtime.

If EA actions go to zero while market fills continue, the cause is the terminal,
not a rule, and the replica must NOT emulate it.
"""
from __future__ import annotations

import statistics
import sys
from collections import Counter, defaultdict

sys.path.insert(0, r"C:\websites\mt5 2")
from tools.forensics.dataset import load_all, FINAL_REGIME_START, CONTRACT  # noqa: E402

TARGET = 30.0
SURVIVORS = [194, 252, 187, 244, 250, 197, 253]


def main() -> None:
    orders, positions, deals, cycles = load_all()
    fin = [c for c in cycles if c.start >= FINAL_REGIME_START]
    lo = min(c.start for c in fin)

    # ---- global activity streams, account-wide -----------------------------
    ea_acts = []        # EA-driven: placements and cancels
    mkt_acts = []       # market-driven: fills (position opens) and SL closes
    for o in orders:
        if o.open_time and o.open_time >= lo:
            ea_acts.append((o.open_time, "place"))
        if o.state == "canceled" and o.end_time and o.end_time >= lo:
            ea_acts.append((o.end_time, "cancel"))
    for p in positions:
        if p.open_time >= lo:
            mkt_acts.append((p.open_time, "fill"))
        if p.close_time and p.close_time >= lo:
            mkt_acts.append((p.close_time, "close"))
    ea_acts.sort()
    mkt_acts.sort()

    # ---- hour-of-day baseline: is there a daily market break? -------------
    print("=" * 104)
    print("A. DAILY ACTIVITY PROFILE -- locate the market break before calling downtime")
    print("=" * 104)
    days = len({t.date() for t, _ in ea_acts})
    eh = Counter(t.hour for t, _ in ea_acts)
    mh = Counter(t.hour for t, _ in mkt_acts)
    mx = max(max(eh.values()), max(mh.values()))
    print(f"  {'hour':>5} {'EA acts':>9} {'mkt acts':>9}  profile")
    for h in range(24):
        e, m = eh.get(h, 0), mh.get(h, 0)
        print(f"  {h:02d}:00 {e:>9} {m:>9}  " + "#" * int(28 * e / mx) +
              "|" + "=" * int(28 * m / mx))
    dead = [h for h in range(24) if eh.get(h, 0) + mh.get(h, 0) == 0]
    print(f"  hours with zero activity of ANY kind: {dead if dead else 'none'}")
    print(f"  ({days} trading days in the window)")

    # ---- per-survivor idle-window forensics --------------------------------
    print()
    print("=" * 104)
    print("B. THE IDLE WINDOWS -- who stopped acting, the EA or the market?")
    print("=" * 104)

    marks = []
    for p in positions:
        marks.append((p.open_time, p.open_price))
        if p.close_time and p.close_price:
            marks.append((p.close_time, p.close_price))
    marks.sort(key=lambda r: r[0])

    for idx in SURVIVORS:
        c = next((x for x in fin if x.index == idx), None)
        if c is None:
            continue
        cl = [o.open_time for o in c.orders
              if o.comment and o.comment.strip().upper().startswith("STR CLOSE")]
        if not cl:
            continue
        t_close = min(cl)

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
        first = None
        for t, m in marks:
            if t < c.start:
                continue
            if t > t_close:
                break
            while j < len(ev) and ev[j][0] <= t:
                _, _, da, db, dc, dr, dg = ev[j]
                A += da; B += db; C += dc; R += dr; G += dg
                j += 1
            v = R + m * A - B + C - 0.125 * G
            if first is None and v >= TARGET:
                first = t
        if first is None:
            continue

        # the largest EA-silent window inside [first, t_close], account-wide
        pts = [first] + [t for t, _ in ea_acts if first < t < t_close] + [t_close]
        k = max(range(len(pts) - 1),
                key=lambda z: (pts[z + 1] - pts[z]).total_seconds())
        a, b = pts[k], pts[k + 1]
        gap = (b - a).total_seconds()
        n_mkt = sum(1 for t, _ in mkt_acts if a < t < b)
        n_ea = sum(1 for t, _ in ea_acts if a < t < b)

        print()
        print(f"  cycle {idx}:  eligible from {str(first)[:19]} "
              f"({first.strftime('%a')})")
        print(f"    largest EA-SILENT window: {str(a)[:19]} -> {str(b)[:19]}"
              f"   {gap/60:.1f} min")
        print(f"      EA actions   (account-wide, any cycle) : {n_ea}")
        print(f"      market fills (account-wide, any cycle) : {n_mkt}")
        # baseline: same clock span on other days
        span_h = (a.hour + a.minute / 60.0, b.hour + b.minute / 60.0)
        base = []
        for d in sorted({t.date() for t, _ in ea_acts}):
            if d == a.date():
                continue
            n = sum(1 for t, _ in ea_acts if t.date() == d and
                    span_h[0] <= t.hour + t.minute / 60.0 <= max(span_h[1], span_h[0]))
            base.append(n)
        if base:
            print(f"      same clock window on the other {len(base)} days: "
                  f"median {statistics.median(base):.0f} EA actions, "
                  f"zero on {sum(1 for n in base if n == 0)}/{len(base)} days")
        verdict = ("MARKET CLOSED (nothing at all happened)" if n_mkt == 0 and n_ea == 0
                   else "EA WAS DOWN -- market kept filling, EA did nothing"
                   if n_mkt > 0 and n_ea == 0
                   else "EA was alive and acting -> a real rule is needed")
        print(f"      -> {verdict}")

    # ---- account-wide silence census --------------------------------------
    print()
    print("=" * 104)
    print("C. ACCOUNT-WIDE EA SILENCE CENSUS -- how often does the Target go quiet?")
    print("=" * 104)
    holes = []
    for k in range(len(ea_acts) - 1):
        g = (ea_acts[k + 1][0] - ea_acts[k][0]).total_seconds()
        if g >= 600.0:
            n_mkt = sum(1 for t, _ in mkt_acts
                        if ea_acts[k][0] < t < ea_acts[k + 1][0])
            holes.append((g, ea_acts[k][0], ea_acts[k + 1][0], n_mkt))
    holes.sort(reverse=True)
    print(f"  EA-silent windows >= 10 min: {len(holes)}")
    print(f"  {'minutes':>9} {'from':>20} {'to':>20} {'day':>5} {'mkt fills inside':>17}")
    for g, a, b, n in holes[:16]:
        print(f"  {g/60:>9.1f} {str(a)[:19]:>20} {str(b)[:19]:>20} "
              f"{a.strftime('%a'):>5} {n:>17}")
    live = [h for h in holes if h[3] > 0]
    print(f"\n  of these, {len(live)} had market fills inside -- i.e. the market was")
    print("  open and the EA was silent anyway.  Those are terminal downtime, not rules.")
    if live:
        print(f"  total downtime with an open market: "
              f"{sum(h[0] for h in live)/3600.0:.1f} h over {days} trading days")


if __name__ == "__main__":
    main()
