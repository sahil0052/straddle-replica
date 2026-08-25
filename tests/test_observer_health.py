import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from straddle_replica.observer_health import analyze_observer_health


UTC = timezone.utc


def test_observer_health_measures_active_ticks_and_zero_drops(
    tmp_path: Path,
) -> None:
    started = datetime(2026, 8, 11, tzinfo=UTC)
    session = tmp_path / "session"
    session.mkdir()
    ticks = [
        {
            "sequence": index + 1,
            "capture_time_utc": (
                started + timedelta(seconds=index)
            ).isoformat(),
            "time_msc": int(
                (started + timedelta(seconds=index)).timestamp() * 1000
            ),
        }
        for index in range(3)
    ]
    (session / "ticks-20260811-00.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in ticks),
        encoding="utf-8",
    )
    (session / "heartbeat.json").write_text(
        json.dumps(
            {
                "capture_time_utc": ticks[-1]["capture_time_utc"],
                "healthy": True,
                "stopped": False,
                "read_only_verified": True,
                "dropped_transactions": 0,
            }
        ),
        encoding="utf-8",
    )

    result = analyze_observer_health(
        session,
        certification_started_utc=started,
    )

    assert result["market_open_hours"] == 0.0006
    assert result["sequence_gaps"] == 0
    assert result["duplicate_sequences"] == 0
    assert result["dropped_transactions"] == 0
    assert result["direct_request_evidence_available"] is False
