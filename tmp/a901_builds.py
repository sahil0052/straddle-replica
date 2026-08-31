"""Build-fingerprint the 901018 tape by comment family over time.

The empty-comment market orders end abruptly on 2026.07.13 and 'STR CLOSE'
carries the same ~100 ms cadence, which suggests the two are the SAME basket-close
mechanism under two different builds rather than manual operator closes.  This
prints the first/last occurrence and the per-day count of every family so the
build boundaries can be dated, and measures the intra-burst cadence of each so
EA authorship can be separated from hand clicking.
"""
from __future__ import annotations

import collections
import csv
import re
from datetime import datetime
from pathlib import Path


def load(name: str) -> list[dict]:
    return list(csv.DictReader(Path(f"tmp/r901018_{name}.csv").open(encoding="utf-8")))


def norm(value: str | None) -> str:
    return (value or "").strip()


def stamp(text: str) -> datetime | None:
    text = norm(text)
    if not text:
        return None
    return datetime.strptime(text, "%Y.%m.%d %H:%M:%S.%f")


def family(comment: str) -> str:
    comment = norm(comment)
    if not comment:
        return "<empty>"
    if comment.startswith("STR B"):
        return "STR B#"
    if comment.startswith("STR S"):
        return "STR S#"
    if comment.startswith("[sl"):
        return "[sl]"
    if re.match(r"^#\d+ by #\d+$", comment):
        return "close-by"
    return comment


def percentile(values: list[float], q: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round(q * (len(ordered) - 1)))))
    return ordered[index]


def main() -> int:
    orders = load("orders")
    rows = []
    for row in orders:
        when = stamp(row["Open Time"])
        if when is None:
            continue
        rows.append((when, family(row["Comment"]), row))
    rows.sort(key=lambda item: item[0])

    print("=== family first/last occurrence ===")
    span: dict[str, list[datetime]] = {}
    for when, fam, _ in rows:
        span.setdefault(fam, [when, when])
        span[fam][1] = when
    for fam, (first, last) in sorted(span.items(), key=lambda kv: kv[1][0]):
        count = sum(1 for _, f, _ in rows if f == fam)
        print(f"  {fam:12s} n={count:6d}  {first}  ..  {last}")
    print()

    print("=== per-day counts by family ===")
    days = sorted({when.date() for when, _, _ in rows})
    families = ["STR B#", "STR S#", "[sl]", "<empty>", "STR CLOSE", "STR ORB",
                "STR ORS", "STR AVB", "STR AVS", "close-by"]
    header = "  day         " + "".join(f"{f:>10s}" for f in families)
    print(header)
    for day in days:
        counts = collections.Counter(
            f for when, f, _ in rows if when.date() == day
        )
        line = f"  {day}  " + "".join(f"{counts.get(f, 0):10d}" for f in families)
        print(line)
    print()

    print("=== intra-burst cadence of the two close families (ms) ===")
    for fam in ("<empty>", "STR CLOSE"):
        stamps = [when for when, f, _ in rows if f == fam]
        gaps = [
            (b - a).total_seconds() * 1000.0
            for a, b in zip(stamps, stamps[1:])
            if (b - a).total_seconds() * 1000.0 < 2000.0
        ]
        print(
            f"  {fam:10s} n={len(stamps):6d} intra-burst gaps={len(gaps):6d} "
            f"p05={percentile(gaps,0.05):8.1f} p50={percentile(gaps,0.50):8.1f} "
            f"p95={percentile(gaps,0.95):8.1f} min={min(gaps) if gaps else 0:8.1f}"
        )
    print()

    print("=== pending placement cadence, for comparison ===")
    stamps = [when for when, f, _ in rows if f in ("STR B#", "STR S#")]
    gaps = [
        (b - a).total_seconds() * 1000.0
        for a, b in zip(stamps, stamps[1:])
        if 0 < (b - a).total_seconds() * 1000.0 < 2000.0
    ]
    print(
        f"  n={len(stamps)} gaps={len(gaps)} p05={percentile(gaps,0.05):.1f} "
        f"p50={percentile(gaps,0.50):.1f} p95={percentile(gaps,0.95):.1f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
