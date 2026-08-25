"""111638511 versus the Target EA: the only comparison that is now live.

SCOPE.  Earlier scripts compared three accounts because three were trading.  Two
are now retired: 111387094 (the old replica) and the pre-rebuild build it ran.
The operator's instruction is to compare ONLY 111638511 -- the account the EA is
actually running on -- against the Target EA's history.  Everything else is
history and is excluded here.

WHAT 111638511 IS, PRECISELY, BECAUSE IT BOUNDS THE EVIDENCE.  The local terminal
at C:\\Program Files\\MetaTrader 5 is logged into 111638511 with the INVESTOR
password (title bar reads "Read Only") and its Algo Trading button is off.  Its
MQL5\\Logs directory is EMPTY and its MQL5\\Files directory is empty, so the EA is
not attached there and writes no telemetry we can read.  The orders are
nonetheless being placed, which means the EA is executing off-box -- MQL5 VPS --
and this terminal is a read-only observer of it.

Consequences, stated because they are limits on every number below:

  * The ONLY evidence for 111638511 is the terminal's Trades-category log:
    fills, with millisecond timestamps, volume and price.  Nothing else.
  * No SL amendments are logged, by MT5 design.  The trailing ratchet -- the
    single largest body of Target behaviour, 2695 SL-closed positions in the
    XLSX -- is INVISIBLE on this account and cannot be checked here.
  * Deals carry no P&L, so the $30 basket target is untestable here too.
  * A stop fill and a flatten fill are indistinguishable.

TIME BASE.  Log timestamps are LOCAL PC time; the Trade tab shows SERVER time.
Deal #9906581477 is logged at 22:47:05 and shown in the terminal at 20:17:05, a
2h30m offset (IST vs the demo server's EET).  Both accounts' logs come from the
same PC clock, so pacing comparisons between them are valid; only absolute
wall-clock labels differ from what the operator sees on screen.

WHAT THE LADDER LOOKS LIKE RIGHT NOW, from the terminal's own order list, as an
independent check on the lattice arithmetic:

    anchor 4640.00   step 1.55  ( = 4640/3000 normalised to 2 digits )
    buy   L1..L10  4641.55 .. 4655.50 @ 0.01      0.06 begins at L11 = 4657.05
    sell  L1..L10  4638.45 .. 4624.50 @ 0.01
    sell  L11..L20 4622.95 .. 4609.00 @ 0.06      (exactly ten orders)
    sell  L21..L30 4607.45 .. 4593.50 @ 0.15      4640 - 30*1.55 = 4593.50

so the deployed ladder is exact to the cent on both sides and the tier
boundaries fall precisely on levels 10/20, matching ProfileCatalog's
SetLotTier(1,10,0.01) / (11,20,0.06) / (21,30,0.15).  The lattice is not where a
gap lives; this script looks for the gap everywhere else.
"""
from __future__ import annotations

import os
import statistics
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
from tools.forensics.live_stream_parity import load, TARGET, FRESH  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DIVISOR = 3000.0
LOTS = (0.01, 0.06, 0.15)
CYCLE_GAP = 180.0        # a silence this long is treated as a cycle boundary


def rule(t: str) -> None:
    print()
    print("=" * 100)
    print(t)
    print("=" * 100)


def pc(a: int, b: int) -> str:
    return f"{100.0 * a / b:5.1f}%" if b else "    --"


def tier_of(vol: float) -> str:
    for i, base in enumerate(LOTS, start=1):
        if abs(vol - base) < 1e-9:
            return f"L{(i - 1) * 10 + 1}-{i * 10}"
        if abs(vol - base * 2.0) < 1e-9:
            return f"L{(i - 1) * 10 + 1}-{i * 10}*"
    return f"?{vol:g}"


def gaps_of(ds):
    return [(b.t - a.t).total_seconds() for a, b in zip(ds, ds[1:])
            if 0.0 <= (b.t - a.t).total_seconds() <= 86400.0]


def clusters_of(ds, window=0.100):
    out, cur = [], [ds[0]] if ds else []
    for a, b in zip(ds, ds[1:]):
        if (b.t - a.t).total_seconds() < window:
            cur.append(b)
        else:
            if len(cur) > 1:
                out.append(cur)
            cur = [b]
    if len(cur) > 1:
        out.append(cur)
    return out


def main() -> None:
    st = load()
    pair = (("TARGET ", st.get(TARGET, [])), ("111638511", st.get(FRESH, [])))

    rule("0. THE TWO STREAMS")
    for name, ds in pair:
        if not ds:
            print(f"  {name}: EMPTY")
            continue
        days = sorted({d.t.date() for d in ds})
        sides = Counter(d.side for d in ds)
        print(f"  {name}  n={len(ds):>5}  {len(days)} day(s)  {days[0]}..{days[-1]}"
              f"  lots={sum(d.vol for d in ds):>7.2f}"
              f"  buy/sell={sides['buy']}/{sides['sell']}"
              f" (buy {pc(sides['buy'], len(ds))})")
    print()
    print("  The Target has 13 days and 111638511 has far fewer, so every RATE")
    print("  below is comparable but no TOTAL is.  Rates only.")

    # ------------------------------------------------------------------ panel 1
    rule("1. VOLUME LADDER AND EXPOSURE DENSITY")
    print("  Volume tags the level band a fill lives in (rescue leg = 2x, marked *).")
    print("  lots/fill is the exposure statistic: a basket's $/point is set by lots.")
    print()
    dens = {}
    for name, ds in pair:
        if not ds:
            continue
        c = Counter(tier_of(d.vol) for d in ds)
        n, lots = len(ds), sum(d.vol for d in ds)
        dens[name] = lots / n
        deep = sum(k for t, k in c.items() if t.startswith("L21"))
        mid = sum(k for t, k in c.items() if t.startswith("L11"))
        print(f"  {name}  n={n:>5}  lots={lots:>7.2f}  lots/fill={lots / n:.4f}"
              f"   L11-20={pc(mid, n)}  L21-30={pc(deep, n)}")
        for t, k in sorted(c.items()):
            print(f"      {t:>9} : {k:>5}  {pc(k, n)}  "
                  f"{'#' * max(1, round(40.0 * k / n))}")
        print()
    if len(dens) == 2:
        r = dens["111638511"] / dens["TARGET "]
        print(f"  exposure density 111638511 / TARGET = {r:.2f}x")
        print("  1.00x is parity.  Below 1.0 means we sit shallower in the ladder")
        print("  than the Target does -- safer, but not identical.")

    # ------------------------------------------------------------------ panel 2
    rule("2. LATTICE STEP ADHERENCE  (mode-free)")
    print("  step must equal anchor/3000 and therefore drifts with gold.  For each")
    print("  day, take |dP| between consecutive same-side fills and report the share")
    print("  landing within +-5% of medianprice/3000.  No mode is picked, so this")
    print("  cannot manufacture a defect the way a modal estimator can.")
    print()
    print(f"  {'stream':>10} {'day':>11} {'n':>5} {'medpx':>7} {'expect':>7}"
          f" {'adhere':>7} {'med|dP|':>8}")
    for name, ds in pair:
        byday = defaultdict(list)
        last = {}
        for d in ds:
            p = last.get(d.side)
            if p is not None and p.t.date() == d.t.date():
                dt = (d.t - p.t).total_seconds()
                g = round(abs(d.price - p.price), 2)
                if 0 < dt <= 120.0 and 0.05 <= g <= 8.0:
                    byday[d.t.date()].append((g, d.price))
            last[d.side] = d
        for day in sorted(byday):
            rows = byday[day]
            if len(rows) < 12:
                continue
            medpx = statistics.median([p for _, p in rows])
            exp = medpx / DIVISOR
            adh = sum(1 for g, _ in rows if abs(g - exp) <= 0.05 * exp)
            print(f"  {name:>10} {str(day):>11} {len(rows):>5} {medpx:>7.0f}"
                  f" {exp:>7.2f} {pc(adh, len(rows))} "
                  f"{statistics.median([g for g, _ in rows]):>8.2f}")

    # ------------------------------------------------------------------ panel 3
    rule("3. THE 20-SECOND METRONOME  (rearm_delay_seconds = 20)")
    print("  The Target quantises its fill stream to 20 s.  This is the sharpest")
    print("  single parity statistic a terminal log can produce.")
    print()
    buckets = [(0.0, 0.001, "same ms"), (0.001, 0.1, "<100ms"),
               (0.1, 1.0, "0.1-1s"), (1.0, 5.0, "1-5s"), (5.0, 15.0, "5-15s"),
               (15.0, 25.0, "15-25s <- 20s"), (25.0, 60.0, "25-60s"),
               (60.0, 300.0, "1-5min"), (300.0, 86400.0, ">5min")]
    for name, ds in pair:
        dl = gaps_of(ds)
        if len(dl) < 10:
            continue
        print(f"  {name}  n={len(dl)} gaps")
        for lo, hi, nm in buckets:
            k = sum(1 for x in dl if lo <= x < hi)
            print(f"      {nm:>16} : {k:>5}  {pc(k, len(dl))}"
                  f"  {'#' * round(40.0 * k / len(dl))}")
        band = [x for x in dl if 19.0 <= x <= 21.5]
        if band:
            print(f"      [19.0,21.5] n={len(band)} ({pc(len(band), len(dl))})"
                  f"  median={statistics.median(band):.3f}s")
        print()

    # ------------------------------------------------------------------ panel 4
    rule("4. ONE ACTION PER TICK  (sub-100 ms clusters = duplicate-fire defect)")
    print("  Members ~one step apart = broker sweeping resting pendings, legitimate.")
    print("  Members at near-identical prices = the EA firing repeatedly in one tick.")
    print()
    for name, ds in pair:
        if len(ds) < 4:
            continue
        cl = clusters_of(ds)
        dl = gaps_of(ds)
        inv = sum(len(c) for c in cl)
        print(f"  {name}  {len(cl)} clusters, {inv} fills ({pc(inv, len(ds))} of stream)"
              f"   same-ms gaps={sum(1 for x in dl if x < 0.001)}")
        if not cl:
            print("      (none -- fully serialised)")
            print()
            continue
        print(f"      sizes {dict(sorted(Counter(len(c) for c in cl).items()))}")
        spreads = sorted(round(max(d.price for d in c) - min(d.price for d in c), 2)
                         for c in cl)
        tight = sum(1 for s in spreads if s < 0.30)
        print(f"      spread median {statistics.median(spreads):.2f}"
              f"  tighter-than-0.30 {tight}/{len(cl)} = {pc(tight, len(cl))}")
        for c in cl[:5]:
            print("        " + f"{c[0].t.date()} " + " | ".join(
                f"{d.t.strftime('%H:%M:%S.%f')[:-3]} {d.side[0]}{d.vol:g}@{d.price:.2f}"
                for d in c))
        print()

    # ------------------------------------------------------------------ panel 5
    rule("5. CYCLE STRUCTURE  (silences >= 3 min treated as boundaries)")
    print("  Fills per cycle and cycle duration are shape statistics that survive")
    print("  without P&L.  A basket that closes on +$30 should show a characteristic")
    print("  size; a basket that never reaches it runs long and wide.")
    print()
    for name, ds in pair:
        if len(ds) < 10:
            continue
        blocks, cur = [], [ds[0]]
        for a, b in zip(ds, ds[1:]):
            if (b.t - a.t).total_seconds() >= CYCLE_GAP:
                blocks.append(cur)
                cur = [b]
            else:
                cur.append(b)
        blocks.append(cur)
        sizes = [len(b) for b in blocks]
        durs = [(b[-1].t - b[0].t).total_seconds() / 60.0 for b in blocks]
        lots = [sum(d.vol for d in b) for b in blocks]
        print(f"  {name}  {len(blocks)} blocks")
        print(f"      fills/block : median {statistics.median(sizes):.0f}"
              f"  mean {statistics.fmean(sizes):.1f}  max {max(sizes)}")
        print(f"      minutes     : median {statistics.median(durs):.1f}"
              f"  mean {statistics.fmean(durs):.1f}  max {max(durs):.0f}")
        print(f"      lots/block  : median {statistics.median(lots):.2f}"
              f"  max {max(lots):.2f}")
        two = sum(1 for b in blocks if len({d.side for d in b}) == 2)
        print(f"      both sides filled in block : {two}/{len(blocks)}"
              f" = {pc(two, len(blocks))}")
        print()


if __name__ == "__main__":
    main()
