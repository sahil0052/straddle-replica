"""V6 -- re-arm semantics and per-level memory, measured on ReportHistory-901018.

The directive's question is narrow and falsifiable: do re-arms return to the
EXACT `level.target_price` established by the cycle's deployment burst, or does
the Target re-anchor a missing level to the prevailing market?

`RearmOneMissingLevel()` (StraddleEngine.mqh:2278-2364) re-places
`m_buy_levels[index].target_price` -- the burst price, never recomputed -- and
`PendingPriceIsValid()` (1529-1540) is a pure side/stops-distance guard that can
only DEFER a re-arm (`continue`), never move it.  So the replica's prediction is
delta == 0.00 against the cycle's own lattice, for every re-arm, forever, with a
DEFERRAL tail rather than a relocation tail.

Two instruments are used, because "delta == 0" alone can be satisfied trivially
if the lattice is re-fitted from the re-arms themselves:

  * the lattice is taken from `Cycle.lattice`, which `_fit_lattice()` builds from
    the deployment SWEEP ONLY (dataset.py:284-292 trims at the first repeat of a
    (side, level) key), so re-arms cannot contaminate their own reference; and
  * part 4 runs the re-anchoring hypothesis forward.  If a missing level were
    re-armed at `market +/- level*step`, then (price - market)/step would equal
    the level index for EVERY re-arm.  That is a hard, sign-carrying prediction
    on a quantity the lattice test never looks at.

Part 5 compares each re-arm's volume against the same (side, level) slot's BURST
volume rather than against a hard-coded ladder -- a ladder comparison is what
produced the retracted "40 volume mismatches" artifact.
"""
from __future__ import annotations

import collections
import statistics
import sys
from bisect import bisect_left, bisect_right
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.forensics.dataset import load_all  # noqa: E402
from tools.forensics.linkage import CLOSE_BY_RE, SL_RE, TP_RE, link_exits  # noqa: E402

ERAS = [
    ("HISTORICAL_50", datetime(2026, 6, 23, 16, 17, 27), datetime(2026, 7, 2, 15, 24, 57)),
    ("HISTORICAL_60", datetime(2026, 7, 2, 15, 24, 57), datetime(2026, 7, 13, 11, 2, 45)),
    ("AGGRESSIVE_30", datetime(2026, 7, 13, 11, 2, 45), datetime(2026, 7, 13, 12, 32, 29)),
    ("LOW_RISK_30", datetime(2026, 7, 13, 12, 32, 29), datetime(2026, 7, 13, 15, 59, 39)),
    ("STARWAVE_30", datetime(2026, 7, 13, 15, 59, 39), datetime(2027, 1, 1)),
]
ORDER = [name for name, _s, _e in ERAS]


def era_of(when):
    for name, start, end in ERAS:
        if start <= when < end:
            return name
    return "?"


def pct(num, den):
    return 0.0 if den <= 0 else 100.0 * num / den


def q(values, p):
    if not values:
        return float("nan")
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round(p * (len(ordered) - 1)))))
    return ordered[index]


def main() -> int:
    orders, positions, deals, cycles = load_all()
    exit_order, _exit_deal, _entry_deal, _stats = link_exits(orders, positions, deals)

    def exit_kind_of(position_id):
        """Classify an exit by the ORDER that produced it (linkage.py:31-32)."""
        order = exit_order.get(position_id)
        if order is None:
            return "unlinked"
        comment = (order.comment or "").strip()
        if SL_RE.fullmatch(comment):
            return "stop"
        if TP_RE.fullmatch(comment):
            return "tp"
        if CLOSE_BY_RE.fullmatch(comment):
            return "closeby"
        if order.order_type in ("buy", "sell"):
            return "basket"
        return "other"

    era_by_cycle = {c.index: era_of(c.start) for c in cycles}
    by_index = {c.index: c for c in cycles}

    # ---------------------------------------------------------------- part 1
    # A re-arm is a grid pending in cycle i whose (side, level) already appeared
    # in cycle i's deployment sweep, placed after the sweep ended.
    rearms = []
    burst_ids = set()
    burst_price = {}
    burst_volume = {}
    for cycle in cycles:
        for order in cycle.burst_orders:
            burst_ids.add(order.order_id)
            burst_price[(cycle.index, order.side, order.level)] = order.price
            burst_volume[(cycle.index, order.side, order.level)] = order.volume

    for order in orders:
        if not order.is_grid or order.price is None or order.cycle < 0:
            continue
        if order.order_id in burst_ids:
            continue
        rearms.append(order)

    print("=" * 78)
    print("PART 1 -- re-arm census (grid pendings that are not deployment-burst orders)")
    print("=" * 78)
    grid_total = sum(1 for o in orders if o.is_grid and o.price is not None)
    print(f"    grid pendings {grid_total}   burst {len(burst_ids)}   re-arms {len(rearms)}")
    per_era = collections.Counter(era_by_cycle.get(o.cycle, "?") for o in rearms)
    cyc_era = collections.Counter(era_by_cycle.values())
    print(f"    {'era':<14} {'cycles':>7} {'re-arms':>9} {'per cycle':>10}")
    for name in ORDER:
        n = per_era.get(name, 0)
        print(f"    {name:<14} {cyc_era.get(name, 0):>7} {n:>9} {n / max(1, cyc_era.get(name, 0)):>10.2f}")

    # ---------------------------------------------------------------- part 2
    print()
    print("=" * 78)
    print("PART 2 -- does every re-arm return to the burst lattice price?")
    print("=" * 78)
    stats = collections.defaultdict(lambda: collections.Counter())
    deltas_all = []
    offenders = []
    for order in rearms:
        key = (order.cycle, order.side, order.level)
        reference = burst_price.get(key)
        era = era_by_cycle.get(order.cycle, "?")
        bucket = stats[era]
        bucket["n"] += 1
        if reference is None:
            bucket["no_reference"] += 1
            continue
        delta = order.price - reference
        deltas_all.append(delta)
        bucket["scored"] += 1
        if delta == 0.0:
            bucket["exact"] += 1
        elif abs(delta) <= 0.005:
            bucket["half_tick"] += 1
        else:
            bucket["moved"] += 1
            offenders.append((order, reference, delta))
    print(f"    {'era':<14} {'scored':>7} {'exact':>7} {'exact%':>8} {'<=1/2 tick':>11} {'moved':>7}")
    tot = collections.Counter()
    for name in ORDER:
        b = stats[name]
        tot.update(b)
        print(
            f"    {name:<14} {b['scored']:>7} {b['exact']:>7} {pct(b['exact'], b['scored']):>8.2f}"
            f" {b['half_tick']:>11} {b['moved']:>7}"
        )
    print(
        f"    {'ALL':<14} {tot['scored']:>7} {tot['exact']:>7} {pct(tot['exact'], tot['scored']):>8.2f}"
        f" {tot['half_tick']:>11} {tot['moved']:>7}"
    )
    print(f"    re-arms with no burst slot for their (side,level): {tot['no_reference']}")
    if offenders:
        print("    first 10 moved re-arms:")
        for order, reference, delta in offenders[:10]:
            print(
                f"      cycle {order.cycle:>3} {order.side}{order.level:<3} #{order.order_id}"
                f" price {order.price:>9.2f} lattice {reference:>9.2f} delta {delta:+.2f}"
            )

    # ---------------------------------------------------------------- part 3
    print()
    print("=" * 78)
    print("PART 3 -- per-level memory: repeated re-arms of one slot inside one cycle")
    print("=" * 78)
    groups = collections.defaultdict(list)
    for order in rearms:
        groups[(order.cycle, order.side, order.level)].append(order)
    multi = {k: v for k, v in groups.items() if len(v) >= 2}
    spreads = []
    inconsistent = 0
    for key, group in multi.items():
        prices = [o.price for o in group]
        spread = max(prices) - min(prices)
        spreads.append(spread)
        if spread > 0.005:
            inconsistent += 1
    print(f"    slots re-armed at least twice: {len(multi)}")
    print(f"    total re-arms in those slots : {sum(len(v) for v in multi.values())}")
    print(f"    deepest repeat count         : {max((len(v) for v in multi.values()), default=0)}")
    print(f"    slots whose repeats disagree by more than half a tick: {inconsistent}")
    print(f"    max intra-slot price spread  : {max(spreads, default=0.0):.4f}")

    # ---------------------------------------------------------------- part 4
    print()
    print("=" * 78)
    print("PART 4 -- re-anchoring hypothesis: is a re-arm placed at market +/- level*step?")
    print("=" * 78)
    quotes = sorted((d.time, d.price) for d in deals if d.price)
    qt = [t for t, _p in quotes]
    used = 0
    matches_level = 0
    dist_steps = []
    for order in rearms:
        cycle = by_index.get(order.cycle)
        if cycle is None or cycle.step <= 0:
            continue
        index = bisect_left(qt, order.open_time)
        candidates = []
        if index < len(quotes):
            candidates.append(quotes[index])
        if index > 0:
            candidates.append(quotes[index - 1])
        if not candidates:
            continue
        when, price = min(candidates, key=lambda c: abs((c[0] - order.open_time).total_seconds()))
        if abs((when - order.open_time).total_seconds()) > 120.0:
            continue
        used += 1
        signed = (order.price - price) / cycle.step
        dist_steps.append(signed if order.side == "B" else -signed)
        if abs(abs(signed) - order.level) <= 0.25:
            matches_level += 1
    print(f"    re-arms with a quote proxy within 120 s: {used}")
    print(f"    |price - market|/step == level (+/-0.25): {matches_level} = {pct(matches_level, used):.2f}%")
    if dist_steps:
        print(
            "    signed distance from market in steps:"
            f" min {min(dist_steps):+.2f}  p05 {q(dist_steps, 0.05):+.2f}  p50 {q(dist_steps, 0.50):+.2f}"
            f"  p95 {q(dist_steps, 0.95):+.2f}  max {max(dist_steps):+.2f}"
        )
        beyond = sum(1 for v in dist_steps if v > 5.0)
        print(f"    re-arms sitting MORE than 5 steps away from market: {beyond} = {pct(beyond, used):.2f}%")

    # ---------------------------------------------------------------- part 5
    print()
    print("=" * 78)
    print("PART 5 -- does a re-arm carry the slot's burst volume?")
    print("=" * 78)
    vol_ok = vol_bad = vol_none = 0
    vol_offenders = []
    for order in rearms:
        reference = burst_volume.get((order.cycle, order.side, order.level))
        if reference is None:
            vol_none += 1
            continue
        if abs(order.volume - reference) <= 1e-9:
            vol_ok += 1
        else:
            vol_bad += 1
            vol_offenders.append((order, reference))
    print(f"    matches burst volume {vol_ok} = {pct(vol_ok, vol_ok + vol_bad):.2f}%   differs {vol_bad}   no slot {vol_none}")
    for order, reference in vol_offenders[:8]:
        print(
            f"      cycle {order.cycle:>3} {order.side}{order.level:<3} #{order.order_id}"
            f" vol {order.volume} burst {reference}"
        )

    # ---------------------------------------------------------------- part 6
    print()
    print("=" * 78)
    print("PART 6 -- what state was the slot in when it re-armed?")
    print("=" * 78)
    # positions per (cycle, side, level), ordered by open time
    slot_positions = collections.defaultdict(list)
    for position in positions:
        if position.grid_side is None or position.cycle < 0:
            continue
        slot_positions[(position.cycle, position.grid_side, position.level)].append(position)
    for group in slot_positions.values():
        group.sort(key=lambda p: p.open_time)

    buckets = collections.Counter()
    latency = collections.defaultdict(list)
    for order in rearms:
        key = (order.cycle, order.side, order.level)
        era = era_by_cycle.get(order.cycle, "?")
        prior = [p for p in slot_positions.get(key, []) if p.open_time < order.open_time]
        if not prior:
            buckets[(era, "no_fill_yet")] += 1
            continue
        last = prior[-1]
        if last.is_open or last.close_time is None or last.close_time > order.open_time:
            buckets[(era, "prev_still_open")] += 1
            continue
        kind = exit_kind_of(last.position_id)
        buckets[(era, "after_" + kind)] += 1
        latency[era].append((order.open_time - last.close_time).total_seconds())
    labels = sorted({label for _era, label in buckets})
    print(f"    {'era':<14} " + " ".join(f"{label:>16}" for label in labels))
    for name in ORDER:
        print(f"    {name:<14} " + " ".join(f"{buckets.get((name, label), 0):>16}" for label in labels))
    print()
    print(f"    {'era':<14} {'n':>6} {'p05':>9} {'p50':>9} {'p95':>9}   (seconds from prior exit to re-arm)")
    for name in ORDER:
        values = latency.get(name, [])
        if not values:
            continue
        print(
            f"    {name:<14} {len(values):>6} {q(values, 0.05):>9.1f} {statistics.median(values):>9.1f}"
            f" {q(values, 0.95):>9.1f}"
        )

    # ---------------------------------------------------------------- part 7
    print()
    print("=" * 78)
    print("PART 7 -- does memory ever survive a restart (stale previous-cycle lattice)?")
    print("=" * 78)
    stale = 0
    for order, reference, delta in offenders:
        previous = burst_price.get((order.cycle - 1, order.side, order.level))
        if previous is not None and abs(order.price - previous) <= 0.005:
            stale += 1
    print(f"    moved re-arms that match the PREVIOUS cycle's lattice price: {stale} of {len(offenders)}")

    # ---------------------------------------------------------------- part 8
    # The moved population must be characterised, not just counted.  Two
    # hypotheses are distinguishable: (a) the EA relocates individual levels,
    # which would show up as ISOLATED moves scattered in time, or (b) the burst
    # detector under-segmented and a whole SECOND deployment was attributed to
    # the previous cycle, which would show up as a dense simultaneous cluster
    # that itself fits one (anchor, step) lattice.  `_burst_clusters()` trims a
    # run at the first repeat of a (side, level) key (dataset.py:284-292), so a
    # back-to-back redeploy is exactly the shape that leaks into "re-arms".
    print()
    print("=" * 78)
    print("PART 8 -- are the moved re-arms isolated relocations or whole redeployments?")
    print("=" * 78)
    moved_by_cycle = collections.defaultdict(list)
    for order, _reference, _delta in offenders:
        moved_by_cycle[order.cycle].append(order)
    clusters = []
    for cycle_index, group in moved_by_cycle.items():
        group.sort(key=lambda o: o.open_time)
        run = [group[0]]
        for order in group[1:]:
            if (order.open_time - run[-1].open_time).total_seconds() <= 60.0:
                run.append(order)
            else:
                clusters.append((cycle_index, run))
                run = [order]
        clusters.append((cycle_index, run))

    def fit(run):
        """Median step and anchor of a candidate lattice, sweep-style."""
        prices = {(o.side, o.level): o.price for o in run}
        diffs = []
        for side in ("B", "S"):
            points = sorted((lv, pr) for (sd, lv), pr in prices.items() if sd == side)
            for (l0, p0), (l1, p1) in zip(points, points[1:]):
                if l1 - l0 != 1:
                    continue
                delta = (p1 - p0) if side == "B" else (p0 - p1)
                if delta > 0:
                    diffs.append(delta)
        step = statistics.median(diffs) if diffs else 0.0
        anchors = [
            (pr - lv * step) if sd == "B" else (pr + lv * step)
            for (sd, lv), pr in prices.items()
        ]
        return (statistics.median(anchors) if anchors else 0.0), step

    lattice_like = [(ci, run) for ci, run in clusters if len({(o.side, o.level) for o in run}) >= 8]
    isolated = [(ci, run) for ci, run in clusters if len({(o.side, o.level) for o in run}) < 8]
    print(f"    moved re-arms {len(offenders)} in {len(clusters)} time clusters")
    print(f"      clusters with >=8 distinct (side,level) keys : {len(lattice_like)}"
          f"  covering {sum(len(r) for _c, r in lattice_like)} orders")
    print(f"      clusters with  <8 distinct keys              : {len(isolated)}"
          f"  covering {sum(len(r) for _c, r in isolated)} orders")
    print()
    print(f"    {'cycle':>6} {'keys':>5} {'orders':>7} {'span s':>8} {'own anchor':>11} {'own step':>9}"
          f" {'cycle anchor':>13} {'cycle step':>11}")
    for cycle_index, run in sorted(lattice_like, key=lambda cr: -len(cr[1]))[:14]:
        anchor, step = fit(run)
        cycle = by_index[cycle_index]
        span = (run[-1].open_time - run[0].open_time).total_seconds()
        print(
            f"    {cycle_index:>6} {len({(o.side, o.level) for o in run}):>5} {len(run):>7} {span:>8.1f}"
            f" {anchor:>11.2f} {step:>9.2f} {cycle.anchor:>13.2f} {cycle.step:>11.2f}"
        )
    print()
    print("    isolated moves (a genuine relocation would live here):")
    shown = 0
    for cycle_index, run in isolated:
        for order in run:
            reference = burst_price[(cycle_index, order.side, order.level)]
            print(
                f"      cycle {cycle_index:>3} {order.side}{order.level:<3} #{order.order_id}"
                f" {order.open_time} price {order.price:>9.2f} lattice {reference:>9.2f}"
                f" delta {order.price - reference:+.2f}"
            )
            shown += 1
            if shown >= 20:
                break
        if shown >= 20:
            break

    # re-score part 2 with lattice-like clusters treated as what they are:
    # deployments the segmenter missed, i.e. not re-arms at all.
    redeploy_ids = {o.order_id for _c, run in lattice_like for o in run}
    rescored = sum(1 for o in rearms if o.order_id not in redeploy_ids and (o.cycle, o.side, o.level) in burst_price)
    rescored_exact = 0
    for order in rearms:
        if order.order_id in redeploy_ids:
            continue
        reference = burst_price.get((order.cycle, order.side, order.level))
        if reference is not None and abs(order.price - reference) <= 0.005:
            rescored_exact += 1
    print()
    print(f"    exact-price rate excluding missed redeployments: {rescored_exact}/{rescored}"
          f" = {pct(rescored_exact, rescored):.2f}%")

    # ---------------------------------------------------------------- part 9
    print()
    print("=" * 78)
    print("PART 9 -- re-arms whose (side,level) has no slot in their cycle's burst")
    print("=" * 78)
    no_slot = [
        o for o in rearms
        if (o.cycle, o.side, o.level) not in burst_price
    ]
    beyond = sum(1 for o in no_slot if o.level > by_index[o.cycle].levels_per_side)
    inside = len(no_slot) - beyond
    print(f"    total {len(no_slot)}   level beyond the burst's levels_per_side {beyond}"
          f"   inside the burst range {inside}")
    per_cycle = collections.Counter(o.cycle for o in no_slot)
    print("    top cycles: " + ", ".join(
        f"{ci} ({n}, {era_by_cycle.get(ci, '?')}, N={by_index[ci].levels_per_side})"
        for ci, n in per_cycle.most_common(8)
    ))
    in_redeploy = sum(1 for o in no_slot if o.order_id in redeploy_ids)
    print(f"    of those, inside a missed-redeployment cluster: {in_redeploy}")

    # --------------------------------------------------------------- part 10
    # Final accounting.  Every order that is not an exact-price return is tested
    # against ONE alternative: it belongs to a second deployment inside the same
    # detected cycle.  Per cycle, fit (anchor, step) to the unexplained orders --
    # 2 free parameters against up to 120 observations, so a scattered
    # relocation population cannot pass -- and then check two things the fit does
    # not see: the residual per order, and whether the fitted anchor sits at the
    # MARKET at the cluster's start (the deployment law of V1).
    print()
    print("=" * 78)
    print("PART 10 -- final accounting: is every non-exact order a missed deployment?")
    print("=" * 78)
    unexplained = collections.defaultdict(list)
    for order, _reference, _delta in offenders:
        unexplained[order.cycle].append(order)
    for order in no_slot:
        unexplained[order.cycle].append(order)

    print(f"    {'cycle':>6} {'era':<14} {'orders':>7} {'keys':>5} {'step':>7} {'anchor':>10}"
          f" {'cyc step':>9} {'cyc anch':>9}"
          f" {'mkt@start':>10} {'|d|':>6} {'resid p95':>10} {'in tick':>8}")
    total_unexplained = 0
    total_on_lattice = 0
    for cycle_index in sorted(unexplained):
        group = sorted(unexplained[cycle_index], key=lambda o: o.open_time)
        anchor, step = fit(group)
        if step <= 0:
            print(f"    {cycle_index:>6} {era_by_cycle.get(cycle_index, '?'):<14} {len(group):>7}"
                  f" {len({(o.side, o.level) for o in group}):>5}   no fit")
            total_unexplained += len(group)
            continue
        residuals = []
        for order in group:
            predicted = anchor + order.level * step if order.side == "B" else anchor - order.level * step
            residuals.append(abs(order.price - predicted))
        on_lattice = sum(1 for r in residuals if r <= 0.005)
        index = bisect_left(qt, group[0].open_time)
        proxy = None
        candidates = []
        if index < len(quotes):
            candidates.append(quotes[index])
        if index > 0:
            candidates.append(quotes[index - 1])
        if candidates:
            when, price = min(candidates, key=lambda c: abs((c[0] - group[0].open_time).total_seconds()))
            if abs((when - group[0].open_time).total_seconds()) <= 120.0:
                proxy = price
        total_unexplained += len(group)
        total_on_lattice += on_lattice
        print(
            f"    {cycle_index:>6} {era_by_cycle.get(cycle_index, '?'):<14} {len(group):>7}"
            f" {len({(o.side, o.level) for o in group}):>5} {step:>7.2f} {anchor:>10.2f}"
            f" {by_index[cycle_index].step:>9.2f} {by_index[cycle_index].anchor:>9.2f}"
            f" {('%10.2f' % proxy) if proxy is not None else '         -'}"
            f" {('%6.2f' % abs(anchor - proxy)) if proxy is not None else '     -'}"
            f" {q(residuals, 0.95):>10.3f} {on_lattice:>4}/{len(group):<4}"
        )
    print()
    print(f"    unexplained orders {total_unexplained}   of which on a fresh lattice"
          f" {total_on_lattice} = {pct(total_on_lattice, total_unexplained):.2f}%")
    redeploy_cycles = sorted({ci for ci, _run in lattice_like})
    print(f"    cycles carrying a missed deployment: {len(redeploy_cycles)} -> {redeploy_cycles}")
    # Do NOT print "detected cycles + missed deployments = 285" as an identity: the
    # two sides count different things, and the sum matching the independent cut is
    # a coincidence of this probe's reach.  tmp/a901_xcheck.py measures the
    # segmenter defect exactly against that cut instead -- 270 of 275 detected
    # cycles carry >=1 independent burst, 15 bursts start inside a cycle that had
    # already opened, 5 cycles carry no burst at all, and 0 bursts are homeless, so
    # 270 + 15 = 285 exactly.  This part can only fit the swallowed bursts whose
    # legs reached the re-arm pool; the other swallowed bursts were filed as some
    # cycle's burst_orders and were never re-arm candidates (part 1 excludes them).
    print(f"    (segmenter defect measured in tmp/a901_xcheck.py:"
          f" {len(cycles)} detected cycles vs 285 independent bursts)")

    # --------------------------------------------------------------- part 11
    # The residual after part 10 is dominated by single-key clusters, which a
    # 2-parameter lattice fit cannot score at all.  Test those against the
    # CYCLE's own (anchor, step) extended to any level: _burst_clusters() trims
    # a deployment run at the first repeated (side,level) key, so a cycle whose
    # burst contained an early duplicate keeps a SHORT slot table and its deeper
    # levels are reported as "no slot" even though the order returned to the
    # lattice exactly.  That predicate is independent of the order being tested:
    # (anchor, step) come from the burst, i.e. from the sweep only.
    print()
    print("=" * 78)
    print("PART 11 -- residual: does it sit on the cycle's OWN lattice, extended?")
    print("=" * 78)
    # Cycle 169 is scored here like every other fitted cycle.  An earlier draft
    # excluded it: its 24 orders fit a lattice at 4074.73 while the 120 s quote
    # proxy read 4111.60, and a buy stop 37 points below market is impossible, so
    # the fit looked like a coincidence.  tmp/a901_c169.py printed the raw tape
    # and refuted the premise -- there is NO deal between 10:25 and 10:55 on
    # 2026-07-13 (nearest before is 18574.9 s stale; nearest after, at 11:02:56,
    # prices 4074.73, the fitted anchor to the cent), so the proxy was 5.2 h
    # stale and the fit is the market.  tmp/a901_xcheck.py then found the same
    # burst in the INDEPENDENT detector at 10:39:29.363, anchor 4074.73 step
    # 0.49, N 13, 24 legs -- an aborted deployment, canceled 23 min later when
    # the next full N=30 burst went out at 11:02:45.
    fresh_ids = set()
    for cycle_index in redeploy_cycles:
        group = unexplained[cycle_index]
        anchor, step = fit(group)
        if step <= 0:
            continue
        for order in group:
            predicted = anchor + order.level * step if order.side == "B" else anchor - order.level * step
            if abs(order.price - predicted) <= 0.005:
                fresh_ids.add(order.order_id)

    on_own, off_own, residual = 0, [], []
    for cycle_index, group in unexplained.items():
        cycle = by_index[cycle_index]
        for order in group:
            if order.order_id in fresh_ids:
                continue
            predicted = (cycle.anchor + order.level * cycle.step) if order.side == "B" \
                else (cycle.anchor - order.level * cycle.step)
            delta = order.price - predicted
            residual.append(abs(delta))
            if abs(delta) <= 0.005:
                on_own += 1
            else:
                off_own.append((order, predicted, delta))
    print(f"    orders not on a fresh lattice: {on_own + len(off_own)}")
    print(f"      on the cycle's own extended lattice : {on_own}"
          f" = {pct(on_own, on_own + len(off_own)):.2f}%")
    print(f"      on neither                          : {len(off_own)}")
    if residual:
        print(f"      |delta| p50 {q(residual, 0.50):.3f}  p95 {q(residual, 0.95):.3f}"
              f"  max {max(residual):.3f}")
    if off_own:
        per_cycle_off = collections.Counter(o.cycle for o, _p, _d in off_own)
        print("      by cycle: " + ", ".join(
            f"{ci} ({n}, {era_by_cycle.get(ci, '?')})" for ci, n in per_cycle_off.most_common(10)
        ))
        print("      first 12:")
        for order, predicted, delta in sorted(off_own, key=lambda t: t[0].open_time)[:12]:
            print(f"        cycle {order.cycle:>3} {order.side}{order.level:<3} #{order.order_id}"
                  f" {order.open_time} price {order.price:>9.2f}"
                  f" own-lattice {predicted:>9.2f} delta {delta:+.2f}")

    # ------------------------------------------------------------ final tally
    print()
    print("=" * 78)
    print("FINAL TALLY -- every grid pending that is not a detected deployment order")
    print("=" * 78)
    exact_to_slot = 0
    for order in rearms:
        if order.order_id in fresh_ids:
            continue
        reference = burst_price.get((order.cycle, order.side, order.level))
        if reference is not None and abs(order.price - reference) <= 0.005:
            exact_to_slot += 1
    denominator = len(rearms) - len(fresh_ids)
    accounted = exact_to_slot + on_own
    print(f"    candidate re-arms                    {len(rearms)}")
    print(f"      orders belonging to a missed deployment (part 10)  -{len(fresh_ids)}")
    print(f"      true re-arms                                       {denominator}")
    print(f"        exact return to the burst slot                   {exact_to_slot}"
          f" = {pct(exact_to_slot, denominator):.2f}%")
    print(f"        exact return to a slot the segmenter trimmed     {on_own}"
          f" = {pct(on_own, denominator):.2f}%")
    print(f"        exact-price returns, total                       {accounted}"
          f" = {pct(accounted, denominator):.2f}%")
    print(f"        neither -- a genuine relocation would live here   {denominator - accounted}")

    # Part 3 re-scored on the true re-arm population.  Its raw "286 slots
    # disagree / max spread 38.4100" is the same segmentation artifact seen from
    # a per-slot angle: a swallowed deployment re-uses every (side,level) key at
    # a DIFFERENT anchor, so its orders land in the same slot bucket as the
    # cycle's own re-arms and inflate the spread.  Drop the 1091 fitted
    # deployment orders and the per-level memory question is answered directly.
    clean = collections.defaultdict(list)
    for order in rearms:
        if order.order_id in fresh_ids:
            continue
        clean[(order.cycle, order.side, order.level)].append(order)
    multi_clean = {k: v for k, v in clean.items() if len(v) >= 2}
    spreads_clean = [max(o.price for o in g) - min(o.price for o in g)
                     for g in multi_clean.values()]
    disagree = sum(1 for s in spreads_clean if s > 0.005)
    print()
    print("    per-level memory, re-scored on the true re-arm population:")
    print(f"      slots re-armed at least twice: {len(multi_clean)}"
          f"   re-arms in them {sum(len(v) for v in multi_clean.values())}")
    print(f"      deepest repeat count         : "
          f"{max((len(v) for v in multi_clean.values()), default=0)}")
    print(f"      slots whose repeats disagree by more than half a tick: {disagree}")
    print(f"      max intra-slot price spread  : {max(spreads_clean, default=0.0):.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
