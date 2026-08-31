"""V4 measured on the TARGET tape, where the armed stop price is a literal.

Every prior V4 result was inferred from the 901018 report, which only ever shows
a position's FINAL S/L snapshot and forced correction (C)'s indirect estimator.
The Starwave export is stronger in exactly the place that matters: an SL exit is
an order with `reason == 4` (ORDER_REASON_SL) whose comment is `[sl <price>]`,
i.e. the server prints the stop level it actually had armed, to the cent, and
`position_id` joins it to the entry deal without any (time,volume,price) guessing.

The two-stage ratchet makes a falsifiable prediction about the LOCKED distance

    locked = dir * (armed_sl - open_price) / step

Activation at +2.0 steps sets sl = market -/+ 2.0*step, so locked == 0.00 at the
moment of arming.  While Stage 1 holds (profit in [2,3) steps) the stop trails at
2.0 steps, so locked = profit - 2.0 lies in [0,1).  At profit >= 3.0 steps Stage 2
tightens the trail to 1.0 step, so locked = profit - 1.0 jumps to >= 2.0.  The
band [1.0, 2.0) is therefore STRUCTURALLY UNREACHABLE -- it is not a soft
preference but an arithmetic consequence of the two distances being 2.0 and 1.0
with the switch at 3.0.  Mass inside it falsifies the model.

Independent second reading in the same run: the trail DISTANCE at the moment of
the exit,

    distance = dir * (high_water - armed_sl) / step

cannot be recovered without a tick-by-tick high-water mark, but its lower bound
can: the exit price itself is a point the market reached, so
dir*(exit - armed_sl) >= 0 must hold for every SL exit, and equality (to within
slippage) is what proves the exit was AT the armed stop rather than merely near it.
"""
from __future__ import annotations

import collections
import csv
import datetime as dt
import re
import statistics
from pathlib import Path

EA_MAGIC = 26011001
BURST_GAP_S = 2.0
MIN_LEGS = 10
ORDERS = Path("Starwave_60542_orders_history.csv")
DEALS = Path("Starwave_60542_full_history.csv")
SL_COMMENT = re.compile(r"^\[sl\s+([0-9.]+)\]$")
LEVEL_COMMENT = re.compile(r"^STR ([BS])(\d+)$")


def when_ms(text):
    value = int(float(text or 0))
    if value <= 0:
        return None
    return dt.datetime.fromtimestamp(value / 1000.0, tz=dt.timezone.utc).replace(tzinfo=None)


def load_orders():
    with ORDERS.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def lattice_rows(orders):
    rows = []
    for row in orders:
        if row["type"] not in ("4", "5"):
            continue
        if int(float(row["magic"] or 0)) != EA_MAGIC:
            continue
        match = LEVEL_COMMENT.match((row["comment"] or "").strip())
        if match is None:
            continue
        setup = when_ms(row["time_setup_msc"])
        if setup is None:
            continue
        rows.append({
            "setup": setup,
            "ticket": int(float(row["ticket"])),
            "position_id": int(float(row["position_id"] or 0)),
            "state": row["state"],
            "is_buy": match.group(1) == "B",
            "level": int(match.group(2)),
            "price": float(row["price_open"]),
        })
    rows.sort(key=lambda item: (item["setup"], item["ticket"]))
    return rows


def cycles(lattice):
    """Split the lattice into deployment bursts and solve each one's geometry.

    Geometry comes from the PAIR rule rather than consecutive differences: for
    level k the tape must satisfy B_k - S_k == 2*k*step, so every k present is an
    independent estimate of step and of the anchor (B_k + S_k)/2.  Disagreement
    between them would itself be a V1 failure, so the spread is reported.
    """
    groups, current = [], []
    for row in lattice:
        if current and (row["setup"] - current[-1]["setup"]).total_seconds() > BURST_GAP_S:
            if len(current) >= MIN_LEGS:
                groups.append(current)
            current = []
        current.append(row)
    if len(current) >= MIN_LEGS:
        groups.append(current)

    out = []
    for legs in groups:
        buys = {leg["level"]: leg["price"] for leg in legs if leg["is_buy"]}
        sells = {leg["level"]: leg["price"] for leg in legs if not leg["is_buy"]}
        steps, anchors = [], []
        for level in sorted(set(buys) & set(sells)):
            steps.append((buys[level] - sells[level]) / (2.0 * level))
            anchors.append((buys[level] + sells[level]) / 2.0)
        if not steps:
            continue
        out.append({
            "start": legs[0]["setup"],
            "end": legs[-1]["setup"],
            "legs": legs,
            "step": round(statistics.median(steps), 10),
            "step_spread": max(steps) - min(steps),
            "anchor": round(statistics.median(anchors), 10),
            "anchor_spread": max(anchors) - min(anchors),
            "n": max(max(buys, default=0), max(sells, default=0)),
        })
    return out


def load_entries():
    """position_id -> entry deal (open price, direction, time, volume)."""
    entries = {}
    with DEALS.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["entry"] != "0":                     # DEAL_ENTRY_IN
                continue
            pid = int(float(row["position_id"] or 0))
            if pid == 0 or int(float(row["magic"] or 0)) != EA_MAGIC:
                continue
            when = when_ms(row["time_msc"])
            if when is None:
                continue
            if pid not in entries or when < entries[pid]["opened"]:
                entries[pid] = {"opened": when, "price": float(row["price"]),
                                "is_buy": row["type"] == "0",
                                "volume": float(row["volume"])}
    return entries


def sl_exits(orders):
    """Every SL-closed order, carrying the ARMED stop parsed out of its comment."""
    out = []
    for row in orders:
        if row["reason"] != "4" or row["state"] != "4":
            continue
        match = SL_COMMENT.match((row["comment"] or "").strip())
        if match is None:
            continue
        out.append({
            "pid": int(float(row["position_id"] or 0)),
            "ticket": int(float(row["ticket"])),
            "when": when_ms(row["time_done_msc"]),
            "armed_sl": float(match.group(1)),
            "exit": float(row["price_open"]),
            "filling": row["type_filling"],
            "volume": float(row["volume_initial"]),
        })
    return out


def bucket(value):
    if value < -0.005:
        return "negative"
    if value < 0.005:
        return "0.00 exact"
    if value < 1.0:
        return "(0.00,1.00) stage-1"
    if value < 2.0:
        return "[1.00,2.00) FORBIDDEN"
    if value < 3.0:
        return "[2.00,3.00) stage-2"
    return ">=3.00 stage-2"


def main() -> int:
    orders = load_orders()
    lattice = lattice_rows(orders)
    spans = cycles(lattice)
    entries = load_entries()
    exits = sl_exits(orders)

    print(f"=== Starwave tape, magic {EA_MAGIC} ===")
    print(f"    lattice stops {len(lattice)}   deployment bursts {len(spans)}   "
          f"entry deals {len(entries)}   SL exits {len(exits)}")
    worst_step = max((c["step_spread"] for c in spans), default=0.0)
    worst_anchor = max((c["anchor_spread"] for c in spans), default=0.0)
    print(f"    V1 pair-rule residual across all bursts: step spread max "
          f"{worst_step:.10f}   anchor spread max {worst_anchor:.10f}")
    sizes = collections.Counter(c["n"] for c in spans)
    print(f"    lattice depth N per burst: "
          + "  ".join(f"N={k}:{v}" for k, v in sorted(sizes.items())))
    print(f"    step values seen: "
          + "  ".join(f"{v:.2f}" for v in sorted({round(c['step'], 2) for c in spans})))
    print()

    def cycle_of(when):
        found = None
        for span in spans:
            if span["start"] <= when:
                found = span
            else:
                break
        return found

    # Level identity per filled lattice order, so a lock can be attributed to a tier.
    level_of = {row["position_id"]: (row["is_buy"], row["level"])
                for row in lattice if row["state"] == "4" and row["position_id"]}

    locks, slippage, unmatched = [], [], 0
    for exit_row in exits:
        entry = entries.get(exit_row["pid"])
        if entry is None:
            unmatched += 1
            continue
        span = cycle_of(entry["opened"])
        if span is None:
            unmatched += 1
            continue
        direction = 1.0 if entry["is_buy"] else -1.0
        locked = direction * (exit_row["armed_sl"] - entry["price"]) / span["step"]
        locks.append({
            "pid": exit_row["pid"], "locked": locked, "step": span["step"],
            "level": level_of.get(exit_row["pid"], (entry["is_buy"], 0))[1],
            "is_buy": entry["is_buy"], "open": entry["price"],
            "sl": exit_row["armed_sl"], "exit": exit_row["exit"],
            "opened": entry["opened"], "closed": exit_row["when"],
        })
        slippage.append(direction * (exit_row["exit"] - exit_row["armed_sl"]))

    print("=== part 1: was the exit AT the armed stop? ===")
    print(f"    SL exits joined to an entry deal and a cycle: {len(locks)} "
          f"(unmatched {unmatched})")
    exact = sum(1 for value in slippage if abs(value) < 0.005)
    adverse = sum(1 for value in slippage if value < -0.005)
    favourable = sum(1 for value in slippage if value > 0.005)
    print(f"    exit == armed sl to the cent: {exact}/{len(slippage)} "
          f"({100.0*exact/max(1,len(slippage)):.2f}%)")
    print(f"    filled BEYOND the stop (slippage): {adverse}   "
          f"filled short of it: {favourable}")
    if slippage:
        ordered = sorted(slippage)
        print(f"    signed distance exit-minus-stop: min {ordered[0]:+.2f}  "
              f"p50 {ordered[len(ordered)//2]:+.2f}  max {ordered[-1]:+.2f}")
    fillings = collections.Counter(row["filling"] for row in exits)
    print(f"    type_filling on SL closes: "
          + "  ".join(f"{k}={v}" for k, v in sorted(fillings.items()))
          + "   (0=FOK 1=IOC 2=RETURN)")
    print()

    print("=== part 2: the LOCKED distribution -- is [1.00,2.00) structurally empty? ===")
    census: collections.Counter = collections.Counter(bucket(row["locked"]) for row in locks)
    order = ["negative", "0.00 exact", "(0.00,1.00) stage-1", "[1.00,2.00) FORBIDDEN",
             "[2.00,3.00) stage-2", ">=3.00 stage-2"]
    for key in order:
        if census[key]:
            print(f"    {key:24s} {census[key]:5d}  "
                  f"({100.0*census[key]/max(1,len(locks)):6.2f}%)")
    forbidden = census["[1.00,2.00) FORBIDDEN"]
    print(f"    => forbidden-band occupancy {forbidden}/{len(locks)} = "
          f"{100.0*forbidden/max(1,len(locks)):.2f}%   "
          f"(the two-stage model requires ~0%)")
    if locks:
        values = sorted(row["locked"] for row in locks)
        print(f"    locked steps: min {values[0]:+.4f}  p05 {values[int(0.05*len(values))]:+.4f}  "
              f"p50 {values[len(values)//2]:+.4f}  p95 {values[int(0.95*len(values))]:+.4f}  "
              f"max {values[-1]:+.4f}")
    print()

    print("=== part 3: fine histogram of locked, 0.10-step resolution over [-1,4] ===")
    fine: collections.Counter = collections.Counter()
    for row in locks:
        fine[round(row["locked"] // 0.1 * 0.1, 1)] += 1
    for edge in [round(-1.0 + 0.1 * i, 1) for i in range(51)]:
        count = fine.get(edge, 0)
        flag = "  <== FORBIDDEN" if 1.0 <= edge < 2.0 else ""
        if count or (1.0 <= edge < 2.0):
            print(f"    [{edge:+.1f},{edge+0.1:+.1f})  {count:5d}  "
                  + "#" * min(60, count) + flag)
    tail = sum(v for k, v in fine.items() if k >= 4.0)
    if tail:
        print(f"    [+4.0, inf)      {tail:5d}")
    print()

    print("=== part 4: negative locks -- the AGGRESSIVE_30 anomaly, re-tested here ===")
    negatives = sorted((row for row in locks if row["locked"] < -0.005),
                       key=lambda item: item["locked"])
    print(f"    positions whose armed stop was WORSE than their open price: "
          f"{len(negatives)}/{len(locks)}"
          f"   [901018 AGGRESSIVE_30 comparison: 9/29, min -7.18]")
    for row in negatives[:20]:
        print(f"      #{row['pid']:<10d} {'B' if row['is_buy'] else 'S'}{row['level']:<3d} "
              f"step {row['step']:.2f}  open {row['open']:9.2f}  armed sl {row['sl']:9.2f}  "
              f"locked {row['locked']:+8.4f}  opened {row['opened']}")
    print()

    print("=== part 5: locked by tier, to see whether the ratchet is lot-independent ===")
    per_tier: dict[str, list] = collections.defaultdict(list)
    for row in locks:
        level = row["level"]
        tier = "L1-10" if level <= 10 else "L11-20" if level <= 20 else "L21-30"
        per_tier[tier].append(row["locked"])
    for tier in ("L1-10", "L11-20", "L21-30"):
        values = sorted(per_tier.get(tier, []))
        if not values:
            continue
        forbidden = sum(1 for v in values if 1.0 <= v < 2.0)
        print(f"    {tier:7s} n={len(values):5d}  p05 {values[int(0.05*len(values))]:+.3f}  "
              f"p50 {values[len(values)//2]:+.3f}  p95 {values[int(0.95*len(values))]:+.3f}  "
              f"forbidden {forbidden}")
    print()
    reference_point_test(locks, lattice, spans, entries)
    return 0


def reference_point_test(locks, lattice, spans, entries):
    """Which price does the ratchet measure from -- the FILL or the lattice price?

    1.91% occupancy of a band the model calls unreachable is either a real third
    behaviour or a measurement offset, and there is exactly one offset available:
    a stop order fills AT OR BEYOND its price, so open = lattice + dir*slip with
    slip >= 0.  Measuring `locked` from the fill price therefore understates it by
    slip/step relative to a ratchet that measures from the lattice price.  Both
    readings are computed on the same positions, so whichever empties the
    forbidden band identifies the Target's reference point -- and that is a
    checkable property of the replica's StopScheduler, not a matter of taste.
    """
    price_of = {row["position_id"]: row["price"]
                for row in lattice if row["state"] == "4" and row["position_id"]}
    rows, slips = [], []
    for row in locks:
        lattice_price = price_of.get(row["pid"])
        if lattice_price is None:
            continue
        direction = 1.0 if row["is_buy"] else -1.0
        slip = direction * (row["open"] - lattice_price)
        alt = direction * (row["sl"] - lattice_price) / row["step"]
        rows.append({**row, "lattice": lattice_price, "slip": slip, "alt": alt})
        slips.append(slip)

    print("=== part 6: fill price vs lattice price as the ratchet's reference ===")
    ordered = sorted(slips)
    print(f"    entry slippage dir*(fill - lattice), n={len(ordered)}: "
          f"min {ordered[0]:+.2f}  p50 {ordered[len(ordered)//2]:+.2f}  "
          f"p95 {ordered[int(0.95*len(ordered))]:+.2f}  max {ordered[-1]:+.2f}")
    negative_slip = sum(1 for value in slips if value < -0.005)
    print(f"    fills BETTER than the stop price (should be impossible): {negative_slip}")
    for label, key in (("from FILL price   ", "locked"), ("from LATTICE price", "alt")):
        forbidden = sum(1 for row in rows if 1.0 <= row[key] < 2.0)
        negative = sum(1 for row in rows if row[key] < -0.005)
        at_zero = sum(1 for row in rows if abs(row[key]) < 0.005)
        print(f"    {label}: forbidden-band {forbidden:4d}/{len(rows)} "
              f"({100.0*forbidden/max(1,len(rows)):5.2f}%)   "
              f"negative {negative:3d}   exactly 0.00 {at_zero:4d}")
    print()

    print("    the 25 forbidden-band cases under both readings, worst slip first:")
    print("      pid          side lvl  step   lattice    fill      slip   "
          "armed sl   locked(fill)  locked(lattice)")
    band = [row for row in rows if 1.0 <= row["locked"] < 2.0]
    for row in sorted(band, key=lambda item: -item["slip"]):
        print(f"      #{row['pid']:<11d} {'B' if row['is_buy'] else 'S'}{row['level']:<3d} "
              f"{row['step']:5.2f} {row['lattice']:9.2f} {row['open']:9.2f} "
              f"{row['slip']:+7.2f} {row['sl']:10.2f}   {row['locked']:+11.4f}  "
              f"{row['alt']:+14.4f}")
    print()
    fixed = sum(1 for row in band if not (1.0 <= row["alt"] < 2.0))
    print(f"    => {fixed} of {len(band)} forbidden cases leave the band when measured "
          f"from the lattice price")
    burst_contamination(rows, spans)


def burst_contamination(rows, spans):
    """The competing explanation: bursts whose own geometry is inconsistent.

    The pair rule gives one (anchor, step) estimate per level present.  A pure
    deployment must return the same numbers from every level; a burst that the
    2 s grouping merged with re-arms carrying a PREVIOUS cycle's prices will not.
    If the forbidden cases sit in inconsistent bursts, the band is a geometry
    artifact rather than a behaviour.
    """
    by_start = {span["start"]: span for span in spans}

    def span_for(when):
        found = None
        for span in spans:
            if span["start"] <= when:
                found = span
            else:
                break
        return found

    clean_forbidden = dirty_forbidden = clean_total = dirty_total = 0
    for row in rows:
        span = span_for(row["opened"])
        if span is None:
            continue
        dirty = span["step_spread"] > 1e-9 or span["anchor_spread"] > 1e-9
        in_band = 1.0 <= row["locked"] < 2.0
        if dirty:
            dirty_total += 1
            dirty_forbidden += in_band
        else:
            clean_total += 1
            clean_forbidden += in_band
    consistent = sum(1 for span in spans
                     if span["step_spread"] <= 1e-9 and span["anchor_spread"] <= 1e-9)
    print()
    print("=== part 7: is the band a burst-geometry artifact instead? ===")
    print(f"    bursts whose pair-rule geometry is self-consistent: "
          f"{consistent}/{len(spans)}")
    print(f"    SL exits from CONSISTENT bursts:   {clean_total:5d}  "
          f"forbidden {clean_forbidden:4d} ({100.0*clean_forbidden/max(1,clean_total):5.2f}%)")
    print(f"    SL exits from INCONSISTENT bursts: {dirty_total:5d}  "
          f"forbidden {dirty_forbidden:4d} ({100.0*dirty_forbidden/max(1,dirty_total):5.2f}%)")
    assert by_start is not None


if __name__ == "__main__":
    raise SystemExit(main())
