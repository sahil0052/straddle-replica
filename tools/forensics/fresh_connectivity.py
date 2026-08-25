"""Correct the 111638511-vs-Target comparison for OBSERVER BLACKOUTS.

WHY THIS SCRIPT HAD TO BE WRITTEN.  fresh_vs_target.py measured 155 fills on
111638511 and reported gap statistics over them.  Those statistics are wrong,
and the Network-category log lines say exactly why:

    18:17:14.793  '111638511': connection to MetaQuotes-Demo lost
    19:50:21.163  '111638511': authorized on MetaQuotes-Demo through Access Point EU 0
    19:50:22.209  '111638511': terminal synchronized ...: 8 positions, 49 orders

The terminal was DISCONNECTED for 93.1 minutes.  Immediately before the drop it
had synchronized to 5 positions / 52 orders; immediately after, 8 positions / 49
orders.  The basket grew by three positions while nobody was watching, so the EA
kept trading throughout -- the log simply did not receive the fills.

That has three consequences, all of which invalidate a previous number:

  1. The 97.3-minute "silence" in the fill stream is an OBSERVER outage, not the
     EA going quiet.  It must not be read as EA behaviour.
  2. Every gap that spans a blackout is fabricated by the outage and must be
     excised before any pacing histogram is computed.
  3. 155 fills is an UNDERCOUNT of unknown size, so no per-day total on this
     account means anything.  Only rates over OBSERVED time are admissible.

WHY THE LOCAL TERMINAL CANNOT BE THE THING TRADING.  From 17:20:04 onward every
authorization for 111638511 carries "trading has been disabled - investor mode".
The account was created at 17:14:52 ("new demo account '111638511' opened"), was
briefly logged in with the master password at 17:16:13 ("trading has been
enabled, demo account - hedging mode"), and has been investor-only since.  Orders
kept appearing anyway.  So the EA is executing off-box -- MQL5 VPS -- exactly as
the empty MQL5\\Logs and MQL5\\Files directories implied.  This is the proof, not
an inference.

THE INSTRUMENT NOBODY HAD USED YET.  Every reconnect logs

    'ACC': terminal synchronized with ...: P positions, Q orders, ...

P + Q is the occupancy of the basket at that instant: how many of the ladder's
levels are live, either as a resting pending or as an open position.  For a
30-level two-sided straddle the ceiling is 60.  This is the ONLY direct readout
of ladder depth available for either account -- the XLSX holds closed deals and
therefore cannot show resting orders at all, and the terminal log's Trades
category holds fills and nothing else.  It is sampled at every reconnect, on both
accounts, across all 13 Target days.  Panel B compares it.

TIME BASE.  All timestamps are the logging PC's local clock.  111638511's log and
the Target's log come from different PCs in the same machine's terminal
directories, but every comparison below is either within one stream or a rate, so
the offset does not enter.  The 2h30m local-vs-server offset established earlier
is re-confirmed here: the account-open line at local 17:14:52 is echoed by
"previous successful authorization performed from 106.219.219.41 on 2026.08.25
14:44:54", which is the same event in server time.
"""
from __future__ import annotations

import glob
import os
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
from tools.forensics.live_stream_parity import load, TARGET, FRESH  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

LOGDIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "artifacts", "live", "terminal-logs")

# Network-category messages that matter.  MT5 wording is stable across builds.
RE_ACC = re.compile(r"^'(?P<acc>\d+)': ")
RE_SYNC = re.compile(r"terminal synchronized with .*?: (?P<pos>\d+) positions,"
                     r" (?P<ord>\d+) orders")
RE_LOST = re.compile(r"connection to \S+ lost|disconnected from \S+")
RE_AUTH = re.compile(r"authorized on \S+")
RE_MODE = re.compile(r"trading has been (?P<mode>enabled|disabled)")

LADDER_LEVELS = 30          # LATEST_30
LADDER_SIDES = 2
LADDER_CEIL = LADDER_LEVELS * LADDER_SIDES


class Ev:
    __slots__ = ("t", "acc", "kind", "pos", "ord", "raw")

    def __init__(self, t, acc, kind, pos=-1, orders=-1, raw=""):
        self.t, self.acc, self.kind = t, acc, kind
        self.pos, self.ord, self.raw = pos, orders, raw


def parse_network() -> dict[str, list[Ev]]:
    """Every Network event, per account, deduplicated and time-ordered.

    The same terminal day can appear in more than one archived file (prod-mt5,
    obs-main, obs-replica all watched overlapping sets of accounts), so identical
    events must be deduped on (account, timestamp, raw text) or a reconnect gets
    counted several times and the blackout arithmetic breaks.
    """
    seen: set[tuple] = set()
    out: dict[str, list[Ev]] = defaultdict(list)
    for path in sorted(glob.glob(os.path.join(LOGDIR, "*.log"))):
        base = os.path.basename(path)
        m = re.search(r"__(\d{8})\.log$", base)
        if not m:
            continue
        day = datetime.strptime(m.group(1), "%Y%m%d").date()
        for line in open(path, encoding="utf-8", errors="replace"):
            f = line.rstrip("\n").split("\t")
            if len(f) < 5 or f[3].strip() != "Network":
                continue
            msg = f[4].strip()
            am = RE_ACC.match(msg)
            if not am:
                continue
            acc = am.group("acc")
            try:
                hh, mm, rest = f[2].strip().split(":")
                ss, ms = rest.split(".")
                t = datetime(day.year, day.month, day.day,
                             int(hh), int(mm), int(ss), int(ms) * 1000)
            except ValueError:
                continue
            key = (acc, t, msg)
            if key in seen:
                continue
            seen.add(key)
            sm = RE_SYNC.search(msg)
            if sm:
                out[acc].append(Ev(t, acc, "sync", int(sm.group("pos")),
                                   int(sm.group("ord")), msg))
            elif RE_LOST.search(msg):
                out[acc].append(Ev(t, acc, "lost", raw=msg))
            elif RE_AUTH.search(msg):
                out[acc].append(Ev(t, acc, "auth", raw=msg))
            else:
                mm2 = RE_MODE.search(msg)
                if mm2:
                    out[acc].append(Ev(t, acc, "mode:" + mm2.group("mode"),
                                       raw=msg))
                else:
                    out[acc].append(Ev(t, acc, "other", raw=msg))
    for acc in out:
        out[acc].sort(key=lambda e: e.t)
    return out


def blackouts(evs: list[Ev], min_seconds: float = 60.0):
    """Intervals during which the terminal was not connected to the account.

    A blackout opens on the first 'lost' and closes on the next 'auth'.  Runs of
    consecutive 'lost' lines (MT5 emits one per failed retry) collapse into one.
    """
    out = []
    open_at = None
    for e in evs:
        if e.kind == "lost" and open_at is None:
            open_at = e.t
        elif e.kind == "auth" and open_at is not None:
            if (e.t - open_at).total_seconds() >= min_seconds:
                out.append((open_at, e.t))
            open_at = None
    return out


def in_any(t, spans) -> bool:
    return any(a <= t <= b for a, b in spans)


def observed_seconds(ds, spans) -> float:
    """Wall-clock seconds of the fill stream's own span, minus blackout time.

    Uses the stream's first and last fill as the bounds because that is the only
    interval in which we can claim the EA was both running and watched.
    """
    if len(ds) < 2:
        return 0.0
    total = 0.0
    for day in sorted({d.t.date() for d in ds}):
        dd = [d for d in ds if d.t.date() == day]
        if len(dd) < 2:
            continue
        lo, hi = dd[0].t, dd[-1].t
        span = (hi - lo).total_seconds()
        for a, b in spans:
            ov = (min(hi, b) - max(lo, a)).total_seconds()
            if ov > 0:
                span -= ov
        total += max(0.0, span)
    return total


def rule(t: str) -> None:
    print()
    print("=" * 100)
    print(t)
    print("=" * 100)


def pc(a, b) -> str:
    return f"{100.0 * a / b:5.1f}%" if b else "    --"


def main() -> None:
    st = load()
    net = parse_network()
    fills = {"TARGET": st.get(TARGET, []), "111638511": st.get(FRESH, [])}
    evs = {"TARGET": net.get(TARGET, []), "111638511": net.get(FRESH, [])}
    bo = {k: blackouts(v) for k, v in evs.items()}

    # ------------------------------------------------------------------ panel A
    rule("A. 111638511 -- WHAT THE TERMINAL COULD ACTUALLY SEE")
    fresh_evs = evs["111638511"]
    print(f"  Network events for 111638511 : {len(fresh_evs)}")
    for e in fresh_evs:
        if e.kind in ("sync", "lost", "auth") or e.kind.startswith("mode"):
            tag = {"sync": "SYNC", "lost": "LOST", "auth": "AUTH",
                   "mode:enabled": "TRADE-ON", "mode:disabled": "TRADE-OFF"}[e.kind]
            extra = (f"  pos={e.pos} ord={e.ord}  occupancy={e.pos + e.ord}"
                     if e.kind == "sync" else "")
            print(f"    {e.t:%Y-%m-%d %H:%M:%S}  {tag:>9}{extra}")
    print()
    print("  BLACKOUTS (>= 60 s with no connection):")
    if not bo["111638511"]:
        print("    none")
    for a, b in bo["111638511"]:
        print(f"    {a:%H:%M:%S} -> {b:%H:%M:%S}   "
              f"{(b - a).total_seconds() / 60.0:7.1f} min  BLIND")
    blind = sum((b - a).total_seconds() for a, b in bo["111638511"])
    print(f"    total blind time : {blind / 60.0:.1f} min")

    print()
    print("  Do the blackouts explain the long fill silences?  Every gap over")
    print("  3 minutes in the fill stream, matched against the blackout list:")
    ds = fills["111638511"]
    for a, b in zip(ds, ds[1:]):
        g = (b.t - a.t).total_seconds()
        if g < 180.0:
            continue
        overlap = 0.0
        for x, y in bo["111638511"]:
            ov = (min(b.t, y) - max(a.t, x)).total_seconds()
            if ov > 0:
                overlap += ov
        verdict = ("EXPLAINED by blackout" if overlap >= 0.5 * g
                   else ("partly blackout" if overlap > 0 else "EA WAS QUIET"))
        print(f"    {a.t:%H:%M:%S} -> {b.t:%H:%M:%S}  {g / 60.0:6.1f} min"
              f"   blackout covers {overlap / 60.0:5.1f} min   {verdict}")

    # ------------------------------------------------------------------ panel B
    rule("B. LADDER OCCUPANCY  (positions + resting orders at every reconnect)")
    print("  This is the only direct readout of ladder depth either account")
    print("  offers.  A 30-level two-sided straddle can occupy at most")
    print(f"  {LADDER_LEVELS} x {LADDER_SIDES} = {LADDER_CEIL} levels.  If the")
    print("  Target's occupancy ceiling differs from ours, the ladder depth")
    print("  itself is a parity gap -- and nothing else in the evidence can see")
    print("  that, because the XLSX has no resting orders in it.")
    print()
    print(f"  {'stream':>10} {'n':>4} {'occ min':>8} {'occ med':>8} {'occ max':>8}"
          f" {'ord max':>8} {'pos max':>8}")
    occs = {}
    for name in ("TARGET", "111638511"):
        sy = [e for e in evs[name] if e.kind == "sync"]
        # A zero/zero sync is the terminal attaching before the account has any
        # state at all (111638511 at 17:16:14, one second after being created).
        # It is not an observation of an idle ladder and would drag the minimum.
        sy = [e for e in sy if e.pos + e.ord > 0]
        if not sy:
            print(f"  {name:>10}  no sync observations")
            continue
        o = [e.pos + e.ord for e in sy]
        occs[name] = o
        print(f"  {name:>10} {len(sy):>4} {min(o):>8} {statistics.median(o):>8.0f}"
              f" {max(o):>8} {max(e.ord for e in sy):>8}"
              f" {max(e.pos for e in sy):>8}")
    print()
    for name, o in occs.items():
        c = Counter(o)
        print(f"  {name} occupancy distribution:")
        for v, k in sorted(c.items()):
            flag = "  <- full ladder" if v == LADDER_CEIL else (
                "  <- OVER CEILING" if v > LADDER_CEIL else "")
            print(f"      {v:>3} : {k:>4}  {pc(k, len(o))}"
                  f"  {'#' * max(1, round(30.0 * k / len(o)))}{flag}")
        print()
    if len(occs) == 2:
        print(f"  Target occupancy ceiling    : {max(occs['TARGET'])}")
        print(f"  111638511 occupancy ceiling : {max(occs['111638511'])}")
        if max(occs["TARGET"]) == max(occs["111638511"]):
            print("  -> SAME ceiling.  Ladder depth is at parity.")
        else:
            print("  -> DIFFERENT ceiling.  Investigate ladder depth.")

    # ------------------------------------------------------------------ panel C
    rule("C. FAIR RATE COMPARISON  (per OBSERVED hour, blackouts removed)")
    print("  An earlier note compared '24 cycle blocks' on 111638511 against the")
    print("  Target's 48/day and called ours less frequent.  That was wrong twice:")
    print("  our stream spans ~5.6 h not 24 h, and 93 min of it was blind.  Rates")
    print("  over observed time are the only comparable form.")
    print()
    print(f"  {'stream':>10} {'fills':>6} {'span h':>7} {'blind h':>8}"
          f" {'obs h':>7} {'fills/h':>8} {'lots/h':>8}")
    for name in ("TARGET", "111638511"):
        d = fills[name]
        if len(d) < 2:
            continue
        raw = 0.0
        for day in sorted({x.t.date() for x in d}):
            dd = [x for x in d if x.t.date() == day]
            if len(dd) > 1:
                raw += (dd[-1].t - dd[0].t).total_seconds()
        obs = observed_seconds(d, bo[name])
        blind_h = (raw - obs) / 3600.0
        print(f"  {name:>10} {len(d):>6} {raw / 3600.0:>7.2f} {blind_h:>8.2f}"
              f" {obs / 3600.0:>7.2f} {len(d) / max(obs / 3600.0, 1e-9):>8.1f}"
              f" {sum(x.vol for x in d) / max(obs / 3600.0, 1e-9):>8.3f}")
    print()
    print("  fills/h is confounded by market volatility and by our blind time")
    print("  hiding fills; lots/h carries the same confound.  Cite the RATIO of")
    print("  the two only as an order of magnitude, never as a parity metric.")

    # ------------------------------------------------------------------ panel D
    rule("D. PACING WITH BLACKOUT-SPANNING GAPS EXCISED")
    print("  Every gap whose interval intersects a blackout is discarded: the")
    print("  terminal cannot know what happened inside it, so the gap is an")
    print("  artifact of the outage and not a cadence the EA produced.")
    print()
    buckets = [(0.0, 0.001, "same ms"), (0.001, 0.1, "<100ms"),
               (0.1, 1.0, "0.1-1s"), (1.0, 5.0, "1-5s"), (5.0, 15.0, "5-15s"),
               (15.0, 25.0, "15-25s <- 20s"), (25.0, 60.0, "25-60s"),
               (60.0, 300.0, "1-5min"), (300.0, 86400.0, ">5min")]
    for name in ("TARGET", "111638511"):
        d = fills[name]
        spans = bo[name]
        keep, drop = [], 0
        for a, b in zip(d, d[1:]):
            g = (b.t - a.t).total_seconds()
            if not (0.0 <= g <= 86400.0):
                continue
            hit = any((min(b.t, y) - max(a.t, x)).total_seconds() > 0
                      for x, y in spans)
            if hit:
                drop += 1
            else:
                keep.append(g)
        if len(keep) < 10:
            continue
        print(f"  {name}  n={len(keep)} gaps kept, {drop} discarded as blackout-spanning")
        for lo, hi, nm in buckets:
            k = sum(1 for x in keep if lo <= x < hi)
            print(f"      {nm:>16} : {k:>5}  {pc(k, len(keep))}"
                  f"  {'#' * round(40.0 * k / len(keep))}")
        band = [x for x in keep if 19.0 <= x <= 21.5]
        if band:
            print(f"      [19.0,21.5] n={len(band)} ({pc(len(band), len(keep))})"
                  f"  median={statistics.median(band):.3f}s")
        fast = sum(1 for x in keep if x < 15.0)
        print(f"      under 15 s  : {fast}  {pc(fast, len(keep))}"
              f"   <- the residual pacing gap")
        print()


if __name__ == "__main__":
    main()
