"""Q2e: is the huge lead real, or is it stale-mark noise?

q2d's conjunction sweep found no admissible parameterisation:

    -X    K  miss  fals  sideOK  lead med  lead max
   150    1     0    12     3/6     212.0     697.8
   200    1     1     7     4/6       0.1     355.7
   400    1     2     3     3/6      30.0     355.7

Three symptoms, and they point at the reconstruction rather than at the threshold:

  * leads of 212-698 minutes.  Under AGENTS.md section 3 that refutes the rule as a
    trigger -- but only if the "first true" instant is real.
  * NEGATIVE leads (-8, -21, -68, -167 min).  The EA cannot have acted before its own
    condition was satisfied.  A negative lead is a proof of measurement error, not of
    a rule.
  * side agreement only 3/6, when the side is the most mechanically determined part
    of the whole trigger.

All three have one candidate cause.  The price series here is not a tick feed: it is
the set of fill and close prints, so between prints the reconstructed mark is FROZEN
at the last trade.  In a quiet stretch that mark can be minutes or hours stale, and
floating is linear in it, so a stale mark produces an arbitrarily wrong drawdown.
q2c already measured print ages of 0s, 2s, 47s, 227s, 196s and 28s AT the six
decision instants -- and those are the busiest moments in each cycle.  Hours earlier,
in the quiet stretch that produced the "first true", the mark is far worse.

The M15 prior close has the same defect twice over: the bar close is the last print
IN that bar, and if a bar has no prints at all the lookup silently walks back to an
older bar.

So: re-run the sweep with a freshness gate, and sweep the gate.  If the long leads
and the negative leads dissolve as the gate tightens, they were artifacts and the
conjunction is admissible.  If they survive a 15-second gate, the rule is wrong.

Panel A  lead and falsifier counts vs mark-freshness gate.
Panel B  per-event detail at the tightest gate, including which side disagreed.
Panel C  how stale the series actually is -- the print-gap distribution, so the
         gate's cost in coverage is visible rather than assumed.
"""
from __future__ import annotations

import statistics
import sys
from bisect import bisect_right
from datetime import datetime, timedelta

sys.path.insert(0, r"C:\websites\mt5 2")
from tools.forensics.dataset import load_all, FINAL_REGIME_START, CONTRACT  # noqa: E402

M15 = timedelta(minutes=15)
MOVE = 20.0


def tier_lot(level: int) -> float:
    return 0.01 if level <= 10 else (0.06 if level <= 20 else 0.15)


def is_base(o) -> bool:
    return abs(o.volume - tier_lot(o.level)) < 1e-9


def is_rescue(o) -> bool:
    return abs(o.volume - 2.0 * tier_lot(o.level)) < 1e-9


def m15_floor(t: datetime) -> datetime:
    return t.replace(minute=(t.minute // 15) * 15, second=0, microsecond=0)


def main() -> None:
    orders, positions, deals, cycles = load_all()

    prints: list[tuple[datetime, float]] = []
    for p in positions:
        prints.append((p.open_time, p.open_price))
        if p.close_time and p.close_price:
            prints.append((p.close_time, p.close_price))
    prints.sort(key=lambda r: r[0])
    ptimes = [t for t, _ in prints]
    pvals = [v for _, v in prints]
    bars: dict[datetime, float] = {}
    for t, v in prints:
        bars[m15_floor(t)] = v
    bar_keys = sorted(bars)

    def price_age(t):
        i = bisect_right(ptimes, t) - 1
        if i < 0:
            return None, 1e9
        return pvals[i], (t - ptimes[i]).total_seconds()

    def prior_close(t, back=6):
        """Return (close, True) only if the bar 6 back actually HAS prints."""
        want = m15_floor(t) - back * M15
        if want in bars:
            return bars[want], True
        i = bisect_right(bar_keys, want) - 1
        return (bars[bar_keys[i]], False) if i >= 0 else (None, False)

    fin = [c for c in cycles if c.start >= FINAL_REGIME_START]

    events = {}
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

    def scan(cyc, dd, pend_k, max_age, strict_bar):
        idx = {}
        for sd in ("B", "S"):
            st, en = [], []
            for o in cyc.orders:
                if (o.is_grid and o.level is not None and o.side == sd
                        and is_base(o)):
                    st.append(o.open_time)
                    en.append(o.end_time if o.end_time else datetime.max)
            idx[sd] = (sorted(st), sorted(en))
        ev = []
        for p in cyc.positions:
            a = p.dir * p.volume * CONTRACT
            ev.append((p.open_time, a, a * p.open_price, p.swap))
            if p.close_time:
                ev.append((p.close_time, -a, -a * p.open_price, -p.swap))
        ev.sort(key=lambda r: r[0])
        grid = sorted({e[0] for e in ev} |
                      {o.open_time for o in cyc.orders} |
                      {o.end_time for o in cyc.orders if o.end_time})
        A = B = C = 0.0
        j = 0
        for g in grid:
            while j < len(ev) and ev[j][0] <= g:
                A += ev[j][1]; B += ev[j][2]; C += ev[j][3]; j += 1
            mark, age = price_age(g)
            if mark is None or age > max_age:
                continue
            pc, exact = prior_close(g)
            if pc is None or (strict_bar and not exact):
                continue
            mv = mark - pc
            if abs(mv) < MOVE:
                continue
            if mark * A - B + C > -dd:
                continue
            sd = "B" if mv > 0 else "S"
            st, en = idx[sd]
            if bisect_right(st, g) - bisect_right(en, g) < pend_k:
                continue
            return g, sd, (mark * A - B + C), mv
        return None, None, None, None

    # ------------------------------------------------------------------ panel A
    print("=" * 100)
    print("A. FRESHNESS GATE -- do the long and negative leads dissolve?")
    print("=" * 100)
    print("  age = maximum allowed staleness of the reconstructed mark, in seconds.")
    print("  strict = the M15 bar 6 back must actually contain prints.")
    print()
    print(f"  {'age':>6} {'strict':>7} {'-X':>5} {'K':>2} {'miss':>5} {'fals':>5} "
          f"{'side':>5} {'neg':>4} {'lead med':>9} {'lead max':>9}")
    for max_age, strict in ((1e9, False), (300.0, False), (60.0, False),
                            (30.0, True), (15.0, True), (5.0, True)):
        for dd in (150.0, 250.0, 350.0, 400.0):
            miss = fals = sideok = neg = 0
            leads = []
            for c in fin:
                g, sd, _, _ = scan(c, dd, 3, max_age, strict)
                if c.index in events:
                    dec, trend = events[c.index]
                    if g is None:
                        miss += 1
                    else:
                        v = (dec - g).total_seconds() / 60.0
                        leads.append(v)
                        neg += (v < -0.5)
                        sideok += (sd == trend)
                elif g is not None:
                    fals += 1
            lm = statistics.median(leads) if leads else float("nan")
            tag = f"{max_age:.0f}" if max_age < 1e8 else "inf"
            print(f"  {tag:>6} {str(strict):>7} {dd:>5.0f} {3:>2} {miss:>5} {fals:>5} "
                  f"{sideok:>3}/6 {neg:>4} {lm:>9.1f} "
                  f"{max(leads) if leads else 0:>9.1f}")
        print()

    # ------------------------------------------------------------------ panel B
    print("=" * 100)
    print("B. PER-EVENT at age<=15s, strict bars -- where does the rule first fire?")
    print("=" * 100)
    for dd in (150.0, 250.0, 400.0):
        print(f"\n  floating <= -{dd:.0f}:")
        print(f"    {'cyc':>4} {'trend':>5} {'firstTrue':<19} {'side':>4} "
              f"{'floating':>9} {'move':>7} {'decision':<19} {'lead(m)':>8}")
        for i in sorted(events):
            c = next(x for x in fin if x.index == i)
            g, sd, fl, mv = scan(c, dd, 3, 15.0, True)
            dec, trend = events[i]
            if g is None:
                print(f"    {i:>4} {trend:>5} {'never true':<19}"
                      f"{'':>4} {'':>9} {'':>7} {str(dec)[:19]:<19} {'MISS':>8}")
            else:
                print(f"    {i:>4} {trend:>5} {str(g)[:19]:<19} {sd:>4} "
                      f"{fl:>9.1f} {mv:>7.2f} {str(dec)[:19]:<19} "
                      f"{(dec-g).total_seconds()/60.0:>8.1f}")

    # ------------------------------------------------------------------ panel C
    print()
    print("=" * 100)
    print("C. HOW STALE IS THE SERIES?  print-to-print gap, final regime")
    print("=" * 100)
    gaps = [(b - a).total_seconds() for a, b in zip(ptimes, ptimes[1:])
            if a >= FINAL_REGIME_START]
    gaps.sort()
    n = len(gaps)
    print(f"  n={n}  median={statistics.median(gaps):.1f}s")
    for q in (50, 75, 90, 95, 99):
        print(f"    p{q:<3} {gaps[int(n*q/100)]:>10.1f}s")
    print(f"    max  {gaps[-1]:>10.1f}s   "
          f"({gaps[-1]/3600:.1f} h -- the mark is frozen this long at worst)")
    for lim in (5.0, 15.0, 30.0, 60.0, 300.0):
        print(f"    fraction of the timeline with a mark fresher than {lim:>5.0f}s: "
              f"{sum(g for g in gaps if g <= lim)/sum(gaps)*100:>5.1f}%")


if __name__ == "__main__":
    main()
