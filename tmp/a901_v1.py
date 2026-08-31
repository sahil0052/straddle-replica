"""V1/V2/V9 on the 901018 tape: anchor law, step law, interleave, lot ladder.

Deployments are recovered by clustering pending placements on their ~103 ms
cadence (gap > 2 s starts a new cluster) rather than by looking for 'STR B1',
because re-arms also emit 'STR B1' and would create phantom cycles.  A cluster
that carries both B1 and S1 and >= 10 legs is a cycle deployment.

Per deployment this checks, exactly:
  anchor  = (B1 + S1) / 2                     -- must be a whole cent
  step    = (B1 - S1) / 2                     -- must equal round(anchor/3000, 2)
  Buy[i]  = anchor + i*step, Sell[i] = anchor - i*step   -- lattice residuals
  order   = B1,S1,B2,S2,...                   -- inversion count
  volume ladder by level                      -- tier boundaries -> N
"""
from __future__ import annotations

import collections
import csv
import re
from datetime import datetime
from pathlib import Path

BURST_GAP_MS = 2000.0
MIN_LEGS = 10


def norm(value: str | None) -> str:
    return (value or "").strip()


def stamp(text: str) -> datetime | None:
    text = norm(text)
    if not text:
        return None
    return datetime.strptime(text, "%Y.%m.%d %H:%M:%S.%f")


def parse_level(comment: str):
    match = re.match(r"^STR ([BS])(\d+)$", norm(comment))
    if match is None:
        return None
    return (match.group(1) == "B", int(match.group(2)))


def parse_volume(text: str) -> tuple[float, float]:
    """MT5 renders Volume as 'initial / filled' (canceled rows read 'X / 0')."""
    parts = [p.strip() for p in norm(text).split("/") if p.strip()]
    if len(parts) == 1:
        value = float(parts[0])
        return value, value
    return float(parts[-1]), float(parts[0])


def percentile(values: list[float], q: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round(q * (len(ordered) - 1)))))
    return ordered[index]


def main() -> int:
    path = Path("tmp/r901018_orders.csv")
    raw_header = next(csv.reader(path.open(encoding="utf-8")))
    print("raw order header:", raw_header)
    dupes = [k for k, n in collections.Counter(raw_header).items() if n > 1 and k]
    print("duplicate header names:", dupes)
    print()

    rows = []
    vol_shapes: collections.Counter = collections.Counter()
    vol_split = 0
    for row in csv.DictReader(path.open(encoding="utf-8")):
        parsed = parse_level(row["Comment"])
        if parsed is None:
            continue
        when = stamp(row["Open Time"])
        if when is None:
            continue
        filled, initial = parse_volume(row["Volume"])
        vol_shapes[norm(row["Volume"])] += 1
        if abs(filled - initial) > 1e-9:
            vol_split += 1
        rows.append({
            "when": when,
            "is_buy": parsed[0],
            "level": parsed[1],
            "price": float(norm(row["Price"])),
            "volume": initial,
            "filled": filled,
            "ticket": norm(row["Order"]),
            "state": norm(row["State"]),
        })
    rows.sort(key=lambda item: (item["when"], item["ticket"]))
    print(f"lattice pendings parsed: {len(rows)}")
    print(f"volume strings where filled != initial: {vol_split}")
    print(f"volume string shapes (top 20): {dict(vol_shapes.most_common(20))}")

    clusters: list[list[dict]] = []
    current: list[dict] = []
    for row in rows:
        if current and (row["when"] - current[-1]["when"]).total_seconds() * 1000.0 > BURST_GAP_MS:
            clusters.append(current)
            current = []
        current.append(row)
    if current:
        clusters.append(current)
    print(f"clusters: {len(clusters)}")

    deployments = []
    for cluster in clusters:
        has_b1 = any(r["is_buy"] and r["level"] == 1 for r in cluster)
        has_s1 = any(not r["is_buy"] and r["level"] == 1 for r in cluster)
        if len(cluster) >= MIN_LEGS and has_b1 and has_s1:
            deployments.append(cluster)
    print(f"deployments (>= {MIN_LEGS} legs, carries B1 and S1): {len(deployments)}")
    sizes = collections.Counter(len(c) for c in deployments)
    print(f"deployment leg-count histogram: {dict(sorted(sizes.items()))}")
    rearm_like = [c for c in clusters if c not in deployments]
    print(f"non-deployment clusters: {len(rearm_like)} "
          f"legs={sum(len(c) for c in rearm_like)}")
    print()

    step_ok = anchor_cent_ok = span_ok = 0
    inversions_total = 0
    perfect_interleave = 0
    lattice_resid: list[float] = []
    ladders: collections.Counter = collections.Counter()
    n_hist: collections.Counter = collections.Counter()
    detail = []

    for cluster in deployments:
        b1 = next(r for r in cluster if r["is_buy"] and r["level"] == 1)
        s1 = next(r for r in cluster if not r["is_buy"] and r["level"] == 1)
        anchor = (b1["price"] + s1["price"]) / 2.0
        step = (b1["price"] - s1["price"]) / 2.0
        law = round(anchor / 3000.0, 2)
        cent = abs(anchor * 100.0 - round(anchor * 100.0)) < 1e-6
        levels = sorted({r["level"] for r in cluster})
        n_levels = max(levels)
        n_hist[n_levels] += 1
        if abs(step - law) < 5e-9:
            step_ok += 1
        if cent:
            anchor_cent_ok += 1
        if abs((b1["price"] - s1["price"]) - 2.0 * step) < 5e-9:
            span_ok += 1

        for r in cluster:
            want = anchor + (r["level"] * step if r["is_buy"] else -r["level"] * step)
            lattice_resid.append(abs(r["price"] - want))

        expect = []
        for level in range(1, n_levels + 1):
            expect.append((True, level))
            expect.append((False, level))
        seen = [(r["is_buy"], r["level"]) for r in cluster]
        rank = {key: index for index, key in enumerate(expect)}
        ranks = [rank[k] for k in seen if k in rank]
        inversions = sum(1 for a, b in zip(ranks, ranks[1:]) if b < a)
        inversions_total += inversions
        if inversions == 0:
            perfect_interleave += 1

        ladder = {}
        for r in cluster:
            ladder.setdefault(r["level"], set()).add(r["volume"])
        ladder_key = tuple(
            (level, tuple(sorted(vols))) for level, vols in sorted(ladder.items())
        )
        tiers = tuple(sorted({v for vols in ladder.values() for v in vols}))
        ladders[(n_levels, tiers)] += 1

        detail.append({
            "when": cluster[0]["when"],
            "legs": len(cluster),
            "n": n_levels,
            "anchor": anchor,
            "step": step,
            "law": law,
            "cent": cent,
            "inv": inversions,
            "tiers": tiers,
        })

    total = len(deployments)
    print("=== V1 anchor and step law ===")
    print(f"  step == round(anchor/3000,2) : {step_ok}/{total}")
    print(f"  anchor is a whole cent       : {anchor_cent_ok}/{total}")
    print(f"  B1-S1 == 2*step              : {span_ok}/{total}")
    print(f"  lattice residual max         : {max(lattice_resid):.10f}")
    print(f"  lattice residual p95         : {percentile(lattice_resid,0.95):.10f}")
    print(f"  legs checked                 : {len(lattice_resid)}")
    print()
    print("=== V2 interleave ===")
    print(f"  zero-inversion deployments   : {perfect_interleave}/{total}")
    print(f"  total inversions             : {inversions_total}")
    print()
    print("=== V9 level count and tier volumes ===")
    print(f"  N histogram: {dict(sorted(n_hist.items()))}")
    for key, count in ladders.most_common(30):
        print(f"  n={key[0]:3d} tiers={key[1]}  x{count}")
    print()

    print("=== per-deployment detail ===")
    print("  when                      legs   N     anchor      step       law  a/step  cent inv tiers")
    for d in detail:
        flag = "" if abs(d["step"] - d["law"]) < 5e-9 else "  <-- STEP LAW MISS"
        ratio = d["anchor"] / d["step"] if d["step"] else 0.0
        print(f"  {d['when']}  {d['legs']:4d} {d['n']:3d} {d['anchor']:10.2f} "
              f"{d['step']:9.2f} {d['law']:9.2f} {ratio:7.0f}  {'Y' if d['cent'] else 'N'}  "
              f"{d['inv']:3d} {d['tiers']}{flag}")
    print()

    print("=== step law by N ===")
    for n_value in sorted(n_hist):
        subset = [d for d in detail if d["n"] == n_value]
        hits = sum(1 for d in subset if abs(d["step"] - d["law"]) < 5e-9)
        steps = [d["step"] for d in subset]
        ratios = sorted(d["anchor"] / d["step"] for d in subset if d["step"])
        print(f"  N={n_value:3d} n={len(subset):4d} law_hits={hits:4d} "
              f"step min={min(steps):.2f} max={max(steps):.2f} "
              f"ratio p05={percentile(ratios,0.05):.0f} p50={percentile(ratios,0.50):.0f} "
              f"p95={percentile(ratios,0.95):.0f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
