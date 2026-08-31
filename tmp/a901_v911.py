"""V10, final instrument: the per-level ROUND-TRIP structure of a rescue.

PART 3c proved the phase-A descending invariant (33/33 passes) but also showed,
in the raw lifecycle dumps, base orders being re-placed at BASE between base
cancels -- e.g. cycle 262 sell L19:

    0.06 canceled  done 16:08:21.029
    0.06 placed         16:08:21.131   <-- 0.102 s later, BASE again
    0.06 canceled  done 16:08:24.797
    0.06 placed         16:08:24.899   <-- BASE again
    0.06 canceled  done 16:08:29.312
    0.12 placed         16:08:29.413   <-- finally 2x

The replica cannot produce that.  TryCancelTrendRescueLevel (StraddleEngine.mqh
:2461-2466) rewrites level_state.volume to lots[index]*multiplier at the moment
of the cancel and ClearTrendRescueReplacement (:2497-2502) never restores it, so
the replica's PlaceOneTrendRescueReplacement lands 2x on the FIRST replacement.
The Target evidently lands base first, one or more times, and 2x only later.

This script measures that difference exactly, and -- decisively -- whether the
intermediate base pendings can ever FILL.  If they always end 'canceled' with a
short lifetime, the divergence is confined to the order tape and cannot touch
fills, exposure or P&L.  If any of them FILLED, it is a real economic divergence.

Definitions
-----------
event window   the (cycle, side) span from the first own-side base cancel to the
               last own-side 2x placement, padded by PAD_S on both ends.
chain          all own-side lattice orders at one level inside the window, in
               time_setup order, each tagged base / x2 / other.
round trip     a base cancel immediately followed (at the same level) by a new
               order.  classified by that successor's volume tier.
"""

import collections
import csv
from datetime import datetime
from pathlib import Path

from a901_eras import norm, parse_level, parse_volume, stamp
from a901_v4578 import build_deployments, load_orders

PAD_S = 5.0
PASS_GAP_S = 1.0
LADDER_SW30 = ((10, 0.01), (20, 0.06), (30, 0.15))


def base_lot(level):
    for bound, lot in LADDER_SW30:
        if level <= bound:
            return lot
    return LADDER_SW30[-1][1]


def tier(volume, level):
    base = base_lot(level)
    if abs(volume - base) <= 1e-9:
        return "base"
    if abs(volume - 2.0 * base) <= 1e-9:
        return "x2"
    return f"other({volume:.2f})"


def rows_for(orders):
    out = []
    for row in orders:
        parsed = parse_level(row["Comment"])
        setup = stamp(row["Open Time"])
        if parsed is None or setup is None:
            continue
        out.append({
            "setup": setup,
            "done": stamp(row["Time"]),
            "is_buy": parsed[0],
            "level": parsed[1],
            "volume": parse_volume(row["Volume"]),
            "state": (norm(row["State"]).split()[0].lower()
                      if norm(row["State"]) else ""),
            "ticket": norm(row["Order"]),
            "price": float(norm(row["Price"])),
        })
    out.sort(key=lambda r: (r["setup"], r["ticket"]))
    return out


def cycle_windows(deployments):
    spans = []
    for i, dep in enumerate(deployments):
        start = dep["when"]
        end = (deployments[i + 1]["when"] if i + 1 < len(deployments)
               else datetime(2099, 1, 1))
        spans.append((start, end, i + 1))
    return spans


def cycle_of(when, spans):
    for start, end, idx in spans:
        if start <= when < end:
            return idx
    return None


CODE = {"base": "B", "x2": "X"}
MARK = {"canceled": "c", "filled": "f", "placed": "w", "started": "w",
        "partial": "p", "rejected": "r", "expired": "e", "": "?"}


def chain_string(chain):
    return " ".join(
        f"{CODE.get(r['tag'], 'O')}{MARK.get(r['state'], '?')}" for r in chain
    )


def main() -> int:
    orders = load_orders()
    deployments = build_deployments(orders)
    spans = cycle_windows(deployments)
    rows = rows_for(orders)
    for row in rows:
        row["cycle"] = cycle_of(row["setup"], spans)
        row["tag"] = tier(row["volume"], row["level"])

    print("=== V10 PART A: per-level order chains at every rescued level ===")
    print("  population: every own-side lattice order in the cycle, at a level")
    print("  that received a 2x order in that cycle.  chain in time_setup order.")
    print("  legend  B=base X=2x O=other   c=canceled f=filled w=working")

    by_side = collections.defaultdict(list)
    for row in rows:
        if row["cycle"] is not None:
            by_side[(row["cycle"], row["is_buy"])].append(row)

    events = []
    for key in sorted(by_side, key=lambda k: (k[0], not k[1])):
        group = by_side[key]
        x2_levels = sorted({r["level"] for r in group if r["tag"] == "x2"})
        if not x2_levels:
            continue
        events.append((key, group, x2_levels))

    trans = collections.Counter()
    fills_of_intermediate = []
    lifetimes = []
    per_event = []
    for (cycle, is_buy), group, x2_levels in events:
        side = "buy " if is_buy else "sell"
        chains = {}
        for level in x2_levels:
            chain = sorted((r for r in group if r["level"] == level),
                           key=lambda r: (r["setup"], r["ticket"]))
            chains[level] = chain
        rt_base, rt_x2, x2_then_base = 0, 0, 0
        for level, chain in chains.items():
            for a, b in zip(chain, chain[1:]):
                trans[(a["tag"], a["state"], b["tag"])] += 1
                if a["tag"] == "base" and a["state"] == "canceled":
                    if b["tag"] == "base":
                        rt_base += 1
                    elif b["tag"] == "x2":
                        rt_x2 += 1
                if a["tag"] == "x2" and b["tag"] == "base":
                    x2_then_base += 1
            # intermediate = a base order that has a later 2x at the same level
            last_x2 = max((i for i, r in enumerate(chain)
                           if r["tag"] == "x2"), default=-1)
            for i, r in enumerate(chain):
                if i >= last_x2 or r["tag"] != "base":
                    continue
                if r["state"] == "filled":
                    fills_of_intermediate.append((cycle, side, level, r))
                if r["done"] is not None:
                    lifetimes.append((r["done"] - r["setup"]).total_seconds())
        per_event.append((cycle, side, len(x2_levels), rt_base, rt_x2,
                          x2_then_base))
        print(f"\n  cycle {cycle:4d}  {side}  rescued levels={len(x2_levels)}"
              f"  base->base round trips={rt_base}"
              f"  base->2x={rt_x2}  2x->base={x2_then_base}")
        for level in sorted(chains)[:6]:
            print(f"       L{level:2d}  {chain_string(chains[level])}")
        if len(chains) > 6:
            print(f"       ... {len(chains) - 6} more levels")

    print("\n=== V10 PART B: the divergence, quantified ===")
    tot_bb = sum(e[3] for e in per_event)
    tot_bx = sum(e[4] for e in per_event)
    tot_xb = sum(e[5] for e in per_event)
    print(f"  base-cancel -> base-replacement round trips : {tot_bb}")
    print(f"  base-cancel -> 2x-replacement round trips   : {tot_bx}")
    print(f"  2x -> base at the same level                : {tot_xb}")
    print("  the replica lands 2x on the FIRST replacement, so it predicts")
    print(f"  base->base = 0.  measured {tot_bb} => DIVERGENCE if > 0.")

    print("\n  can an intermediate base pending FILL?  (the economic question)")
    print(f"      intermediate base orders that FILLED: {len(fills_of_intermediate)}")
    for cycle, side, level, r in fills_of_intermediate[:12]:
        print(f"        cycle {cycle} {side} L{level:2d}  {r['setup']}"
              f"  vol {r['volume']:.2f}  #{r['ticket']}")
    if lifetimes:
        lifetimes.sort()
        n = len(lifetimes)
        print(f"      intermediate base pending lifetime  n={n}"
              f"  min={lifetimes[0]:.3f}s"
              f"  p50={lifetimes[n // 2]:.3f}s"
              f"  max={lifetimes[-1]:.3f}s")

    print("\n=== V10 PART C: transition census (tag,state) -> tag ===")
    for (ta, st, tb), n in sorted(trans.items(), key=lambda kv: -kv[1]):
        print(f"      {ta:>6s} {st:<9s} -> {tb:<6s}  n={n}")

    print("\n=== V10 PART D: the base RE-PLACEMENTS, properly scoped ===")
    print("  PART B's 'intermediate fills' counted the deployment leg itself,")
    print("  which is why the p50 lifetime was 10,228 s.  scope it correctly:")
    print("  a base RE-PLACEMENT is a base order whose immediate predecessor at")
    print("  the same level is a CANCELED base order.  those are the 85 orders")
    print("  the replica does not emit at all -- after TryCancelTrendRescueLevel")
    print("  the level carries volume=2x, rearm_requested=false and")
    print("  trend_rescue_replacement=true, so nothing re-places it at base.")
    repl = []
    for (cycle, is_buy), group, x2_levels in events:
        side = "buy " if is_buy else "sell"
        for level in x2_levels:
            chain = sorted((r for r in group if r["level"] == level),
                           key=lambda r: (r["setup"], r["ticket"]))
            for a, b in zip(chain, chain[1:]):
                if a["tag"] == "base" and a["state"] == "canceled" \
                        and b["tag"] == "base":
                    repl.append({
                        "cycle": cycle, "side": side, "level": level,
                        "gap": ((b["setup"] - a["done"]).total_seconds()
                                if a["done"] else None),
                        "life": ((b["done"] - b["setup"]).total_seconds()
                                 if b["done"] else None),
                        "state": b["state"], "ticket": b["ticket"],
                        "setup": b["setup"], "price_same":
                            abs(b["price"] - a["price"]) <= 1e-9,
                    })
    print(f"\n  base re-placements: {len(repl)}")
    states = collections.Counter(r["state"] for r in repl)
    for state, n in states.most_common():
        print(f"      final state {state:<10s} n={n}")
    print(f"      re-placed at the IDENTICAL price: "
          f"{sum(1 for r in repl if r['price_same'])}/{len(repl)}")
    gaps = sorted(r["gap"] for r in repl if r["gap"] is not None)
    lives = sorted(r["life"] for r in repl if r["life"] is not None)
    if gaps:
        print(f"      cancel->replace gap  n={len(gaps)}  min={gaps[0]:.3f}s"
              f"  p50={gaps[len(gaps) // 2]:.3f}s  max={gaps[-1]:.3f}s")
    if lives:
        print(f"      replacement lifetime n={len(lives)}  min={lives[0]:.3f}s"
              f"  p50={lives[len(lives) // 2]:.3f}s  max={lives[-1]:.3f}s")
    print("\n  THE ECONOMIC QUESTION: a filled base re-placement would be a")
    print("  position the replica never opens.  filled re-placements:"
          f" {states.get('filled', 0)}")
    for r in repl:
        if r["state"] == "filled":
            print(f"        cycle {r['cycle']} {r['side']} L{r['level']:2d}"
                  f"  {r['setup']}  #{r['ticket']}  life={r['life']}")

    print("\n  per-event round-trip depth (how many base orders before the 2x)")
    print("  cyc  side  levels  depth histogram (base orders preceding the 2x)")
    for (cycle, is_buy), group, x2_levels in events:
        side = "buy " if is_buy else "sell"
        hist = collections.Counter()
        for level in x2_levels:
            chain = sorted((r for r in group if r["level"] == level),
                           key=lambda r: (r["setup"], r["ticket"]))
            first_x2 = next((i for i, r in enumerate(chain)
                             if r["tag"] == "x2"), None)
            if first_x2 is None:
                continue
            hist[sum(1 for r in chain[:first_x2] if r["tag"] == "base")] += 1
        shape = "  ".join(f"{k}B x{v}" for k, v in sorted(hist.items()))
        print(f"  {cycle:4d} {side}  {len(x2_levels):5d}   {shape}")

    print("\n=== V10 PART E: phase-B ASCENDING invariant, tested PER PASS ===")
    print("  PlaceOneTrendRescueReplacement (StraddleEngine.mqh:2506) walks")
    print("  for(index=0; index<levels_per_side; index++) -- ASCENDING, the")
    print("  mirror of phase A's descending walk at :2481.  PART 3b's")
    print("  'imm_asc 5/7' concatenated every pass of an event into one run,")
    print("  the same artifact that made phase A read 2/7 before per-pass")
    print("  testing raised it to 40/40.  segment on a TIME gap (the pacer is")
    print(f"  0.102 s p50, 0.140 s p95) so the split is independent of the")
    print("  level order being tested -- non-circular.")
    tot_runs, tot_asc = 0, 0
    for (cycle, is_buy), group, x2_levels in events:
        side = "buy " if is_buy else "sell"
        x2 = sorted((r for r in group if r["tag"] == "x2"),
                    key=lambda r: (r["setup"], r["ticket"]))
        runs, current = [], []
        for row in x2:
            if current and (row["setup"] - current[-1]["setup"]
                            ).total_seconds() > PASS_GAP_S:
                runs.append(current)
                current = []
            current.append(row)
        if current:
            runs.append(current)
        asc = 0
        shapes = []
        for run in runs:
            levels = [r["level"] for r in run]
            if all(b > a for a, b in zip(levels, levels[1:])):
                asc += 1
            shapes.append(f"{levels[0]}-{levels[-1]}"
                          if len(levels) > 1 else f"{levels[0]}")
        tot_runs += len(runs)
        tot_asc += asc
        print(f"  {cycle:4d} {side}  2x={len(x2):3d}  passes={len(runs)}"
              f"  strictly ascending={asc}/{len(runs)}"
              f"  ranges={shapes[:8]}")
    print(f"\n  phase-B per-pass ascending total: {tot_asc}/{tot_runs}"
          f"   <== :2506 requires {tot_runs}/{tot_runs}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
