from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path


TIME_FORMAT = "%Y.%m.%d %H:%M:%S"


@dataclass(frozen=True)
class TesterOrder:
    open_time: datetime
    order_id: int
    symbol: str
    order_type: str
    volume: float
    filled_volume: float
    price: float | None
    stop_loss: float | None
    take_profit: float | None
    end_time: datetime | None
    state: str
    comment: str


@dataclass(frozen=True)
class TesterDeal:
    time: datetime
    deal_id: int
    symbol: str
    deal_type: str
    direction: str
    volume: float
    price: float
    order_id: int
    commission: float
    swap: float
    profit: float
    balance: float
    comment: str


@dataclass(frozen=True)
class MT5TesterReport:
    orders: tuple[TesterOrder, ...]
    deals: tuple[TesterDeal, ...]


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        del attrs
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._cell is not None:
            assert self._row is not None
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None


def _number(value: str) -> float:
    return float(value.replace(" ", "").replace(",", ""))


def _optional_number(value: str) -> float | None:
    return None if value == "" else _number(value)


def _time(value: str) -> datetime | None:
    if value == "":
        return None
    try:
        return datetime.strptime(value, TIME_FORMAT)
    except ValueError:
        return None


def _volume(value: str) -> tuple[float, float]:
    parts = [part.strip() for part in value.split("/", 1)]
    total = _number(parts[0])
    filled = _number(parts[1]) if len(parts) == 2 else total
    return total, filled


def parse_mt5_tester_report(path: Path) -> MT5TesterReport:
    parser = _TableParser()
    parser.feed(path.read_text(encoding="utf-16"))

    section = ""
    orders: list[TesterOrder] = []
    deals: list[TesterDeal] = []
    for row in parser.rows:
        if "Orders" in row:
            section = "orders"
            continue
        if "Deals" in row:
            section = "deals"
            continue
        row_time = _time(row[0]) if row else None
        if row_time is None:
            continue

        if section == "orders" and len(row) >= 11:
            volume, filled_volume = _volume(row[4])
            orders.append(
                TesterOrder(
                    open_time=row_time,
                    order_id=int(row[1]),
                    symbol=row[2],
                    order_type=row[3],
                    volume=volume,
                    filled_volume=filled_volume,
                    price=_optional_number(row[5]),
                    stop_loss=_optional_number(row[6]),
                    take_profit=_optional_number(row[7]),
                    end_time=_time(row[8]),
                    state=row[9],
                    comment=row[10],
                )
            )
        elif section == "deals" and len(row) >= 13 and row[2]:
            deals.append(
                TesterDeal(
                    time=row_time,
                    deal_id=int(row[1]),
                    symbol=row[2],
                    deal_type=row[3],
                    direction=row[4],
                    volume=_number(row[5]),
                    price=_number(row[6]),
                    order_id=int(row[7]),
                    commission=_number(row[8]),
                    swap=_number(row[9]),
                    profit=_number(row[10]),
                    balance=_number(row[11]),
                    comment=row[12],
                )
            )

    return MT5TesterReport(orders=tuple(orders), deals=tuple(deals))
