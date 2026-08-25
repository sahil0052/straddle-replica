from __future__ import annotations

from dataclasses import dataclass, replace
import re
from typing import Any, Iterable, Mapping, Sequence


LEVEL_PATTERN = re.compile(r"^STR ([BS])(\d+)$")
ENTRY_IN = 0
ENTRY_OUT = 1
ENTRY_INOUT = 2
ENTRY_OUT_BY = 3


def latest_30_base_volume(level: int) -> float:
    if not 1 <= level <= 30:
        raise ValueError("LATEST_30 level must be between 1 and 30")
    if level <= 10:
        return 0.01
    if level <= 20:
        return 0.06
    return 0.15


@dataclass(frozen=True)
class CycleWindow:
    started_msc: int
    deployment_end_msc: int
    anchor: float
    step: float
    order_tickets: tuple[int, ...]
    next_started_msc: int | None = None


@dataclass(frozen=True)
class PositionState:
    position_id: int
    comment: str
    side: str
    level: int
    deal_type: int
    volume: float
    price_open: float


@dataclass(frozen=True)
class CycleState:
    realized: float
    unique_exit_deals: int
    positions: tuple[PositionState, ...]
    position_count: int
    gross_lots: float


@dataclass(frozen=True)
class RecoveryEpisode:
    cycle_started_msc: int
    cycle_next_started_msc: int | None
    side: str
    first_cancel_done_msc: int
    first_double_setup_msc: int
    last_double_setup_msc: int
    replacement_levels: tuple[int, ...]
    volume_multiplier: float
    price_mismatch_count: int


@dataclass
class _MutablePosition:
    position_id: int
    comment: str
    side: str
    level: int
    deal_type: int
    volume: float
    notional: float


def _level_identity(row: Mapping[str, Any]) -> tuple[str, int] | None:
    match = LEVEL_PATTERN.fullmatch(str(row.get("comment") or ""))
    if match is None:
        return None
    level = int(match.group(2))
    if not 1 <= level <= 30:
        return None
    return match.group(1), level


def _number(row: Mapping[str, Any], field: str) -> float:
    return float(row.get(field) or 0.0)


def _integer(row: Mapping[str, Any], field: str) -> int:
    value = row.get(field)
    return int(value) if value is not None else 0


def _matches_source(
    row: Mapping[str, Any],
    *,
    magic: int | None,
    symbol: str | None,
) -> bool:
    if magic is not None and _integer(row, "magic") != magic:
        return False
    if symbol is not None and str(row.get("symbol") or "") != symbol:
        return False
    return True


def find_latest_30_cycles(
    orders: Iterable[Mapping[str, Any]],
    *,
    magic: int | None = 26011001,
    symbol: str | None = "XAUUSD",
    price_tolerance: float = 0.02,
    maximum_deployment_span_msc: int = 120_000,
) -> list[CycleWindow]:
    expected = [
        (side, level, latest_30_base_volume(level))
        for level in range(1, 31)
        for side in ("B", "S")
    ]
    candidates: list[tuple[Mapping[str, Any], str, int]] = []
    for row in orders:
        identity = _level_identity(row)
        if identity is None or not _matches_source(
            row,
            magic=magic,
            symbol=symbol,
        ):
            continue
        candidates.append((row, identity[0], identity[1]))
    candidates.sort(
        key=lambda value: (
            _integer(value[0], "time_setup_msc"),
            _integer(value[0], "ticket"),
        )
    )

    cycles: list[CycleWindow] = []
    for index in range(max(0, len(candidates) - 59)):
        window = candidates[index : index + 60]
        if len(window) != 60:
            continue
        if any(
            side != expected_side
            or level != expected_level
            or abs(
                _number(row, "volume_initial") - expected_volume
            )
            > 1e-9
            for (row, side, level), (
                expected_side,
                expected_level,
                expected_volume,
            ) in zip(window, expected)
        ):
            continue

        started_msc = _integer(window[0][0], "time_setup_msc")
        deployment_end_msc = _integer(
            window[-1][0],
            "time_setup_msc",
        )
        if started_msc <= 0:
            continue
        if deployment_end_msc - started_msc > maximum_deployment_span_msc:
            continue
        if cycles and cycles[-1].started_msc == started_msc:
            continue

        buy_one = _number(window[0][0], "price_open")
        sell_one = _number(window[1][0], "price_open")
        buy_two = _number(window[2][0], "price_open")
        step = buy_two - buy_one
        anchor = (buy_one + sell_one) / 2.0
        if step <= 0:
            continue
        geometry_matches = True
        for row, side, level in window:
            expected_price = anchor + (
                level * step if side == "B" else -level * step
            )
            if abs(_number(row, "price_open") - expected_price) > price_tolerance:
                geometry_matches = False
                break
        if not geometry_matches:
            continue
        cycles.append(
            CycleWindow(
                started_msc=started_msc,
                deployment_end_msc=deployment_end_msc,
                anchor=anchor,
                step=step,
                order_tickets=tuple(
                    _integer(row, "ticket")
                    for row, _, _ in window
                ),
            )
        )

    return [
        replace(
            cycle,
            next_started_msc=(
                cycles[index + 1].started_msc
                if index + 1 < len(cycles)
                else None
            ),
        )
        for index, cycle in enumerate(cycles)
    ]


def reconstruct_cycle_state(
    deals: Iterable[Mapping[str, Any]],
    *,
    cycle_started_msc: int,
    through_msc: int,
    magic: int,
    symbol: str,
) -> CycleState:
    positions: dict[int, _MutablePosition] = {}
    seen_tickets: set[int] = set()
    realized = 0.0
    unique_exit_deals = 0
    ordered = sorted(
        deals,
        key=lambda row: (
            _integer(row, "time_msc"),
            _integer(row, "ticket"),
        ),
    )
    for deal in ordered:
        deal_time_msc = _integer(deal, "time_msc")
        if deal_time_msc < cycle_started_msc:
            continue
        if deal_time_msc >= through_msc:
            break
        if not _matches_source(deal, magic=magic, symbol=symbol):
            continue
        ticket = _integer(deal, "ticket")
        if ticket <= 0 or ticket in seen_tickets:
            continue
        seen_tickets.add(ticket)

        entry_value = deal.get("entry")
        entry = int(entry_value) if entry_value is not None else -1
        position_id = _integer(deal, "position_id")
        volume = _number(deal, "volume")
        price = _number(deal, "price")

        if entry in (ENTRY_OUT, ENTRY_INOUT, ENTRY_OUT_BY):
            realized += sum(
                _number(deal, field)
                for field in ("profit", "swap", "commission", "fee")
            )
            unique_exit_deals += 1
            position = positions.get(position_id)
            if position is not None:
                closed_volume = min(volume, position.volume)
                average_price = (
                    position.notional / position.volume
                    if position.volume > 0
                    else 0.0
                )
                position.volume -= closed_volume
                position.notional -= average_price * closed_volume
                if position.volume <= 1e-9:
                    positions.pop(position_id, None)

        if entry in (ENTRY_IN, ENTRY_INOUT):
            identity = _level_identity(deal)
            deal_type = _integer(deal, "type")
            side = (
                identity[0]
                if identity is not None
                else ("B" if deal_type == 0 else "S")
            )
            level = identity[1] if identity is not None else 0
            position = positions.get(position_id)
            if position is None:
                position = _MutablePosition(
                    position_id=position_id,
                    comment=str(deal.get("comment") or ""),
                    side=side,
                    level=level,
                    deal_type=deal_type,
                    volume=0.0,
                    notional=0.0,
                )
                positions[position_id] = position
            position.volume += volume
            position.notional += volume * price

    immutable_positions = tuple(
        PositionState(
            position_id=position.position_id,
            comment=position.comment,
            side=position.side,
            level=position.level,
            deal_type=position.deal_type,
            volume=position.volume,
            price_open=(
                position.notional / position.volume
                if position.volume > 0
                else 0.0
            ),
        )
        for position in sorted(
            positions.values(),
            key=lambda value: value.position_id,
        )
    )
    return CycleState(
        realized=round(realized, 10),
        unique_exit_deals=unique_exit_deals,
        positions=immutable_positions,
        position_count=len(immutable_positions),
        gross_lots=round(
            sum(position.volume for position in immutable_positions),
            10,
        ),
    )


def _volume_ratio(row: Mapping[str, Any], level: int) -> float:
    return _number(row, "volume_initial") / latest_30_base_volume(level)


def find_recovery_episodes(
    orders: Iterable[Mapping[str, Any]],
    cycles: Sequence[CycleWindow],
    *,
    cancellation_lookback_msc: int = 30_000,
    replacement_group_gap_msc: int = 5_000,
    price_tolerance: float = 0.02,
) -> list[RecoveryEpisode]:
    parsed: list[tuple[Mapping[str, Any], str, int]] = []
    for row in orders:
        identity = _level_identity(row)
        if identity is not None:
            parsed.append((row, identity[0], identity[1]))
    parsed.sort(
        key=lambda value: (
            _integer(value[0], "time_setup_msc"),
            _integer(value[0], "ticket"),
        )
    )

    episodes: list[RecoveryEpisode] = []
    for cycle in cycles:
        cycle_end = cycle.next_started_msc or 2**63 - 1
        cycle_rows = [
            value
            for value in parsed
            if cycle.started_msc
            <= _integer(value[0], "time_setup_msc")
            < cycle_end
        ]
        doubled = [
            value
            for value in cycle_rows
            if abs(_volume_ratio(value[0], value[2]) - 2.0) <= 1e-9
        ]
        groups: list[list[tuple[Mapping[str, Any], str, int]]] = []
        for value in doubled:
            setup_msc = _integer(value[0], "time_setup_msc")
            if (
                not groups
                or value[1] != groups[-1][-1][1]
                or setup_msc
                - _integer(groups[-1][-1][0], "time_setup_msc")
                > replacement_group_gap_msc
            ):
                groups.append([value])
            else:
                groups[-1].append(value)

        for group in groups:
            matched: list[
                tuple[
                    Mapping[str, Any],
                    str,
                    int,
                    Mapping[str, Any],
                ]
            ] = []
            for replacement, side, level in group:
                setup_msc = _integer(
                    replacement,
                    "time_setup_msc",
                )
                prior = [
                    row
                    for row, prior_side, prior_level in cycle_rows
                    if prior_side == side
                    and prior_level == level
                    and abs(_volume_ratio(row, level) - 1.0) <= 1e-9
                    and _integer(row, "state") == 2
                    and setup_msc - cancellation_lookback_msc
                    <= _integer(row, "time_done_msc")
                    <= setup_msc
                ]
                if not prior:
                    continue
                cancelled = max(
                    prior,
                    key=lambda row: _integer(row, "time_done_msc"),
                )
                matched.append(
                    (replacement, side, level, cancelled)
                )
            levels = sorted({value[2] for value in matched})
            if len(levels) < 2:
                continue
            first_setup = min(
                _integer(value[0], "time_setup_msc")
                for value in matched
            )
            last_setup = max(
                _integer(value[0], "time_setup_msc")
                for value in matched
            )
            episodes.append(
                RecoveryEpisode(
                    cycle_started_msc=cycle.started_msc,
                    cycle_next_started_msc=cycle.next_started_msc,
                    side=matched[0][1],
                    first_cancel_done_msc=min(
                        _integer(value[3], "time_done_msc")
                        for value in matched
                    ),
                    first_double_setup_msc=first_setup,
                    last_double_setup_msc=last_setup,
                    replacement_levels=tuple(levels),
                    volume_multiplier=2.0,
                    price_mismatch_count=sum(
                        abs(
                            _number(replacement, "price_open")
                            - _number(cancelled, "price_open")
                        )
                        > price_tolerance
                        for replacement, _, _, cancelled in matched
                    ),
                )
            )
    return episodes


def recovery_level_volume_sequences(
    orders: Iterable[Mapping[str, Any]],
    episode: RecoveryEpisode,
) -> dict[str, tuple[float, ...]]:
    cycle_end = episode.cycle_next_started_msc or 2**63 - 1
    sequences: dict[str, list[tuple[int, int, float]]] = {}
    for row in orders:
        identity = _level_identity(row)
        if identity is None or identity[0] != episode.side:
            continue
        setup_msc = _integer(row, "time_setup_msc")
        if not episode.first_double_setup_msc <= setup_msc < cycle_end:
            continue
        ratio = _volume_ratio(row, identity[1])
        if abs(ratio - 1.0) > 1e-9 and abs(ratio - 2.0) > 1e-9:
            continue
        comment = f"STR {identity[0]}{identity[1]}"
        sequences.setdefault(comment, []).append(
            (setup_msc, _integer(row, "ticket"), round(ratio, 10))
        )
    return {
        comment: tuple(
            value[2]
            for value in sorted(values)
        )
        for comment, values in sequences.items()
    }
