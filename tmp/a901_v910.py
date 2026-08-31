"""V9/V10 -- lot-tier population scoping, and the trend-rescue mechanism.

Two questions, one instrument, because they share a population.

V9 scored 25,447/25,447 lattice legs at their configured tier lot.  That
figure comes from `build_deployments()`, which only admits a burst that is
a 2 s-gap cluster of >=10 legs at >=0.80 slot density -- i.e. a DEPLOYMENT.
`ProfileCatalog.mqh:445-446` records 125 orders placed at 2x the tier lot
in the final regime.  If both are true, the 2x orders must live OUTSIDE
every deployment cluster.  PART 1 measures that instead of assuming it.

V10 is then a positive verification of an ACTIVE mechanism.  From source
(`StraddleEngine.mqh:2630-2675`) the rescue is a two-phase, one-side,
one-order-per-tick replacement:

    ProcessTrendRescue()
      trigger  = TrendRescueSide()               :2384-2404
                 floating <= -drawdown_money AND
                 (ask - iClose(tf,bars) >= move_price  -> +1) or
                 (iClose(tf,bars) - bid >= move_price  -> -1)
      refuse   same side twice until a side==0 tick clears it   :2635-2643
      require  HasTrendRescueBasePending(side)                  :2644
      phase A  TryCancelOneTrendRescueOrder  DESCENDING index   :2479-2495
      phase B  PlaceOneTrendRescueReplacement ASCENDING index   :2504-2614
               volume = lots[index] * trend_rescue_volume_multiplier
               price  = level.target_price   (the ORIGINAL lattice price)

So the tape signature is falsifiable on five independent axes: the 2x
volume, the unchanged lattice price, the one-sidedness, the descending
cancel run, and the ascending placement run.  PARTS 2-5 test all five.
PART 6 answers the directive's second V10 question on the Starwave tape.
"""
from __future__ import annotations

import collections
import csv
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from a901_eras import norm, parse_level, parse_volume, stamp  # noqa: E402
from a901_v4578 import build_deployments, load_orders, pct  # noqa: E402

# ProfileCatalog.mqh SetLotTier() calls, verbatim, keyed by the era name the
# signature map assigns.  (first_level, last_level, volume), 1-indexed.
LADDER = {
    "HISTORICAL_50": ((1, 15, 0.01), (16, 25, 0.03), (26, 50, 0.06)),   # :132-134
    "HISTORICAL_60": ((1, 15, 0.01), (16, 45, 0.02), (46, 60, 0.05)),   # :168-170
    "AGGRESSIVE_30": ((1, 10, 0.08), (11, 20, 0.41), (21, 30, 0.82)),   # :210-212
    "LOW_RISK_30":   ((1, 10, 0.01), (11, 20, 0.02), (21, 30, 0.05)),   # :231-233
    "STARWAVE_30":   ((1, 10, 0.01), (11, 20, 0.06), (21, 30, 0.15)),   # :491-493
}
PACING_BREAK = datetime(2026, 7, 24, 12, 0, 0)
STARWAVE_CSV = Path("Starwave_60542_orders_history.csv")
ERAS = ["HISTORICAL_50", "HISTORICAL_60", "AGGRESSIVE_30", "LOW_RISK_30",
        "STARWAVE_30"]


def base_lot(era, level):
    for first, last, volume in LADDER.get(era, ()):
        if first <= level <= last:
            return volume
    return None


def regime(era, when):
    if era != "STARWAVE_30":
        return era
    return era + ("/pre-break" if when < PACING_BREAK else "/post-break")


def lattice_rows(orders):
    """Every order the EA stamped with a level comment, cycle-assigned."""
    rows = []
    for row in orders:
        parsed = parse_level(row["Comment"])
        when = stamp(row["Open Time"])
        if parsed is None or when is None:
            continue
        state = norm(row["State"])
        rows.append({
            "when": when,
            "is_buy": parsed[0],
            "level": parsed[1],
            "price": float(norm(row["Price"])),
            "volume": parse_volume(row["Volume"]),
            "ticket": norm(row["Order"]),
            "state": state.split()[0].lower() if state else "",
            "resolved": stamp(row["Time"]),
        })
    rows.sort(key=lambda item: (item["when"], item["ticket"]))
    return rows


def assign_cycles(rows, deployments):
    """Attach cycle index / era / base lot / tier ratio to every lattice row."""
    starts = [record["when"] for record in deployments]
    for row in rows:
        idx = None
        for i in range(len(starts) - 1, -1, -1):
            if starts[i] <= row["when"]:
                idx = i
                break
        row["cycle"] = idx
        era = deployments[idx]["assigned"] if idx is not None else None
        row["era"] = era
        row["regime"] = regime(era, row["when"]) if era else "pre-first-deploy"
        lot = base_lot(era, row["level"]) if era else None
        row["base"] = lot
        row["ratio"] = (row["volume"] / lot) if lot else None
    return rows
def bucket(ratio):
    if ratio is None:
        return "no-ladder"
    if abs(ratio - 1.0) <= 1e-9:
        return "base"
    if abs(ratio - 2.0) <= 1e-9:
        return "x2"
    return "other"


def part1(rows, deployments):
    print("=== PART 1: is the 25,447 figure the DEPLOYMENT population? ===")
    print("  build_deployments() admits only 2 s-gap clusters of >=10 legs at")
    print("  >=0.80 density.  A mid-cycle rescue replacement cannot qualify.")
    cluster_tickets = set()
    legs = 0
    for record in deployments:
        for leg in record["cluster"]:
            cluster_tickets.add(leg["ticket"])
            legs += 1
    print(f"  deployments={len(deployments)}  cluster legs={legs}"
          f"  distinct tickets={len(cluster_tickets)}")
    print(f"  lattice-comment orders on the whole tape: {len(rows)}")
    inside = [r for r in rows if r["ticket"] in cluster_tickets]
    outside = [r for r in rows if r["ticket"] not in cluster_tickets]
    print(f"    inside  a deployment cluster: {len(inside)}")
    print(f"    outside a deployment cluster: {len(outside)}"
          f"   (re-arms + rescue replacements)")
    print()
    print("  population x tier-ratio, per regime:")
    print("  regime                        pop        n     base       x2"
          "    other  no-ladder")
    for name, pop in (("INSIDE", inside), ("OUTSIDE", outside)):
        by = collections.defaultdict(lambda: collections.Counter())
        for r in pop:
            by[r["regime"]][bucket(r["ratio"])] += 1
            by[r["regime"]]["n"] += 1
        for key in [k for k in ERAS + ["STARWAVE_30/pre-break",
                                       "STARWAVE_30/post-break",
                                       "pre-first-deploy"] if k in by]:
            c = by[key]
            print(f"  {key:24s} {name:>8s} {c['n']:8d} {c['base']:8d}"
                  f" {c['x2']:8d} {c['other']:8d} {c['no-ladder']:10d}")
    bad = [r for r in inside if bucket(r["ratio"]) != "base"]
    print(f"\n  non-base legs INSIDE a deployment cluster: {len(bad)}"
          f"   <== V9's 25,447/25,447 requires 0")
    for r in bad[:8]:
        print(f"       {r['when']}  L{r['level']:3d} vol={r['volume']}"
              f" base={r['base']} ratio={r['ratio']}")
    return inside, outside
def group_events(outside, gap_s=600.0):
    """2x rows -> events, keyed (cycle, side), split on a placement-time gap."""
    x2 = [r for r in outside if bucket(r["ratio"]) == "x2"]
    x2.sort(key=lambda r: (r["cycle"] if r["cycle"] is not None else -1,
                           r["is_buy"], r["when"]))
    events = []
    current = []
    for row in x2:
        if current and (
            row["cycle"] != current[-1]["cycle"]
            or row["is_buy"] != current[-1]["is_buy"]
            or (row["when"] - current[-1]["when"]).total_seconds() > gap_s
        ):
            events.append(current)
            current = []
        current.append(row)
    if current:
        events.append(current)
    events.sort(key=lambda e: e[0]["when"])
    return x2, events


def part2(outside, deployments):
    x2, events = group_events(outside)
    print("=== PART 2: the 2x population, and its event structure ===")
    print(f"  orders at exactly 2x the tier lot: {len(x2)}"
          "    in-source claim: 125")
    per_regime = collections.Counter(r["regime"] for r in x2)
    print(f"  by regime: {dict(per_regime)}")
    vols = collections.Counter((r["level"], r["base"], r["volume"]) for r in x2)
    print("  (level-tier, base, 2x) volumes observed:")
    for (lvl, base, vol), n in sorted(vols.items()):
        print(f"       L{lvl:3d}  base={base:.2f}  placed={vol:.2f}"
              f"  ratio={vol/base:.4f}  n={n}")
    print(f"\n  events (same cycle, same side, <600 s apart): {len(events)}"
          "    in-source claim: 6")
    print("  #  regime                  side   n  levels      span_s"
          "  ascending  price_dev")
    for i, ev in enumerate(events):
        rec = deployments[ev[0]["cycle"]] if ev[0]["cycle"] is not None else None
        levels = [r["level"] for r in ev]
        span = (ev[-1]["when"] - ev[0]["when"]).total_seconds()
        asc = all(levels[j] <= levels[j + 1] for j in range(len(levels) - 1))
        dev = 0.0
        if rec is not None:
            for r in ev:
                want = (rec["anchor"] + r["level"] * rec["step"] if r["is_buy"]
                        else rec["anchor"] - r["level"] * rec["step"])
                dev = max(dev, abs(r["price"] - want))
        print(f"  {i}  {ev[0]['regime']:22s} {'buy' if ev[0]['is_buy'] else 'sell':>4s}"
              f" {len(ev):3d}  {min(levels):2d}-{max(levels):2d}  {span:10.3f}"
              f"  {str(asc):>9s}  {dev:9.4f}")
    return x2, events
def part3(rows, events, deployments):
    print("\n=== PART 3: phase A -- the cancel run that precedes each event ===")
    print("  source: TryCancelOneTrendRescueOrder walks index DESCENDING and")
    print("  cancels ONE base-volume pending per tick on the trend side only.")
    print("  so the run must be same-side, base-volume, descending in level.")
    print("  #  cancels  levels     desc  gap_p50  gap_min  gap_max  other_side"
          "  place_gap_p50")
    for i, ev in enumerate(events):
        cyc = ev[0]["cycle"]
        side = ev[0]["is_buy"]
        first = ev[0]["when"]
        floor_ = deployments[cyc]["when"] if cyc is not None else None
        run = [r for r in rows
               if r["cycle"] == cyc and r["state"].startswith("cancel")
               and r["resolved"] is not None and r["resolved"] <= first
               and (floor_ is None or r["resolved"] >= floor_)
               and bucket(r["ratio"]) == "base"]
        run.sort(key=lambda r: r["resolved"])
        # keep only the trailing cluster (<=60 s gaps) that ends before `first`
        cluster = []
        for r in run:
            if cluster and (r["resolved"] - cluster[-1]["resolved"]).total_seconds() > 60.0:
                cluster = []
            cluster.append(r)
        same = [r for r in cluster if r["is_buy"] == side]
        other = [r for r in cluster if r["is_buy"] != side]
        levels = [r["level"] for r in same]
        desc = all(levels[j] >= levels[j + 1] for j in range(len(levels) - 1))
        gaps = sorted((same[j + 1]["resolved"] - same[j]["resolved"]).total_seconds()
                      for j in range(len(same) - 1))
        pgaps = sorted((ev[j + 1]["when"] - ev[j]["when"]).total_seconds()
                       for j in range(len(ev) - 1))
        print(f"  {i}  {len(same):7d}  {min(levels) if levels else 0:2d}-"
              f"{max(levels) if levels else 0:2d}  {str(desc):>7s}"
              f"  {pct(gaps,0.50) if gaps else float('nan'):7.3f}"
              f"  {gaps[0] if gaps else float('nan'):7.3f}"
              f"  {gaps[-1] if gaps else float('nan'):7.3f}"
              f"  {len(other):10d}  {pct(pgaps,0.50) if pgaps else float('nan'):13.3f}")
        if len(same) != len(ev):
            print(f"       NOTE cancels={len(same)} != replacements={len(ev)}"
                  f"   levels cancelled={sorted(set(levels))}"
                  f"   replaced={sorted({r['level'] for r in ev})}")
def part4():
    print("\n=== PART 4: the Starwave 60542 tape -- the directive's question 2 ===")
    print("  'Is trend rescue disabled for Starwave profiles, matching the total")
    print("   absence of doubled orders in the Starwave dataset?'")
    if not STARWAVE_CSV.exists():
        print(f"  {STARWAVE_CSV} not found -- skipped")
        return
    per_level = collections.defaultdict(collections.Counter)
    total = 0
    with STARWAVE_CSV.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            parsed = parse_level(row["comment"])
            if parsed is None:
                continue
            volume = float(row["volume_initial"])
            per_level[parsed[1]][volume] += 1
            total += 1
    modal = {lvl: c.most_common(1)[0][0] for lvl, c in per_level.items()}
    off = sum(n for lvl, c in per_level.items()
              for v, n in c.items() if abs(v - modal[lvl]) > 1e-9)
    doubled = sum(n for lvl, c in per_level.items()
                  for v, n in c.items() if abs(v - 2.0 * modal[lvl]) <= 1e-9)
    print(f"  lattice orders={total}  levels={min(per_level)}-{max(per_level)}")
    tiers = collections.defaultdict(list)
    for lvl in sorted(modal):
        tiers[modal[lvl]].append(lvl)
    for vol in sorted(tiers):
        band = tiers[vol]
        print(f"       {vol:.2f}  levels {min(band)}-{max(band)}"
              f"  ({len(band)} levels, {sum(per_level[l].total() for l in band)} orders)")
    print(f"  orders off their level's modal volume: {off}")
    print(f"  orders at exactly 2x their level's modal volume: {doubled}"
          "   <== the 'absence of doubled orders' claim")
    print("\n  the modal ladder above matches NO single catalogue profile and"
          f"\n  {off}/{total} orders sit off their level's mode, so the tape is"
          "\n  multi-epoch and the modal test is weak.  the assumption-free"
          "\n  version: the six Starwave ladders only ever use the tier values"
          "\n  {0.01,0.03,0.04,0.05,0.06,0.15,0.20}, so a 2x replacement must"
          "\n  show up as 0.02/0.08/0.10/0.12/0.30/0.40 -- none of which is a"
          "\n  Starwave tier -- or as 0.06 (=2x0.03), the one collision.")
    tier_set = (0.01, 0.03, 0.04, 0.05, 0.06, 0.15, 0.20)
    allvol = collections.Counter()
    for lvl, counter in per_level.items():
        for vol, n in counter.items():
            allvol[vol] += n
    print("  distinct volumes on the whole Starwave tape:")
    stray = 0
    for vol in sorted(allvol):
        band = sorted(l for l, c in per_level.items() if vol in c)
        is_tier = any(abs(vol - t) <= 1e-9 for t in tier_set)
        if not is_tier:
            stray += allvol[vol]
        print(f"       {vol:.2f}  n={allvol[vol]:5d}  levels {min(band)}-{max(band)}"
              f"  {'configured Starwave tier' if is_tier else 'NOT A STARWAVE TIER'}")
    print(f"  orders whose volume is not a Starwave tier value: {stray}")
    pairs = [(lvl, sorted(c)) for lvl, c in sorted(per_level.items())
             if any(abs(b - 2.0 * a) <= 1e-9 for a in c for b in c)]
    print(f"  levels where one observed volume is exactly 2x another observed"
          f" volume\n  at the SAME level: {len(pairs)}"
          "   <== the only residual doubling channel")
    for lvl, vols in pairs:
        print(f"       L{lvl:3d}  volumes={['%.2f' % v for v in vols]}"
              f"  counts={[per_level[lvl][v] for v in vols]}")


def cycle_window(deployments, cyc):
    if cyc is None:
        return None, None
    lo = deployments[cyc]["when"]
    hi = deployments[cyc + 1]["when"] if cyc + 1 < len(deployments) else None
    return lo, hi


def cancel_clusters(rows, cyc, side, lo, hi, gap_s=60.0):
    """base-volume own-side cancels inside one cycle, split on a 60 s gap."""
    run = [r for r in rows
           if r["cycle"] == cyc and r["is_buy"] == side
           and r["state"].startswith("cancel") and r["resolved"] is not None
           and bucket(r["ratio"]) == "base"
           and (lo is None or r["resolved"] >= lo)
           and (hi is None or r["resolved"] < hi)]
    run.sort(key=lambda r: r["resolved"])
    out, cur = [], []
    for r in run:
        if cur and (r["resolved"] - cur[-1]["resolved"]).total_seconds() > gap_s:
            out.append(cur)
            cur = []
        cur.append(r)
    if cur:
        out.append(cur)
    return out


def part3b(rows, x2, deployments, follow_s=300.0):
    print("\n=== PART 3b: the SOURCE definition of an event, and the LATCH ===")
    print("  ProcessTrendRescue refuses a repeat of m_trend_rescue_consumed_side")
    print("  until a side==0 tick clears it (:2635-2645), so one (cycle,side)")
    print("  carries ONE event unless a second cancel run appears.  And")
    print("  TryCancelTrendRescueLevel sets trend_rescue_latched=true and rewrites")
    print("  level_state.volume to lots[i]*2 (:2465-2470), so every LATER re-arm")
    print("  of that level is 2x as well; MarkTrendRescuePositionRearms (:2647)")
    print("  marks levels holding a POSITION, which get 2x with NO cancel at all.")
    print("  => replacements >= cancels is PREDICTED by the source, not a defect.")
    groups = collections.defaultdict(list)
    for r in x2:
        groups[(r["cycle"], r["is_buy"])].append(r)
    for key in groups:
        groups[key].sort(key=lambda r: r["when"])
    by_cycle = collections.defaultdict(set)
    for cyc, side in groups:
        by_cycle[cyc].add(side)
    both = sorted(c for c, s in by_cycle.items() if len(s) > 1)
    print(f"\n  distinct (cycle, side) pairs carrying 2x orders: {len(groups)}"
          "    in-source claim: 6 events")
    print(f"  distinct cycles carrying 2x orders: {len(by_cycle)}")
    print(f"  cycles carrying 2x on BOTH sides: {len(both)}"
          "   <== one-sidedness requires 0")
    print("\n  cyc  regime                 side  2x  runs  cnl  imm  latch"
          "  cnl_desc  imm_asc  imm_levels==cnl_levels")
    total_imm = total_latch = total_cnl = 0
    ok_desc = ok_asc = ok_eq = 0
    cgaps_all, igaps_all = [], []
    for (cyc, side), members in sorted(groups.items(),
                                       key=lambda kv: kv[1][0]["when"]):
        lo, hi = cycle_window(deployments, cyc)
        clusters = cancel_clusters(rows, cyc, side, lo, hi)
        seen = set()
        qual, immediate = [], []
        for cluster in clusters:
            levels = {r["level"] for r in cluster}
            end = cluster[-1]["resolved"]
            hits = [r for r in members
                    if r["level"] in levels
                    and cluster[0]["resolved"] <= r["when"]
                    <= end + timedelta(seconds=follow_s)
                    and r["ticket"] not in seen]
            if not hits:
                continue
            qual.append(cluster)
            for r in hits:
                seen.add(r["ticket"])
            immediate.extend(hits)
        latched = [r for r in members if r["ticket"] not in seen]
        cnl = [r for cluster in qual for r in cluster]
        cnl.sort(key=lambda r: r["resolved"])
        immediate.sort(key=lambda r: r["when"])
        clv = [r["level"] for r in cnl]
        ilv = [r["level"] for r in immediate]
        desc = all(clv[j] >= clv[j + 1] for j in range(len(clv) - 1))
        asc = all(ilv[j] <= ilv[j + 1] for j in range(len(ilv) - 1))
        eq = set(clv) == set(ilv)
        ok_desc += bool(desc)
        ok_asc += bool(asc)
        ok_eq += bool(eq)
        total_imm += len(immediate)
        total_latch += len(latched)
        total_cnl += len(cnl)
        cgaps_all += [(cnl[j + 1]["resolved"] - cnl[j]["resolved"]).total_seconds()
                      for j in range(len(cnl) - 1)]
        igaps_all += [(immediate[j + 1]["when"] - immediate[j]["when"]).total_seconds()
                      for j in range(len(immediate) - 1)]
        print(f"  {cyc:3d}  {members[0]['regime']:22s}"
              f" {'buy' if side else 'sell':>4s} {len(members):3d} {len(qual):5d}"
              f" {len(cnl):4d} {len(immediate):4d} {len(latched):6d}"
              f"  {str(desc):>8s} {str(asc):>8s}  {str(eq):>22s}")
    n = len(groups)
    print(f"\n  totals: 2x={total_imm + total_latch}"
          f"  immediate-replacement={total_imm}  latched-rearm={total_latch}"
          f"  cancels={total_cnl}")
    print(f"  cancel run DESCENDING in level: {ok_desc}/{n}"
          f"    replacement run ASCENDING in level: {ok_asc}/{n}")
    print(f"  cancelled level set == replaced level set: {ok_eq}/{n}"
          "   <== 'cancel count == pending count', properly scoped")
    if cgaps_all:
        cg = sorted(cgaps_all)
        print(f"  cancel-to-cancel gaps  n={len(cg)}  p05={pct(cg,0.05):.3f}"
              f"  p50={pct(cg,0.50):.3f}  p95={pct(cg,0.95):.3f}  min={cg[0]:.3f}")
    if igaps_all:
        ig = sorted(igaps_all)
        print(f"  place-to-place gaps    n={len(ig)}  p05={pct(ig,0.05):.3f}"
              f"  p50={pct(ig,0.50):.3f}  p95={pct(ig,0.95):.3f}  min={ig[0]:.3f}")


def part5(outside):
    print("\n=== PART 5: the 'other'-ratio rows -- neither base nor 2x ===")
    print("  hypothesis: era mis-attribution across the Jul-13 input changes.")
    print("  a re-arm placed after an input change but before the next")
    print("  deployment is scored against the PREVIOUS deployment's ladder.")
    print("  the test: does the observed volume match SOME catalogue ladder at")
    print("  that level?  if yes for every row, the rows are attribution noise,")
    print("  not EA behaviour.")
    odd = [r for r in outside if bucket(r["ratio"]) == "other"]
    print(f"  rows: {len(odd)}")
    print("  when                        assigned era     L   vol   base"
          "   ratio  volume matches these ladders at that level")
    matched = 0
    for r in sorted(odd, key=lambda item: item["when"]):
        hits = [name for name in ERAS
                if base_lot(name, r["level"]) is not None
                and abs(base_lot(name, r["level"]) - r["volume"]) <= 1e-9]
        matched += bool(hits)
        print(f"  {r['when']}  {r['era']:14s} {r['level']:3d} {r['volume']:5.2f}"
              f" {r['base']:6.2f} {r['ratio']:7.4f}  {','.join(hits) or '(none)'}")
    print(f"\n  rows whose volume IS a configured tier lot at that level in some")
    print(f"  catalogue ladder: {matched}/{len(odd)}"
          "   <== attribution noise requires all")


def part3c(rows, x2, deployments):
    """PART 3b measured 2-3 base cancels per replaced level.  The source says
    ONE: after TryCancelTrendRescueLevel latches (:2461-2466) level_state.volume
    is 2x, so any later re-arm places 2x and IsBaseLevelVolume (:2450) refuses
    to cancel it again.  ClearTrendRescueReplacement (:2497-2502) clears only
    the flag and the mask -- it does NOT restore the volume.  So either my
    cluster window merges an unrelated cancel population, or the latch leaks."""
    print("\n=== PART 3c: is the base cancel really once-per-level-per-cycle? ===")
    print("  source: the latch rewrites level_state.volume to 2x (:2463-2466)")
    print("  and ClearTrendRescueReplacement (:2497-2502) does NOT restore it,")
    print("  so IsBaseLevelVolume (:2450) must refuse every later cancel at")
    print("  that level.  PREDICTION: <=1 base cancel per level per cycle.")
    groups = collections.defaultdict(list)
    for r in x2:
        groups[(r["cycle"], r["is_buy"])].append(r)
    spans = {}
    for (cyc, side), members in sorted(groups.items(),
                                       key=lambda kv: kv[1][0]["when"]):
        lo, hi = cycle_window(deployments, cyc)
        own = [r for r in rows if r["cycle"] == cyc and r["is_buy"] == side]
        cnl = [r for r in own
               if r["state"].startswith("cancel") and r["resolved"] is not None
               and bucket(r["ratio"]) == "base"
               and (lo is None or r["resolved"] >= lo)
               and (hi is None or r["resolved"] < hi)]
        cnl.sort(key=lambda r: r["resolved"])
        lv = collections.Counter(r["level"] for r in cnl)
        multi = sorted(l for l, n in lv.items() if n > 1)
        passes, cur = [], []
        for r in cnl:
            if cur and r["level"] > cur[-1]["level"]:
                passes.append(cur)
                cur = []
            cur.append(r)
        if cur:
            passes.append(cur)
        strict = sum(1 for p in passes
                     if all(p[j]["level"] > p[j + 1]["level"]
                            for j in range(len(p) - 1)))
        spans[(cyc, side)] = (members[0]["when"], members[-1]["when"])
        print(f"\n  cycle {cyc}  {'buy' if side else 'sell':4s}"
              f"  base cancels={len(cnl):3d}  distinct levels={len(lv):3d}"
              f"  levels cancelled >1x={len(multi):3d}  2x placed={len(members):3d}")
        print(f"      descending passes={len(passes)}"
              f"  strictly descending={strict}/{len(passes)}"
              f"  pass level ranges="
              f"{[f'{p[0]['level']}-{p[-1]['level']}' for p in passes][:6]}")
        for lvl in multi[:2]:
            print(f"      L{lvl} full order lifecycle on this side, this cycle:")
            for r in sorted((q for q in own if q["level"] == lvl),
                            key=lambda q: q["when"]):
                ratio = "None" if r["ratio"] is None else f"{r['ratio']:.4f}"
                print(f"        setup {r['when']}  vol {r['volume']:.2f}"
                      f"  x{ratio:>6s}  {r['state']:9s}"
                      f"  done {r['resolved']}  #{r['ticket']}")
    print("\n  m_trend_rescue_side is a SCALAR, so two events in one cycle on")
    print("  opposite sides must be time-DISJOINT.  same-cycle span overlap:")
    bycyc = collections.defaultdict(list)
    for (cyc, side), span in spans.items():
        bycyc[cyc].append((side, span))
    viol = 0
    for cyc, items in sorted(bycyc.items()):
        if len(items) < 2:
            continue
        items.sort(key=lambda kv: kv[1][0])
        (s1, (a1, b1)), (s2, (a2, b2)) = items[0], items[1]
        overlap = a2 <= b1
        viol += bool(overlap)
        print(f"      cycle {cyc}: {'buy' if s1 else 'sell'} {a1}..{b1}"
              f"  then {'buy' if s2 else 'sell'} {a2}..{b2}"
              f"  gap={(a2 - b1).total_seconds():.3f}s"
              f"  OVERLAP={overlap}")
    print(f"      same-cycle opposite-side overlaps: {viol}"
          "   <== scalar-side invariant requires 0")


SW_STATE = {"0": "started", "1": "placed", "2": "canceled", "3": "partial",
            "4": "filled", "5": "rejected", "6": "expired"}
EPOCH = datetime(1970, 1, 1)


def ms_stamp(msc):
    """epoch ms -> the 'YYYY.MM.DD HH:MM:SS.mmm' text stamp() parses."""
    when = EPOCH + timedelta(milliseconds=int(msc))
    return when.strftime("%Y.%m.%d %H:%M:%S.") + f"{when.microsecond // 1000:03d}"


def load_starwave_rows():
    """Adapt the msc-format Starwave export to the 901018 column names, so the
    validated build_deployments() predicate and lattice_rows() apply unchanged."""
    out = []
    if not STARWAVE_CSV.exists():
        return out
    with STARWAVE_CSV.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            if parse_level(row.get("comment", "") or "") is None:
                continue
            try:
                setup = int(row["time_setup_msc"])
            except (KeyError, TypeError, ValueError):
                continue
            try:
                done = int(row.get("time_done_msc") or 0)
            except ValueError:
                done = 0
            out.append({
                "Open Time": ms_stamp(setup),
                "Order": norm(row["ticket"]),
                "Volume": norm(row["volume_initial"]),
                "Price": norm(row["price_open"]),
                "State": SW_STATE.get(norm(row.get("state", "")), ""),
                "Time": ms_stamp(done) if done else "",
                "Comment": row["comment"],
            })
    out.sort(key=lambda r: r["Open Time"])
    return out


def part6():
    """The assumption-free Starwave test.  PART 4 is POOLED over the whole tape,
    so an unmodelled epoch whose tier lot happens to be 2x another epoch's tier
    lot at the same level is indistinguishable from a rescue.  A rescue is
    CYCLE-LOCAL, so recover each cycle's own ladder from its own deployment
    legs and score every order in that cycle against THAT ladder."""
    print("\n=== PART 6: Starwave, per CYCLE against its OWN recovered ladder ===")
    sw = load_starwave_rows()
    if not sw:
        print(f"  {STARWAVE_CSV} not found -- skipped")
        return
    deps = build_deployments(sw)
    rws = lattice_rows(sw)
    starts = [d["when"] for d in deps]
    for r in rws:
        idx = None
        for i in range(len(starts) - 1, -1, -1):
            if starts[i] <= r["when"]:
                idx = i
                break
        r["cycle"] = idx
    print(f"  lattice orders={len(rws)}  deployments={len(deps)}"
          f"  span {rws[0]['when']} .. {rws[-1]['when']}")
    # the ladder of a cycle = the volume of the FIRST order the cycle placed at
    # each level.  the deployment leg is by construction the first, and it is
    # placed at m_profile.lots[index] before any rescue or re-arm can fire.
    ladders = {}
    bycyc = collections.defaultdict(list)
    for r in rws:
        bycyc[r["cycle"]].append(r)
    for cyc, members in bycyc.items():
        first = {}
        for r in sorted(members, key=lambda q: (q["when"], q["ticket"])):
            first.setdefault(r["level"], r["volume"])
        ladders[cyc] = first
    tally = collections.Counter()
    doubles = []
    for cyc, members in sorted(bycyc.items(), key=lambda kv: (kv[0] is None, kv[0])):
        lad = ladders[cyc]
        for r in members:
            tier = lad.get(r["level"])
            if tier is None or tier <= 0.0:
                tally["no-tier"] += 1
                continue
            ratio = r["volume"] / tier
            tally[bucket(ratio)] += 1
            if abs(ratio - 2.0) <= 1e-9:
                doubles.append((cyc, r, tier))
    print(f"  scored against own-cycle ladder: base={tally['base']}"
          f"  x2={tally['x2']}  other={tally['other']}  no-tier={tally['no-tier']}")
    print(f"  orders at exactly 2x their OWN CYCLE's tier at that level:"
          f" {len(doubles)}")
    for cyc, r, tier in doubles[:25]:
        print(f"       cycle {cyc}  {r['when']}  {'B' if r['is_buy'] else 'S'}"
              f"{r['level']:<3d} vol {r['volume']:.2f}  tier {tier:.2f}"
              f"  {r['state']}")
    sig = collections.Counter()
    for cyc, lad in ladders.items():
        if cyc is None or len(lad) < 10:
            continue
        tiers, prev = [], None
        for lvl in sorted(lad):
            if prev is None or abs(lad[lvl] - prev) > 1e-9:
                tiers.append((lvl, lad[lvl]))
                prev = lad[lvl]
        sig["  ".join(f"L{l}+@{v:.2f}" for l, v in tiers)] += 1
    print(f"\n  distinct per-cycle ladders recovered (>=10 levels):"
          f" {len(sig)}   <== the catalogue models 6 Starwave profiles")
    for text, n in sig.most_common():
        print(f"       {n:3d} cycles   {text}")


# <<APPEND>>


def main() -> int:
    orders = load_orders()
    deployments = build_deployments(orders)
    rows = assign_cycles(lattice_rows(orders), deployments)
    inside, outside = part1(rows, deployments)
    print()
    _x2, events = part2(outside, deployments)
    part3(rows, events, deployments)
    part3b(rows, _x2, deployments)
    part3c(rows, _x2, deployments)
    part4()
    part5(outside)
    part6()
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

