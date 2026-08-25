from __future__ import annotations

import bisect
import re
from dataclasses import dataclass

from .profiles import ProfileName, get_profile, normalize_price
from .report import MT5Report, OrderRecord


GRID_COMMENT_RE = re.compile(r"^STR ([BS])(\d+)$")


@dataclass(frozen=True)
class GeometryMismatch:
    order_id: int
    cycle_start: str
    comment: str
    field: str
    expected: object
    actual: object


@dataclass(frozen=True)
class GeometryComparison:
    grid_orders: int
    compared_orders: int
    skipped_without_cycle: int
    mismatches: tuple[GeometryMismatch, ...]

    @property
    def is_match(self) -> bool:
        return self.skipped_without_cycle == 0 and not self.mismatches


def _mismatch(
    order: OrderRecord,
    cycle_start: str,
    field: str,
    expected: object,
    actual: object,
) -> GeometryMismatch:
    return GeometryMismatch(
        order_id=order.order_id,
        cycle_start=cycle_start,
        comment=order.comment or "",
        field=field,
        expected=expected,
        actual=actual,
    )


def compare_report_grid_geometry(
    report: MT5Report,
    tick_size: float,
    include_rearms: bool = False,
) -> GeometryComparison:
    if tick_size <= 0:
        raise ValueError("Tick size must be positive")
    deployments = sorted(report.deployments, key=lambda item: item.start)
    orders = sorted(
        (*report.historical_orders, *report.working_orders),
        key=lambda item: (item.open_time, item.order_id),
    )
    grid_orders = [
        order
        for order in orders
        if order.comment and GRID_COMMENT_RE.fullmatch(order.comment)
    ]
    compared = 0
    skipped = 0
    mismatches: list[GeometryMismatch] = []

    def compare_order(order: OrderRecord, deployment: object) -> None:
        nonlocal compared
        cycle_start = deployment.start.isoformat(sep=" ")
        profile = get_profile(ProfileName(deployment.profile_hint))
        match = GRID_COMMENT_RE.fullmatch(order.comment or "")
        assert match is not None
        side = match.group(1)
        level = int(match.group(2))
        compared += 1

        if level > profile.levels_per_side:
            mismatches.append(
                _mismatch(
                    order,
                    cycle_start,
                    "level",
                    f"1..{profile.levels_per_side}",
                    level,
                )
            )
            return
        expected_type = "buy stop" if side == "B" else "sell stop"
        if order.order_type != expected_type:
            mismatches.append(
                _mismatch(
                    order,
                    cycle_start,
                    "order_type",
                    expected_type,
                    order.order_type,
                )
            )
        expected_volume = profile.lot_for_level(level)
        if abs(order.volume - expected_volume) > 1e-9:
            mismatches.append(
                _mismatch(
                    order,
                    cycle_start,
                    "volume",
                    expected_volume,
                    order.volume,
                )
            )
        if order.price is None:
            mismatches.append(
                _mismatch(
                    order,
                    cycle_start,
                    "price",
                    "pending price",
                    None,
                )
            )
            return
        direction = 1.0 if side == "B" else -1.0
        expected_price = normalize_price(
            deployment.anchor + direction * level * deployment.step,
            tick_size,
        )
        if abs(order.price - expected_price) > tick_size / 2 + 1e-12:
            mismatches.append(
                _mismatch(
                    order,
                    cycle_start,
                    "price",
                    expected_price,
                    order.price,
                )
            )

    if include_rearms:
        deployment_starts = [deployment.start for deployment in deployments]
        for order in grid_orders:
            deployment_index = (
                bisect.bisect_right(deployment_starts, order.open_time) - 1
            )
            if deployment_index < 0:
                skipped += 1
                continue
            compare_order(order, deployments[deployment_index])
    else:
        grid_order_times = [order.open_time for order in grid_orders]
        for deployment in deployments:
            first = bisect.bisect_left(grid_order_times, deployment.start)
            last = bisect.bisect_right(grid_order_times, deployment.end)
            for order in grid_orders[first:last]:
                compare_order(order, deployment)

    return GeometryComparison(
        grid_orders=len(grid_orders),
        compared_orders=compared,
        skipped_without_cycle=skipped,
        mismatches=tuple(mismatches),
    )
