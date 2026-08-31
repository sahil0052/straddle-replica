"""What are the four unpaced close packs?  Bimodality test + raw tape context.

a901_cadence.py settled the pacing question: the EA's basket close has a HARD
floor at 97 ms (3,100 of 3,154 gaps >= 95 ms) exactly like the timer-paced
lattice placements (27,221 of 27,221 gaps >= 96 ms), while server-authored
stop-out cascades sit at 93.75% below 10 ms.  But 53 close gaps fell below 95 ms
and they were not scattered -- they collapsed onto FOUR bursts, every one with
d(ticket)=1 and internal spacing of 2-8 ms.

So the residual question is not "how does the EA pace its sweep" but "who sent
those four packs".  Two candidate authors:

  EA      a basket sweep that somehow lost its delay.  Then the pack must look
          like a sweep in every OTHER respect: pendings bulk-canceled just
          before it (cancel_before_close, 271/282 on this tape), the basket
          flattened, and a fresh deployment burst about restart_delay_ms later.
  HUMAN   the operator flattening by hand in the terminal.  A manual close
          carries NO comment (which is why it lands in the same comment family
          as the pre-2026-07-13 build's sweeps -- DIV-3 makes comment a BUILD
          fingerprint, not an authorship one), dispatches as fast as the
          terminal can send, and does NOT cancel pendings first.

The operator is a known actor here: on the Starwave tape the partial-close
chains turned out to be manual closes (magic 0, ORDER_REASON_CLIENT), not an EA
mechanism.  The 901018 report carries no magic and no reason column, so the test
has to be structural.

Instrument, in two parts:
  1. Bimodality.  Median internal gap per close burst, histogrammed.  A single
     population centred on ~105 ms means one author; two separated modes mean two.
  2. Context.  For every burst whose median internal gap is under 50 ms, dump the
     complete order tape (all types, all comments, states and fill times) for
     -60 s .. +60 s around it, so cancels, stop-outs and the next deployment are
     all visible at once.
"""
from __future__ import annotations

import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from a901_cadence import bursts, era_indexer, population  # noqa: E402
from a901_v4578 import build_deployments, load_orders, norm, stamp  # noqa: E402

UNPACED_MS = 50.0
CONTEXT_S = 60.0


def median(values):
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


def internal_gaps(burst):
    return [(right["when"] - left["when"]).total_seconds() * 1000.0
            for left, right in zip(burst, burst[1:])]


def main() -> int:
    orders = load_orders()
    records = build_deployments(orders)
    era_at = era_indexer(records)
    deploy_starts = [r["when"] for r in records]

    closes = population(orders, "EA_CLOSE")
    packs = []
    modes: collections.Counter = collections.Counter()
    for burst in bursts(closes):
        gaps = internal_gaps(burst)
        if not gaps:
            modes["singleton"] += 1
            continue
        mid = median(gaps)
        bucket = ("<10ms" if mid < 10 else "10-50ms" if mid < 50 else
                  "50-95ms" if mid < 95 else "95-135ms" if mid < 135 else ">=135ms")
        modes[bucket] += 1
        if mid < UNPACED_MS:
            packs.append((burst, gaps, mid))

    print("=== part 1: median INTERNAL gap per close burst (is it bimodal?) ===")
    total = sum(modes.values())
    for key in ("singleton", "<10ms", "10-50ms", "50-95ms", "95-135ms", ">=135ms"):
        if modes[key]:
            print(f"  {key:10s} {modes[key]:5d} bursts  ({100.0*modes[key]/total:5.2f}%)")
    print(f"  total      {total:5d} bursts")
    print()

    print(f"=== part 2: raw tape around each unpaced pack ({len(packs)} of them) ===")
    for burst, gaps, mid in packs:
        lo = burst[0]["when"].timestamp() - CONTEXT_S
        hi = burst[-1]["when"].timestamp() + CONTEXT_S
        pack_tickets = {row["ticket"] for row in burst}
        span = (burst[-1]["when"] - burst[0]["when"]).total_seconds()
        print(f"\n  ---- pack of {len(burst)} closes, era={era_at(burst[0]['when'])}, "
              f"{burst[0]['when']} .. {burst[-1]['when']}  span={span:.3f}s  "
              f"median gap={mid:.1f}ms  gaps={[f'{g:.0f}' for g in gaps][:12]}")
        # Was a fresh deployment burst started right after?  (EA restart signature)
        after = [d for d in deploy_starts if d > burst[-1]["when"]]
        if after:
            print(f"       next deployment burst starts "
                  f"{(after[0]-burst[-1]['when']).total_seconds():+.3f}s later "
                  f"({after[0]})")
        rows = []
        for row in orders:
            when = stamp(row["Open Time"])
            if when is None or not (lo <= when.timestamp() <= hi):
                continue
            rows.append((when, row))
        rows.sort(key=lambda item: (item[0], norm(item[1]["Order"])))
        tally: collections.Counter = collections.Counter()
        print("       open time                 ticket     type       vol          "
              "price     state      fill/cancel time          comment")
        for when, row in rows:
            ticket = norm(row["Order"])
            mark = ">>" if ticket in pack_tickets else "  "
            kind = norm(row["Type"])
            state = norm(row["State"])
            tally[f"{kind}/{state}"] += 1
            print(f"    {mark} {when}   {ticket:10s} {kind:10s} "
                  f"{norm(row['Volume']):12s} {norm(row['Price']):9s} {state:9s} "
                  f"{norm(row['Time']):24s}  {norm(row['Comment'])}")
        print(f"       window census: "
              + "  ".join(f"{k}={v}" for k, v in sorted(tally.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
