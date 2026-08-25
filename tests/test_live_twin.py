from __future__ import annotations

from datetime import datetime, timedelta, timezone

from straddle_replica.canonical_events import CanonicalizationResult
from straddle_replica.live_twin import (
    compare_paired_cycles,
    load_demo_telemetry_events,
    load_demo_telemetry_stream,
    load_jsonl_events,
)


UTC = timezone.utc


def lot_for_level(level: int) -> float:
    if level <= 10:
        return 0.01
    if level <= 20:
        return 0.06
    return 0.15


def deployment_events(
    *,
    cycle_id: str,
    start: datetime,
    anchor: float = 4080.0,
    step: float = 1.36,
) -> list[dict]:
    events: list[dict] = []
    for level in range(1, 31):
        for side in ("B", "S"):
            index = (level - 1) * 2 + (0 if side == "B" else 1)
            events.append(
                {
                    "cycle_id": cycle_id,
                    "time_utc": (
                        start + timedelta(milliseconds=index * 100)
                    ).isoformat(),
                    "kind": "pending_request",
                    "comment": f"STR {side}{level}",
                    "side": "buy" if side == "B" else "sell",
                    "volume": lot_for_level(level),
                    "price": anchor
                    + (1 if side == "B" else -1) * level * step,
                    "sl": 0.0,
                    "tp": 0.0,
                    "commission": 0.0,
                    "swap": 0.0,
                    "profit": 0.0,
                }
            )
    return events


def complete_cycle(
    events: list[dict],
    *,
    time: datetime,
    demo: bool = False,
) -> None:
    events.append(
        {
            "cycle_id": events[0]["cycle_id"],
            "time_utc": time.isoformat(),
            "kind": "shadow_reset_complete" if demo else "cycle_complete",
            "comment": "",
            "side": "",
            "volume": 0.0,
            "price": 0.0,
            "sl": 0.0,
            "tp": 0.0,
            "retcode": 0,
            "commission": 0.0,
            "swap": 0.0,
            "profit": 0.0,
        }
    )


def test_paired_cycle_passes_with_exact_decisions_and_tolerated_fill() -> None:
    start = datetime(2026, 8, 4, 14, 0, tzinfo=UTC)
    target = deployment_events(cycle_id="cycle-1", start=start)
    demo = deployment_events(
        cycle_id="cycle-1",
        start=start + timedelta(milliseconds=300),
    )
    target.append(
        {
            "cycle_id": "cycle-1",
            "time_utc": (start + timedelta(seconds=30)).isoformat(),
            "kind": "fill",
            "comment": "STR B1",
            "side": "buy",
            "volume": 0.01,
            "price": 4081.36,
            "sl": 0.0,
            "tp": 0.0,
            "commission": -0.05,
            "swap": 0.0,
            "profit": 0.0,
        }
    )
    demo.append(
        {
            **target[-1],
            "time_utc": (
                start + timedelta(seconds=30, milliseconds=800)
            ).isoformat(),
            "price": 4081.37,
        }
    )
    complete_cycle(target, time=start + timedelta(seconds=60))
    complete_cycle(
        demo,
        time=start + timedelta(seconds=59),
        demo=True,
    )

    report = compare_paired_cycles(
        target,
        demo,
        tick_size=0.01,
        time_tolerance_seconds=1.0,
    )

    assert report["status"] == "PASS"
    assert report["deterministic_mismatch_count"] == 0
    assert report["execution_mismatch_count"] == 0


def test_paired_cycle_fails_for_missing_or_duplicate_slot() -> None:
    start = datetime(2026, 8, 4, 14, 0, tzinfo=UTC)
    target = deployment_events(cycle_id="cycle-1", start=start)
    demo = deployment_events(cycle_id="cycle-1", start=start)
    demo = [
        event for event in demo if event["comment"] != "STR B1"
    ]
    demo.append({**demo[0], "comment": "STR S1"})
    complete_cycle(target, time=start + timedelta(seconds=60))
    complete_cycle(demo, time=start + timedelta(seconds=59), demo=True)

    report = compare_paired_cycles(
        target,
        demo,
        tick_size=0.01,
        time_tolerance_seconds=1.0,
    )

    assert report["status"] == "FAIL"
    assert "STR B1" in report["deployment"]["demo_missing_slots"]
    assert "STR S1" in report["deployment"]["demo_duplicate_slots"]
    assert report["fidelity"]["strict"]["f1_percent"] < 100.0


def test_paired_cycle_fails_when_decision_sequence_changes() -> None:
    start = datetime(2026, 8, 4, 14, 0, tzinfo=UTC)
    target = deployment_events(cycle_id="cycle-1", start=start)
    demo = deployment_events(cycle_id="cycle-1", start=start)
    demo[0], demo[1] = demo[1], demo[0]
    complete_cycle(target, time=start + timedelta(seconds=60))
    complete_cycle(demo, time=start + timedelta(seconds=59), demo=True)

    report = compare_paired_cycles(
        target,
        demo,
        tick_size=0.01,
        time_tolerance_seconds=1.0,
    )

    assert report["status"] == "FAIL"
    assert report["deployment"]["sequence_match"] is False


def test_fill_execution_difference_does_not_fail_logic() -> None:
    start = datetime(2026, 8, 4, 14, 0, tzinfo=UTC)
    target = deployment_events(cycle_id="cycle-1", start=start)
    demo = deployment_events(cycle_id="cycle-1", start=start)
    target.append(
        {
            "cycle_id": "cycle-1",
            "time_utc": (start + timedelta(seconds=30)).isoformat(),
            "kind": "fill",
            "comment": "STR B1",
            "side": "buy",
            "volume": 0.01,
            "price": 4081.36,
            "sl": 0.0,
            "tp": 0.0,
            "commission": -0.05,
            "swap": 0.0,
            "profit": 0.0,
        }
    )
    demo.append(
        {
            **target[-1],
            "time_utc": (start + timedelta(seconds=32)).isoformat(),
            "price": 4081.38,
        }
    )
    complete_cycle(target, time=start + timedelta(seconds=60))
    complete_cycle(demo, time=start + timedelta(seconds=59), demo=True)

    report = compare_paired_cycles(
        target,
        demo,
        tick_size=0.01,
        time_tolerance_seconds=1.0,
    )

    assert report["status"] == "PASS"
    assert report["logic_status"] == "PASS"
    assert report["execution_status"] == "DIFFERENT"
    assert report["execution_mismatch_count"] == 1
    assert report["deterministic_mismatch_count"] == 0


def test_unpaired_cycle_is_reported_explicitly() -> None:
    start = datetime(2026, 8, 4, 14, 0, tzinfo=UTC)

    report = compare_paired_cycles(
        deployment_events(cycle_id="target-cycle", start=start),
        deployment_events(cycle_id="demo-cycle", start=start),
        tick_size=0.01,
        time_tolerance_seconds=1.0,
    )

    assert report["status"] == "UNPAIRED"


def test_active_cycle_is_invalid_until_both_lifecycles_complete() -> None:
    start = datetime(2026, 8, 4, 14, 0, tzinfo=UTC)

    report = compare_paired_cycles(
        deployment_events(cycle_id="cycle-1", start=start),
        deployment_events(cycle_id="cycle-1", start=start),
        tick_size=0.01,
        time_tolerance_seconds=1.0,
    )

    assert report["status"] == "INVALID"
    assert report["reason"] == "Cycle lifecycle is not complete"


def test_valid_rearm_does_not_count_as_duplicate_deployment_slot() -> None:
    start = datetime(2026, 8, 4, 14, 0, tzinfo=UTC)
    target = deployment_events(cycle_id="cycle-1", start=start)
    demo = deployment_events(cycle_id="cycle-1", start=start)
    stop = {
        "cycle_id": "cycle-1",
        "time_utc": (start + timedelta(seconds=20)).isoformat(),
        "kind": "stop_exit",
        "comment": "STR B1",
        "side": "buy",
        "volume": 0.01,
        "price": 4081.50,
        "sl": 0.0,
        "tp": 0.0,
        "commission": -0.05,
        "swap": 0.0,
        "profit": 0.14,
    }
    rearm = {
        "cycle_id": "cycle-1",
        "time_utc": (start + timedelta(seconds=40)).isoformat(),
        "kind": "pending_request",
        "comment": "STR B1",
        "side": "buy",
        "volume": 0.01,
        "price": 4081.36,
        "sl": 0.0,
        "tp": 0.0,
        "retcode": 10008,
    }
    target.extend([stop, rearm])
    demo.extend([stop, rearm])
    complete_cycle(target, time=start + timedelta(seconds=60))
    complete_cycle(demo, time=start + timedelta(seconds=59), demo=True)

    report = compare_paired_cycles(
        target,
        demo,
        tick_size=0.01,
        time_tolerance_seconds=1.0,
        tick_value_per_lot=1.0,
    )

    assert report["status"] == "PASS"
    assert report["deployment"]["target_count"] == 60
    assert report["deployment"]["target_rearm_count"] == 1


def test_pending_duplicate_without_prior_stop_is_ineligible_rearm() -> None:
    start = datetime(2026, 8, 4, 14, 0, tzinfo=UTC)
    target = deployment_events(cycle_id="cycle-1", start=start)
    demo = deployment_events(cycle_id="cycle-1", start=start)
    duplicate = {
        **target[0],
        "time_utc": (start + timedelta(seconds=20)).isoformat(),
    }
    target.append(duplicate)
    demo.append(duplicate)
    complete_cycle(target, time=start + timedelta(seconds=60))
    complete_cycle(demo, time=start + timedelta(seconds=59), demo=True)

    report = compare_paired_cycles(
        target,
        demo,
        tick_size=0.01,
        time_tolerance_seconds=1.0,
    )

    assert report["status"] == "FAIL"
    assert report["deployment"]["target_ineligible_rearms"] == ["STR B1"]


def test_request_retcode_mismatch_is_deterministic_failure() -> None:
    start = datetime(2026, 8, 4, 14, 0, tzinfo=UTC)
    target = deployment_events(cycle_id="cycle-1", start=start)
    demo = deployment_events(cycle_id="cycle-1", start=start)
    target[0]["retcode"] = 10008
    demo[0]["retcode"] = 10016
    complete_cycle(target, time=start + timedelta(seconds=60))
    complete_cycle(demo, time=start + timedelta(seconds=59), demo=True)

    report = compare_paired_cycles(
        target,
        demo,
        tick_size=0.01,
        time_tolerance_seconds=1.0,
    )

    assert report["status"] == "FAIL"
    assert any(
        mismatch["category"] == "decision"
        for mismatch in report["deterministic_mismatches"]
    )


def test_matching_rejected_initial_attempt_can_retry_same_slot() -> None:
    start = datetime(2026, 8, 4, 14, 0, tzinfo=UTC)
    target = deployment_events(cycle_id="cycle-1", start=start)
    demo = deployment_events(cycle_id="cycle-1", start=start)
    rejected = {
        **target[0],
        "time_utc": (start - timedelta(milliseconds=100)).isoformat(),
        "retcode": 10016,
    }
    target.insert(0, rejected)
    demo.insert(0, dict(rejected))
    complete_cycle(target, time=start + timedelta(seconds=60))
    complete_cycle(demo, time=start + timedelta(seconds=59), demo=True)

    report = compare_paired_cycles(
        target,
        demo,
        tick_size=0.01,
        time_tolerance_seconds=1.0,
    )

    assert report["status"] == "PASS"
    assert report["deployment"]["target_count"] == 60
    assert report["deployment"]["target_ineligible_rearms"] == []


def test_numeric_mismatch_report_proposes_advisory_adjustment() -> None:
    start = datetime(2026, 8, 4, 14, 0, tzinfo=UTC)
    target = deployment_events(cycle_id="cycle-1", start=start)
    demo = deployment_events(cycle_id="cycle-1", start=start)
    demo[0]["price"] += 0.01
    complete_cycle(target, time=start + timedelta(seconds=60))
    complete_cycle(demo, time=start + timedelta(seconds=59), demo=True)

    report = compare_paired_cycles(
        target,
        demo,
        tick_size=0.01,
        time_tolerance_seconds=1.0,
    )

    assert report["status"] == "FAIL"
    assert report["numeric_candidates"]["advisory_only"] is True
    adjustment = report["numeric_candidates"]["field_adjustments"][
        "price"
    ]["median_target_minus_demo"]
    assert round(adjustment, 2) == -0.01


def test_partial_fill_count_mismatch_fails_execution_comparison() -> None:
    start = datetime(2026, 8, 4, 14, 0, tzinfo=UTC)
    target = deployment_events(cycle_id="cycle-1", start=start)
    demo = deployment_events(cycle_id="cycle-1", start=start)
    fill = {
        "cycle_id": "cycle-1",
        "time_utc": (start + timedelta(seconds=20)).isoformat(),
        "kind": "fill",
        "comment": "STR B1",
        "side": "buy",
        "volume": 0.005,
        "price": 4081.36,
        "commission": -0.02,
        "swap": 0.0,
        "profit": 0.0,
    }
    target.extend(
        [
            fill,
            {
                **fill,
                "time_utc": (
                    start + timedelta(seconds=20, milliseconds=200)
                ).isoformat(),
            },
        ]
    )
    demo.append({**fill, "volume": 0.01, "commission": -0.04})
    complete_cycle(target, time=start + timedelta(seconds=60))
    complete_cycle(demo, time=start + timedelta(seconds=59), demo=True)

    report = compare_paired_cycles(
        target,
        demo,
        tick_size=0.01,
        time_tolerance_seconds=1.0,
    )

    assert report["status"] == "PASS"
    assert report["logic_status"] == "PASS"
    assert report["execution_status"] == "DIFFERENT"
    assert any(
        mismatch["category"] == "execution_missing"
        for mismatch in report["execution_mismatches"]
    )


def test_demo_loader_ignores_partially_written_numeric_row(tmp_path) -> None:
    path = tmp_path / "telemetry.csv"
    path.write_text(
        "utc_time,cycle_id,kind,comment,side,volume,price,sl,tp,"
        "retcode,commission,swap,profit\n"
        "2026-08-04T14:00:00Z,cycle-1,pending_request,STR B1,buy,"
        "0.01,4081.36,0,0,10008,0,0,0\n"
        "2026-08-04T14:00:01Z,cycle-1,pending_request,STR S1,sell,"
        "partial,",
        encoding="utf-8",
    )

    events = load_demo_telemetry_events(path)

    assert len(events) == 1
    assert events[0]["comment"] == "STR B1"


def test_demo_loader_reads_extended_rows_after_legacy_header(tmp_path) -> None:
    path = tmp_path / "telemetry.csv"
    legacy_header = (
        "utc_time,server_time,cycle_id,command_seq,kind,comment,side,"
        "volume,price,sl,tp,state,level,ticket,request_id,retcode,"
        "commission,swap,profit"
    )
    rows = [
        (
            "2026-08-13T15:35:57Z,2026.08.13 17:35:57,cycle-1,0,"
            "cycle_start,,,0,4363.02,0,0,CYCLE_DEPLOYING,,0,0,0,"
            "0,0,0,4,1,cycle-1:event:1,0,0,0,0,0,0,30,"
            "FORMAL_CANDIDATE"
        ),
        (
            "2026-08-13T16:35:37Z,2026.08.13 18:35:37,cycle-1,0,"
            "cycle_complete,flat,,0,0,0,0,CYCLE_RESTARTING,,0,0,0,"
            "0,0,0,4,2,cycle-1:event:2,0,0,0,121.27,0,121.27,30,"
            "FORMAL_CANDIDATE"
        ),
        (
            "2026-08-13T16:35:57Z,2026.08.13 18:35:57,cycle-1,0,"
            "cycle_restart,new_cycle,,0,0,0,0,CYCLE_IDLE,,0,0,0,"
            "0,0,0,4,3,cycle-1:event:3,0,0,0,121.27,0,121.27,30,"
            "FORMAL_CANDIDATE"
        ),
    ]
    path.write_text(
        legacy_header + "\n" + "\n".join(rows) + "\n",
        encoding="utf-8",
    )

    capture = load_demo_telemetry_stream(path)

    assert capture.invalid_rows == 0
    assert [event["kind"] for event in capture.events] == [
        "cycle_start",
        "cycle_complete",
        "cycle_restart",
    ]
    assert [event["sequence"] for event in capture.events] == [1, 2, 3]
    assert capture.events[1]["cycle_realized"] == 121.27
    assert capture.events[1]["basket_target"] == 30.0


def test_target_loader_ignores_partially_written_json_line(tmp_path) -> None:
    path = tmp_path / "target.jsonl"
    path.write_text(
        '{"cycle_id":"cycle-1","time_utc":"2026-08-04T14:00:00Z",'
        '"kind":"pending_request","comment":"STR B1"}\n'
        '{"cycle_id":"cycle-1"',
        encoding="utf-8",
    )

    events = load_jsonl_events(path)

    assert len(events) == 1
    assert events[0]["cycle_id"] == "cycle-1"
    assert events[0]["kind"] == "pending_request"
    assert events[0]["side"] == "buy"


def test_demo_stream_deduplicates_execution_deal_identity(tmp_path) -> None:
    path = tmp_path / "telemetry.csv"
    path.write_text(
        "session_id,utc_time,cycle_id,event_sequence,kind,comment,side,"
        "volume,price,deal_ticket,position_ticket,evidence_grade\n"
        "candidate-session,2026-08-04T14:00:00Z,cycle-1,1,stop_exit,"
        "STR B1,buy,0.01,4081.36,7001,9001,FORMAL_CANDIDATE\n"
        "candidate-session,2026-08-04T14:00:00Z,cycle-1,2,stop_exit,"
        "STR B1,buy,0.01,4081.36,7001,9001,FORMAL_CANDIDATE\n",
        encoding="utf-8",
    )

    capture = load_demo_telemetry_stream(path)

    assert len(capture.events) == 1
    assert capture.duplicate_event_ids == (
        "candidate:candidate-session:cycle-1:deal:7001:stop_exit",
    )


def test_duplicate_capture_identity_invalidates_comparison() -> None:
    start = datetime(2026, 8, 4, 14, 0, tzinfo=UTC)
    target = deployment_events(cycle_id="cycle-1", start=start)
    demo = deployment_events(cycle_id="cycle-1", start=start)
    complete_cycle(target, time=start + timedelta(minutes=1))
    complete_cycle(demo, time=start + timedelta(minutes=1), demo=True)
    demo_capture = CanonicalizationResult(
        events=tuple(demo),
        duplicate_event_ids=("candidate:session:cycle-1:deal:1:fill",),
        invalid_rows=0,
    )

    report = compare_paired_cycles(
        target,
        demo,
        tick_size=0.01,
        time_tolerance_seconds=1.0,
        demo_capture=demo_capture,
    )

    assert report["status"] == "INVALID"
    assert "duplicate" in report["reason"].lower()


def test_duplicate_level_identity_is_a_deterministic_failure() -> None:
    start = datetime(2026, 8, 4, 14, 0, tzinfo=UTC)
    target = deployment_events(cycle_id="cycle-1", start=start)
    demo = deployment_events(cycle_id="cycle-1", start=start)
    demo.append(
        {
            "cycle_id": "cycle-1",
            "time_utc": (start + timedelta(seconds=30)).isoformat(),
            "kind": "duplicate_level_identity",
            "comment": "STR B1",
            "source": "candidate",
        }
    )
    complete_cycle(target, time=start + timedelta(seconds=60))
    complete_cycle(demo, time=start + timedelta(seconds=59), demo=True)

    report = compare_paired_cycles(
        target,
        demo,
        tick_size=0.01,
        time_tolerance_seconds=1.0,
    )

    assert report["status"] == "FAIL"
    assert any(
        mismatch["category"] == "duplicate_level_identity"
        for mismatch in report["deterministic_mismatches"]
    )
