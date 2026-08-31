"""Era-segment the 901018 tape and re-score V1/V2/V9 against the CORRECT profile.

The first pass scored every deployment against step=round(anchor/3000,2) and got
103/210.  That was the wrong test: the tape is not one configuration.  Clustering
recovered four distinct (N, lot-ladder) signatures, and all four are already in
ProfileCatalog.mqh:

    N=50  lots 0.01/0.03/0.06   ATR step   -> HISTORICAL_50   (line 56)
    N=60  lots 0.01/0.02/0.05   ATR step   -> HISTORICAL_60   (line 68)
    N=30  lots 0.08/0.41/0.82   div 6000   -> AGGRESSIVE_30   (line 80)
    N=30  lots 0.01/0.02/0.05   div 3000   -> LOW_RISK_30     (line 90)
    N=30  lots 0.01/0.06/0.15   div 3000   -> STARWAVE_30     (line 328)

So the step law must be scored per era, tier boundaries must be checked per era,
and the ORB/ORS + AVB/AVS + close-comment families must be located in the era
timeline -- because IsHistoricalProfile() (StraddleEngine.mqh:1540) gates the
crossed-price market recovery on exactly HISTORICAL_50 || HISTORICAL_60.
"""
from __future__ import annotations

import collections
import csv
import re
from datetime import datetime
from pathlib import Path

BURST_GAP_MS = 2000.0
MIN_LEGS = 10

# (levels_per_side, sorted tier volumes) -> (profile name, anchor divisor or None for ATR)
SIGNATURE = {
    (50, (0.01, 0.03, 0.06)): ("HISTORICAL_50", None),
    (60, (0.01, 0.02, 0.05)): ("HISTORICAL_60", None),
    (30, (0.08, 0.41, 0.82)): ("AGGRESSIVE_30", 6000.0),
    (30, (0.01, 0.02, 0.05)): ("LOW_RISK_30", 3000.0),
    (30, (0.01, 0.06, 0.15)): ("STARWAVE_30", 3000.0),
}
# Expected tier boundaries, from ProfileCatalog SetLotTier calls.
BOUNDS = {
    "HISTORICAL_50": [(1, 15, 0.01), (16, 25, 0.03), (26, 50, 0.06)],
    "HISTORICAL_60": [(1, 15, 0.01), (16, 45, 0.02), (46, 60, 0.05)],
    "AGGRESSIVE_30": [(1, 10, 0.08), (11, 20, 0.41), (21, 30, 0.82)],
    "LOW_RISK_30": [(1, 10, 0.01), (11, 20, 0.02), (21, 30, 0.05)],
    "STARWAVE_30": [(1, 10, 0.01), (11, 20, 0.06), (21, 30, 0.15)],
}


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


def parse_volume(text: str) -> float:
    parts = [p.strip() for p in norm(text).split("/") if p.strip()]
    return float(parts[0])


def load_orders() -> list[dict]:
    return list(csv.DictReader(Path("tmp/r901018_orders.csv").open(encoding="utf-8")))


def main() -> int:
    orders = load_orders()
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
        })
    rows.sort(key=lambda item: (item["when"], item["ticket"]))

    clusters: list[list[dict]] = []
    current: list[dict] = []
    for row in rows:
        if current and (row["when"] - current[-1]["when"]).total_seconds() * 1000.0 > BURST_GAP_MS:
            clusters.append(current)
            current = []
        current.append(row)
    if current:
        clusters.append(current)

    deployments = [
        c for c in clusters
        if len(c) >= MIN_LEGS
        and any(r["is_buy"] and r["level"] == 1 for r in c)
        and any(not r["is_buy"] and r["level"] == 1 for r in c)
    ]

    # --- classify each deployment ---------------------------------------------
    records = []
    for cluster in deployments:
        b1 = next(r for r in cluster if r["is_buy"] and r["level"] == 1)
        s1 = next(r for r in cluster if not r["is_buy"] and r["level"] == 1)
        anchor = (b1["price"] + s1["price"]) / 2.0
        step = (b1["price"] - s1["price"]) / 2.0
        n_levels = max(r["level"] for r in cluster)
        tiers = tuple(sorted({r["volume"] for r in cluster}))
        name, divisor = SIGNATURE.get((n_levels, tiers), (None, None))
        records.append({
            "when": cluster[0]["when"],
            "end": cluster[-1]["when"],
            "legs": len(cluster),
            "n": n_levels,
            "anchor": anchor,
            "step": step,
            "tiers": tiers,
            "name": name,
            "divisor": divisor,
            "cluster": cluster,
        })

    # Fragments (a deployment my 2 s gap split, or a cycle cut short) inherit the
    # era of the nearest preceding fully-signed deployment.
    last_full = None
    for record in records:
        if record["name"] is not None:
            last_full = record["name"]
            record["assigned"] = record["name"]
            record["inherited"] = False
        else:
            record["assigned"] = last_full
            record["inherited"] = True
            if last_full in ("HISTORICAL_50", "HISTORICAL_60"):
                record["divisor"] = None
            else:
                record["divisor"] = 6000.0 if last_full == "AGGRESSIVE_30" else 3000.0

    print("=== era timeline (contiguous runs of the same assigned profile) ===")
    runs = []
    for record in records:
        if runs and runs[-1][0] == record["assigned"]:
            runs[-1][2] = record["end"]
            runs[-1][3] += 1
        else:
            runs.append([record["assigned"], record["when"], record["end"], 1])
    for name, start, end, count in runs:
        print(f"  {str(name):14s} {start}  ..  {end}   deployments={count}")
    print()

    print("=== V1 step law, scored under each deployment's own profile ===")
    by_name: dict[str, list[dict]] = collections.defaultdict(list)
    for record in records:
        by_name[str(record["assigned"])].append(record)
    for name, subset in sorted(by_name.items()):
        divisor_mode = [r for r in subset if r["divisor"] is not None]
        atr_mode = [r for r in subset if r["divisor"] is None]
        hits = sum(
            1 for r in divisor_mode
            if abs(r["step"] - round(r["anchor"] / r["divisor"], 2)) < 5e-9
        )
        steps = [r["step"] for r in subset]
        print(f"  {name:14s} n={len(subset):4d} divisor-mode={len(divisor_mode):4d} "
              f"law_hits={hits:4d} atr-mode={len(atr_mode):4d} "
              f"step min={min(steps):.2f} max={max(steps):.2f}")
        for r in divisor_mode:
            want = round(r["anchor"] / r["divisor"], 2)
            if abs(r["step"] - want) >= 5e-9:
                print(f"      MISS {r['when']} anchor={r['anchor']:.2f} "
                      f"step={r['step']:.2f} want={want:.2f} legs={r['legs']} "
                      f"tiers={r['tiers']} inherited={r['inherited']}")
    print()

    print("=== V9 tier boundaries, scored under each deployment's own profile ===")
    for name, subset in sorted(by_name.items()):
        expected = BOUNDS.get(name)
        if expected is None:
            print(f"  {name}: no expected ladder")
            continue
        checked = ok = 0
        misses: collections.Counter = collections.Counter()
        for record in subset:
            for leg in record["cluster"]:
                want = None
                for lo, hi, vol in expected:
                    if lo <= leg["level"] <= hi:
                        want = vol
                        break
                if want is None:
                    continue
                checked += 1
                if abs(leg["volume"] - want) < 1e-9:
                    ok += 1
                else:
                    misses[(leg["level"], leg["volume"], want)] += 1
        pct = 100.0 * ok / checked if checked else 0.0
        print(f"  {name:14s} legs={checked:6d} ladder_ok={ok:6d} ({pct:6.2f}%)")
        for key, count in misses.most_common(8):
            print(f"      level={key[0]:3d} saw={key[1]} want={key[2]} x{count}")
    print()

    print("=== V2 interleave, per era ===")
    for name, subset in sorted(by_name.items()):
        total_inv = 0
        clean = 0
        for record in subset:
            n_levels = record["n"]
            expect = []
            for level in range(1, n_levels + 1):
                expect.append((True, level))
                expect.append((False, level))
            rank = {key: index for index, key in enumerate(expect)}
            ranks = [rank[(r["is_buy"], r["level"])] for r in record["cluster"]]
            inv = sum(1 for a, b in zip(ranks, ranks[1:]) if b < a)
            total_inv += inv
            if inv == 0:
                clean += 1
            else:
                print(f"      INVERSION {record['when']} {name} legs={record['legs']} "
                      f"n={n_levels} inversions={inv}")
        print(f"  {name:14s} zero-inversion={clean}/{len(subset)} total_inversions={total_inv}")
    print()

    # --- locate the non-lattice families inside the era timeline ---------------
    def era_at(when: datetime) -> str:
        chosen = "before-first-deployment"
        for record in records:
            if record["when"] <= when:
                chosen = str(record["assigned"])
            else:
                break
        return chosen

    print("=== non-lattice families vs era ===")
    fams: dict[str, list[datetime]] = collections.defaultdict(list)
    for row in orders:
        comment = norm(row["Comment"])
        when = stamp(row["Open Time"])
        if when is None:
            continue
        if comment in ("STR ORB", "STR ORS", "STR AVB", "STR AVS", "STR CLOSE"):
            fams[comment].append(when)
        elif comment == "" and norm(row["Type"]) in ("buy", "sell"):
            fams["<empty market>"].append(when)
    for fam, stamps in sorted(fams.items()):
        hist = collections.Counter(era_at(w) for w in stamps)
        print(f"  {fam:16s} n={len(stamps):6d}  {dict(hist)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
