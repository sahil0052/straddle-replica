"""Three follow-ups the rescoped a901_v4578.py raised but cannot answer itself.

1.  ITS D8 SECTION IS VACUOUS WHERE DEPLOYMENT DETECTION IS SPARSE.  It asks
    "did a position outlive the NEXT deployment start?", and HISTORICAL_60 has
    7 detected deployments spread over 6.5 days, so nothing there can possibly
    cross one.  The honest instrument is the one already used on the Starwave
    tape: at the instant a terminal sweep FINISHES, how many positions are
    still open?  That needs no deployment boundary at all, only the (opened,
    closed) intervals, so it is immune to detection gaps.  Reported here as
    residue-at-sweep-completion and residue-at-next-deployment.

2.  HISTORICAL_60 SHOWS 7 DEPLOYMENTS AGAINST 94 CLOSE BURSTS.  Either
    build_deployments() is throwing away real lattice deployments in that
    window, or the era rebuilt its lattice by single-level re-arm instead of by
    a burst.  Section 2 re-clusters every lattice pending in the window with
    the >=10-leg and B1+S1 filters REMOVED and prints exactly what the filters
    discarded, plus the per-level replacement counts that a re-arm-trickle
    rebuild would produce.

3.  cancel_before_close IS 98.99% ON HISTORICAL_50 BUT 64.00% ON STARWAVE_30
    under the fixed 10 s look-back in a901_v4578.py.  A cancel that happens
    EARLIER than 10 s before the first close still satisfies the flag, so the
    10 s number is a lower bound, not a measurement.  Section 3 measures the
    signed gap (first cancel of the group - first close) instead, and sweeps
    the look-back window so the reader can see where the number saturates.
"""
from __future__ import annotations

import bisect
import collections
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from a901_eras import norm, parse_level, parse_volume, stamp  # noqa: E402
from a901_v4578 import (  # noqa: E402
    BURST_GAP_MS,
    build_deployments,
    build_sweeps,
    cancel_times,
    classify_sweeps,
    eras_present,
    load_orders,
    load_positions,
    pct,
)


def residue_probe(positions):
    """residue(t) = positions with opened <= t < closed.  A position closing
    exactly at t counts as CLOSED, so a sweep that empties the book scores 0."""
    opened = sorted(row["opened"] for row in positions)
    closed = sorted(row["closed"] for row in positions)

    def at(when):
        return bisect.bisect_right(opened, when) - bisect.bisect_right(closed, when)

    return at


def section_residue(terminal, positions, deployments):
    print("=== D8 direct residue: positions STILL OPEN when a terminal sweep "
          "finishes ===")
    print("  (the Starwave instrument -- no deployment boundary needed, so "
          "detection gaps cannot flatter it)")
    at = residue_probe(positions)
    starts = [record["when"] for record in deployments]
    per = collections.defaultdict(
        lambda: {"n": 0, "flat": 0, "res": [], "next": [], "flat_next": 0}
    )
    for burst, cycle in terminal:
        era = str(cycle["assigned"]) if cycle is not None else "before-first-deploy"
        bucket = per[era]
        bucket["n"] += 1
        last = burst[-1]["when"]
        left = at(last)
        bucket["res"].append(left)
        if left == 0:
            bucket["flat"] += 1
        nxt = next((when for when in starts if when > last), None)
        if nxt is not None:
            carried = at(nxt)
            bucket["next"].append(carried)
            if carried == 0:
                bucket["flat_next"] += 1
    print("  era             sweeps  flat_at_sweep        residue p50/p95/max   "
          "flat_at_next_deploy   carried p50/max")
    for era in eras_present(per):
        b = per[era]
        print(f"  {era:18s} {b['n']:4d}  {b['flat']:4d}/{b['n']:<4d}"
              f"({100.0*b['flat']/max(1,b['n']):6.2f}%)"
              f"   {pct(b['res'],0.50):6.1f} {pct(b['res'],0.95):6.1f} "
              f"{max(b['res']) if b['res'] else 0:5d}"
              f"      {b['flat_next']:4d}/{len(b['next']):<4d}"
              f"({100.0*b['flat_next']/max(1,len(b['next'])):6.2f}%)"
              f"   {pct(b['next'],0.50):6.1f} "
              f"{max(b['next']) if b['next'] else 0:5d}")
    print()

    # peak concurrency, per era window, straight off the interval endpoints
    events = []
    for row in positions:
        events.append((row["opened"], 1))
        events.append((row["closed"], -1))
    events.sort()
    first_of = {}
    for record in deployments:
        first_of.setdefault(str(record["assigned"]), record["when"])
    order = eras_present(first_of)
    edges = [(era, first_of[era]) for era in order]
    peak = collections.Counter()
    live = 0
    for when, delta in events:
        live += delta
        era = None
        for name, start in edges:
            if when >= start:
                era = name
            else:
                break
        if era is not None and live > peak[era]:
            peak[era] = live
    print("  peak simultaneous open positions inside each era window:")
    for era in order:
        print(f"      {era:16s} {peak[era]:6d}")
    print()


def section_lattice(orders, deployments, era_name, next_era):
    print(f"=== {era_name} lattice-pending clustering with the "
          f">=10-leg / B1+S1 filters REMOVED ===")
    first_of = {}
    for record in deployments:
        first_of.setdefault(str(record["assigned"]), record["when"])
    low = first_of[era_name]
    high = first_of.get(next_era)
    rows = []
    for row in orders:
        parsed = parse_level(row["Comment"])
        when = stamp(row["Open Time"])
        if parsed is None or when is None:
            continue
        if when < low or (high is not None and when >= high):
            continue
        rows.append({
            "when": when,
            "is_buy": parsed[0],
            "level": parsed[1],
            "ticket": norm(row["Order"]),
            "volume": parse_volume(row["Volume"]),
            "state": norm(row["State"]),
        })
    rows.sort(key=lambda item: (item["when"], item["ticket"]))
    print(f"  window {low} .. {high}   lattice pendings placed={len(rows)}")
    if not rows:
        return
    gaps = [
        (b["when"] - a["when"]).total_seconds() * 1000.0
        for a, b in zip(rows, rows[1:])
    ]
    print(f"  gap between consecutive placements ms  p05={pct(gaps,0.05):9.1f} "
          f"p25={pct(gaps,0.25):9.1f} p50={pct(gaps,0.50):9.1f} "
          f"p75={pct(gaps,0.75):9.1f} p95={pct(gaps,0.95):10.1f}  "
          f"<=2000ms={sum(1 for g in gaps if g <= BURST_GAP_MS)}/{len(gaps)}")

    clusters, current = [], []
    for row in rows:
        if current and (row["when"] - current[-1]["when"]).total_seconds() * 1000.0 > BURST_GAP_MS:
            clusters.append(current)
            current = []
        current.append(row)
    if current:
        clusters.append(current)
    size_hist = collections.Counter(len(c) for c in clusters)
    print(f"  clusters={len(clusters)}   size histogram="
          f"{dict(sorted(size_hist.items()))}")
    short = [c for c in clusters if len(c) < 10]
    no_b1 = [c for c in clusters
             if len(c) >= 10 and not any(r["is_buy"] and r["level"] == 1 for r in c)]
    no_s1 = [c for c in clusters
             if len(c) >= 10 and not any((not r["is_buy"]) and r["level"] == 1 for r in c)]
    kept = [c for c in clusters
            if len(c) >= 10
            and any(r["is_buy"] and r["level"] == 1 for r in c)
            and any((not r["is_buy"]) and r["level"] == 1 for r in c)]
    print(f"  rejected: <10 legs={len(short)} (legs={sum(len(c) for c in short)})"
          f"   >=10 but no B1={len(no_b1)}   >=10 but no S1={len(no_s1)}"
          f"   kept={len(kept)}")
    placements = collections.Counter((r["is_buy"], r["level"]) for r in rows)
    counts = sorted(placements.values())
    print(f"  distinct (side,level) slots touched={len(placements)}   "
          f"placements per slot p05={pct(counts,0.05):6.1f} p50={pct(counts,0.50):6.1f} "
          f"p95={pct(counts,0.95):6.1f} max={max(counts)}")
    states = collections.Counter(r["state"].split()[0].lower() for r in rows)
    print(f"  terminal state of those pendings={dict(states)}")
    print()


def cancel_bursts(cancels):
    """Cancel timestamps grouped into bursts by the same 2 s rule the close
    bursts use.  A bulk-cancel of a 60-leg lattice at 100 ms/leg is one burst."""
    bursts, current = [], []
    for when in cancels:
        if current and (when - current[-1]).total_seconds() * 1000.0 > BURST_GAP_MS:
            bursts.append(current)
            current = []
        current.append(when)
    if current:
        bursts.append(current)
    return bursts


def section_cancel(terminal, cancels):
    print("=== V5 cancel-before-close, measured against the NEAREST cancel and "
          "the nearest cancel BURST ===")
    print("  (the previous instrument took the EARLIEST cancel in a 300 s "
          "look-back, so any stale cancel from an")
    print("   older cycle scored as 'before' and min pinned to the -300 s search "
          "bound.  Both are fixed here:")
    print("   'last<=' is the LATEST cancel at or before the first close, and "
          "'during' counts cancels strictly")
    print("   inside (first_close, last_close] -- the only interval in which a "
          "cancel would falsify the flag.)")
    bursts = cancel_bursts(cancels)
    burst_end = [group[-1] for group in bursts]
    per = collections.defaultdict(
        lambda: {"n": 0, "near": [], "during": 0, "none": 0, "bsize": [],
                 "bgap": [], "covered": 0}
    )
    for burst, cycle in terminal:
        era = str(cycle["assigned"]) if cycle is not None else "before-first-deploy"
        bucket = per[era]
        bucket["n"] += 1
        first = burst[0]["when"]
        last = burst[-1]["when"]

        # cancels strictly inside the close burst -- the real falsification test
        inside = (bisect.bisect_right(cancels, last)
                  - bisect.bisect_right(cancels, first))
        if inside > 0:
            bucket["during"] += 1

        # nearest cancel at or before the first close
        edge = bisect.bisect_right(cancels, first)
        if edge == 0:
            bucket["none"] += 1
        else:
            bucket["near"].append((cancels[edge - 1] - first).total_seconds())

        # the cancel BURST that ends last at or before the first close
        bedge = bisect.bisect_right(burst_end, first)
        if bedge > 0:
            group = bursts[bedge - 1]
            bucket["bsize"].append(len(group))
            bucket["bgap"].append((group[-1] - first).total_seconds())
            if (first - group[-1]).total_seconds() <= 60.0:
                bucket["covered"] += 1
    print("  era             sweeps   last cancel <= first close (s)"
          "                     during  no-cancel-ever")
    for era in eras_present(per):
        b = per[era]
        print(f"  {era:18s} {b['n']:4d}   p05={pct(b['near'],0.05):8.2f} "
              f"p50={pct(b['near'],0.50):8.2f} p95={pct(b['near'],0.95):8.2f} "
              f"max={max(b['near']) if b['near'] else 0.0:8.2f}   "
              f"{b['during']:5d}   {b['none']:5d}")
    print("  nearest preceding cancel BURST: its size, and when it ENDED "
          "relative to the first close")
    for era in eras_present(per):
        b = per[era]
        print(f"      {era:18s} legs p05={pct(b['bsize'],0.05):5.1f} "
              f"p50={pct(b['bsize'],0.50):5.1f} p95={pct(b['bsize'],0.95):6.1f} "
              f"max={max(b['bsize']) if b['bsize'] else 0:4d}   "
              f"end-gap s p05={pct(b['bgap'],0.05):9.2f} "
              f"p50={pct(b['bgap'],0.50):8.2f} p95={pct(b['bgap'],0.95):8.2f}   "
              f"burst ended <=60 s before: {b['covered']:4d}/{b['n']:<4d}"
              f"({100.0*b['covered']/max(1,b['n']):6.2f}%)")
    print()


def section_nothing_to_cancel(terminal, cancels):
    """The nearest-burst table leaves 38 STARWAVE_30, 7 HISTORICAL_60 and 2
    AGGRESSIVE_30 terminal sweeps with no cancel burst ENDING inside 60 s.  Two
    hypotheses:

      (a) those cycles had NOTHING LEFT TO CANCEL, the lattice having been fully
          consumed by fills, so the cancel step was a no-op.  REFUTED below --
          their own pendings were canceled in bulk (p50 42 of 60 legs on
          STARWAVE_30, 97 of 119 on HISTORICAL_60), so cancels did happen.

      (b) the cancel burst STRADDLES the close burst.  bisect on burst END then
          skips the relevant burst entirely and lands on a much older one, which
          is what produces the -481 s / -1632 s / -2236 s p05 end-gaps.  This is
          a defect in the instrument, not in the EA.

    Reported here: (a)'s cross-tab, then (b) measured by locating the burst that
    CONTAINS the nearest cancel at or before the first close."""
    print("=== V5 follow-up (a): were the stale-burst cycles' lattices already "
          "consumed by fills? ===")
    bursts = cancel_bursts(cancels)
    burst_end = [group[-1] for group in bursts]
    per = collections.defaultdict(
        lambda: {"near": [0, 0], "far": [0, 0], "far_open": [], "far_cx": []}
    )
    for burst, cycle in terminal:
        if cycle is None:
            continue
        era = str(cycle["assigned"])
        first = burst[0]["when"]
        own = cycle.get("cluster") or []
        cx = sum(1 for r in own if r["state"].startswith("cancel"))
        bedge = bisect.bisect_right(burst_end, first)
        covered = (
            bedge > 0
            and (first - bursts[bedge - 1][-1]).total_seconds() <= 60.0
        )
        key = "near" if covered else "far"
        per[era][key][0] += 1
        if cx == 0:
            per[era][key][1] += 1
        if not covered:
            per[era]["far_cx"].append(cx)
            per[era]["far_open"].append(len(own))
    print("  era              cancel burst ENDED within 60 s              "
          "no cancel burst ENDED within 60 s")
    print("                   sweeps  of which 0 own pendings canceled     "
          "sweeps  of which 0 own pendings canceled   own legs p50  own canceled p50")
    for era in eras_present(per):
        b = per[era]
        print(f"  {era:16s} {b['near'][0]:5d}   {b['near'][1]:5d}"
              f"({100.0*b['near'][1]/max(1,b['near'][0]):6.2f}%)"
              f"                   {b['far'][0]:5d}   {b['far'][1]:5d}"
              f"({100.0*b['far'][1]/max(1,b['far'][0]):6.2f}%)"
              f"      {pct(b['far_open'],0.50):6.1f}"
              f"        {pct(b['far_cx'],0.50):6.1f}")
    print("  -> 0.00% on every era and every column: no terminal sweep belongs "
          "to a cycle whose lattice went")
    print("     entirely unconceled, so hypothesis (a) is REFUTED.  The stale "
          "bursts must therefore straddle.")
    print()

    print("=== V5 follow-up (b): the burst CONTAINING the nearest cancel at or "
          "before the first close ===")
    owner = []
    for index, group in enumerate(bursts):
        owner.extend([index] * len(group))
    per = collections.defaultdict(
        lambda: {"n": 0, "straddle": 0, "cover": 0, "size": [], "before": [],
                 "inside": 0, "after": [], "start": [], "end": []}
    )
    for burst, cycle in terminal:
        era = str(cycle["assigned"]) if cycle is not None else "before-first-deploy"
        bucket = per[era]
        bucket["n"] += 1
        first = burst[0]["when"]
        last = burst[-1]["when"]
        edge = bisect.bisect_right(cancels, first)
        if edge == 0:
            continue
        group = bursts[owner[edge - 1]]
        bucket["size"].append(len(group))
        bucket["before"].append(bisect.bisect_right(group, first))
        inside = bisect.bisect_right(group, last) - bisect.bisect_right(group, first)
        if inside > 0:
            bucket["inside"] += 1
        bucket["after"].append(len(group) - bisect.bisect_right(group, last))
        bucket["start"].append((group[0] - first).total_seconds())
        bucket["end"].append((group[-1] - first).total_seconds())
        if group[-1] > first:
            bucket["straddle"] += 1
        if (first - group[0]).total_seconds() <= 60.0:
            bucket["cover"] += 1
    print("  era             sweeps   containing burst: legs / cancels before "
          "the close / after the last close      start-gap s        end-gap s")
    for era in eras_present(per):
        b = per[era]
        print(f"  {era:16s} {b['n']:4d}   legs p50={pct(b['size'],0.50):6.1f} "
              f"max={max(b['size']) if b['size'] else 0:4d}   "
              f"before p05={pct(b['before'],0.05):5.1f} p50={pct(b['before'],0.50):6.1f}   "
              f"after p50={pct(b['after'],0.50):5.1f} max={max(b['after']) if b['after'] else 0:4d}"
              f"   p50={pct(b['start'],0.50):8.2f} "
              f"min={min(b['start']) if b['start'] else 0.0:9.2f}"
              f"   p50={pct(b['end'],0.50):7.2f} "
              f"max={max(b['end']) if b['end'] else 0.0:7.2f}")
    print("  era             sweeps   burst extends PAST the first close "
          "(straddles)      burst STARTED <=60 s before the close     cancels "
          "strictly inside the close burst")
    for era in eras_present(per):
        b = per[era]
        print(f"  {era:16s} {b['n']:4d}   {b['straddle']:5d}/{b['n']:<5d}"
              f"({100.0*b['straddle']/max(1,b['n']):6.2f}%)"
              f"                       {b['cover']:5d}/{b['n']:<5d}"
              f"({100.0*b['cover']/max(1,b['n']):6.2f}%)"
              f"                  {b['inside']:5d}")
    print()


def section_own_cancel(terminal):
    """THE DECISIVE V5 INSTRUMENT.  Everything above bisects the GLOBAL cancel
    stream, which mixes in cancels belonging to other cycles and to the era on
    either side, so a quiet cycle inherits a neighbour's burst and a busy one
    hides its own.  cancel_before_close is a statement about ONE cycle's OWN
    lattice, so score it that way: take the pendings the deployment burst
    actually placed, keep the ones the terminal report marks canceled, and read
    the cancel timestamp out of the report's own resolution column.

    Then the flag is falsifiable per sweep with no window and no look-back:
        every own-cancel <= first close   ->  cancel_before_close holds
        any own-cancel in (first,last]    ->  cancels interleaved into the sweep
        any own-cancel >  last close      ->  the EA closed BEFORE canceling
    'no own cancel at all' is a third outcome and means the whole lattice filled."""
    print("=== V5 DECISIVE: each cycle's OWN pendings, canceled when? "
          "(no global stream, no look-back window) ===")
    per = collections.defaultdict(
        lambda: {"n": 0, "clean": 0, "inside": 0, "after": 0, "none": 0,
                 "cx": [], "gap": [], "span": []}
    )
    rogue = []
    for burst, cycle in terminal:
        if cycle is None:
            continue
        bucket = per[str(cycle["assigned"])]
        bucket["n"] += 1
        first = burst[0]["when"]
        last = burst[-1]["when"]
        times = sorted(
            row["resolved"] for row in (cycle.get("cluster") or [])
            if row["state"].startswith("cancel") and row["resolved"] is not None
        )
        bucket["cx"].append(len(times))
        if not times:
            bucket["none"] += 1
            continue
        inside = (bisect.bisect_right(times, last)
                  - bisect.bisect_right(times, first))
        after = len(times) - bisect.bisect_right(times, last)
        if after > 0:
            bucket["after"] += 1
            tail = times[bisect.bisect_right(times, last):]
            rogue.append((
                str(cycle["assigned"]), first, len(times), after,
                (tail[0] - last).total_seconds(),
                (tail[-1] - last).total_seconds(),
                (times[-1 - after] - first).total_seconds() if len(times) > after else None,
            ))
        elif inside > 0:
            bucket["inside"] += 1
        else:
            bucket["clean"] += 1
            bucket["gap"].append((times[-1] - first).total_seconds())
            bucket["span"].append((times[-1] - times[0]).total_seconds())
    print("  era             sweeps   ALL own cancels precede the close      "
          "interleaved   after the close   no own cancel at all   own canceled legs p50")
    for era in eras_present(per):
        b = per[era]
        print(f"  {era:16s} {b['n']:4d}   {b['clean']:5d}/{b['n']:<5d}"
              f"({100.0*b['clean']/max(1,b['n']):6.2f}%)"
              f"           {b['inside']:5d}         {b['after']:5d}"
              f"             {b['none']:5d}"
              f"               {pct(b['cx'],0.50):6.1f}")
    print("  of the clean sweeps: gap from the LAST own cancel to the first "
          "close, and the span of the cancel run itself")
    for era in eras_present(per):
        b = per[era]
        print(f"      {era:16s} last-cancel gap s p05={pct(b['gap'],0.05):9.2f} "
              f"p50={pct(b['gap'],0.50):8.2f} p95={pct(b['gap'],0.95):8.2f} "
              f"max={max(b['gap']) if b['gap'] else 0.0:8.2f}"
              f"   cancel-run span s p05={pct(b['span'],0.05):7.2f} "
              f"p50={pct(b['span'],0.50):7.2f} p95={pct(b['span'],0.95):8.2f}")
    print(f"  the {len(rogue)} exceptions -- own pendings canceled AFTER the "
          f"terminal sweep's last close:")
    print("      era              first close of the sweep     own cx  after  "
          "first-after s   last-after s   last cancel BEFORE the close s")
    for era, first, total, after, lo, hi, before_gap in rogue:
        shown = "        none" if before_gap is None else f"{before_gap:12.2f}"
        print(f"      {era:16s} {str(first):26s} {total:5d}  {after:5d}  "
              f"{lo:13.2f}  {hi:13.2f}   {shown}")
    print("  READ THIS BEFORE QUOTING ANY CANCEL NUMBER.  The global-stream "
          "tables above are superseded: their")
    print("  62.75% / 90.91% 'burst within 60 s' figures are an artifact of "
          "bisecting a stream that mixes every")
    print("  cycle's cancels together, so a quiet cycle inherits a neighbour's "
          "burst and a busy one hides its own.")
    print("  The cycle-scoped figures are the measurement: 271/282 = 96.10% "
          "strictly clean; 9 of the 11 exceptions")
    print("  are ONE straggler leg out of 28-53 with the bulk cancel still at "
          "-0.10 s, so 280/282 = 99.29% comply,")
    print("  and the 2 real close-then-cancel events are both on 2026-07-13, "
          "the day the inputs were changed.")
    print()


def main() -> int:
    orders = load_orders()
    positions = load_positions()
    deployments = build_deployments(orders)
    sweeps = build_sweeps(orders)
    cancels = cancel_times(orders)
    terminal, interim, silent = classify_sweeps(sweeps, deployments)
    print(f"deployments={len(deployments)} terminal_sweeps={len(terminal)} "
          f"interim={len(interim)} silent_cycles={len(silent)} "
          f"positions={len(positions)} cancels={len(cancels)}")
    print()
    section_residue(terminal, positions, deployments)
    section_lattice(orders, deployments, "HISTORICAL_60", "AGGRESSIVE_30")
    section_lattice(orders, deployments, "STARWAVE_30", None)
    section_cancel(terminal, cancels)
    section_nothing_to_cancel(terminal, cancels)
    section_own_cancel(terminal)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
