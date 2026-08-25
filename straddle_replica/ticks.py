from __future__ import annotations

import csv
import gzip
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, Sequence


UTC = timezone.utc


@dataclass(frozen=True)
class TickSample:
    time: datetime
    bid: float
    ask: float
    last: float = 0.0
    volume: int = 0
    flags: int = 0


@dataclass(frozen=True)
class TickCoverage:
    count: int
    first_time: datetime | None
    last_time: datetime | None
    large_gap_count: int
    maximum_gap_seconds: float


@dataclass(frozen=True)
class TickArchiveAudit:
    expected_segments: int
    total_ticks: int
    first_time: datetime | None
    last_time: datetime | None
    empty_segments: tuple[str, ...]
    missing_segments: tuple[str, ...]
    missing_data_files: tuple[str, ...]
    invalid_segments: tuple[str, ...]
    large_gap_count: int
    maximum_gap_seconds: float
    is_complete: bool


def server_time_to_utc(server_time: datetime, offset: timedelta) -> datetime:
    if server_time.tzinfo is not None:
        server_time = server_time.replace(tzinfo=None)
    return (server_time - offset).replace(tzinfo=UTC)


def infer_server_offset(
    server_time: datetime, ticks: Sequence[TickSample]
) -> timedelta:
    if not ticks:
        raise ValueError("Tick samples are required")
    best_offset: timedelta | None = None
    best_distance: float | None = None
    for hours in range(-14, 15):
        offset = timedelta(hours=hours)
        candidate = server_time_to_utc(server_time, offset)
        distance = min(abs((candidate - tick.time).total_seconds()) for tick in ticks)
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best_offset = offset
    assert best_offset is not None
    return best_offset


def validate_tick_coverage(
    ticks: Sequence[TickSample], maximum_gap_seconds: float = 300
) -> TickCoverage:
    if not ticks:
        return TickCoverage(0, None, None, 0, 0.0)
    ordered = sorted(ticks, key=lambda tick: tick.time)
    gaps = [
        (current.time - previous.time).total_seconds()
        for previous, current in zip(ordered, ordered[1:])
    ]
    return TickCoverage(
        count=len(ordered),
        first_time=ordered[0].time,
        last_time=ordered[-1].time,
        large_gap_count=sum(gap > maximum_gap_seconds for gap in gaps),
        maximum_gap_seconds=max(gaps, default=0.0),
    )


def iter_time_chunks(
    start_utc: datetime, end_utc: datetime, chunk_days: float = 1
) -> Iterator[tuple[datetime, datetime]]:
    if start_utc.tzinfo is None or end_utc.tzinfo is None:
        raise ValueError("Chunk boundaries must be timezone-aware")
    if start_utc >= end_utc:
        raise ValueError("Start must be before end")
    if chunk_days <= 0:
        raise ValueError("Chunk days must be positive")
    current = start_utc
    delta = timedelta(days=chunk_days)
    while current < end_utc:
        chunk_end = min(current + delta, end_utc)
        yield current, chunk_end
        current = chunk_end


def audit_tick_archive(
    input_directory: Path,
    symbol: str,
    start_utc: datetime,
    end_utc: datetime,
    segment_hours: int = 12,
) -> TickArchiveAudit:
    if start_utc.tzinfo is None or end_utc.tzinfo is None:
        raise ValueError("Archive boundaries must be timezone-aware")
    if segment_hours <= 0:
        raise ValueError("Segment hours must be positive")

    total_ticks = 0
    first_time: datetime | None = None
    last_time: datetime | None = None
    empty_segments: list[str] = []
    missing_segments: list[str] = []
    missing_data_files: list[str] = []
    invalid_segments: list[str] = []
    large_gap_count = 0
    maximum_gap_seconds = 0.0
    expected_segments = 0

    for segment_start, segment_end in iter_time_chunks(
        start_utc.astimezone(UTC),
        end_utc.astimezone(UTC),
        chunk_days=segment_hours / 24,
    ):
        expected_segments += 1
        stem = (
            f"{symbol}_{segment_start:%Y%m%d_%H%M}_"
            f"{segment_end:%Y%m%d_%H%M}.csv"
        )
        data_path = input_directory / f"{stem}.gz"
        coverage_path = input_directory / f"{stem}.coverage.json"
        if not data_path.is_file():
            missing_data_files.append(data_path.name)
        if not coverage_path.is_file():
            missing_segments.append(coverage_path.name)
            continue

        try:
            coverage = json.loads(coverage_path.read_text(encoding="utf-8-sig"))
            count = int(coverage["count"])
            segment_first = (
                datetime.fromisoformat(coverage["first_time"])
                if coverage.get("first_time")
                else None
            )
            segment_last = (
                datetime.fromisoformat(coverage["last_time"])
                if coverage.get("last_time")
                else None
            )
            segment_large_gaps = int(coverage["large_gap_count"])
            segment_maximum_gap = float(coverage["maximum_gap_seconds"])
            if count < 0 or segment_large_gaps < 0 or segment_maximum_gap < 0:
                raise ValueError("Coverage values cannot be negative")
            if count == 0:
                if segment_first is not None or segment_last is not None:
                    raise ValueError("Empty coverage has tick boundaries")
                empty_segments.append(stem)
            else:
                if segment_first is None or segment_last is None:
                    raise ValueError("Non-empty coverage lacks tick boundaries")
                if segment_first.tzinfo is None or segment_last.tzinfo is None:
                    raise ValueError("Tick boundaries must be timezone-aware")
                if not (
                    segment_start <= segment_first <= segment_last <= segment_end
                ):
                    raise ValueError("Tick boundaries are outside the segment")
                first_time = (
                    segment_first
                    if first_time is None
                    else min(first_time, segment_first)
                )
                last_time = (
                    segment_last
                    if last_time is None
                    else max(last_time, segment_last)
                )
            total_ticks += count
            large_gap_count += segment_large_gaps
            maximum_gap_seconds = max(
                maximum_gap_seconds, segment_maximum_gap
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            invalid_segments.append(coverage_path.name)

    is_complete = not (
        missing_segments or missing_data_files or invalid_segments
    )
    return TickArchiveAudit(
        expected_segments=expected_segments,
        total_ticks=total_ticks,
        first_time=first_time,
        last_time=last_time,
        empty_segments=tuple(empty_segments),
        missing_segments=tuple(missing_segments),
        missing_data_files=tuple(missing_data_files),
        invalid_segments=tuple(invalid_segments),
        large_gap_count=large_gap_count,
        maximum_gap_seconds=maximum_gap_seconds,
        is_complete=is_complete,
    )


def iter_tick_archive(
    input_directory: Path,
    symbol: str,
    start_utc: datetime,
    end_utc: datetime,
    segment_hours: int = 12,
) -> Iterator[TickSample]:
    if start_utc.tzinfo is None or end_utc.tzinfo is None:
        raise ValueError("Archive boundaries must be timezone-aware")
    if segment_hours <= 0:
        raise ValueError("Segment hours must be positive")

    last_time: datetime | None = None
    for segment_start, segment_end in iter_time_chunks(
        start_utc.astimezone(UTC),
        end_utc.astimezone(UTC),
        chunk_days=segment_hours / 24,
    ):
        filename = (
            f"{symbol}_{segment_start:%Y%m%d_%H%M}_"
            f"{segment_end:%Y%m%d_%H%M}.csv.gz"
        )
        path = input_directory / filename
        if not path.is_file():
            raise FileNotFoundError(f"Missing tick segment: {path}")
        with gzip.open(path, mode="rt", newline="", encoding="utf-8") as source:
            for row in csv.DictReader(source):
                tick_time = datetime.fromisoformat(row["time_utc"])
                if tick_time.tzinfo is None:
                    raise ValueError(f"Naive tick timestamp in {path}")
                tick_time = tick_time.astimezone(UTC)
                if not segment_start <= tick_time < segment_end:
                    continue
                if last_time is not None and tick_time <= last_time:
                    continue
                last_time = tick_time
                yield TickSample(
                    time=tick_time,
                    bid=float(row["bid"]),
                    ask=float(row["ask"]),
                    last=float(row["last"]),
                    volume=int(row["volume"]),
                    flags=int(row["flags"]),
                )


def download_ticks(
    terminal_path: Path,
    symbol: str,
    start_utc: datetime,
    end_utc: datetime,
) -> list[TickSample]:
    import MetaTrader5 as mt5

    if start_utc.tzinfo is None or end_utc.tzinfo is None:
        raise ValueError("Tick download dates must be timezone-aware UTC datetimes")
    if not mt5.initialize(path=str(terminal_path)):
        raise RuntimeError(f"MetaTrader5 initialize failed: {mt5.last_error()}")
    try:
        raw_ticks = mt5.copy_ticks_range(
            symbol,
            start_utc.astimezone(UTC),
            end_utc.astimezone(UTC),
            mt5.COPY_TICKS_ALL,
        )
        if raw_ticks is None:
            raise RuntimeError(f"Tick download failed: {mt5.last_error()}")
        return [
            TickSample(
                time=datetime.fromtimestamp(
                    float(record["time_msc"]) / 1000,
                    tz=UTC,
                ),
                bid=float(record["bid"]),
                ask=float(record["ask"]),
                last=float(record["last"]),
                volume=int(record["volume"]),
                flags=int(record["flags"]),
            )
            for record in raw_ticks
        ]
    finally:
        mt5.shutdown()


def export_ticks_csv(ticks: Sequence[TickSample], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.suffix.lower() == ".gz":
        destination_context = gzip.open(
            output_path, mode="wt", newline="", encoding="utf-8"
        )
    else:
        destination_context = output_path.open(
            mode="w", newline="", encoding="utf-8"
        )
    with destination_context as destination:
        writer = csv.writer(destination)
        writer.writerow(["time_utc", "bid", "ask", "last", "volume", "flags"])
        for tick in ticks:
            writer.writerow(
                [
                    tick.time.astimezone(UTC).isoformat(),
                    tick.bid,
                    tick.ask,
                    tick.last,
                    tick.volume,
                    tick.flags,
                ]
            )


def download_ticks_to_csv(
    terminal_path: Path,
    symbol: str,
    start_utc: datetime,
    end_utc: datetime,
    output_path: Path,
    chunk_days: float = 1,
    maximum_gap_seconds: float = 300,
) -> TickCoverage:
    import MetaTrader5 as mt5

    if start_utc.tzinfo is None or end_utc.tzinfo is None:
        raise ValueError("Tick download dates must be timezone-aware")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not mt5.initialize(path=str(terminal_path)):
        raise RuntimeError(f"MetaTrader5 initialize failed: {mt5.last_error()}")

    total = 0
    first_time: datetime | None = None
    last_time: datetime | None = None
    last_time_msc: int | None = None
    large_gap_count = 0
    maximum_gap = 0.0
    try:
        if output_path.suffix.lower() == ".gz":
            destination_context = gzip.open(
                output_path, mode="wt", newline="", encoding="utf-8"
            )
        else:
            destination_context = output_path.open(
                mode="w", newline="", encoding="utf-8"
            )
        with destination_context as destination:
            writer = csv.writer(destination)
            writer.writerow(["time_utc", "bid", "ask", "last", "volume", "flags"])
            for chunk_start, chunk_end in iter_time_chunks(
                start_utc.astimezone(UTC),
                end_utc.astimezone(UTC),
                chunk_days,
            ):
                raw_ticks = mt5.copy_ticks_range(
                    symbol,
                    chunk_start,
                    chunk_end,
                    mt5.COPY_TICKS_ALL,
                )
                if raw_ticks is None:
                    raise RuntimeError(
                        f"Tick download failed for {chunk_start}: {mt5.last_error()}"
                    )
                for record in raw_ticks:
                    time_msc = int(record["time_msc"])
                    if last_time_msc is not None and time_msc <= last_time_msc:
                        continue
                    tick_time = datetime.fromtimestamp(time_msc / 1000, tz=UTC)
                    if last_time is not None:
                        gap = (tick_time - last_time).total_seconds()
                        maximum_gap = max(maximum_gap, gap)
                        if gap > maximum_gap_seconds:
                            large_gap_count += 1
                    writer.writerow(
                        [
                            tick_time.isoformat(),
                            float(record["bid"]),
                            float(record["ask"]),
                            float(record["last"]),
                            int(record["volume"]),
                            int(record["flags"]),
                        ]
                    )
                    if first_time is None:
                        first_time = tick_time
                    last_time = tick_time
                    last_time_msc = time_msc
                    total += 1
    finally:
        mt5.shutdown()

    return TickCoverage(
        count=total,
        first_time=first_time,
        last_time=last_time,
        large_gap_count=large_gap_count,
        maximum_gap_seconds=maximum_gap,
    )
