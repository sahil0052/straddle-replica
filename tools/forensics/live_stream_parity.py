"""Three-way LIVE parity: does the replica's own broker-attested fill stream
match the Target's, on the axes a terminal log can actually see?

Every previous script in this directory reads ReportHistory-901018.xlsx -- the
Target's history, and only the Target's.  Parity was therefore always an
INFERENCE: "the replica's code computes the same number the Target's history
shows".  That inference cannot see a divergence that lives outside the code:
a wrong preset on the running terminal, a different symbol tick size, a broker
that rejects a volume, a human clicking buttons.

This script closes that hole.  artifacts/live/terminal-logs/ holds 62 archived
MT5 terminal logs covering THREE accounts simultaneously:

    901018      the LIVE Target        (AchieverGlobalMarkets)
    111387094   the replica            (AchieverGlobalMarkets)
    111638511   a fresh demo           (MetaQuotes-Demo)

so for the first time the same instrument, the same measurement code and the
same units can be applied to Target and replica side by side.

WHAT A TERMINAL LOG CAN AND CANNOT PROVE -- read this before citing anything
below, because the limits are severe and asymmetric:

  CAN   volume ladder (every fill carries its volume)
  CAN   price lattice step (fill prices are exact, to the cent)
  CAN   pacing / serialization (millisecond timestamps)
  CAN   side balance, burst structure, session boundaries
  CANNOT stop-loss levels -- MT5's Trades category logs FILLS, not order
         amendments.  There is not one 'modify' line in 2.1 MB of logs.  The
         ratchet is INVISIBLE here and must keep being measured off the XLSX.
  CANNOT profit / balance -- deals carry price and volume, never P&L.  So the
         $30 basket target cannot be tested on this evidence either.
  CANNOT closure REASON -- a flatten fill and a stop fill look identical.

So this is not a replacement for the XLSX forensics; it is the orthogonal
instrument that catches configuration and environment drift, which is exactly
the class the XLSX is blind to.

DEDUPLICATION MATTERS.  The same account is observed by several terminals at
once, so the same deal id appears in several files.  Keyed on
(account, deal_id) -- raw line counts overstate volume by ~2x and must not be
quoted.
"""
from __future__ import annotations

import glob
import os
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

LOGDIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "artifacts", "live", "terminal-logs")

TARGET = "901018"
REPLICA = "111387094"
FRESH = "111638511"
FOCUS = (TARGET, REPLICA, FRESH)

# 'ACC': deal #ID side VOL SYMBOL at PRICE done (based on order #OID)
DEAL_RE = re.compile(
    r"^'(?P<acc>\d+)': deal #(?P<did>\d+) (?P<side>buy|sell) "
    r"(?P<vol>[\d.]+) (?P<sym>\S+) at (?P<price>[\d.]+) done"
    r"(?: \(based on order #(?P<oid>\d+)\))?"
)
DAY_RE = re.compile(r"(\d{8})\.log$")


class Deal:
    __slots__ = ("acc", "did", "side", "vol", "sym", "price", "oid", "t")

    def __init__(self, acc, did, side, vol, sym, price, oid, t):
        self.acc, self.did, self.side = acc, did, side
        self.vol, self.sym, self.price = vol, sym, price
        self.oid, self.t = oid, t

    def __repr__(self):
        return f"<{self.acc} {self.t} {self.side} {self.vol} @ {self.price}>"


def load() -> dict[str, list[Deal]]:
    """Parse every archived log; dedupe on (account, deal_id)."""
    seen: dict[tuple[str, str], Deal] = {}
    for path in sorted(glob.glob(os.path.join(LOGDIR, "*.log"))):
        m = DAY_RE.search(os.path.basename(path))
        if not m:
            continue
        day = m.group(1)
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                f = line.rstrip("\n").split("\t")
                if len(f) < 5:
                    continue
                d = DEAL_RE.match(f[4])
                if not d:
                    continue
                key = (d.group("acc"), d.group("did"))
                if key in seen:
                    continue
                try:
                    t = datetime.strptime(day + " " + f[2].split(".")[0],
                                          "%Y%m%d %H:%M:%S")
                    t = t.replace(microsecond=int(
                        (f[2].split(".") + ["0"])[1].ljust(3, "0")[:3]) * 1000)
                except ValueError:
                    continue
                seen[key] = Deal(d.group("acc"), d.group("did"), d.group("side"),
                                 float(d.group("vol")), d.group("sym"),
                                 float(d.group("price")), d.group("oid") or "", t)
    out: dict[str, list[Deal]] = defaultdict(list)
    for d in seen.values():
        out[d.acc].append(d)
    for v in out.values():
        v.sort(key=lambda d: (d.t, d.did))
    return out


def rule(title: str) -> None:
    print()
    print("=" * 100)
    print(title)
    print("=" * 100)


def pct(a: int, b: int) -> str:
    return f"{100.0 * a / b:5.1f}%" if b else "    --"


# --------------------------------------------------------------------- panel 1
def panel_inventory(streams) -> None:
    rule("1. WHAT THE LIVE EVIDENCE ACTUALLY CONTAINS")
    print(f"  {'account':>12} {'deals':>7} {'days':>5} {'symbols':>22} "
          f"{'first':>17} {'last':>17}")
    for acc in FOCUS:
        ds = streams.get(acc, [])
        if not ds:
            print(f"  {acc:>12}       0 -- absent")
            continue
        days = sorted({d.t.date() for d in ds})
        syms = Counter(d.sym for d in ds)
        st = ",".join(f"{k}" for k, _ in syms.most_common(2))
        print(f"  {acc:>12} {len(ds):>7} {len(days):>5} {st:>22} "
              f"{str(ds[0].t)[:16]:>17} {str(ds[-1].t)[:16]:>17}")
    print()
    print("  Deduped on (account, deal_id): the same account is watched by")
    print("  several terminals at once, so raw grep counts double-count.")


# --------------------------------------------------------------------- panel 2
def panel_volume(streams) -> None:
    rule("2. VOLUME LADDER -- the most directly comparable invariant")
    print("  A deployment ladder is a design decision baked into the preset.  If the")
    print("  replica's ladder differs from the Target's, every downstream quantity")
    print("  (gross exposure, $/point, the $30 target's reachability) differs too.")
    print()
    for acc in FOCUS:
        ds = streams.get(acc, [])
        if not ds:
            continue
        c = Counter(d.vol for d in ds)
        tot = sum(c.values())
        tag = {TARGET: "TARGET ", REPLICA: "replica", FRESH: "fresh  "}[acc]
        print(f"  {tag} {acc}   n={tot}")
        for v, n in sorted(c.items()):
            bar = "#" * max(1, round(40.0 * n / tot))
            print(f"      {v:>6.2f} lots : {n:>5}  {pct(n, tot)}  {bar}")
        gross = sum(d.vol for d in ds)
        print(f"      distinct={sorted(c)}  total traded volume={gross:.2f} lots")
        print()


# --------------------------------------------------------------------- panel 3
def panel_lattice(streams) -> None:
    rule("3. PRICE LATTICE STEP -- 1.55 on screen vs ~1.36 in the XLSX forensics")
    print("  The straddle deploys pendings on a fixed lattice.  Adjacent fills on the")
    print("  SAME side, inside one deployment, are one step apart.  Measure it: per")
    print("  account/day/side, sort fill prices, take successive differences, and")
    print("  histogram those in a plausible lattice range.")
    print()
    for acc in FOCUS:
        ds = streams.get(acc, [])
        if not ds:
            continue
        gaps: list[float] = []
        for (_day, _side), grp in _group(ds, lambda d: (d.t.date(), d.side)):
            ps = sorted({round(d.price, 2) for d in grp})
            for a, b in zip(ps, ps[1:]):
                g = round(b - a, 2)
                if 0.2 <= g <= 6.0:
                    gaps.append(g)
        if not gaps:
            print(f"  {acc}: no measurable gaps")
            continue
        c = Counter(gaps)
        tag = {TARGET: "TARGET ", REPLICA: "replica", FRESH: "fresh  "}[acc]
        print(f"  {tag} {acc}   n={len(gaps)} adjacent-price gaps")
        for g, n in c.most_common(8):
            bar = "#" * max(1, round(44.0 * n / len(gaps)))
            print(f"      {g:>5.2f} : {n:>5}  {pct(n, len(gaps))}  {bar}")
        print(f"      median={statistics.median(gaps):.2f}  "
              f"mode={c.most_common(1)[0][0]:.2f}")
        print()


# --------------------------------------------------------------------- panel 4
def panel_pacing(streams) -> None:
    rule("4. PACING -- the 20-second family and the 100 ms one-action-per-tick model")
    print("  AGENTS.md records close_interval_seconds=20, rearm_delay_seconds=20 and")
    print("  a 100 ms OnTimer that performs at most ONE action per tick.  Both are")
    print("  visible here: 20 s spacing should appear as a spike near 20.0, and the")
    print("  one-action rule forbids many same-millisecond fills from ONE decision")
    print("  (though a broker CAN fill several resting pendings on one tick, so")
    print("  sub-100 ms clusters are evidence about the BROKER, not the EA).")
    print()
    for acc in FOCUS:
        ds = streams.get(acc, [])
        if len(ds) < 3:
            continue
        tag = {TARGET: "TARGET ", REPLICA: "replica", FRESH: "fresh  "}[acc]
        deltas = []
        for a, b in zip(ds, ds[1:]):
            dt = (b.t - a.t).total_seconds()
            if 0.0 <= dt <= 3600.0:
                deltas.append(dt)
        if not deltas:
            continue
        buckets = [(0.0, 0.001, "same ms"), (0.001, 0.1, "<100ms"),
                   (0.1, 1.0, "0.1-1s"), (1.0, 5.0, "1-5s"),
                   (5.0, 15.0, "5-15s"), (15.0, 25.0, "15-25s <-20s family"),
                   (25.0, 60.0, "25-60s"), (60.0, 3600.0, ">1min")]
        print(f"  {tag} {acc}   n={len(deltas)} inter-deal gaps")
        for lo, hi, name in buckets:
            n = sum(1 for x in deltas if lo <= x < hi)
            bar = "#" * max(0, round(40.0 * n / len(deltas)))
            print(f"      {name:>20} : {n:>5}  {pct(n, len(deltas))}  {bar}")
        near20 = [x for x in deltas if 19.0 <= x <= 21.5]
        if near20:
            print(f"      gaps in [19.0,21.5]: n={len(near20)}  "
                  f"median={statistics.median(near20):.3f}s  "
                  f"min={min(near20):.3f}  max={max(near20):.3f}")
        print()


# --------------------------------------------------------------------- panel 5
def panel_bursts(streams) -> None:
    rule("5. BURST STRUCTURE -- how many legs fill together, and on which side")
    print("  A straddle fills pendings in clusters as price sweeps a lattice.  The")
    print("  cluster SIZE distribution and its side purity are structural signatures")
    print("  that survive without any P&L data.")
    print()
    for acc in FOCUS:
        ds = streams.get(acc, [])
        if len(ds) < 3:
            continue
        tag = {TARGET: "TARGET ", REPLICA: "replica", FRESH: "fresh  "}[acc]
        bursts: list[list[Deal]] = []
        cur = [ds[0]]
        for a, b in zip(ds, ds[1:]):
            if (b.t - a.t).total_seconds() <= 1.0:
                cur.append(b)
            else:
                bursts.append(cur)
                cur = [b]
        bursts.append(cur)
        sizes = Counter(len(b) for b in bursts)
        pure = sum(1 for b in bursts if len({d.side for d in b}) == 1)
        sides = Counter(d.side for d in ds)
        print(f"  {tag} {acc}   {len(bursts)} bursts (<=1s apart)")
        for s, n in sorted(sizes.items())[:8]:
            print(f"      size {s:>2} : {n:>5}  {pct(n, len(bursts))}")
        print(f"      single-side bursts : {pure}/{len(bursts)} "
              f"= {pct(pure, len(bursts))}")
        print(f"      side balance       : buy {sides['buy']}  sell {sides['sell']}"
              f"   (buy share {pct(sides['buy'], len(ds))})")
        print()


def _group(items, keyf):
    g: dict = defaultdict(list)
    for it in items:
        g[keyf(it)].append(it)
    return sorted(g.items(), key=lambda kv: str(kv[0]))


def main() -> None:
    streams = load()
    print(f"parsed {sum(len(v) for v in streams.values())} unique deals "
          f"across {len(streams)} accounts from {LOGDIR}")
    panel_inventory(streams)
    panel_volume(streams)
    panel_lattice(streams)
    panel_pacing(streams)
    panel_bursts(streams)


if __name__ == "__main__":
    main()
