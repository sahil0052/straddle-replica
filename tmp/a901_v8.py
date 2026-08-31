"""V8 -- cycle restart floor and state machine, on ReportHistory-901018.

The engine's restart gate is an INTEGER-SECOND comparison:

    StraddleEngine.mqh:3811-3812
        if(TimeCurrent()-m_restart_started_at >= (m_profile.restart_delay_ms+999)/1000)

Both operands are whole-second datetimes, and (ms+999)/1000 is integer
division -- i.e. exactly ceil(ms/1000).  Call that quantum T.

  m_restart_started_at is TimeCurrent() at the instant the basket went flat
  (StraddleEngine.mqh:2955 for the cancel-first path, :3020 for the
  close-first path), so it is the flat instant TRUNCATED DOWN to its second.

Two consequences, and they are different instruments:

  (1) MODEL-FREE:  floor(next_deploy) - floor(last_close) reproduces the
      engine's own comparison exactly.  Its mode IS T.  No latency model,
      no assumption about tick lag.  This is the instrument the in-source
      Starwave note used ("floor(next_deploy)-floor(flat) = 2 s on 96
      cycles").  PART 1.

  (2) MODELLED:  the real-valued interval is  T - f + eps,  where f is the
      fractional part of the flat instant (uniform on [0,1) whenever the
      close itself is not clock-quantised) and eps is timer + placement
      lag.  So the real interval spreads over (T-1, T+0.4), NOT over
      (T, T+0.4).  A measured FLOOR of F therefore implies T ~= F + 1,
      not T ~= F.  PART 2 tests the uniformity that this rests on.

PART 3 audits the state machine as an ordering: cancel run, then close
burst, then the restart wait, then the next deployment -- with no overlap.
PART 4 isolates the intervals that are shorter than any T can explain.
"""
from __future__ import annotations

import collections
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from a901_eras import norm, stamp  # noqa: E402
from a901_v4578 import (  # noqa: E402
    build_deployments, build_sweeps, cancel_times, classify_sweeps,
    eras_present, load_orders, pct,
)

# ProfileCatalog.mqh, verbatim.  Value is restart_delay_ms; T = ceil(ms/1000).
CONFIGURED_MS = {
    "HISTORICAL_50": 3000,   # inherited ResetProfile default, :35
    "HISTORICAL_60": 3000,   # inherited ResetProfile default, :35
    "AGGRESSIVE_30": 3000,   # inherited ResetProfile default, :35
    "LOW_RISK_30": 3000,     # inherited ResetProfile default, :35
    "STARWAVE_30": 20000,    # the era is LATEST_30 on the pacing field, :359
}
# The 20-second pacing change, ProfileCatalog.mqh:317-334.  Burst sweeps run
# to Jul 24 09:10, paced sweeps resume Jul 24 15:48, so any split inside that
# window separates the two sub-regimes cleanly.
PACING_BREAK = datetime(2026, 7, 24, 12, 0, 0)
SPLIT_ERA = "STARWAVE_30"


def quantum(later, earlier):
    """The engine's own operand: whole-second difference, both sides floored."""
    return int(
        (later.replace(microsecond=0) - earlier.replace(microsecond=0)).total_seconds()
    )


def era_of(cycle, when):
    era = str(cycle["assigned"]) if cycle else "before-first-deployment"
    if era == SPLIT_ERA:
        return era + ("/pre-break" if when < PACING_BREAK else "/post-break")
    return era


def restart_pairs(orders):
    """(era, last close, next deployment start) for every terminal sweep that
    has a following deployment."""
    deployments = build_deployments(orders)
    sweeps = build_sweeps(orders)
    terminal, interim, _silent = classify_sweeps(sweeps, deployments)
    starts = [record["when"] for record in deployments]

    pairs = []
    for burst, cycle in terminal:
        last = burst[-1]["when"]
        nxt = None
        for record in deployments:
            if record["when"] > last:
                nxt = record
                break
        if nxt is None:
            continue
        pairs.append({
            "era": era_of(cycle, last),
            "cycle": cycle,
            "next": nxt,
            "flat": last,
            "first_close": burst[0]["when"],
            "deploy": nxt["when"],
            "real": (nxt["when"] - last).total_seconds(),
            "quantum": quantum(nxt["when"], last),
            "legs": len(burst),
            "burst": burst,
            "cross_era": (cycle is not None
                          and str(cycle["assigned"]) != str(nxt["assigned"])),
        })
    _ = starts
    return pairs, deployments, interim


def order_label(mapping):
    return [k for k in (
        "HISTORICAL_50", "HISTORICAL_60", "AGGRESSIVE_30", "LOW_RISK_30",
        "STARWAVE_30/pre-break", "STARWAVE_30/post-break",
    ) if k in mapping] + [
        k for k in mapping if k not in (
            "HISTORICAL_50", "HISTORICAL_60", "AGGRESSIVE_30", "LOW_RISK_30",
            "STARWAVE_30/pre-break", "STARWAVE_30/post-break",
        )
    ]


def main() -> int:
    orders = load_orders()
    pairs, deployments, interim = restart_pairs(orders)
    cancels = cancel_times(orders)
    print(f"restarts={len(pairs)} deployments={len(deployments)} "
          f"interim_bursts={len(interim)} cancels={len(cancels)}")
    print()

    by_era = collections.defaultdict(list)
    for row in pairs:
        by_era[row["era"]].append(row)

    print("=== PART 1: the model-free quantum -- floor(next_deploy)-floor(flat) ===")
    print("  this IS the engine's comparison operand.  Its mode is T=ceil(ms/1000).")
    for era in order_label(by_era):
        rows = by_era[era]
        hist = collections.Counter(r["quantum"] for r in rows)
        near = {q: c for q, c in hist.items() if q <= 30}
        far = sum(c for q, c in hist.items() if q > 30)
        mode = max(near.items(), key=lambda kv: kv[1])[0] if near else None
        cfg = CONFIGURED_MS.get(era.split("/")[0])
        want = -(-cfg // 1000) if cfg else None
        print(f"  -- {era:24s} n={len(rows):4d}  configured {cfg} ms => T={want}")
        for q in sorted(near):
            flag = "  <== configured T" if q == want else ""
            print(f"       q={q:3d} s  {near[q]:4d}  {'#'*min(near[q],60)}{flag}")
        if far:
            print(f"       q>30 s   {far:4d}  (operator gaps / market closures)")
        if mode is not None:
            share = 100.0 * hist[mode] / len(rows)
            print(f"       mode T={mode} s on {hist[mode]}/{len(rows)} = {share:5.2f}%"
                  f"   verdict: {'MATCH' if mode == want else 'MISMATCH'}")
    print()

    print("=== PART 2: the modelled interval -- real seconds, and the f-test ===")
    print("  prediction: real = T - f + eps with f ~ U[0,1), so real lands in")
    print("  (T-1, T+0.4) and the residual r = real-(T-1) is ~U(0,1)+eps.")
    for era in order_label(by_era):
        rows = [r for r in by_era[era] if r["real"] <= 600.0]
        if not rows:
            continue
        cfg = CONFIGURED_MS.get(era.split("/")[0])
        want = -(-cfg // 1000) if cfg else None
        vals = sorted(r["real"] for r in rows)
        print(f"  -- {era:24s} n={len(vals):4d}  T={want}")
        print(f"       real     min={vals[0]:8.3f} p05={pct(vals,0.05):8.3f} "
              f"p25={pct(vals,0.25):8.3f} p50={pct(vals,0.50):8.3f} "
              f"p95={pct(vals,0.95):8.3f} max={vals[-1]:8.3f}")
        if want is None:
            continue
        res = sorted(v - (want - 1) for v in vals)
        inside = sum(1 for v in vals if want - 1 < v < want + 0.4)
        print(f"       residual min={res[0]:8.3f} p25={pct(res,0.25):8.3f} "
              f"p50={pct(res,0.50):8.3f} p75={pct(res,0.75):8.3f} "
              f"max={res[-1]:8.3f}   (U(0,1)+eps predicts p25/p50/p75 ~ .25/.50/.75)")
        print(f"       inside (T-1,T+0.4): {inside}/{len(vals)} = "
              f"{100.0*inside/len(vals):5.2f}%")
        # What floor would the WRONG model (real floor == T) have implied?
        print(f"       floor-implied T under the truncation model = "
              f"{vals[0]:.3f} + 1 - eps  =>  T ~= {round(vals[0] + 1):d}")
    print()

    print("=== PART 3: state-machine ordering, per cycle ===")
    print("  CANCELING -> CLOSING -> RESTARTING -> IDLE -> DEPLOYING must appear")
    print("  as: last cancel <= first close <= last close < next deployment.")
    tally = collections.defaultdict(lambda: collections.Counter())
    for row in pairs:
        era, cycle = row["era"], row["cycle"]
        bucket = tally[era]
        bucket["n"] += 1
        if row["deploy"] <= row["flat"]:
            bucket["deploy_before_flat"] += 1
        if row["first_close"] > row["flat"]:
            bucket["close_order_inverted"] += 1
        floor_ = cycle["when"] if cycle else None
        window = [c for c in cancels
                  if (floor_ is None or floor_ <= c) and c <= row["deploy"]]
        if not window:
            bucket["no_cancel_run"] += 1
            continue
        last_cancel = window[-1]
        if last_cancel <= row["first_close"]:
            bucket["cancel_then_close"] += 1
        elif last_cancel <= row["flat"]:
            bucket["cancel_overlaps_close"] += 1
        else:
            bucket["cancel_after_flat"] += 1
        if last_cancel >= row["deploy"]:
            bucket["cancel_after_deploy"] += 1
    keys = ["n", "cancel_then_close", "cancel_overlaps_close", "cancel_after_flat",
            "no_cancel_run", "deploy_before_flat", "close_order_inverted",
            "cancel_after_deploy"]
    print("  era                       " + "".join(f"{k[:11]:>13s}" for k in keys))
    for era in order_label(tally):
        print(f"  {era:24s}  " + "".join(f"{tally[era][k]:13d}" for k in keys))
    print()

    print("=== PART 4: intervals no quantum can explain (real < T-1) ===")
    for era in order_label(by_era):
        cfg = CONFIGURED_MS.get(era.split("/")[0])
        if cfg is None:
            continue
        want = -(-cfg // 1000)
        bad = [r for r in by_era[era] if r["real"] < want - 1]
        print(f"  {era:24s} T={want:2d}  under-floor {len(bad)}/{len(by_era[era])}")
        for r in sorted(bad, key=lambda r: r["real"])[:6]:
            print(f"       {r['flat']}  real={r['real']:7.3f}  q={r['quantum']:3d}"
                  f"  legs={r['legs']:3d}  deploy={r['deploy']}")
    print()
    print("=== PART 5: the clean subset -- same-era pairs, no operator gap ===")
    print("  drops (a) pairs whose next deployment belongs to a DIFFERENT era")
    print("  (an input change happened during the wait) and (b) real>600 s.")
    print("  T is then read off the mode, and the implied ms window printed.")
    clean = collections.defaultdict(list)
    dropped = collections.Counter()
    measured = {}
    for row in pairs:
        if row["cross_era"]:
            dropped[row["era"]] += 1
            continue
        if row["real"] > 600.0:
            dropped[row["era"]] += 1
            continue
        clean[row["era"]].append(row)
    for era in order_label(clean):
        rows = clean[era]
        hist = collections.Counter(r["quantum"] for r in rows)
        mode = max(hist.items(), key=lambda kv: (kv[1], -kv[0]))[0]
        if len(rows) >= 10:
            measured[era] = mode
        cfg = CONFIGURED_MS.get(era.split("/")[0])
        want = -(-cfg // 1000) if cfg else None
        at_mode = hist[mode]
        lag = hist.get(mode - 1, 0)
        vals = sorted(r["real"] for r in rows)
        print(f"  -- {era:24s} n={len(rows):4d} (dropped {dropped[era]})"
              f"  configured {cfg} ms => T={want}")
        print(f"       q histogram {dict(sorted(hist.items()))}")
        print(f"       mode T={mode}  at-mode {at_mode}/{len(rows)}"
              f"  quote-lag bucket q={mode-1}: {lag}"
              f"  covered {100.0*(at_mode+lag)/len(rows):5.2f}%")
        print(f"       => restart_delay_ms in ({(mode-1)*1000}, {mode*1000}]"
              f"   configured {cfg}  "
              f"{'CONSISTENT' if want == mode else 'DIVERGENT'}")
        print(f"       real p05={pct(vals,0.05):8.3f} p50={pct(vals,0.50):8.3f}"
              f" p95={pct(vals,0.95):8.3f}  band for T={mode}: "
              f"({mode-1}, {mode}+eps)")
    print()

    print("=== PART 6: dissection of every under-floor pair, vs the MEASURED T ===")
    print("  under-floor means real < T_meas-1: shorter than ANY draw of")
    print("  T-f+eps can be.  hypothesis: the burst's tail legs are late/async")
    print("  fills, so the engine saw CyclePositionCount()==0 at an EARLIER leg")
    print("  (or at the end of the cancel run) and started the wait there.")
    for era in order_label(clean):
        want = measured.get(era)
        if want is None:
            continue
        bad = [r for r in clean[era] if r["real"] < want - 1]
        print(f"  -- {era}  T_meas={want}  under-floor {len(bad)}/{len(clean[era])}")
        for r in sorted(bad, key=lambda r: r["real"]):
            legs = r["burst"]
            offs = [(r["deploy"] - leg["when"]).total_seconds() for leg in legs]
            hit = [i for i, d in enumerate(offs) if want - 1 < d < want + 0.4]
            prior = [c for c in cancels if c <= r["deploy"]]
            dc = (r["deploy"] - prior[-1]).total_seconds() if prior else None
            verdict = ("quote-lag branch q=T-1" if r["quantum"] == want - 1
                       and want - 2 < r["real"] < want - 0.6
                       else "in-burst flat at leg " + str(hit[0]) if hit
                       else "cancel-run flat" if dc is not None
                       and want - 1 < dc < want + 0.4
                       else "UNEXPLAINED")
            print(f"     {r['flat']}  legs={len(legs):3d} real={r['real']:7.3f}"
                  f"  burst span={offs[0]-offs[-1]:7.3f}"
                  f"  deploy-last_cancel={('%8.3f' % dc) if dc is not None else '     n/a'}"
                  f"  => {verdict}")
    print()

    print("=== PART 7: does the restart clock run in PARALLEL with a residual")
    print("    cancel run?  (the replica's CYCLE_RESTARTING drains orders and")
    print("    `break`s -- StraddleEngine.mqh:3789-3793 -- so it defers the")
    print("    delay check until the drain finishes.)")
    for era in order_label(clean):
        want = measured.get(era)
        if want is None:
            continue
        late = []
        for r in clean[era]:
            floor_ = r["cycle"]["when"] if r["cycle"] else None
            window = [c for c in cancels
                      if (floor_ is None or floor_ <= c) and c <= r["deploy"]]
            if not window or window[-1] <= r["flat"]:
                continue
            late.append((r, window[-1]))
        if not late:
            print(f"  -- {era:24s} no pair has a cancel after the flat instant")
            continue
        par = sum(1 for r, _ in late if want - 1 < r["real"] < want + 0.4)
        beyond = [(r, c) for r, c in late
                  if (c - r["flat"]).total_seconds() > want]
        print(f"  -- {era:24s} pairs with a post-flat cancel: {len(late)}")
        print(f"       still deploying inside the T band: {par}/{len(late)}"
              f"   cancel run extending BEYOND T after the flat: {len(beyond)}")
        for r, c in sorted(late, key=lambda kv: kv[0]["flat"])[:4]:
            print(f"       {r['flat']}  last_cancel=+"
                  f"{(c-r['flat']).total_seconds():7.3f}s  deploy=+{r['real']:7.3f}s"
                  f"  q={r['quantum']}")
        if beyond:
            print("       -- the discriminating rows (cancel run outlives T):")
            print("          if the clock is anchored at the FLAT the engine should")
            print("          deploy ~0.1 s after the drain; if at the DRAIN END it")
            print(f"          should deploy ~{want} s after it.")
            for r, c in sorted(beyond, key=lambda kv: kv[0]["flat"]):
                after = (r["deploy"] - c).total_seconds()
                which = ("drain-end anchored" if want - 1 < after < want + 0.4
                         else "flat anchored" if after < 0.6 else "neither")
                print(f"          {r['flat']}  cancel_run=+"
                      f"{(c-r['flat']).total_seconds():8.3f}s"
                      f"  deploy-last_cancel={after:7.3f}s  q={r['quantum']:3d}"
                      f"  => {which}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
