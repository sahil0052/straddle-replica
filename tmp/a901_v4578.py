"""Per-era V4 / V5 / V7 / V8 audit of the ReportHistory-901018 tape.

Everything here is scored under the profile that was actually running, because
the tape is five configurations, not one.  Vectors:

  V4  two-stage trailing ratchet -- locked = dir*(sl - open)/step must fall in
      [0,1) (Stage 1, trail 2 steps) or [2,inf) (Stage 2, trail 1 step), with
      the band [1,2) structurally EMPTY.  Scored with each cycle's own step over
      every position that carries an S/L -- see (C) below.
  V5  basket liquidation -- cancel-before-close adherence, strict reverse-ticket
      LIFO inside each sweep, and the inter-close cadence.
  V7  basket money exit -- what the cycle had realized when the sweep fired.
  V8  restart floor -- gap from the sweep's last close to the next deployment.

The sweep marker is build-dependent (DIV-3): an EMPTY comment before the
2026.07.13 12:28 changeover and "STR CLOSE" after it.  Both are handled.

THREE MEASUREMENT CORRECTIONS ARE BAKED IN, all self-caught, and all of them
move the numbers this file printed on its first pass.

(A) close_price == S/L DOES NOT IDENTIFY SL EXITS ON THIS TAPE.  Only 1,856 of
    the 14,913 S/L-carrying positions close exactly on the stop, against 13,872
    closing deals commented "[sl <price>]".  Stop fills slip: dir*(close - sl)
    has p50 -0.05, p25 -0.13, p01 -0.77, min -14.03.  The discriminator here is
    therefore dir*(close - sl) <= 0, "filled at or worse than the stop".  On
    this tape it captures 13,680 of the 13,872 [sl] closes (98.62%) with ZERO
    false positives, which the closing-comment census proves outright:
        17,632 positions = 13,872 [sl] + 3,760 other
         3,760 other     =  2,719 blank S/L + 1,041 S/L closed on the good side
    so exact(1,856) + short(11,824) = 13,680 is exactly the [sl] family, and the
    192 rows it misses are [sl] closes that filled BETTER than their own stop.
    Exact equality would have discarded 86.6% of the population.

(B) MOST CLOSE BURSTS ARE NOT TERMINAL BASKET SWEEPS.  STARWAVE_30 shows 386
    close bursts against 101 deployments, 316 of them singletons (~3.8 bursts
    per cycle).  Scoring cancel-before-close or the restart floor over every
    burst answers the wrong question -- it asks "was the lattice cancelled
    before this close?" of closes that were never basket exits at all.  The
    TERMINAL sweep of a cycle is defined here as the LAST close burst before the
    next deployment starts.  V5/V7/V8 are scored on those; the interim bursts
    are reported separately, because under the Target's orphan leak they are the
    expected signature of partial or aborted sweeps (audit item D8).

(C) THE DIRECT TRAILING-DISTANCE ESTIMATOR dir*(close - sl)/step IS INVALID and
    is deliberately not computed here.  The stop only ratchets favourably
    against the high-water excursion while a sweep closes at CURRENT market, so
    that ratio is D*step minus the pullback (smeared down), and a stale stop
    smears it up; measured on STARWAVE_30, where D can only be 1.0 or 2.0, it
    runs to 27.6.  The valid instrument is locked = dir*(sl - open)/step, a
    property of stop PLACEMENT rather than of the fill, scored over every
    S/L-carrying position -- exit type cannot inform where the stop was written.
"""
from __future__ import annotations

import collections
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from a901_eras import BOUNDS, SIGNATURE, norm, parse_level, parse_volume, stamp  # noqa: E402,F401

BURST_GAP_MS = 2000.0
MIN_LEGS = 10
CLOSE_BURST_GAP_S = 2.0
ERA_ORDER = ["HISTORICAL_50", "HISTORICAL_60", "AGGRESSIVE_30", "LOW_RISK_30", "STARWAVE_30"]


def pct(values, q):
    if not values:
        return float("nan")
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round(q * (len(ordered) - 1)))))
    return ordered[index]


def eras_present(mapping):
    return [e for e in ERA_ORDER if e in mapping] + [
        e for e in mapping if e not in ERA_ORDER
    ]


def load_orders():
    return list(csv.DictReader(Path("tmp/r901018_orders.csv").open(encoding="utf-8")))


def load_deals():
    return list(csv.DictReader(Path("tmp/r901018_deals.csv").open(encoding="utf-8")))
def load_positions():
    """The Positions table repeats 'Time' and 'Price', so read it positionally."""
    rows = []
    with Path("tmp/r901018_positions.csv").open(encoding="utf-8") as handle:
        reader = csv.reader(handle)
        next(reader)
        for row in reader:
            if len(row) < 13 or not norm(row[1]):
                continue
            opened = stamp(row[0])
            closed = stamp(row[8])
            if opened is None or closed is None:
                continue
            rows.append({
                "opened": opened,
                "ticket": int(norm(row[1])),
                "is_buy": norm(row[3]) == "buy",
                "volume": float(norm(row[4])),
                "open_price": float(norm(row[5])),
                "sl": float(norm(row[6])) if norm(row[6]) else 0.0,
                "tp": float(norm(row[7])) if norm(row[7]) else 0.0,
                "closed": closed,
                "close_price": float(norm(row[9])),
                "profit": float(norm(row[12])),
            })
    rows.sort(key=lambda item: (item["closed"], item["ticket"]))
    return rows


def is_sl_exit(row) -> bool:
    """Filled AT OR WORSE than the recorded stop.  Correction (A) in the header:
    exact close==sl catches only 13.4% of this tape's stop exits, this catches
    98.62% of them with no false positives."""
    if row["sl"] == 0.0:
        return False
    direction = 1.0 if row["is_buy"] else -1.0
    return direction * (row["close_price"] - row["sl"]) <= 1e-9
def build_deployments(orders):
    """Same clustering as a901_eras.py: lattice pendings, 2 s gap, >=10 legs."""
    rows = []
    for row in orders:
        parsed = parse_level(row["Comment"])
        when = stamp(row["Open Time"])
        if parsed is None or when is None:
            continue
        rows.append({
            "when": when,
            "is_buy": parsed[0],
            "level": parsed[1],
            "price": float(norm(row["Price"])),
            "volume": parse_volume(row["Volume"]),
            "ticket": norm(row["Order"]),
            "state": norm(row["State"]).split()[0].lower() if norm(row["State"]) else "",
            "resolved": stamp(row["Time"]),
        })
    rows.sort(key=lambda item: (item["when"], item["ticket"]))

    clusters = []
    current = []
    for row in rows:
        if current and (row["when"] - current[-1]["when"]).total_seconds() * 1000.0 > BURST_GAP_MS:
            clusters.append(current)
            current = []
        current.append(row)
    if current:
        clusters.append(current)

    # -----------------------------------------------------------------------
    # DEPLOYMENT PREDICATE.  The first version of this function demanded that a
    # burst contain BOTH B1 and S1, because it recovered the geometry from that
    # one pair.  On the 901018 tape that threw away real deployments wholesale:
    # the HISTORICAL_60 window holds 75 near-complete lattices (7x120, 60x119,
    # 7x118, 1x115 legs) and only 7 survived -- 43 were missing B1 and 40 were
    # missing S1, because level 1 is the closest pending to the anchor and is
    # routinely FILLED during the deployment burst itself, so it never reaches
    # the canceled/working population the burst is reconstructed from.
    #
    # Replaced by two intrinsic tests plus a k-agnostic geometry recovery:
    #
    #   1. >= MIN_LEGS legs, as before.
    #   2. DENSITY: the burst must cover >= 80% of the (side,level) slots its
    #      own span implies -- slots / (2 * max_level) >= 0.80.  This needs no
    #      prior N, and it is what separates a lattice deployment from a re-arm
    #      trickle: 120 legs spanning 60 levels scores 1.00, while 12 re-arms
    #      scattered over the same 60 levels score 0.10.  A deployment aborted
    #      part-way (30 legs to level 15) still scores 1.00 and is still a
    #      deployment -- it fixes an anchor and a step and it starts a cycle.
    #   3. GEOMETRY from ANY concordant (Bk,Sk) pair, not just k=1:
    #           anchor = (bk + sk) / 2        (exact for every k)
    #           step   = (bk - sk) / (2k)     (error divided by k, so take max k)
    #      Density >= 0.80 guarantees a concordant pair exists: each side holds
    #      at most max_level slots, so slots >= 1.6*max_level forces both sides
    #      above 0.6*max_level and at least 0.2*max_level levels overlap.
    # -----------------------------------------------------------------------
    records = []
    for cluster in clusters:
        if len(cluster) < MIN_LEGS:
            continue
        top = max(r["level"] for r in cluster)
        slots = {(r["is_buy"], r["level"]) for r in cluster}
        if top <= 0 or len(slots) < 0.80 * 2 * top:
            continue
        buys = {r["level"]: r["price"] for r in cluster if r["is_buy"]}
        sells = {r["level"]: r["price"] for r in cluster if not r["is_buy"]}
        shared = sorted(set(buys) & set(sells))
        if not shared:
            continue
        k = shared[-1]
        anchors = [(buys[j] + sells[j]) / 2.0 for j in shared]
        records.append({
            "when": cluster[0]["when"],
            "end": cluster[-1]["when"],
            "legs": len(cluster),
            "n": top,
            "anchor": (buys[k] + sells[k]) / 2.0,
            "step": (buys[k] - sells[k]) / (2.0 * k),
            "pair_k": k,
            "anchor_spread": max(anchors) - min(anchors),
            "density": len(slots) / (2.0 * top),
            "tiers": tuple(sorted({r["volume"] for r in cluster})),
            "cluster": cluster,
        })
    last_full = None
    for record in records:
        name = SIGNATURE.get((record["n"], record["tiers"]), (None, None))[0]
        if name is not None:
            last_full = name
        record["assigned"] = last_full
        record["inherited"] = name is None
    return records
def build_sweeps(orders):
    """Close-family market orders, burst-grouped.  Marker is build-dependent."""
    closes = []
    for row in orders:
        comment = norm(row["Comment"])
        when = stamp(row["Open Time"])
        if when is None or norm(row["Type"]) not in ("buy", "sell"):
            continue
        if comment == "":
            marker = "<empty>"
        elif comment == "STR CLOSE":
            marker = "STR CLOSE"
        else:
            continue
        closes.append({"when": when, "marker": marker, "ticket": norm(row["Order"])})
    closes.sort(key=lambda item: (item["when"], item["ticket"]))

    sweeps = []
    current = []
    for row in closes:
        if current and (row["when"] - current[-1]["when"]).total_seconds() > CLOSE_BURST_GAP_S:
            sweeps.append(current)
            current = []
        current.append(row)
    if current:
        sweeps.append(current)
    return sweeps


def cancel_times(orders):
    """(cancel time) for every lattice pending the terminal reports as canceled."""
    out = []
    for row in orders:
        if "cancel" not in norm(row["State"]).lower():
            continue
        if parse_level(row["Comment"]) is None:
            continue
        when = stamp(row["Time"])
        if when is not None:
            out.append(when)
    out.sort()
    return out
def classify_sweeps(sweeps, deployments):
    """Correction (B): the TERMINAL sweep of a cycle is its LAST close burst
    before the next deployment starts.  Everything else that cycle fired is
    interim -- a partial or aborted close, which is what the orphan leak
    predicts and what D8 has to account for."""
    starts = [record["when"] for record in deployments]
    grouped = collections.defaultdict(list)
    for sweep in sweeps:
        first = sweep[0]["when"]
        index = -1
        for i, when in enumerate(starts):
            if when <= first:
                index = i
            else:
                break
        grouped[index].append(sweep)

    terminal, interim = [], []
    for index, bursts in grouped.items():
        bursts.sort(key=lambda burst: burst[0]["when"])
        cycle = deployments[index] if index >= 0 else None
        for burst in bursts[:-1]:
            interim.append((burst, cycle))
        terminal.append((bursts[-1], cycle))
    terminal.sort(key=lambda item: item[0][0]["when"])
    interim.sort(key=lambda item: item[0][0]["when"])
    silent = [i for i in range(len(deployments)) if i not in grouped]
    return terminal, interim, silent
def new_bucket():
    return {
        "sweeps": 0, "orders": 0, "one_leg": 0, "cancel_ok": 0,
        "lifo_pairs": 0, "lifo_ok": 0, "lifo_tied": 0,
        "lifo_sweeps": 0, "lifo_clean": 0,
        "gaps": [], "matched": 0, "sl_inside": 0,
        "realized": [], "pre_realized": [], "restart": [], "legs": [],
    }


def score(labelled, positions, cancels, starts):
    """Accumulate V5/V7/V8 over a list of (burst, cycle) pairs."""
    per_era = collections.defaultdict(new_bucket)
    for sweep, cycle in labelled:
        first, last = sweep[0]["when"], sweep[-1]["when"]
        era = str(cycle["assigned"]) if cycle else "before-first-deployment"
        bucket = per_era[era]
        bucket["sweeps"] += 1
        bucket["orders"] += len(sweep)
        bucket["legs"].append(len(sweep))
        if len(sweep) == 1:
            bucket["one_leg"] += 1

        # cancel_before_close: a lattice pending cancelled in the 10 s window
        # that ends at this sweep's first close.
        window_lo = first.timestamp() - 10.0
        if any(window_lo <= when.timestamp() <= first.timestamp() for when in cancels):
            bucket["cancel_ok"] += 1

        for a, b in zip(sweep, sweep[1:]):
            bucket["gaps"].append((b["when"] - a["when"]).total_seconds() * 1000.0)

        # LIFO over the positions that closed inside the burst window, with stop
        # exits removed by the corrected discriminator.
        closed_here = []
        for row in positions:
            if row["closed"] < first:
                continue
            if row["closed"] > last:
                break
            if is_sl_exit(row):
                bucket["sl_inside"] += 1
                continue
            closed_here.append(row)
        bucket["matched"] += len(closed_here)
        order = sorted(closed_here, key=lambda item: (item["closed"], -item["ticket"]))
        pairs = list(zip(order, order[1:]))
        tied = sum(1 for a, b in pairs if a["closed"] == b["closed"])
        good = sum(1 for a, b in pairs
                   if a["closed"] != b["closed"] and b["ticket"] < a["ticket"])
        bucket["lifo_pairs"] += len(pairs) - tied
        bucket["lifo_ok"] += good
        bucket["lifo_tied"] += tied
        if len(pairs) - tied > 0:
            bucket["lifo_sweeps"] += 1
            if good == len(pairs) - tied:
                bucket["lifo_clean"] += 1

        if cycle is not None:
            bucket["realized"].append(sum(
                row["profit"] for row in positions
                if cycle["when"] <= row["closed"] <= last))
            bucket["pre_realized"].append(sum(
                row["profit"] for row in positions
                if cycle["when"] <= row["closed"] < first))

        nxt = next((when for when in starts if when > last), None)
        if nxt is not None:
            bucket["restart"].append((nxt - last).total_seconds())
    return per_era
def print_v5(per_era, title):
    print(f"=== V5 basket liquidation -- {title} ===")
    for era in eras_present(per_era):
        b = per_era[era]
        cancel_pct = 100.0 * b["cancel_ok"] / b["sweeps"] if b["sweeps"] else 0.0
        lifo_pct = 100.0 * b["lifo_ok"] / b["lifo_pairs"] if b["lifo_pairs"] else 0.0
        print(f"  {era:14s} sweeps={b['sweeps']:4d} close_orders={b['orders']:5d} "
              f"singletons={b['one_leg']:4d} matched_positions={b['matched']:5d} "
              f"sl_inside={b['sl_inside']:5d}")
        print(f"      cancel_before_close={b['cancel_ok']}/{b['sweeps']} "
              f"({cancel_pct:6.2f}%)   "
              f"LIFO pairs={b['lifo_ok']}/{b['lifo_pairs']} ({lifo_pct:6.2f}%) "
              f"tied={b['lifo_tied']}  clean={b['lifo_clean']}/{b['lifo_sweeps']}")
        if b["gaps"]:
            print(f"      inter-close ms  p05={pct(b['gaps'],0.05):7.1f} "
                  f"p50={pct(b['gaps'],0.50):7.1f} p95={pct(b['gaps'],0.95):7.1f} "
                  f"min={min(b['gaps']):7.1f} n={len(b['gaps'])}")
        if b["legs"]:
            print(f"      legs per sweep  p05={pct(b['legs'],0.05):4.0f} "
                  f"p50={pct(b['legs'],0.50):4.0f} p95={pct(b['legs'],0.95):4.0f} "
                  f"max={max(b['legs']):4d}")
    print()


def print_v7(per_era, title):
    print(f"=== V7 cycle realized at sweep completion -- {title} ===")
    for era in eras_present(per_era):
        values = per_era[era]["realized"]
        pre = per_era[era]["pre_realized"]
        if not values:
            continue
        print(f"  {era:14s} n={len(values):4d} p05={pct(values,0.05):9.2f} "
              f"p25={pct(values,0.25):9.2f} p50={pct(values,0.50):9.2f} "
              f"p75={pct(values,0.75):9.2f} p95={pct(values,0.95):9.2f} "
              f"min={min(values):9.2f} max={max(values):9.2f}")
        print(f"      negative={sum(1 for v in values if v < 0.0)}  "
              f">=25={sum(1 for v in values if v >= 25.0)} "
              f">=20={sum(1 for v in values if v >= 20.0)} "
              f">=10={sum(1 for v in values if v >= 10.0)}   "
              f"pre-sweep realized p50={pct(pre,0.50):9.2f}")
    print()


def print_v8(per_era, title):
    print(f"=== V8 restart interval (sweep last close -> next deployment) -- {title} ===")
    for era in eras_present(per_era):
        allv = per_era[era]["restart"]
        if not allv:
            continue
        values = [v for v in allv if v <= 600.0]
        print(f"  {era:14s} n={len(allv):4d} "
              f">=2.0s={sum(1 for v in allv if v >= 2.0)} "
              f"in[2,3)={sum(1 for v in allv if 2.0 <= v < 3.0)} "
              f"min={min(allv):8.3f}")
        if values:
            print(f"      <=600s subset n={len(values):4d} p05={pct(values,0.05):8.3f} "
                  f"p50={pct(values,0.50):8.3f} p95={pct(values,0.95):8.3f}")
    print()
def main() -> int:
    orders = load_orders()
    positions = load_positions()
    deployments = build_deployments(orders)
    sweeps = build_sweeps(orders)
    cancels = cancel_times(orders)
    starts = [record["when"] for record in deployments]

    terminal, interim, silent = classify_sweeps(sweeps, deployments)
    print(f"deployments={len(deployments)} close_bursts={len(sweeps)} "
          f"terminal_sweeps={len(terminal)} interim_bursts={len(interim)} "
          f"cycles_with_no_close={len(silent)} positions={len(positions)} "
          f"canceled_pendings={len(cancels)}")
    print("  (terminal sweep = the last close burst before the next deployment; "
          "correction (B))")
    print()

    per_era = score(terminal, positions, cancels, starts)
    print_v5(per_era, "TERMINAL sweeps only")
    print_v7(per_era, "TERMINAL sweeps only")
    print_v8(per_era, "TERMINAL sweeps only")

    per_interim = score(interim, positions, cancels, starts)
    print_v5(per_interim, "INTERIM bursts (D8 leak / partial-abort evidence)")
    print_v7(per_interim, "INTERIM bursts (D8 leak / partial-abort evidence)")

    def cycle_of(when):
        chosen = None
        for record in deployments:
            if record["when"] <= when:
                chosen = record
            else:
                break
        return chosen

    # ---- V4 -----------------------------------------------------------------
    print("=== V4 two-stage ratchet: locked = dir*(sl-open)/step ===")
    print("  population = EVERY position carrying an S/L (stop PLACEMENT, so the "
          "exit type is irrelevant -- correction (C))")
    keys = ["<0", "[0,1)", "[1.00,1.98)", "[1.98,2.00)", "[2,3)", "[3,4)", "[4,inf)"]

    def band_of(locked):
        if locked < -1e-9:
            return "<0"
        if locked < 1.0:
            return "[0,1)"
        if locked < 1.98:
            return "[1.00,1.98)"
        if locked < 2.0 - 1e-9:
            return "[1.98,2.00)"
        if locked < 3.0:
            return "[2,3)"
        if locked < 4.0:
            return "[3,4)"
        return "[4,inf)"

    for label, only_sl in (("all S/L-carrying positions", False),
                           ("stop exits only (dir*(close-sl)<=0)", True)):
        bands = collections.defaultdict(collections.Counter)
        totals = collections.Counter()
        no_step = 0
        for row in positions:
            if row["sl"] == 0.0:
                continue
            if only_sl and not is_sl_exit(row):
                continue
            cycle = cycle_of(row["opened"])
            if cycle is None or cycle["step"] <= 0.0:
                no_step += 1
                continue
            era = str(cycle["assigned"])
            direction = 1.0 if row["is_buy"] else -1.0
            locked = direction * (row["sl"] - row["open_price"]) / cycle["step"]
            bands[era][band_of(locked)] += 1
            totals[era] += 1
        print(f"  -- {label}")
        print("  era            " + "".join(f"{k:>13s}" for k in keys) + "       n")
        for era in eras_present(totals):
            print(f"  {era:14s} "
                  + "".join(f"{bands[era].get(k,0):13d}" for k in keys)
                  + f"{totals[era]:8d}")
        for era in eras_present(totals):
            if not totals[era]:
                continue
            strict = bands[era].get("[1.00,1.98)", 0)
            wall = bands[era].get("[1.98,2.00)", 0)
            print(f"      {era:14s} strict trough {strict}/{totals[era]} = "
                  f"{100.0*strict/totals[era]:5.2f}%   boundary [1.98,2.00) {wall}"
                  f"   (a single-stage 1-step trail would fill ~33%)")
        print(f"      (positions with no resolvable cycle step: {no_step})")
    print()
    # ---- D8: positions that outlived their own cycle -------------------------
    print("=== D8 orphan residue: positions still open when the NEXT cycle "
          "deployed ===")
    index_of = {record["when"]: i for i, record in enumerate(deployments)}
    survived = collections.defaultdict(collections.Counter)
    outlived_cycles = collections.defaultdict(list)
    totals = collections.Counter()
    for row in positions:
        cycle = cycle_of(row["opened"])
        if cycle is None:
            continue
        era = str(cycle["assigned"])
        totals[era] += 1
        i = index_of[cycle["when"]]
        crossed = sum(1 for when in starts[i + 1:] if when < row["closed"])
        if crossed:
            survived[era][min(crossed, 5)] += 1
            outlived_cycles[era].append(crossed)
    print("  era                n   outlived  %      crossed 1    2    3    4   5+"
          "   max")
    for era in eras_present(totals):
        counter = survived[era]
        out = sum(counter.values())
        worst = max(outlived_cycles[era]) if outlived_cycles[era] else 0
        print(f"  {era:14s} {totals[era]:6d} {out:6d}  {100.0*out/max(1,totals[era]):5.2f}%"
              f"        {counter.get(1,0):6d}{counter.get(2,0):5d}"
              f"{counter.get(3,0):5d}{counter.get(4,0):5d}{counter.get(5,0):5d}"
              f"{worst:6d}")
    print()

    # ---- position / deal fold ----------------------------------------------
    print("=== position close-event fold ===")
    key_hist = collections.Counter(
        (row["closed"], row["volume"], row["close_price"]) for row in positions
    )
    collisions = {k: v for k, v in key_hist.items() if v > 1}
    print(f"  positions={len(positions)} distinct (close_time,volume,price) keys="
          f"{len(key_hist)} colliding keys={len(collisions)} "
          f"extra rows={sum(v-1 for v in collisions.values())}")
    exact = sum(1 for r in positions if r["sl"] != 0.0
                and abs(r["close_price"] - r["sl"]) < 5e-9)
    stopped = sum(1 for r in positions if is_sl_exit(r))
    print(f"  stop exits by dir*(close-sl)<=0: {stopped}   of which exactly on "
          f"the stop: {exact}   ({100.0*exact/max(1,stopped):5.2f}%)")
    print(f"  blank SL={sum(1 for r in positions if r['sl']==0.0)}  "
          f"any TP={sum(1 for r in positions if r['tp']!=0.0)}  "
          f"non-stop exits={len(positions)-stopped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
