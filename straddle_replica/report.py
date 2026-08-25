from __future__ import annotations

import csv
import re
import statistics
import zipfile
from dataclasses import dataclass, fields
from datetime import datetime
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET


NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
CELL_REF_RE = re.compile(r"([A-Z]+)(\d+)")
TIME_RE = re.compile(r"^\d{4}\.\d{2}\.\d{2} \d{2}:\d{2}:\d{2}\.\d{3}$")
GRID_COMMENT_RE = re.compile(r"^STR ([BS])(\d+)$")
TIME_FORMAT = "%Y.%m.%d %H:%M:%S.%f"
DEPLOYMENT_FRAGMENT_WINDOW_SECONDS = 60
PROFILE_LEVELS = {
    "HISTORICAL_50": 50,
    "HISTORICAL_60": 60,
    "AGGRESSIVE_30": 30,
    "LOW_RISK_30": 30,
    "LATEST_30": 30,
}


@dataclass(frozen=True)
class PositionRecord:
    row: int
    open_time: datetime
    position_id: int
    symbol: str
    side: str
    volume: float
    open_price: float
    stop_loss: float | None
    take_profit: float | None
    close_time: datetime | None
    close_price: float | None
    commission: float
    swap: float
    profit: float
    comment: str | None = None


@dataclass(frozen=True)
class OrderRecord:
    row: int
    open_time: datetime
    order_id: int
    symbol: str | None
    order_type: str
    volume: float
    filled_volume: float
    price: float | None
    stop_loss: float | None
    take_profit: float | None
    end_time: datetime | None
    state: str | None
    comment: str | None


@dataclass(frozen=True)
class DealRecord:
    row: int
    time: datetime
    deal_id: int
    symbol: str | None
    deal_type: str
    direction: str | None
    volume: float
    price: float | None
    order_id: int | None
    commission: float
    fee: float
    swap: float
    profit: float
    balance: float
    comment: str | None


@dataclass(frozen=True)
class DeploymentRecord:
    start: datetime
    end: datetime
    levels_per_side: int
    anchor: float
    step: float
    first_gap: float | None
    initial_order_count: int
    profile_hint: str


@dataclass(frozen=True)
class MT5Report:
    metadata: dict[str, str]
    closed_positions: tuple[PositionRecord, ...]
    open_positions: tuple[PositionRecord, ...]
    historical_orders: tuple[OrderRecord, ...]
    working_orders: tuple[OrderRecord, ...]
    deals: tuple[DealRecord, ...]
    deployments: tuple[DeploymentRecord, ...]

    @property
    def total_trades(self) -> int:
        return len(self.closed_positions) + len(self.open_positions)


def _column_index(cell_ref: str) -> int:
    match = CELL_REF_RE.fullmatch(cell_ref)
    if not match:
        raise ValueError(f"Invalid cell reference: {cell_ref}")
    result = 0
    for character in match.group(1):
        result = result * 26 + ord(character) - ord("A") + 1
    return result - 1


def _read_shared_strings(workbook_path: Path) -> list[str]:
    strings: list[str] = []
    with zipfile.ZipFile(workbook_path) as archive:
        with archive.open("xl/sharedStrings.xml") as source:
            for _, element in ET.iterparse(source, events=("end",)):
                if element.tag != f"{NS}si":
                    continue
                strings.append(
                    "".join(
                        node.text or ""
                        for node in element.iter()
                        if node.tag == f"{NS}t"
                    )
                )
                element.clear()
    return strings


def _parse_number(raw: str | None) -> object | None:
    if raw in (None, ""):
        return None
    try:
        value = float(raw)
    except ValueError:
        return raw
    return int(value) if value.is_integer() else value


def _iter_rows(
    workbook_path: Path, shared_strings: list[str], max_columns: int = 16
) -> Iterable[tuple[int, list[object | None]]]:
    with zipfile.ZipFile(workbook_path) as archive:
        with archive.open("xl/worksheets/sheet1.xml") as source:
            for _, element in ET.iterparse(source, events=("end",)):
                if element.tag != f"{NS}row":
                    continue
                row_number = int(element.attrib["r"])
                values: list[object | None] = [None] * max_columns
                for cell in element.findall(f"{NS}c"):
                    index = _column_index(cell.attrib["r"])
                    if index >= max_columns:
                        continue
                    cell_type = cell.attrib.get("t")
                    value_node = cell.find(f"{NS}v")
                    raw = value_node.text if value_node is not None else None
                    if raw is None:
                        value: object | None = None
                    elif cell_type == "s":
                        value = shared_strings[int(raw)]
                    elif cell_type == "b":
                        value = raw == "1"
                    else:
                        value = _parse_number(raw)
                    values[index] = value
                yield row_number, values
                element.clear()


def _time(value: object | None) -> datetime | None:
    if not isinstance(value, str) or not TIME_RE.match(value):
        return None
    return datetime.strptime(value, TIME_FORMAT)


def _float(value: object | None, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    return float(str(value).replace(" ", "").replace(",", ""))


def _optional_float(value: object | None) -> float | None:
    try:
        return None if value in (None, "") else _float(value)
    except ValueError:
        return None


def _integer(value: object | None) -> int | None:
    if value in (None, ""):
        return None
    return int(float(value))


def _volume(value: object | None) -> tuple[float, float]:
    if value in (None, ""):
        return 0.0, 0.0
    parts = [part.strip() for part in str(value).split("/", 1)]
    volume = float(parts[0])
    filled = float(parts[1]) if len(parts) == 2 else volume
    return volume, filled


def _parse_position(
    row: int, values: list[object | None], is_open: bool
) -> PositionRecord | None:
    open_time = _time(values[0])
    if open_time is None:
        return None
    position_id = _integer(values[1])
    if position_id is None:
        return None
    volume, _ = _volume(values[4])
    if is_open:
        return PositionRecord(
            row,
            open_time,
            position_id,
            str(values[2]),
            str(values[3]),
            volume,
            _float(values[5]),
            _optional_float(values[6]),
            _optional_float(values[7]),
            None,
            _optional_float(values[8]),
            0.0,
            _float(values[9]),
            _float(values[11]),
            str(values[12]) if values[12] is not None else None,
        )
    return PositionRecord(
        row,
        open_time,
        position_id,
        str(values[2]),
        str(values[3]),
        volume,
        _float(values[5]),
        _optional_float(values[6]),
        _optional_float(values[7]),
        _time(values[8]),
        _optional_float(values[9]),
        _float(values[10]),
        _float(values[11]),
        _float(values[12]),
    )


def _parse_order(
    row: int, values: list[object | None], is_working: bool
) -> OrderRecord | None:
    open_time = _time(values[0])
    if open_time is None:
        return None
    order_id = _integer(values[1])
    if order_id is None:
        return None
    volume, filled = _volume(values[4])
    return OrderRecord(
        row,
        open_time,
        order_id,
        str(values[2]) if values[2] is not None else None,
        str(values[3]),
        volume,
        filled,
        _optional_float(values[5]),
        _optional_float(values[6]),
        _optional_float(values[7]),
        None if is_working else _time(values[8]),
        str(values[9]) if values[9] is not None else None,
        str(values[11]) if values[11] is not None else None,
    )


def _parse_deal(row: int, values: list[object | None]) -> DealRecord | None:
    deal_time = _time(values[0])
    if deal_time is None:
        return None
    deal_id = _integer(values[1])
    if deal_id is None:
        return None
    volume, _ = _volume(values[5])
    return DealRecord(
        row,
        deal_time,
        deal_id,
        str(values[2]) if values[2] is not None else None,
        str(values[3]),
        str(values[4]) if values[4] is not None else None,
        volume,
        _optional_float(values[6]),
        _integer(values[7]),
        _float(values[8]),
        _float(values[9]),
        _float(values[10]),
        _float(values[11]),
        _float(values[12]),
        str(values[13]) if values[13] is not None else None,
    )


def _side_step(levels: dict[str, OrderRecord], side: str) -> float | None:
    ordered = sorted(
        (
            (int(key[1:]), order.price)
            for key, order in levels.items()
            if key.startswith(side) and order.price is not None
        ),
        key=lambda item: item[0],
    )
    differences: list[float] = []
    for (_, previous), (_, current) in zip(ordered, ordered[1:]):
        difference = current - previous if side == "B" else previous - current
        if difference > 0:
            differences.append(difference)
    return statistics.median(differences) if differences else None


def _profile_hint(levels: dict[str, OrderRecord]) -> str:
    maximum_level = max((int(key[1:]) for key in levels), default=0)
    maximum_volume = max((order.volume for order in levels.values()), default=0.0)
    if maximum_volume >= 0.4:
        return "AGGRESSIVE_30"
    if maximum_level >= 55:
        return "HISTORICAL_60"
    if maximum_level >= 40:
        return "HISTORICAL_50"
    if maximum_volume >= 0.1:
        return "LATEST_30"
    return "LOW_RISK_30"


def _next_grid_comment(comment: str | None) -> str | None:
    match = GRID_COMMENT_RE.fullmatch(comment or "")
    if match is None:
        return None
    side = match.group(1)
    level = int(match.group(2))
    return f"STR S{level}" if side == "B" else f"STR B{level + 1}"


def _detect_deployments(orders: list[OrderRecord]) -> list[DeploymentRecord]:
    grid_orders = sorted(
        (
            order
            for order in orders
            if order.order_type in {"buy stop", "sell stop"}
            and order.comment
            and GRID_COMMENT_RE.fullmatch(order.comment)
        ),
        key=lambda order: (order.open_time, order.order_id),
    )
    raw_clusters: list[list[OrderRecord]] = []
    cluster: list[OrderRecord] = []
    for order in grid_orders:
        if not cluster or (order.open_time - cluster[-1].open_time).total_seconds() <= 2:
            cluster.append(order)
        else:
            raw_clusters.append(cluster)
            cluster = [order]
    if cluster:
        raw_clusters.append(cluster)

    merged_clusters: list[list[OrderRecord]] = []
    index = 0
    while index < len(raw_clusters):
        cluster = list(raw_clusters[index])
        while index + 1 < len(raw_clusters):
            next_cluster = raw_clusters[index + 1]
            elapsed = (
                next_cluster[-1].open_time - cluster[0].open_time
            ).total_seconds()
            if elapsed > DEPLOYMENT_FRAGMENT_WINDOW_SECONDS:
                break
            if _next_grid_comment(cluster[-1].comment) != next_cluster[0].comment:
                break
            cluster.extend(next_cluster)
            index += 1
        merged_clusters.append(cluster)
        index += 1

    deployments: list[DeploymentRecord] = []
    for cluster in merged_clusters:
        unique: dict[str, OrderRecord] = {}
        for order in cluster:
            unique.setdefault((order.comment or "").removeprefix("STR "), order)
        buy_count = sum(key.startswith("B") for key in unique)
        sell_count = sum(key.startswith("S") for key in unique)
        if len(unique) < 40 or buy_count < 20 or sell_count < 20:
            continue
        buy_step = _side_step(unique, "B")
        sell_step = _side_step(unique, "S")
        steps = [step for step in (buy_step, sell_step) if step is not None]
        if not steps:
            continue
        step = statistics.median(steps)
        anchor_candidates: list[float] = []
        for key, order in unique.items():
            if order.price is None:
                continue
            level = int(key[1:])
            anchor_candidates.append(
                order.price - level * step
                if key.startswith("B")
                else order.price + level * step
            )
        anchor = statistics.median(anchor_candidates)
        buy_one = unique.get("B1")
        sell_one = unique.get("S1")
        first_gap = (
            buy_one.price - sell_one.price
            if buy_one
            and sell_one
            and buy_one.price is not None
            and sell_one.price is not None
            else None
        )
        profile_hint = _profile_hint(unique)
        levels_per_side = PROFILE_LEVELS[profile_hint]
        deployments.append(
            DeploymentRecord(
                start=cluster[0].open_time,
                end=cluster[-1].open_time,
                levels_per_side=levels_per_side,
                anchor=round(anchor, 8),
                step=round(step, 8),
                first_gap=round(first_gap, 8) if first_gap is not None else None,
                initial_order_count=len(cluster),
                profile_hint=profile_hint,
            )
        )
    return deployments


def parse_mt5_report(workbook_path: Path) -> MT5Report:
    shared_strings = _read_shared_strings(workbook_path)
    metadata: dict[str, str] = {}
    closed_positions: list[PositionRecord] = []
    open_positions: list[PositionRecord] = []
    historical_orders: list[OrderRecord] = []
    working_orders: list[OrderRecord] = []
    deals: list[DealRecord] = []
    section: str | None = None
    section_names = {
        "Positions",
        "Orders",
        "Deals",
        "Open Positions",
        "Working Orders",
        "Results",
    }

    for row, values in _iter_rows(workbook_path, shared_strings):
        first = values[0]
        if isinstance(first, str) and first in section_names:
            section = first
            continue
        if row in {2, 3, 4, 5} and isinstance(first, str):
            value = next(
                (candidate for candidate in values[1:] if candidate not in (None, "")),
                "",
            )
            metadata[first.rstrip(":").lower()] = str(value)
        if section == "Positions":
            position = _parse_position(row, values, False)
            if position:
                closed_positions.append(position)
        elif section == "Open Positions":
            position = _parse_position(row, values, True)
            if position:
                open_positions.append(position)
        elif section == "Orders":
            order = _parse_order(row, values, False)
            if order:
                historical_orders.append(order)
        elif section == "Working Orders":
            order = _parse_order(row, values, True)
            if order:
                working_orders.append(order)
        elif section == "Deals":
            deal = _parse_deal(row, values)
            if deal:
                deals.append(deal)

    order_by_id = {order.order_id: order for order in historical_orders}
    closed_positions = [
        PositionRecord(
            **{
                **position.__dict__,
                "comment": (
                    order_by_id[position.position_id].comment
                    if position.position_id in order_by_id
                    else None
                ),
            }
        )
        for position in closed_positions
    ]

    return MT5Report(
        metadata=metadata,
        closed_positions=tuple(closed_positions),
        open_positions=tuple(open_positions),
        historical_orders=tuple(historical_orders),
        working_orders=tuple(working_orders),
        deals=tuple(deals),
        deployments=tuple(
            _detect_deployments([*historical_orders, *working_orders])
        ),
    )


def _write_records(path: Path, records: Iterable[object]) -> None:
    records = tuple(records)
    if not records:
        path.write_text("", encoding="utf-8")
        return
    names = [field.name for field in fields(records[0])]
    with path.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=names)
        writer.writeheader()
        for record in records:
            row = {
                name: (
                    value.isoformat(sep=" ")
                    if isinstance(value := getattr(record, name), datetime)
                    else value
                )
                for name in names
            }
            writer.writerow(row)


def export_golden_dataset(report: MT5Report, output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "positions": output_dir / "positions.csv",
        "open_positions": output_dir / "open_positions.csv",
        "orders": output_dir / "orders.csv",
        "working_orders": output_dir / "working_orders.csv",
        "deals": output_dir / "deals.csv",
        "deployments": output_dir / "deployments.csv",
    }
    _write_records(outputs["positions"], report.closed_positions)
    _write_records(outputs["open_positions"], report.open_positions)
    _write_records(outputs["orders"], report.historical_orders)
    _write_records(outputs["working_orders"], report.working_orders)
    _write_records(outputs["deals"], report.deals)
    _write_records(outputs["deployments"], report.deployments)
    return outputs
