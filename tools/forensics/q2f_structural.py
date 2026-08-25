"""Q2f: the rescue trigger as a STRUCTURAL condition -- no price reconstruction.

q2e settled a methodological question by demolishing the previous approach.  The
reconstructed price series is the set of trade prints, and Panel C measured it:

    median print gap  32.4 s        p90   388 s
    p99             1677 s          max  49.4 h
    fraction of the timeline with a mark fresher than 15 s:  0.3 %

Floating is linear in the mark, so a drawdown threshold evaluated anywhere other
than a print instant is noise.  That is not a fixable defect -- the report simply
does not contain a tick feed.  Two consequences showed up as symptoms in q2d/q2e and
both are now explained rather than mysterious:

  * the "first true" instants were fake.  Tightening the freshness gate did not
    shrink the leads (212 -> 356 min); it just deleted real events (miss 0 -> 1).
  * at those instants the M15 move pointed at the WRONG SIDE in 3 of 6 cases
    (cycle 197 trend=S read +20.12 -> B; 250 trend=B read -21.05 -> S; 252 trend=S
    read +21.89 -> B).  A sparse-print M15 proxy manufactures moves that never
    happened.

So: stop trying to measure floating away from prints.  There is a competing
hypothesis that requires no price at all, and it comes from the mechanism already
established rather than from curve-fitting.

    PendingPriceIsValid requires a buy stop to sit ABOVE the ask.  Once price has
    marched past a buy level's lattice price, that level can never be re-armed as a
    stop.  In a sustained trend the trend-side lattice is therefore destroyed level
    by level, and the EA runs out of grid on precisely the side price is moving
    through.  The rescue is the response to that exhaustion.

That predicts a structural trigger, and every term in it is EXACTLY reconstructible
from the Orders and Positions sheets with no mark whatsoever:

    pend[S]     live base-volume pendings on side S
    open[S]     open positions on side S
    gone[S]     levels with neither -- the destroyed levels
    maxfill[S]  deepest level ever filled on side S
    maxopen[S]  deepest level currently open on side S

Supporting circumstantial evidence already in hand: the 6 rescue cycles are the
LONGEST cycles in the population (4.4 h, 8.7 h, 9.5 h, 57.3 h, 10.6 h, 23.2 h -- the
tail of the duration distribution), and in 4 of 6 events the first 2x order sits at
the very next level beyond the deepest occupied trend-side level.  Both are what
grid exhaustion looks like.

Panel A  exact structural snapshot at the corrected decision instant, both sides.
Panel B  lead time + falsifiers for each single structural feature, swept.  Same
         standard as everywhere else: lead ~ 0 admissible, lead >> 0 refuted.
Panel C  side attribution -- does the exhausted side identify the rescued side?
         This is the test q2e failed 3/6 on with a price proxy.
Panel D  the duration confound: are these just the long cycles?
"""
from __future__ import annotations

import statistics
import sys
from bisect import bisect_right
from datetime import datetime

sys.path.insert(0, r"C:\websites\mt5 2")
from tools.forensics.dataset import load_all, FINAL_REGIME_START  # noqa: E402

BREAK = datetime(2026, 7, 24, 12, 0, 0)
OPP = {"B": "S", "S": "B"}


def tier_lot(level: int) -> float:
    return 0.01 if level <= 10 else (0.06 if level <= 20 else 0.15)


def is_base(o) -> bool:
    return abs(o.volume - tier_lot(o.level)) < 1e-9


def is_rescue(o) -> bool:
    return abs(o.volume - 2.0 * tier_lot(o.level)) < 1e-9


def regime(t: datetime) -> str:
    return "EARLY" if t < BREAK else "LATE"


class Struct:
    """Exact per-side structural state of one cycle as a function of time.

    Everything here is derived from order open/end times and position open/close
    times, which the report gives to the millisecond.  No price, no mark, no bars.
    """

    def __init__(self, cyc, levels: int):
        self.levels = levels
        self.pend: dict[str, tuple[list, list]] = {}
        self.opos: dict[str, tuple[list, list]] = {}
        self.fill: dict[str, list[tuple[datetime, int]]] = {}
        self.opn: dict[str, list[tuple[datetime, datetime, int]]] = {}
        for sd in ("B", "S"):
            ps, pe = [], []
            for o in cyc.orders:
                if (o.is_grid and o.level is not None and o.side == sd
                        and is_base(o)):
                    ps.append(o.open_time)
                    pe.append(o.end_time if o.end_time else datetime.max)
            self.pend[sd] = (sorted(ps), sorted(pe))

            os_, oe = [], []
            fl, op = [], []
            for p in cyc.positions:
                if p.grid_side != sd or p.level is None:
                    continue
                os_.append(p.open_time)
                oe.append(p.close_time if p.close_time else datetime.max)
                fl.append((p.open_time, p.level))
                op.append((p.open_time,
                           p.close_time if p.close_time else datetime.max,
                           p.level))
            self.opos[sd] = (sorted(os_), sorted(oe))
            self.fill[sd] = sorted(fl)
            self.opn[sd] = op

    def n_pend(self, sd, t):
        s, e = self.pend[sd]
        return bisect_right(s, t) - bisect_right(e, t)

    def n_open(self, sd, t):
        s, e = self.opos[sd]
        return bisect_right(s, t) - bisect_right(e, t)

    def gone(self, sd, t):
        return self.levels - self.n_pend(sd, t) - self.n_open(sd, t)

    def maxfill(self, sd, t):
        m = 0
        for ot, lv in self.fill[sd]:
            if ot > t:
                break
            m = max(m, lv)
        return m

    def maxopen(self, sd, t):
        m = 0
        for a, b, lv in self.opn[sd]:
            if a <= t < b:
                m = max(m, lv)
        return m

    def grid(self, cyc):
        g = {o.open_time for o in cyc.orders}
        g |= {o.end_time for o in cyc.orders if o.end_time}
        g |= {p.open_time for p in cyc.positions}
        g |= {p.close_time for p in cyc.positions if p.close_time}
        return sorted(g)


FEATURES = {
    "gone[trend]":        lambda st, sd, t: st.gone(sd, t),
    "maxfill[trend]":     lambda st, sd, t: st.maxfill(sd, t),
    "maxopen[trend]":     lambda st, sd, t: st.maxopen(sd, t),
    "open[trend]":        lambda st, sd, t: st.n_open(sd, t),
    "gone-gone[opp]":     lambda st, sd, t: st.gone(sd, t) - st.gone(OPP[sd], t),
    "maxfill-maxfill":    lambda st, sd, t: st.maxfill(sd, t) - st.maxfill(OPP[sd], t),
    "open-open[opp]":     lambda st, sd, t: st.n_open(sd, t) - st.n_open(OPP[sd], t),
}


def main() -> None:
    orders, positions, deals, cycles = load_all()
    fin = [c for c in cycles if c.start >= FINAL_REGIME_START]

    # ---- corrected decision instant (first trend-side cancel later re-placed 2x)
    events: dict[int, tuple[datetime, str]] = {}
    for c in fin:
        resc = sorted((o for o in c.orders
                       if o.is_grid and o.level is not None and is_rescue(o)),
                      key=lambda o: o.open_time)
        if not resc:
            continue
        slots: dict[tuple, list] = {}
        for o in c.orders:
            if o.is_grid and o.level is not None:
                slots.setdefault((o.side, o.level), []).append(o)
        for v in slots.values():
            v.sort(key=lambda o: o.open_time)
        trend = resc[0].side
        cancels = [q.end_time for o in resc
                   for q in ([x for x in slots[(o.side, o.level)]
                              if x.open_time < o.open_time][-1:])
                   if q.state == "canceled" and q.end_time and o.side == trend]
        events[c.index] = (min(cancels) if cancels else resc[0].open_time, trend)

    st = {c.index: Struct(c, c.levels_per_side or 30) for c in fin}

    # ------------------------------------------------------------------ panel A
    print("=" * 100)
    print("A. EXACT STRUCTURAL SNAPSHOT at the corrected decision instant")
    print("=" * 100)
    print("  Both sides shown.  T = the side that got rescued, O = the other side.")
    print("  gone = levels with neither a live pending nor an open position.")
    print()
    print(f"  {'cyc':>4} {'reg':<5} {'T':>2} {'lv':>3} | "
          f"{'pendT':>5} {'openT':>5} {'goneT':>5} {'mxfT':>4} {'mxoT':>4} | "
          f"{'pendO':>5} {'openO':>5} {'goneO':>5} {'mxfO':>4} {'mxoO':>4}")
    rows = []
    for i in sorted(events):
        dec, tr = events[i]
        s = st[i]
        c = next(x for x in fin if x.index == i)
        r = (i, tr,
             s.n_pend(tr, dec), s.n_open(tr, dec), s.gone(tr, dec),
             s.maxfill(tr, dec), s.maxopen(tr, dec),
             s.n_pend(OPP[tr], dec), s.n_open(OPP[tr], dec), s.gone(OPP[tr], dec),
             s.maxfill(OPP[tr], dec), s.maxopen(OPP[tr], dec))
        rows.append(r)
        print(f"  {i:>4} {regime(dec):<5} {tr:>2} {c.levels_per_side or 30:>3} | "
              f"{r[2]:>5} {r[3]:>5} {r[4]:>5} {r[5]:>4} {r[6]:>4} | "
              f"{r[7]:>5} {r[8]:>5} {r[9]:>5} {r[10]:>4} {r[11]:>4}")

    print()
    for lab, k in (("gone[trend]", 4), ("maxfill[trend]", 5), ("open[trend]", 3),
                   ("gone[trend]-gone[opp]", None)):
        if k is None:
            v = sorted(r[4] - r[9] for r in rows)
        else:
            v = sorted(r[k] for r in rows)
        print(f"  {lab:<24} min={v[0]:>4}  med={statistics.median(v):>6.1f}  "
              f"max={v[-1]:>4}   values " + " ".join(str(x) for x in v))

    # ------------------------------------------------------------------ panel B
    print()
    print("=" * 100)
    print("B. LEAD TIME + FALSIFIERS for each structural feature (exact, no price)")
    print("=" * 100)
    print("  For every cycle, scan its exact event grid for the first instant the")
    print("  feature reaches the threshold on EITHER side.  Then compare to the")
    print("  decision instant.  miss = fired but never true.  fals = true, never fired.")
    print()
    for name, fn in FEATURES.items():
        print(f"  --- {name}")
        print(f"      {'>=X':>5} {'miss':>5} {'fals':>5} {'side':>5} {'neg':>4} "
              f"{'lead med':>9} {'lead max':>9}   leads (min)")
        lo = -10 if "-" in name else 1
        for x in range(lo, 30, 2 if lo < 0 else 3):
            miss = fals = sideok = neg = 0
            leads = []
            for c in fin:
                s = st[c.index]
                first = None
                for g in s.grid(c):
                    for sd in ("B", "S"):
                        if fn(s, sd, g) >= x:
                            first = (g, sd)
                            break
                    if first:
                        break
                if c.index in events:
                    dec, tr = events[c.index]
                    if first is None:
                        miss += 1
                    else:
                        v = (dec - first[0]).total_seconds() / 60.0
                        leads.append(v)
                        neg += (v < -0.5)
                        sideok += (first[1] == tr)
                elif first is not None:
                    fals += 1
            lm = statistics.median(leads) if leads else float("nan")
            flag = ""
            if miss == 0 and fals <= 12 and leads and abs(lm) < 60:
                flag = "  <=="
            print(f"      {x:>5} {miss:>5} {fals:>5} {sideok:>3}/6 {neg:>4} "
                  f"{lm:>9.1f} {max(leads) if leads else 0:>9.1f}   "
                  + " ".join(f"{v:.0f}" for v in sorted(leads)) + flag)
        print()

    # ------------------------------------------------------------------ panel C
    print("=" * 100)
    print("C. SIDE ATTRIBUTION -- does the more-exhausted side identify the rescued side?")
    print("=" * 100)
    print("  q2e's price proxy got this right only 3/6.  Structure needs no price.")
    ok = tie = 0
    for i in sorted(events):
        dec, tr = events[i]
        s = st[i]
        gt, go = s.gone(tr, dec), s.gone(OPP[tr], dec)
        mark = "OK " if gt > go else ("tie" if gt == go else "NO ")
        ok += gt > go
        tie += gt == go
        print(f"    cycle {i:<4} trend={tr}  gone[trend]={gt:>3}  gone[opp]={go:>3}   "
              f"{mark}  (maxfill {s.maxfill(tr,dec)} vs {s.maxfill(OPP[tr],dec)})")
    print(f"    more-exhausted side == rescued side in {ok}/6 (ties {tie})")

    # ------------------------------------------------------------------ panel D
    print()
    print("=" * 100)
    print("D. DURATION CONFOUND -- are the rescue cycles simply the long ones?")
    print("=" * 100)
    durs = []
    for c in fin:
        if c.end:
            durs.append(((c.end - c.start).total_seconds() / 3600.0,
                         c.index, c.index in events))
    durs.sort(reverse=True)
    print(f"  final-regime cycles with a known end: {len(durs)}")
    print(f"  {'rank':>5} {'hours':>8} {'cyc':>5}  rescue?")
    for r, (h, i, f) in enumerate(durs[:16], 1):
        print(f"  {r:>5} {h:>8.2f} {i:>5}  {'YES' if f else ''}")
    ranks = [r for r, (h, i, f) in enumerate(durs, 1) if f]
    print(f"\n  ranks of the 6 rescue cycles by duration: {ranks} of {len(durs)}")
    print(f"  duration alone: top-{max(ranks)} contains all 6 -> "
          f"{max(ranks)-6} falsifiers if duration were the rule")


if __name__ == "__main__":
    main()
