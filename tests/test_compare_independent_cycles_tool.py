from datetime import datetime, timedelta, timezone

from tools import compare_independent_cycles


UTC = timezone.utc


def cycle(cycle_id: str, started: datetime) -> list[dict]:
    return [
        {
            "cycle_id": cycle_id,
            "time_utc": started.isoformat(),
            "kind": "cycle_start",
        },
        {
            "cycle_id": cycle_id,
            "time_utc": (started + timedelta(seconds=1)).isoformat(),
            "kind": "cycle_complete",
        },
        {
            "cycle_id": cycle_id,
            "time_utc": (started + timedelta(seconds=2)).isoformat(),
            "kind": "cycle_restart",
        },
    ]


def test_cli_filters_prequalification_and_explicitly_excluded_cycles(
    tmp_path,
    monkeypatch,
) -> None:
    cutoff = datetime(2026, 8, 12, 13, 0, tzinfo=UTC)
    target_events = [
        *cycle("target-old", cutoff - timedelta(minutes=5)),
        *cycle("target-excluded", cutoff + timedelta(minutes=1)),
        *cycle("target-eligible", cutoff + timedelta(minutes=2)),
    ]
    candidate_events = [
        *cycle("candidate-old", cutoff - timedelta(minutes=4)),
        *cycle("candidate-excluded", cutoff + timedelta(minutes=1)),
        *cycle("candidate-eligible", cutoff + timedelta(minutes=2)),
    ]
    captured: dict[str, list[dict]] = {}

    monkeypatch.setattr(
        compare_independent_cycles,
        "load_jsonl_events",
        lambda _: target_events,
    )
    monkeypatch.setattr(
        compare_independent_cycles,
        "load_demo_telemetry_events",
        lambda _: candidate_events,
    )

    def capture_pairs(target, candidate, **_):
        captured["target"] = target
        captured["candidate"] = candidate
        return []

    monkeypatch.setattr(
        compare_independent_cycles,
        "pair_complete_cycles",
        capture_pairs,
    )

    result = compare_independent_cycles.main(
        [
            "--target-events",
            str(tmp_path / "target.jsonl"),
            "--candidate-telemetry",
            str(tmp_path / "candidate.csv"),
            "--pairing",
            "ordinal",
            "--build-id",
            "build-1",
            "--certification-started-utc",
            cutoff.isoformat(),
            "--exclude-target-cycle-id",
            "target-excluded",
            "--exclude-candidate-cycle-id",
            "candidate-excluded",
            "--output-dir",
            str(tmp_path / "reports"),
        ]
    )

    assert result == 2
    assert {
        event["cycle_id"] for event in captured["target"]
    } == {"target-eligible"}
    assert {
        event["cycle_id"] for event in captured["candidate"]
    } == {"candidate-eligible"}


def test_cli_allows_aligned_target_to_start_just_before_cutoff(
    tmp_path,
    monkeypatch,
) -> None:
    cutoff = datetime(2026, 8, 13, 18, 0, tzinfo=UTC)
    target_events = [
        *cycle("target-too-old", cutoff - timedelta(seconds=10)),
        *cycle("target-aligned", cutoff - timedelta(seconds=2)),
    ]
    candidate_events = cycle("candidate-aligned", cutoff)
    captured: dict[str, list[dict]] = {}

    monkeypatch.setattr(
        compare_independent_cycles,
        "load_jsonl_events",
        lambda _: target_events,
    )
    monkeypatch.setattr(
        compare_independent_cycles,
        "load_demo_telemetry_events",
        lambda _: candidate_events,
    )

    def capture_pairs(target, candidate, **_):
        captured["target"] = target
        captured["candidate"] = candidate
        return []

    monkeypatch.setattr(
        compare_independent_cycles,
        "pair_complete_cycles",
        capture_pairs,
    )

    result = compare_independent_cycles.main(
        [
            "--target-events",
            str(tmp_path / "target.jsonl"),
            "--candidate-telemetry",
            str(tmp_path / "candidate.csv"),
            "--pairing",
            "ordinal",
            "--build-id",
            "build-1",
            "--certification-started-utc",
            cutoff.isoformat(),
            "--target-start-grace-seconds",
            "5",
            "--output-dir",
            str(tmp_path / "reports"),
        ]
    )

    assert result == 2
    assert {
        event["cycle_id"] for event in captured["target"]
    } == {"target-aligned"}
    assert {
        event["cycle_id"] for event in captured["candidate"]
    } == {"candidate-aligned"}
