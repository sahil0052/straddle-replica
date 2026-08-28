"""
parity_full_audit.py -- ONE consolidated, method-identical parity audit of our live
account against the Target EA's book.

WHY THIS SCRIPT EXISTS
----------------------
Over this project the parity question has been answered piecemeal by ~90 separate
forensics scripts, each with its own sweep definition, its own regime boundary and
its own P&L formula.  That fragmentation is how several false gaps were manufactured
(see the near-miss log in AGENTS.md).  This script measures every live discriminator
on BOTH books with EXACTLY the same code path, so a difference in the output is a
difference in behaviour and not a difference in instrumentation.

THE TWO REGIME BOUNDARIES -- DO NOT CONFLATE THEM
-------------------------------------------------
  dataset.FINAL_REGIME_START = 2026-07-14   <- the LOT-SCHEDULE break
  PACING_BREAK               = 2026-07-24   <- the CLOSE-PACING break (20 s family)
The comparable Target population for our live EA is the POST-PACING-BREAK slice,
2026-07-24 12:00 -> 2026-07-30.  Everything before that ran a different close cadence
and mixes two behaviours into one median.  Every Target figure in this script is
reported for both slices so the reader can see which one is being compared.

THE SWEEP DEFINITION (validated, do not change without re-deriving)
------------------------------------------------------------------
A basket flatten is identified by the stop_loss discriminator, NOT by comment text:
    p.stop_loss == 0 (or blank)  ->  closed by an explicit market close  (FLATTEN leg)
    p.stop_loss  > 0            ->  closed by its own trailing stop     (SL leg)
This holds on both books: our orders carry an SL at send time 0/1983 and the Target's
0/37047, so a non-zero stop_loss can only have been written by the ratchet, and a
position whose stop_loss is still zero at close time can only have been closed by
BeginClose().  A sweep is the set of stop-free closes inside a 900 s window opened by
the first such close; sweeps of >= 4 legs are kept.

CYCLE P&L is every close (SL legs included) between the end of the previous sweep and
the end of this sweep.  That is the only definition that reconciles to the balance --
verified on our stream: the cycle values plus the post-last-sweep tail equal
balance - 5000.00 exactly.
"""

from __future__ import annotations

import os
import statistics as st
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.forensics import dataset as DS  # noqa: E402

PACING_BREAK = datetime(2026, 7, 24, 12, 0, 0)
SWEEP_MAX = 900.0
MIN_LEGS = 4

GOLDEN = ROOT / ".cache" / "golden"
VANTAGE = ROOT / ".cache" / "vantage"
FRESH = ROOT / ".cache" / "fresh"


# ----------------------------------------------------------------------------- utils
def med(xs):
    return st.median(xs) if xs else float("nan")


def pct(n, d):
    return 100.0 * n / d if d else float("nan")


def spearman(xs, ys):
    n = len(xs)
    if n < 3:
        return None

    def ranks(v):
        order = sorted(range(n), key=lambda i: v[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    rx, ry = ranks(xs), ranks(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = sum((a - mx) ** 2 for a in rx) ** 0.5
    dy = sum((b - my) ** 2 for b in ry) ** 0.5
    return num / (dx * dy) if dx and dy else None


def flat_leg(p) -> bool:
    """True if this position was closed by an explicit market close, not by its SL."""
    return not (p.stop_loss and p.stop_loss > 0)


def level_of(p):
    m = DS.GRID_RE.match((p.comment or "").strip())
    return int(m.group(2)) if m else None


def inversion_rate(sw):
    """Fraction of leg pairs closed in reverse-of-open order.  1.0 = pure LIFO."""
    n = len(sw)
    inv = tot = 0
    for i in range(n):
        for j in range(i + 1, n):
            ti, tj = sw[i].open_time, sw[j].open_time
            if ti == tj:
                continue
            tot += 1
            if ti > tj:
                inv += 1
    return (inv / tot) if tot else None


# ------------------------------------------------------------------------- the loader
class Stream:
    def __init__(self, label, dirpath, lo=None, hi=None):
        self.label = label
        DS.GOLDEN = dirpath
        orders, positions, deals, cycles = DS.load_all()
        self.orders = orders
        self.deals = deals
        self.cycles = cycles
        cl = [p for p in positions if not p.is_open and p.close_time]
        if lo:
            cl = [p for p in cl if p.close_time >= lo]
        if hi:
            cl = [p for p in cl if p.close_time < hi]
        cl.sort(key=lambda p: p.close_time)
        self.closed = cl
        self.sweeps = self._build_sweeps()
        self.cycle_pnl = self._build_cycle_pnl()

    def _build_sweeps(self):
        out = []
        used = set()
        for i, p in enumerate(self.closed):
            if i in used or not flat_leg(p):
                continue
            t0 = p.close_time
            sw, idx = [], []
            for j in range(i, len(self.closed)):
                q = self.closed[j]
                if (q.close_time - t0).total_seconds() > SWEEP_MAX:
                    break
                if j in used or not flat_leg(q):
                    continue
                sw.append(q)
                idx.append(j)
            if len(sw) >= MIN_LEGS:
                out.append(sw)
                used.update(idx)
        return out

    def _build_cycle_pnl(self):
        """P&L of every close between the end of one sweep and the end of the next."""
        out = []
        prev = None
        for sw in self.sweeps:
            end = sw[-1].close_time
            legs = [
                p
                for p in self.closed
                if (prev is None or p.close_time > prev) and p.close_time <= end
            ]
            out.append(
                {
                    "start": sw[0].close_time,
                    "end": end,
                    "span": (end - sw[0].close_time).total_seconds(),
                    "legs": len(sw),
                    "sweep_pnl": sum(p.net for p in sw),
                    "cycle_pnl": sum(p.net for p in legs),
                    "win_legs": sum(1 for p in sw if p.net > 0),
                    "lose_legs": sum(1 for p in sw if p.net < 0),
                }
            )
            prev = end
        return out

    # ------------------------------------------------------------------ measurements
    def m_closure_mix(self):
        sl = sum(1 for p in self.closed if not flat_leg(p))
        fl = len(self.closed) - sl
        return sl, fl, pct(sl, len(self.closed))

    def m_ratchet(self):
        """Terminal SL distance in steps, split by ratchet phase."""
        step_by_cyc = {}
        for c in self.cycles:
            step_by_cyc[c.index] = c.step
        p1, p2 = [], []
        neg = 0
        for p in self.closed:
            if flat_leg(p):
                continue
            step = None
            for c in self.cycles:
                if c.start <= p.open_time and (c.end is None or p.open_time <= c.end):
                    step = c.step
                    break
            if not step:
                continue
            if p.stop_loss <= 0:
                neg += 1
                continue
            d = abs(p.close_price - p.open_price) / step
            fav = (p.close_price - p.open_price) * (1 if p.side == "buy" else -1) / step
            (p1 if fav < 2.0 else p2).append(d)
        return med(p1), len(p1), med(p2), len(p2), neg

    def m_pacing(self):
        gaps = []
        for sw in self.sweeps:
            for a, b in zip(sw, sw[1:]):
                gaps.append((b.close_time - a.close_time).total_seconds())
        exact20 = sum(1 for g in gaps if abs(g - round(g / 20.0) * 20.0) < 0.05 and g > 5)
        return med(gaps), len(gaps), exact20

    def m_burst_shape(self):
        red = sum(1 for c in self.cycle_pnl if c["sweep_pnl"] < 0)
        redpos = sum(
            1 for c in self.cycle_pnl if c["sweep_pnl"] < 0 and c["cycle_pnl"] > 0
        )
        neg = sum(1 for c in self.cycle_pnl if c["cycle_pnl"] < 0)
        return (
            pct(red, len(self.cycle_pnl)),
            pct(redpos, red),
            med([c["sweep_pnl"] for c in self.cycle_pnl]),
            med([c["cycle_pnl"] for c in self.cycle_pnl]),
            pct(neg, len(self.cycle_pnl)),
        )

    def m_lifo(self):
        rates = [r for r in (inversion_rate(sw) for sw in self.sweeps) if r is not None]
        exact_lifo = sum(1 for r in rates if r == 1.0)
        exact_fifo = sum(1 for r in rates if r == 0.0)
        return med(rates), len(rates), exact_lifo, exact_fifo, sum(
            1 for r in rates if r >= 0.90
        )

    def m_level_order(self):
        rhos, inner, outer, norule = [], 0, 0, 0
        for sw in self.sweeps:
            lv = [level_of(p) for p in sw]
            if any(v is None for v in lv):
                continue
            r = spearman(list(range(len(lv))), lv)
            if r is None:
                continue
            rhos.append(r)
            if r > 0.5:
                inner += 1
            elif r < -0.5:
                outer += 1
            else:
                norule += 1
        return med(rhos), len(rhos), inner, outer, norule

    def m_lots(self):
        tiers = {}
        for p in self.closed:
            lv = level_of(p)
            if lv is None:
                continue
            band = "L1-10" if lv <= 10 else ("L11-20" if lv <= 20 else "L21+")
            tiers.setdefault(band, set()).add(round(p.volume, 2))
        mx = max((level_of(p) or 0) for p in self.closed) if self.closed else 0
        over = sum(1 for p in self.closed if (level_of(p) or 0) > 30)
        return tiers, mx, over

    def m_perpos(self):
        sl = [p.net for p in self.closed if not flat_leg(p)]
        fl = [p.net for p in self.closed if flat_leg(p)]
        perlot = [p.net / p.volume for p in self.closed if p.volume]
        return med(sl), med(fl), med(perlot)

    def m_depth(self):
        return med([c["legs"] for c in self.cycle_pnl]), med(
            [c["span"] for c in self.cycle_pnl]
        )

    def m_cascade(self):
        """Fraction of consecutive SL-close pairs separated by < 100 ms."""
        sl = [p for p in self.closed if not flat_leg(p)]
        sl.sort(key=lambda p: p.close_time)
        n = sub = 0
        for a, b in zip(sl, sl[1:]):
            n += 1
            if (b.close_time - a.close_time).total_seconds() < 0.100:
                sub += 1
        return pct(sub, n), n

    def m_doubling(self):
        """Legs whose volume is exactly 2x the base tier for their level."""
        base = {}
        for p in self.closed:
            lv = level_of(p)
            if lv is None:
                continue
            base.setdefault(lv, []).append(round(p.volume, 2))
        mode = {lv: min(v) for lv, v in base.items()}
        dbl = tot = 0
        for p in self.closed:
            lv = level_of(p)
            if lv is None or lv not in mode:
                continue
            tot += 1
            if abs(round(p.volume, 2) - 2.0 * mode[lv]) < 1e-9 and mode[lv] > 0:
                dbl += 1
        return dbl, tot, pct(dbl, tot)


# ------------------------------------------------------------------------------ main
def main():
    print("=" * 100)
    print("CONSOLIDATED PARITY AUDIT -- identical method on every stream")
    print("=" * 100)

    streams = []
    streams.append(Stream("TARGET pre-break", GOLDEN, hi=PACING_BREAK))
    streams.append(Stream("TARGET post-break", GOLDEN, lo=PACING_BREAK))
    if (VANTAGE / "positions.csv").exists():
        streams.append(Stream("OURS 25954110", VANTAGE))
    if (FRESH / "positions.csv").exists():
        streams.append(Stream("OURS 111638511", FRESH))

    for s in streams:
        span = (
            f"{s.closed[0].close_time:%Y-%m-%d} -> {s.closed[-1].close_time:%Y-%m-%d}"
            if s.closed
            else "empty"
        )
        print(
            f"  {s.label:<20} closed {len(s.closed):>6}  sweeps {len(s.sweeps):>4}"
            f"  cycles {len(s.cycle_pnl):>4}   {span}"
        )

    def cell(v, w):
        return f"{v:<{-w}}" if w < 0 else f"{v:>{w}}"

    def table(title, rows, hdr):
        print()
        print("-" * 100)
        print(title)
        print("-" * 100)
        print("  " + "".join(cell(h, w) for h, w in hdr))
        for r in rows:
            print("  " + "".join(cell(v, w) for v, (_, w) in zip(r, hdr)))

    # A -- closure mix
    rows = []
    for s in streams:
        sl, fl, p = s.m_closure_mix()
        rows.append([s.label, f"{sl}", f"{fl}", f"{p:.1f}%"])
    table(
        "A  CLOSURE MIX -- how positions leave the book",
        rows,
        [("stream", -22), ("by SL", 10), ("by flatten", 12), ("SL share", 10)],
    )

    # B -- ratchet
    rows = []
    for s in streams:
        a, na, b, nb, neg = s.m_ratchet()
        rows.append(
            [s.label, f"{a:.3f}", f"{na}", f"{b:.3f}", f"{nb}", f"{neg}"]
        )
    table(
        "B  TRAILING RATCHET -- terminal SL distance in grid steps",
        rows,
        [
            ("stream", -22),
            ("phase1 med", 12),
            ("n", 7),
            ("phase2 med", 12),
            ("n", 7),
            ("negSL", 7),
        ],
    )

    # C -- pacing
    rows = []
    for s in streams:
        m, n, e = s.m_pacing()
        rows.append([s.label, f"{m:.2f}s", f"{n}", f"{e}", f"{pct(e,n):.1f}%"])
    table(
        "C  CLOSE PACING -- seconds between consecutive flatten legs",
        rows,
        [("stream", -22), ("median gap", 12), ("n gaps", 9), ("exact x20", 11), ("share", 9)],
    )

    # D -- burst shape
    rows = []
    for s in streams:
        red, redpos, mb, mc, negc = s.m_burst_shape()
        rows.append(
            [s.label, f"{red:.0f}%", f"{redpos:.0f}%", f"{mb:+.2f}", f"{mc:+.2f}", f"{negc:.1f}%"]
        )
    table(
        "D  CLOSING-BURST SHAPE -- is the visible flatten red, and does the cycle still win?",
        rows,
        [
            ("stream", -22),
            ("burst red", 11),
            ("yet cyc +", 11),
            ("med burst", 11),
            ("med cycle", 11),
            ("cyc lost", 10),
        ],
    )

    # E -- LIFO
    rows = []
    for s in streams:
        m, n, el, ef, ge = s.m_lifo()
        rows.append([s.label, f"{m:.3f}", f"{n}", f"{el}", f"{ef}", f"{ge}"])
    table(
        "E  SWEEP DIRECTION -- inversion rate (1.0 = pure LIFO / newest first)",
        rows,
        [("stream", -22), ("median", 10), ("sweeps", 9), ("=LIFO", 8), ("=FIFO", 8), (">=0.90", 9)],
    )

    # F -- level order
    rows = []
    for s in streams:
        m, n, i, o, nr = s.m_level_order()
        rows.append([s.label, f"{m:+.3f}", f"{n}", f"{i}", f"{o}", f"{nr}"])
    table(
        "F  SWEEP LEVEL ORDER -- rho(close position, grid level) from COMMENTS",
        rows,
        [("stream", -22), ("median rho", 12), ("sweeps", 9), ("inner1st", 10), ("outer1st", 10), ("no rule", 9)],
    )

    # G -- lots
    print()
    print("-" * 100)
    print("G  LOT SCHEDULE + LADDER DEPTH")
    print("-" * 100)
    for s in streams:
        tiers, mx, over = s.m_lots()
        t = "  ".join(
            f"{k} {sorted(tiers[k])}" for k in ("L1-10", "L11-20", "L21+") if k in tiers
        )
        print(f"  {s.label:<22} maxlevel {mx:>3}  levels>30 {over:>5}   {t}")

    # H -- per-position money
    rows = []
    for s in streams:
        a, b, c = s.m_perpos()
        rows.append([s.label, f"{a:+.2f}", f"{b:+.2f}", f"{c:+.1f}"])
    table(
        "H  PER-POSITION MONEY",
        rows,
        [("stream", -22), ("med SL exit", 13), ("med flat exit", 15), ("med per-lot", 13)],
    )

    # I -- depth / duration
    rows = []
    for s in streams:
        legs, span = s.m_depth()
        rows.append([s.label, f"{legs:.1f}", f"{span:.0f}s"])
    table(
        "I  BASKET DEPTH AT TRIGGER + SWEEP DURATION",
        rows,
        [("stream", -22), ("med legs", 11), ("med span", 11)],
    )

    # J -- cascade
    rows = []
    for s in streams:
        p, n = s.m_cascade()
        rows.append([s.label, f"{p:.2f}%", f"{n}"])
    table(
        "J  SIMULTANEOUS STOP-OUT CASCADE -- consecutive SL closes < 100 ms apart",
        rows,
        [("stream", -22), ("sub-100ms", 12), ("pairs", 9)],
    )

    # K -- doubling
    rows = []
    for s in streams:
        d, t, p = s.m_doubling()
        rows.append([s.label, f"{d}", f"{t}", f"{p:.2f}%"])
    table(
        "K  TREND-RESCUE DOUBLING -- legs at exactly 2x their level's base lot",
        rows,
        [("stream", -22), ("doubled", 10), ("base legs", 11), ("rate", 9)],
    )

    # L -- stop discipline at send
    print()
    print("-" * 100)
    print("L  STOP DISCIPLINE AT SEND -- orders that carried an SL in the request")
    print("-" * 100)
    for s in streams:
        with_sl = sum(1 for o in s.orders if getattr(o, "stop_loss", 0) or 0)
        print(f"  {s.label:<22} {with_sl} / {len(s.orders)}")

    # per-cycle detail for our live stream
    for s in streams:
        if not s.label.startswith("OURS 25954110"):
            continue
        print()
        print("=" * 100)
        print(f"PER-CYCLE DETAIL -- {s.label}")
        print("=" * 100)
        print(
            f"  {'#':>3} {'sweep start':<24}{'span_s':>8}{'legs':>6}"
            f"{'sweepPnL':>11}{'cyclePnL':>11}{'win':>5}{'lose':>6}{'inv':>7}"
        )
        tot = 0.0
        for i, c in enumerate(s.cycle_pnl):
            inv = inversion_rate(s.sweeps[i])
            tot += c["cycle_pnl"]
            print(
                f"  {i:>3} {c['start']!s:<24}{c['span']:>8.1f}{c['legs']:>6}"
                f"{c['sweep_pnl']:>+11.2f}{c['cycle_pnl']:>+11.2f}"
                f"{c['win_legs']:>5}{c['lose_legs']:>6}"
                f"{(f'{inv:.3f}' if inv is not None else '-'):>7}"
            )
        last = s.cycle_pnl[-1]["end"] if s.cycle_pnl else None
        tail = [p for p in s.closed if last and p.close_time > last]
        print(f"\n  {len(s.cycle_pnl)} cycles sum {tot:+.2f}")
        print(f"  closes after last sweep: {len(tail)}  sum {sum(p.net for p in tail):+.2f}")
        print(f"  GRAND TOTAL {tot + sum(p.net for p in tail):+.2f}")


if __name__ == "__main__":
    main()
