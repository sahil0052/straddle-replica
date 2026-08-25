import gzip
import json
from datetime import datetime, timedelta, timezone

from straddle_replica.ticks import (
    TickSample,
    audit_tick_archive,
    export_ticks_csv,
    infer_server_offset,
    iter_tick_archive,
    iter_time_chunks,
    server_time_to_utc,
    validate_tick_coverage,
)


UTC = timezone.utc


def test_infers_whole_hour_server_offset_from_known_fill():
    server_time = datetime(2026, 7, 30, 17, 15, 0)
    ticks = [
        TickSample(datetime(2026, 7, 30, 14, 14, 59, tzinfo=UTC), 4090.0, 4090.3),
        TickSample(datetime(2026, 7, 30, 14, 15, 0, tzinfo=UTC), 4090.8, 4091.1),
    ]

    assert infer_server_offset(server_time, ticks) == timedelta(hours=3)
    assert server_time_to_utc(server_time, timedelta(hours=3)) == ticks[1].time


def test_tick_coverage_reports_boundaries_and_large_gaps():
    ticks = [
        TickSample(datetime(2026, 7, 30, 10, 0, 0, tzinfo=UTC), 1, 2),
        TickSample(datetime(2026, 7, 30, 10, 0, 1, tzinfo=UTC), 1, 2),
        TickSample(datetime(2026, 7, 30, 10, 1, 0, tzinfo=UTC), 1, 2),
    ]

    coverage = validate_tick_coverage(ticks, maximum_gap_seconds=30)

    assert coverage.count == 3
    assert coverage.first_time == ticks[0].time
    assert coverage.last_time == ticks[-1].time
    assert coverage.large_gap_count == 1
    assert coverage.maximum_gap_seconds == 59


def test_time_chunks_cover_range_without_overlap():
    start = datetime(2026, 7, 1, tzinfo=UTC)
    end = datetime(2026, 7, 3, 12, tzinfo=UTC)

    chunks = list(iter_time_chunks(start, end, chunk_days=1))

    assert chunks == [
        (start, datetime(2026, 7, 2, tzinfo=UTC)),
        (datetime(2026, 7, 2, tzinfo=UTC), datetime(2026, 7, 3, tzinfo=UTC)),
        (datetime(2026, 7, 3, tzinfo=UTC), end),
    ]


def test_time_chunks_support_subday_downloads():
    start = datetime(2026, 7, 1, tzinfo=UTC)
    end = datetime(2026, 7, 2, tzinfo=UTC)

    chunks = list(iter_time_chunks(start, end, chunk_days=0.5))

    assert chunks == [
        (start, datetime(2026, 7, 1, 12, tzinfo=UTC)),
        (datetime(2026, 7, 1, 12, tzinfo=UTC), end),
    ]


def test_tick_export_supports_gzip(tmp_path):
    output = tmp_path / "ticks.csv.gz"
    export_ticks_csv(
        [TickSample(datetime(2026, 7, 30, 10, tzinfo=UTC), 1.0, 1.1)],
        output,
    )

    with gzip.open(output, "rt", encoding="utf-8") as source:
        lines = source.readlines()
    assert len(lines) == 2
    assert lines[0].startswith("time_utc,bid,ask")


def test_tick_archive_audit_requires_every_segment_and_data_file(tmp_path):
    start = datetime(2026, 7, 1, tzinfo=UTC)
    end = datetime(2026, 7, 2, tzinfo=UTC)
    for segment_start, segment_end in iter_time_chunks(start, end, chunk_days=0.5):
        stem = (
            f"XAUUSD_{segment_start:%Y%m%d_%H%M}_"
            f"{segment_end:%Y%m%d_%H%M}.csv"
        )
        (tmp_path / f"{stem}.gz").write_bytes(b"placeholder")
        (tmp_path / f"{stem}.coverage.json").write_text(
            json.dumps(
                {
                    "count": 10,
                    "first_time": segment_start.isoformat(),
                    "last_time": (segment_end - timedelta(seconds=1)).isoformat(),
                    "large_gap_count": 0,
                    "maximum_gap_seconds": 1.0,
                }
            ),
            encoding="utf-8",
        )

    audit = audit_tick_archive(
        tmp_path,
        symbol="XAUUSD",
        start_utc=start,
        end_utc=end,
        segment_hours=12,
    )

    assert audit.is_complete
    assert audit.expected_segments == 2
    assert audit.total_ticks == 20
    assert audit.missing_segments == ()
    assert audit.missing_data_files == ()

    next(tmp_path.glob("*.csv.gz")).unlink()
    incomplete = audit_tick_archive(
        tmp_path,
        symbol="XAUUSD",
        start_utc=start,
        end_utc=end,
        segment_hours=12,
    )
    assert not incomplete.is_complete
    assert len(incomplete.missing_data_files) == 1


def test_tick_archive_iterator_reads_segments_in_order(tmp_path):
    start = datetime(2026, 7, 1, tzinfo=UTC)
    middle = start + timedelta(hours=12)
    end = start + timedelta(days=1)
    first = TickSample(start + timedelta(seconds=1), 4100.0, 4100.2)
    second = TickSample(middle + timedelta(seconds=1), 4101.0, 4101.2)
    export_ticks_csv(
        [first],
        tmp_path / "XAUUSD_20260701_0000_20260701_1200.csv.gz",
    )
    export_ticks_csv(
        [second],
        tmp_path / "XAUUSD_20260701_1200_20260702_0000.csv.gz",
    )

    ticks = list(
        iter_tick_archive(
            tmp_path,
            symbol="XAUUSD",
            start_utc=start,
            end_utc=end,
            segment_hours=12,
        )
    )

    assert ticks == [first, second]
