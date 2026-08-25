from __future__ import annotations

from typing import Any, Iterable, Mapping


def basket_candidates(
    snapshots: Iterable[Mapping[str, Any]],
    *,
    trigger_time_msc: int,
    fixed_targets: tuple[float, ...],
) -> dict[str, dict[str, float | int | None]]:
    ordered = sorted(snapshots, key=lambda row: int(row["time_msc"]))
    result: dict[str, dict[str, float | int | None]] = {}
    for target in fixed_targets:
        crossing = next(
            (
                int(row["time_msc"])
                for row in ordered
                if float(row.get("realized") or 0.0)
                + float(row.get("floating") or 0.0)
                >= target
            ),
            None,
        )
        key = f"fixed_{target:g}"
        result[key] = {
            "target": target,
            "first_crossing_msc": crossing,
            "trigger_delay_ms": (
                trigger_time_msc - crossing
                if crossing is not None
                else None
            ),
        }
    return result
