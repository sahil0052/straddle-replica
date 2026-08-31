"""Does the 901018 tape leak displaced positions the way the Starwave tape does?

The Starwave audit (D6/D7) proved the Target's level table owns exactly ONE
position ticket per (side,level) and a re-fill OVERWRITES it, so the displaced
position is never tracked, never trailed, never swept: 153 of 2,468 fills
survived to the end of the window, 148 of them outlived at least one complete
basket sweep, 66 outlived 61 or more, and 0 of 153 ever received an [sl] order.
That is the evidence behind `replica_orphan_leak`.

The 901018 tape contradicts it at first glance -- D8 found the residue does NOT
ratchet there (max deployment boundaries crossed = 1 in every era, flat-at-sweep
84-100%, residue p50 0.0, and the report ends with only 7 open positions).  Two
readings fit that:

  BUILD    901018's build sweeps the BOOK (every position carrying the magic)
           instead of the tracked tickets, so a displaced position is picked up
           by the very next sweep.  Then `replica_orphan_leak` is a per-build
           flag and the Starwave profiles are the only ones entitled to it.
  SERVER   901018's displaced positions are cleaned by the SERVER, not the EA.
           A position that was tracked long enough to be trailed carries an S/L;
           once it falls out of the table that stop stays armed, so the next
           adverse move stops it out.  Then the leak is identical on both tapes
           and the difference is only that 901018 traded a regime where stops
           existed and got hit -- no code change, and the flag stays as it is.

The discriminator is what CLOSED each displaced position.  A market close from
the EA's own sweep family (empty comment / "STR CLOSE") means BUILD; an [sl]
exit means SERVER.  Exit classification uses correction (A)'s validated rule
dir*(close - sl) <= 0 (13,680/13,872 = 98.62%, zero false positives), never
close_price == sl equality, which only catches 13.57%.

Orphan definition, matching D6/D7's wording exactly -- "same-level OVERLAPPING
pairs".  A slot filling twice inside a cycle is NOT displacement on its own: the
ordinary loop is fill -> stopped out -> level re-armed -> fill again, which is
sequential occupancy of one slot and leaves nothing untracked.  Displacement
requires OVERLAP: the later fill must arrive while the earlier position is still
open, so the table's single `position_ticket` write actually orphans a live
position.  Scoring the loose "filled more than once" definition instead labels
10,475 of 17,515 fills (59.81%) displaced, of which 10,384 (99.13%) had already
been closed by their own [sl] before the slot was re-used -- i.e. the loose
definition measures the re-arm loop, not the leak.
"""
from __future__ import annotations

import collections
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from a901_cadence import era_indexer  # noqa: E402
from a901_v4578 import build_deployments, load_orders, norm, parse_level, stamp  # noqa: E402


def load_positions_all():
    """Positions table, positional read, KEEPING the still-open rows."""
    rows = []
    with Path("tmp/r901018_positions.csv").open(encoding="utf-8") as handle:
        reader = csv.reader(handle)
        next(reader)
        for row in reader:
            if len(row) < 13 or not norm(row[1]):
                continue
            opened = stamp(row[0])
            if opened is None:
                continue
            rows.append({
                "opened": opened,
                "ticket": int(norm(row[1])),
                "is_buy": norm(row[3]) == "buy",
                "volume": float(norm(row[4])),
                "open_price": float(norm(row[5])),
                "sl": float(norm(row[6])) if norm(row[6]) else 0.0,
                "closed": stamp(row[8]),
                "close_price": float(norm(row[9])) if norm(row[9]) else 0.0,
                "profit": float(norm(row[12])) if norm(row[12]) else 0.0,
            })
    rows.sort(key=lambda item: (item["opened"], item["ticket"]))
    return rows


def lattice_map(orders):
    """ticket -> (is_buy, level) for every FILLED lattice stop order."""
    out = {}
    for row in orders:
        if norm(row["Type"]) not in ("buy stop", "sell stop"):
            continue
        if norm(row["State"]) != "filled":
            continue
        parsed = parse_level(row["Comment"])
        if parsed is None:
            continue
        try:
            out[int(norm(row["Order"]))] = parsed
        except ValueError:
            continue
    return out


def exit_class(position):
    if position["closed"] is None:
        return "STILL-OPEN"
    if position["sl"] <= 0.0:
        return "MARKET(no-sl)"
    direction = 1.0 if position["is_buy"] else -1.0
    return "SL" if direction * (position["close_price"] - position["sl"]) <= 0.0 else "MARKET"


def main() -> int:
    orders = load_orders()
    records = build_deployments(orders)
    era_at = era_indexer(records)
    starts = [r["when"] for r in records]
    levels = lattice_map(orders)
    positions = [p for p in load_positions_all() if p["ticket"] in levels]

    def cycle_of(when):
        found = -1
        for index, start in enumerate(starts):
            if start <= when:
                found = index
            else:
                break
        return found

    groups: dict[tuple, list] = collections.defaultdict(list)
    for position in positions:
        is_buy, level = levels[position["ticket"]]
        groups[(cycle_of(position["opened"]), is_buy, level)].append(position)

    displaced, survivors, refills = [], [], 0
    for key, members in groups.items():
        if len(members) < 2:
            continue
        members.sort(key=lambda item: (item["opened"], item["ticket"]))
        refills += len(members) - 1
        survivors.append(members[-1])
        # OVERLAP is the displacement condition: some later fill at this slot
        # arrived while this position was still open, so the table's single
        # position_ticket was overwritten on a LIVE position.
        for index, position in enumerate(members[:-1]):
            end = position["closed"]
            if any(end is None or later["opened"] < end for later in members[index + 1:]):
                position["slot"] = key
                displaced.append(position)

    print(f"=== lattice fills on the 901018 tape: {len(positions)} "
          f"(of {len(levels)} filled lattice orders) ===")
    print(f"    (side,level) slots re-used inside one cycle: {len(survivors)} slots, "
          f"{refills} re-fills")
    print(f"    of those re-fills, OVERLAPPING (earlier position still open when the "
          f"slot was rewritten): {len(displaced)}")
    print(f"    DISPLACED / orphaned positions: {len(displaced)}"
          f"  = {100.0*len(displaced)/max(1,len(positions)):.2f}% of fills"
          f"   [Starwave comparison: 153/2468 = 6.20%]")
    print()

    print("=== what closed each displaced position, and did it outlive a cycle? ===")
    print("  era              displaced   boundaries-crossed 0 / 1 / 2 / >=3        "
          "SL   MARKET  MARKET(no-sl)  STILL-OPEN")
    per_era: dict[str, dict] = collections.defaultdict(
        lambda: {"n": 0, "cross": collections.Counter(), "exit": collections.Counter(),
                 "max_cross": 0})
    for position in displaced:
        end = position["closed"]
        crossed = sum(1 for start in starts
                      if position["opened"] < start and (end is None or start < end))
        era = era_at(position["opened"])
        bucket = per_era[era]
        bucket["n"] += 1
        bucket["cross"][min(crossed, 3)] += 1
        bucket["exit"][exit_class(position)] += 1
        bucket["max_cross"] = max(bucket["max_cross"], crossed)
        position["crossed"] = crossed
    order = ["HISTORICAL_50", "HISTORICAL_60", "AGGRESSIVE_30", "LOW_RISK_30", "STARWAVE_30"]
    for era in order + [k for k in per_era if k not in order]:
        if era not in per_era:
            continue
        bucket = per_era[era]
        cross, exits = bucket["cross"], bucket["exit"]
        print(f"  {era:16s} {bucket['n']:9d}   "
              f"{cross[0]:5d} /{cross[1]:4d} /{cross[2]:4d} /{cross[3]:5d}   "
              f"(max {bucket['max_cross']:2d})  "
              f"{exits['SL']:5d} {exits['MARKET']:7d} {exits['MARKET(no-sl)']:12d} "
              f"{exits['STILL-OPEN']:11d}")
    total_cross: collections.Counter = collections.Counter()
    total_exit: collections.Counter = collections.Counter()
    for bucket in per_era.values():
        total_cross.update(bucket["cross"])
        total_exit.update(bucket["exit"])
    print(f"  {'ALL':16s} {len(displaced):9d}   "
          f"{total_cross[0]:5d} /{total_cross[1]:4d} /{total_cross[2]:4d} /{total_cross[3]:5d}"
          f"           {total_exit['SL']:5d} {total_exit['MARKET']:7d} "
          f"{total_exit['MARKET(no-sl)']:12d} {total_exit['STILL-OPEN']:11d}")
    print()

    # The decisive split.  Only positions that outlived at least one deployment
    # boundary are leaked at all -- and for those, SL vs MARKET names the author
    # of the cleanup.
    leaked = [p for p in displaced if p["crossed"] >= 1]
    print(f"=== of the {len(displaced)} displaced, {len(leaked)} outlived a deployment "
          f"boundary (a full cycle + its sweep) ===")
    census: collections.Counter = collections.Counter(exit_class(p) for p in leaked)
    for key, count in census.most_common():
        print(f"    {key:14s} {count:5d}  ({100.0*count/max(1,len(leaked)):5.2f}%)")
    with_sl = sum(1 for p in leaked if p["sl"] > 0.0)
    print(f"    carried an S/L at close time: {with_sl}/{len(leaked)}"
          f"  ({100.0*with_sl/max(1,len(leaked)):.2f}%)")
    print()

    print("=== every leaked displaced position, oldest first ===")
    print("  era              ticket     side lvl  opened                    "
          "closed                    crossed  sl        close     exit")
    for position in sorted(leaked, key=lambda item: item["opened"]):
        is_buy, level = levels[position["ticket"]]
        closed = "STILL OPEN" if position["closed"] is None else str(position["closed"])
        print(f"  {era_at(position['opened']):16s} {position['ticket']:10d} "
              f"{'B' if is_buy else 'S'}   {level:3d}  {position['opened']}   "
              f"{closed:24s}  {position['crossed']:5d}   "
              f"{position['sl']:9.2f} {position['close_price']:9.2f} "
              f"{exit_class(position)}")
    print()
    rearm_gate_test(orders, records, era_at, cycle_of, levels, positions)
    return 0


def rearm_gate_test(orders, records, era_at, cycle_of, levels, positions):
    """Did the Target RE-ARM a level while that level still held a position?

    Zero overlapping fills is a necessary consequence of a re-arm gated on
    !has_position, but it is ALSO what a lucky tape looks like: a stop-entry
    ladder whose position carries a trailing stop is normally stopped out on the
    retrace that would be needed to re-load the level, so overlap can be absent
    even from an ungated build.  The gate itself is directly observable one level
    up -- at the moment the re-arm PENDING is placed.

      gated    every re-arm pending for slot (side,level) is dispatched strictly
               after that slot's position closed.  `RearmEligible()`'s
               `rearm_requested && !has_position`.
      ungated  some re-arm pendings are dispatched while the slot's position is
               still open.  That is the Starwave build, and the displaced
               position it eventually creates is `replica_orphan_leak`.

    A re-arm pending is any FILLED-or-CANCELED lattice stop order placed OUTSIDE
    every deployment burst window, so the initial interleaved sweep and the
    DIV-5 tail retry (both inside the burst) are excluded by construction.
    """
    spans = [(r["when"], r["end"]) for r in records]

    def in_burst(when):
        for start, end in spans:
            if start <= when <= end:
                return True
            if start > when:
                break
        return False

    open_intervals: dict[tuple, list] = collections.defaultdict(list)
    for position in positions:
        is_buy, level = levels[position["ticket"]]
        open_intervals[(cycle_of(position["opened"]), is_buy, level)].append(position)

    per_era: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    offenders = []
    for row in orders:
        if norm(row["Type"]) not in ("buy stop", "sell stop"):
            continue
        parsed = parse_level(row["Comment"])
        if parsed is None:
            continue
        when = stamp(row["Open Time"])
        if when is None or in_burst(when):
            continue
        is_buy, level = parsed
        era = era_at(when)
        bucket = per_era[era]
        bucket["rearms"] += 1
        live = [p for p in open_intervals[(cycle_of(when), is_buy, level)]
                if p["opened"] < when and (p["closed"] is None or when < p["closed"])]
        if live:
            bucket["over-live-position"] += 1
            offenders.append((when, era, is_buy, level, norm(row["Order"]), live))
        else:
            bucket["after-close"] += 1

    print("=== part 2: was a level ever RE-ARMED while it still held a position? ===")
    print("  era               re-arm pendings   dispatched after close   "
          "dispatched OVER a live position")
    order = ["HISTORICAL_50", "HISTORICAL_60", "AGGRESSIVE_30", "LOW_RISK_30", "STARWAVE_30"]
    total: collections.Counter = collections.Counter()
    for era in order + [k for k in per_era if k not in order]:
        if era not in per_era:
            continue
        bucket = per_era[era]
        total.update(bucket)
        print(f"  {era:16s} {bucket['rearms']:15d}   {bucket['after-close']:22d}   "
              f"{bucket['over-live-position']:31d}")
    print(f"  {'ALL':16s} {total['rearms']:15d}   {total['after-close']:22d}   "
          f"{total['over-live-position']:31d}")
    for when, era, is_buy, level, ticket, live in offenders[:25]:
        print(f"    >> {when}  era={era:16s} {'B' if is_buy else 'S'}{level:<3d} "
              f"order={ticket}  live={[p['ticket'] for p in live]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
