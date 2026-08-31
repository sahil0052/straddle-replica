"""Sub-cadence closes: is the ~105 ms close pacing a DELAY or a round trip?

V5's terminal table left one number unexplained: HISTORICAL_60's inter-close gap
has p05 = 101.0 ms but min = 0.0 ms, and AGGRESSIVE_30's median inter-close gap
is 3.0 ms.  Both matter for parity, because the replica paces its basket sweep at
one close per OnTimer tick with the timer period pinned to
MathMax(20, inter_order_delay_ms) = 100 ms.  If the Target ever fired two closes
inside the same millisecond then that pacing is not what the Target did, and the
~105 ms median everyone reads as "a configured 100 ms delay" would instead be the
broker round trip of a synchronous OrderSend inside a tight loop.

Contamination is ruled out by construction, not by assumption: build_sweeps()
admits ONLY the two basket-close comment families (empty before the 2026-07-13
12:28 build changeover, "STR CLOSE" after it -- DIV-3), so broker stop-outs,
which carry "[sl <price>]", were never in the population that produced min=0.0.

Three populations are scored on one axis so the answer cannot come from the
instrument:

  PENDING   lattice stop orders inside a deployment burst.  These ARE timer-paced
            -- one placement per tick, 15,604 gaps, p50 105 ms -- so they are the
            positive control for what a 100 ms delay looks like on this tape.
  EA_CLOSE  the basket-close market orders.  The population under test.
  STOP_OUT  "[sl ...]" market orders, authored by the SERVER when price runs
            through a cluster of stops.  These are the negative control: nothing
            paces them, so a cascade should pile up below 10 ms.

If EA_CLOSE matches PENDING and STOP_OUT does not, the 100 ms delay is real and
the sub-cadence tail is a handful of oddities.  If EA_CLOSE carries a STOP_OUT-
shaped sub-10 ms mass, the sweep is a loop and the replica's one-per-tick sweep
is a divergence.
"""
from __future__ import annotations

import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from a901_v4578 import (  # noqa: E402
    build_deployments,
    eras_present,
    load_orders,
    norm,
    parse_level,
    parse_volume,
    pct,
    stamp,
)

BURST_S = 2.0
EDGES = [0.0, 1.0, 10.0, 50.0, 95.0, 135.0, 250.0, 500.0, 1e18]


def population(orders, kind):
    """Rows of one authorship family, sorted by (time, ticket)."""
    rows = []
    for row in orders:
        kind_text = norm(row["Type"])
        comment = norm(row["Comment"])
        when = stamp(row["Open Time"])
        if when is None:
            continue
        if kind == "PENDING":
            if kind_text not in ("buy stop", "sell stop") or parse_level(comment) is None:
                continue
        elif kind == "EA_CLOSE":
            if kind_text not in ("buy", "sell") or comment not in ("", "STR CLOSE"):
                continue
        elif kind == "STOP_OUT":
            if kind_text not in ("buy", "sell") or not comment.startswith("[sl"):
                continue
        rows.append({
            "when": when,
            "ticket": norm(row["Order"]),
            "comment": comment,
            "volume": parse_volume(row["Volume"]),
            "side": kind_text,
        })
    rows.sort(key=lambda item: (item["when"], item["ticket"]))
    return rows


def bursts(rows, gap_s=BURST_S):
    out, current = [], []
    for row in rows:
        if current and (row["when"] - current[-1]["when"]).total_seconds() > gap_s:
            out.append(current)
            current = []
        current.append(row)
    if current:
        out.append(current)
    return out


def era_indexer(records):
    starts = [(r["when"], str(r["assigned"])) for r in records]

    def era_at(when):
        found = "before-first-deployment"
        for start, name in starts:
            if start <= when:
                found = name
            else:
                break
        return found

    return era_at


def histogram(values):
    counts = [0] * (len(EDGES) - 1)
    for value in values:
        for index, (lo, hi) in enumerate(zip(EDGES, EDGES[1:])):
            if lo <= value < hi:
                counts[index] += 1
                break
    return counts


def main() -> int:
    orders = load_orders()
    era_at = era_indexer(build_deployments(orders))

    per_kind: dict[str, dict[str, list[float]]] = {}
    sub_cadence: list[tuple] = []
    for kind in ("PENDING", "EA_CLOSE", "STOP_OUT"):
        rows = population(orders, kind)
        by_era: dict[str, list[float]] = collections.defaultdict(list)
        for burst in bursts(rows):
            for left, right in zip(burst, burst[1:]):
                gap = (right["when"] - left["when"]).total_seconds() * 1000.0
                era = era_at(left["when"])
                by_era[era].append(gap)
                if kind == "EA_CLOSE" and gap < 95.0:
                    sub_cadence.append((era, gap, left, right, len(burst)))
        per_kind[kind] = by_era

    print("=== one axis, three authorship families: within-burst gap in ms ===")
    print("  family    era                  n     <1   1-10  10-50  50-95  "
          "95-135  135-250  250-500   >=500     min    p05    p50    p95")
    for kind in ("PENDING", "EA_CLOSE", "STOP_OUT"):
        by_era = per_kind[kind]
        for era in eras_present(by_era):
            gaps = by_era[era]
            if len(gaps) < 5:
                continue
            counts = histogram(gaps)
            cells = "".join(f"{value:7d}" if index < 4 else f"{value:9d}"
                            for index, value in enumerate(counts))
            print(f"  {kind:9s} {era:16s} {len(gaps):6d}{cells}  "
                  f"{min(gaps):6.1f} {pct(gaps, 0.05):6.1f} "
                  f"{pct(gaps, 0.50):6.1f} {pct(gaps, 0.95):6.1f}")
        totals = [g for gaps in by_era.values() for g in gaps]
        counts = histogram(totals)
        share = 100.0 * (counts[0] + counts[1]) / len(totals)
        print(f"  {kind:9s} {'ALL':16s} {len(totals):6d}"
              + "".join(f"{value:7d}" if index < 4 else f"{value:9d}"
                        for index, value in enumerate(counts))
              + f"  {min(totals):6.1f} {pct(totals, 0.05):6.1f} "
                f"{pct(totals, 0.50):6.1f} {pct(totals, 0.95):6.1f}   "
                f"sub-10ms={share:.2f}%")
        print()

    print(f"=== every EA_CLOSE gap below 95 ms ({len(sub_cadence)} of them) ===")
    print("  era              gap ms   left time                 right time                "
          "d(ticket)  vols        burst legs")
    for era, gap, left, right, legs in sorted(sub_cadence, key=lambda item: item[1]):
        try:
            delta = int(right["ticket"]) - int(left["ticket"])
        except ValueError:
            delta = 0
        print(f"  {era:16s} {gap:6.1f}   {left['when']}   {right['when']}   "
              f"{delta:8d}  {left['volume']:.2f}/{right['volume']:.2f}   {legs:4d}")

    # A same-millisecond pair means two OrderSend calls inside one millisecond,
    # which a synchronous send to a live broker cannot do.  Count them exactly.
    print()
    closes = population(orders, "EA_CLOSE")
    by_ms: collections.Counter = collections.Counter(row["when"] for row in closes)
    collisions = {when: count for when, count in by_ms.items() if count > 1}
    print(f"=== EA_CLOSE orders sharing an exact millisecond: "
          f"{sum(collisions.values())} orders in {len(collisions)} timestamps ===")
    for when, count in sorted(collisions.items())[:20]:
        tickets = [row["ticket"] for row in closes if row["when"] == when]
        print(f"  {when}  x{count}  era={era_at(when):16s} tickets={tickets}")

    # Same question for the timer-paced control, as a calibration of clock noise.
    pendings = population(orders, "PENDING")
    pend_ms: collections.Counter = collections.Counter(row["when"] for row in pendings)
    pend_coll = {when: count for when, count in pend_ms.items() if count > 1}
    print(f"  control: PENDING orders sharing an exact millisecond: "
          f"{sum(pend_coll.values())} orders in {len(pend_coll)} timestamps "
          f"(of {len(pendings)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
