from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from straddle_replica.observer_adapter import (
    ObserverAdapterConfig,
    ObserverEventAdapter,
)


UTC = timezone.utc


def _write_session(
    root: Path,
    *,
    now: datetime,
    orders: list[dict] | None = None,
    positions: list[dict] | None = None,
    history_server_offset_seconds: int = 0,
    session_id: str = "20260805T000000Z_901018_XAUUSD",
) -> Path:
    session = root / session_id
    session.mkdir(parents=True)
    (root / "current-session.json").write_text(
        json.dumps({"session_id": session_id}),
        encoding="utf-8",
    )
    (session / "manifest.json").write_text(
        json.dumps(
            {
                "time_domains": {
                    "history_server_offset_seconds": (
                        history_server_offset_seconds
                    )
                }
            }
        ),
        encoding="utf-8",
    )
    (session / "heartbeat.json").write_text(
        json.dumps(
            {
                "capture_time_utc": now.isoformat(),
                "healthy": True,
                "stopped": False,
            }
        ),
        encoding="utf-8",
    )
    snapshot = {
        "capture_time_utc": now.isoformat(),
        "sequence": 10,
        "orders": orders or [],
        "positions": positions or [],
    }
    (session / "snapshots-20260805-00.jsonl").write_text(
        json.dumps(snapshot) + "\n",
        encoding="utf-8",
    )
    return session


def test_session_change_reseeds_active_state_and_emits_boundary_event(
    tmp_path: Path,
) -> None:
    started = datetime(2026, 8, 5, 0, 0, tzinfo=UTC)
    root = tmp_path / "observer"
    state_path = tmp_path / "adapter.json"
    active_orders = [
        _order(
            ticket=101,
            comment="STR B1",
            price=4081.36,
            time_setup_msc=int(started.timestamp() * 1000),
        ),
        _order(
            ticket=102,
            comment="STR S1",
            price=4078.64,
            time_setup_msc=int(started.timestamp() * 1000) + 100,
        ),
    ]
    _write_session(root, now=started, orders=active_orders)
    adapter = ObserverEventAdapter(
        ObserverAdapterConfig(
            observer_root=root,
            state_path=state_path,
        )
    )
    assert adapter.poll(now=started) == []

    restarted_at = started + timedelta(minutes=1)
    restarted_session = "20260805T000100Z_901018_XAUUSD"
    _write_session(
        root,
        now=restarted_at,
        orders=active_orders,
        session_id=restarted_session,
    )

    assert adapter.poll(now=restarted_at) == [
        {
            "session_id": f"{restarted_session}-observer",
            "sequence": 1,
            "time_utc": restarted_at.isoformat(),
            "kind": "observer_session_start",
            "comment": "",
            "side": "",
            "volume": 0.0,
            "price": 0.0,
            "sl": 0.0,
            "tp": 0.0,
            "request_id": 0,
            "retcode": 0,
            "evidence_grade": "BEST_EFFORT",
            "deal_ticket": 0,
            "order_ticket": 0,
            "position_ticket": 0,
            "source": "observer_inferred",
            "capture_limit": "no_originating_request_payload",
            "reason": "observer_session_changed",
            "previous_session_id": (
                "20260805T000000Z_901018_XAUUSD"
            ),
        }
    ]
    assert adapter.state["session_id"] == restarted_session
    assert adapter.state["next_sequence"] == 2
    assert adapter.state["suppress_current_cycle"] is True
    assert adapter.state["waiting_for_flat"] is True
    assert adapter.state["seen_order_tickets"] == [101, 102]


def _append_snapshot(
    session: Path,
    *,
    now: datetime,
    sequence: int,
    orders: list[dict] | None = None,
    positions: list[dict] | None = None,
) -> None:
    path = session / "snapshots-20260805-00.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "capture_time_utc": now.isoformat(),
                    "sequence": sequence,
                    "orders": orders or [],
                    "positions": positions or [],
                }
            )
            + "\n"
        )
    (session / "heartbeat.json").write_text(
        json.dumps(
            {
                "capture_time_utc": now.isoformat(),
                "healthy": True,
                "stopped": False,
            }
        ),
        encoding="utf-8",
    )


def _order(
    *,
    ticket: int,
    comment: str,
    price: float,
    time_setup_msc: int,
    volume: float = 0.01,
) -> dict:
    return {
        "ticket": ticket,
        "comment": comment,
        "symbol": "XAUUSD",
        "price_open": price,
        "time_setup_msc": time_setup_msc,
        "volume_initial": volume,
    }


def _append_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def test_initial_active_cycle_is_seeded_without_start_events(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 8, 5, 0, 0, tzinfo=UTC)
    root = tmp_path / "observer"
    _write_session(
        root,
        now=now,
        orders=[
            _order(
                ticket=101,
                comment="STR B1",
                price=4081.36,
                time_setup_msc=int(now.timestamp() * 1000),
            ),
            _order(
                ticket=102,
                comment="STR S1",
                price=4078.64,
                time_setup_msc=int(now.timestamp() * 1000) + 100,
            ),
        ],
    )
    adapter = ObserverEventAdapter(
        ObserverAdapterConfig(
            observer_root=root,
            state_path=tmp_path / "adapter.json",
        )
    )

    assert adapter.poll(now=now) == []
    assert adapter.state["waiting_for_flat"] is True
    assert adapter.state["armed_for_next_cycle"] is False
    assert adapter.state["seen_order_tickets"] == [101, 102]


def test_initial_flat_state_arms_next_cycle_without_replay(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 8, 5, 0, 0, tzinfo=UTC)
    root = tmp_path / "observer"
    _write_session(root, now=now)
    adapter = ObserverEventAdapter(
        ObserverAdapterConfig(
            observer_root=root,
            state_path=tmp_path / "adapter.json",
        )
    )

    assert adapter.poll(now=now) == []
    assert adapter.state["waiting_for_flat"] is False
    assert adapter.state["armed_for_next_cycle"] is True
    assert adapter.state["seen_order_tickets"] == []


def test_flat_transition_then_fresh_pair_emits_one_startable_pair(
    tmp_path: Path,
) -> None:
    started = datetime(2026, 8, 5, 0, 0, tzinfo=UTC)
    root = tmp_path / "observer"
    session = _write_session(
        root,
        now=started,
        orders=[
            _order(
                ticket=101,
                comment="STR B1",
                price=4081.36,
                time_setup_msc=int(started.timestamp() * 1000),
            ),
            _order(
                ticket=102,
                comment="STR S1",
                price=4078.64,
                time_setup_msc=int(started.timestamp() * 1000) + 100,
            ),
        ],
    )
    state_path = tmp_path / "adapter.json"
    adapter = ObserverEventAdapter(
        ObserverAdapterConfig(
            observer_root=root,
            state_path=state_path,
        )
    )
    assert adapter.poll(now=started) == []

    flat_time = started.replace(second=10)
    _append_snapshot(
        session,
        now=flat_time,
        sequence=11,
    )
    assert adapter.poll(now=flat_time) == []

    confirmed_flat_time = flat_time + timedelta(seconds=1)
    _append_snapshot(
        session,
        now=confirmed_flat_time,
        sequence=12,
    )
    flat_events = adapter.poll(now=confirmed_flat_time)

    assert [event["kind"] for event in flat_events] == [
        "cancel_request"
    ]
    assert adapter.state["armed_for_next_cycle"] is True

    b1 = _order(
        ticket=201,
        comment="STR B1",
        price=4082.36,
        time_setup_msc=int(flat_time.timestamp() * 1000) + 20_000,
    )
    b1_time = flat_time.replace(second=30)
    _append_snapshot(
        session,
        now=b1_time,
        sequence=13,
        orders=[b1],
    )
    b1_events = adapter.poll(now=b1_time)

    s1 = _order(
        ticket=202,
        comment="STR S1",
        price=4079.64,
        time_setup_msc=int(b1_time.timestamp() * 1000) + 100,
    )
    s1_time = b1_time.replace(microsecond=200_000)
    _append_snapshot(
        session,
        now=s1_time,
        sequence=14,
        orders=[b1, s1],
    )
    s1_events = adapter.poll(now=s1_time)

    pair = [*b1_events, *s1_events]
    assert [event["comment"] for event in pair] == [
        "STR B1",
        "STR S1",
    ]
    assert all(event["kind"] == "pending_request" for event in pair)
    assert all(event["source"] == "observer_inferred" for event in pair)
    assert pair[0]["price"] == 4082.36
    assert pair[1]["price"] == 4079.64
    assert adapter.state["waiting_for_flat"] is True
    assert adapter.state["armed_for_next_cycle"] is False

    assert adapter.poll(now=s1_time) == []
    restarted = ObserverEventAdapter(
        ObserverAdapterConfig(
            observer_root=root,
            state_path=state_path,
        )
    )
    assert restarted.poll(now=s1_time) == []


def test_flat_boundary_waits_for_late_final_history_deal(
    tmp_path: Path,
) -> None:
    started = datetime(2026, 8, 5, 0, 0, tzinfo=UTC)
    root = tmp_path / "observer"
    session = _write_session(
        root,
        now=started,
        positions=[
            {
                "ticket": 1001,
                "comment": "STR B3",
                "volume": 0.01,
                "price_open": 4084.08,
                "sl": 4082.60,
            }
        ],
    )
    adapter = ObserverEventAdapter(
        ObserverAdapterConfig(
            observer_root=root,
            state_path=tmp_path / "adapter.json",
        )
    )
    assert adapter.poll(now=started) == []

    first_flat = started + timedelta(seconds=1)
    _append_snapshot(
        session,
        now=first_flat,
        sequence=11,
    )

    assert adapter.poll(now=first_flat) == []

    final_close = first_flat + timedelta(milliseconds=150)
    _append_jsonl(
        session / "history-deals-20260805-00.jsonl",
        [
            {
                "ticket": 501,
                "order": 201,
                "position_id": 1001,
                "time_msc": int(final_close.timestamp() * 1000),
                "type": 1,
                "entry": 1,
                "comment": "STR CLOSE",
                "volume": 0.01,
                "price": 4085.00,
                "commission": 0.0,
                "swap": 0.0,
                "profit": 0.92,
                "reason": 3,
            }
        ],
    )
    confirmed_flat = started + timedelta(seconds=2)
    _append_snapshot(
        session,
        now=confirmed_flat,
        sequence=12,
    )

    events = adapter.poll(now=confirmed_flat)

    assert [event["kind"] for event in events] == [
        "close_fill",
        "cancel_request",
    ]
    assert events[0]["comment"] == "STR B3"
    assert events[0]["deal_ticket"] == 501
    assert events[1]["comment"] == ""


def test_history_rows_emit_fill_stop_close_and_cancel(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 8, 5, 0, 0, tzinfo=UTC)
    root = tmp_path / "observer"
    session = _write_session(root, now=now)
    adapter = ObserverEventAdapter(
        ObserverAdapterConfig(
            observer_root=root,
            state_path=tmp_path / "adapter.json",
        )
    )
    assert adapter.poll(now=now) == []

    _append_jsonl(
        session / "history-orders-20260805-00.jsonl",
        [
            {
                "ticket": 301,
                "time_done_msc": int(now.timestamp() * 1000) + 500,
                "type": 4,
                "state": 2,
                "comment": "STR B2",
                "volume_initial": 0.01,
                "price_open": 4082.72,
            }
        ],
    )
    _append_jsonl(
        session / "history-deals-20260805-00.jsonl",
        [
            {
                "ticket": 501,
                "order": 201,
                "position_id": 1001,
                "time_msc": int(now.timestamp() * 1000) + 100,
                "type": 0,
                "entry": 0,
                "comment": "STR B1",
                "volume": 0.01,
                "price": 4081.36,
                "commission": 0.0,
                "swap": 0.0,
                "profit": 0.0,
                "reason": 3,
            },
            {
                "ticket": 502,
                "order": 202,
                "position_id": 1001,
                "time_msc": int(now.timestamp() * 1000) + 200,
                "type": 1,
                "entry": 1,
                "comment": "[sl 4080.00]",
                "volume": 0.01,
                "price": 4080.00,
                "commission": 0.0,
                "swap": 0.0,
                "profit": -1.36,
                "reason": 4,
            },
            {
                "ticket": 503,
                "order": 203,
                "position_id": 1002,
                "time_msc": int(now.timestamp() * 1000) + 300,
                "type": 1,
                "entry": 0,
                "comment": "STR S1",
                "volume": 0.01,
                "price": 4078.64,
                "commission": 0.0,
                "swap": 0.0,
                "profit": 0.0,
                "reason": 3,
            },
            {
                "ticket": 504,
                "order": 204,
                "position_id": 1002,
                "time_msc": int(now.timestamp() * 1000) + 400,
                "type": 0,
                "entry": 1,
                "comment": "",
                "volume": 0.01,
                "price": 4079.00,
                "commission": 0.0,
                "swap": 0.0,
                "profit": -0.36,
                "reason": 3,
            },
        ],
    )

    events = adapter.poll(now=now.replace(second=1))
    by_kind = {event["kind"]: event for event in events}

    assert [event["sequence"] for event in events] == list(
        range(1, len(events) + 1)
    )
    assert by_kind["fill"]["comment"] in {"STR B1", "STR S1"}
    stop = next(event for event in events if event["kind"] == "stop_exit")
    assert stop["comment"] == "STR B1"
    assert stop["price"] == 4080.0
    assert stop["profit"] == -1.36
    assert stop["deal_ticket"] == 502
    assert stop["position_ticket"] == 1001
    assert stop["evidence_grade"] == "BEST_EFFORT"
    close = next(event for event in events if event["kind"] == "close_fill")
    assert close["comment"] == "STR S1"
    cancel = next(
        event
        for event in events
        if event["kind"] == "cancel_request"
        and event["comment"] == "STR B2"
    )
    assert cancel["price"] == 4082.72
    assert all(event["source"] == "observer_inferred" for event in events)

    assert adapter.poll(now=now.replace(second=1)) == []


def test_filled_history_order_backfills_unseen_pending_request(
    tmp_path: Path,
) -> None:
    started = datetime(2026, 8, 5, 0, 0, tzinfo=UTC)
    root = tmp_path / "observer"
    session = _write_session(root, now=started)
    adapter = ObserverEventAdapter(
        ObserverAdapterConfig(
            observer_root=root,
            state_path=tmp_path / "adapter.json",
        )
    )
    assert adapter.poll(now=started) == []

    setup_at = started + timedelta(seconds=1)
    b1 = _order(
        ticket=201,
        comment="STR B1",
        price=4081.36,
        time_setup_msc=int(setup_at.timestamp() * 1000),
    )
    _append_snapshot(
        session,
        now=setup_at + timedelta(seconds=20),
        sequence=11,
        orders=[b1],
        positions=[
            {
                "ticket": 202,
                "comment": "STR S1",
                "volume": 0.01,
                "price_open": 4078.64,
                "sl": 0.0,
            }
        ],
    )
    _append_jsonl(
        session / "history-orders-20260805-00.jsonl",
        [
            {
                "ticket": 202,
                "time_setup_msc": (
                    int(setup_at.timestamp() * 1000) + 100
                ),
                "time_done_msc": (
                    int(setup_at.timestamp() * 1000) + 20_000
                ),
                "type": 5,
                "state": 4,
                "comment": "STR S1",
                "volume_initial": 0.01,
                "price_open": 4078.64,
            }
        ],
    )

    events = adapter.poll(now=setup_at + timedelta(seconds=20))

    assert [event["kind"] for event in events] == [
        "pending_request",
        "pending_request",
    ]
    assert [event["comment"] for event in events] == [
        "STR B1",
        "STR S1",
    ]
    assert events[1]["time_utc"] == (
        setup_at + timedelta(milliseconds=100)
    ).isoformat()
    assert events[1]["capture_limit"] == (
        "pending_request_reconstructed_from_filled_order"
    )


def test_partial_history_line_is_not_consumed_until_complete(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 8, 5, 0, 0, tzinfo=UTC)
    root = tmp_path / "observer"
    session = _write_session(root, now=now)
    adapter = ObserverEventAdapter(
        ObserverAdapterConfig(
            observer_root=root,
            state_path=tmp_path / "adapter.json",
        )
    )
    assert adapter.poll(now=now) == []

    path = session / "history-deals-20260805-00.jsonl"
    valid = {
        "ticket": 501,
        "position_id": 1001,
        "time_msc": int(now.timestamp() * 1000) + 100,
        "type": 0,
        "entry": 0,
        "comment": "STR B1",
        "volume": 0.01,
        "price": 4081.36,
    }
    path.write_text(
        json.dumps(valid) + "\n" + '{"ticket":502',
        encoding="utf-8",
    )

    events = adapter.poll(now=now.replace(second=1))

    assert [event["deal"] for event in events] == [501]


def test_broker_timestamps_are_normalized_to_genuine_utc(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 8, 5, 0, 0, tzinfo=UTC)
    root = tmp_path / "observer"
    session = _write_session(
        root,
        now=now,
        history_server_offset_seconds=7_200,
    )
    adapter = ObserverEventAdapter(
        ObserverAdapterConfig(
            observer_root=root,
            state_path=tmp_path / "adapter.json",
        )
    )
    assert adapter.poll(now=now) == []

    accepted_at = now + timedelta(seconds=1)
    broker_time = accepted_at + timedelta(seconds=7_200)
    _append_snapshot(
        session,
        now=accepted_at,
        sequence=11,
        orders=[
            _order(
                ticket=201,
                comment="STR B1",
                price=4081.36,
                time_setup_msc=int(broker_time.timestamp() * 1000),
            )
        ],
    )

    pending = adapter.poll(now=accepted_at)

    assert pending[0]["time_utc"] == accepted_at.isoformat()
    assert adapter.state["history_server_offset_seconds"] == 7_200

    filled_at = accepted_at + timedelta(seconds=1)
    broker_fill_time = filled_at + timedelta(seconds=7_200)
    _append_jsonl(
        session / "history-deals-20260805-00.jsonl",
        [
            {
                "ticket": 501,
                "position_id": 1001,
                "time_msc": int(broker_fill_time.timestamp() * 1000),
                "type": 0,
                "entry": 0,
                "comment": "STR B1",
                "volume": 0.01,
                "price": 4081.36,
            }
        ],
    )

    fill = adapter.poll(now=filled_at)

    assert fill[0]["time_utc"] == filled_at.isoformat()


def test_position_sl_change_emits_one_inferred_stop_request(
    tmp_path: Path,
) -> None:
    started = datetime(2026, 8, 5, 0, 0, tzinfo=UTC)
    root = tmp_path / "observer"
    session = _write_session(root, now=started)
    adapter = ObserverEventAdapter(
        ObserverAdapterConfig(
            observer_root=root,
            state_path=tmp_path / "adapter.json",
        )
    )
    assert adapter.poll(now=started) == []

    opened = {
        "ticket": 1001,
        "comment": "STR B1",
        "volume": 0.01,
        "price_open": 4081.36,
        "sl": 0.0,
    }
    first = started + timedelta(seconds=1)
    _append_snapshot(
        session,
        now=first,
        sequence=11,
        positions=[opened],
    )
    assert adapter.poll(now=first) == []

    second = started + timedelta(seconds=2)
    _append_snapshot(
        session,
        now=second,
        sequence=12,
        positions=[{**opened, "sl": 4081.56}],
    )
    events = adapter.poll(now=second)

    assert len(events) == 1
    assert events[0]["kind"] == "stop_request"
    assert events[0]["comment"] == "STR B1"
    assert events[0]["position_ticket"] == 1001
    assert events[0]["price"] == 4081.56
    assert events[0]["sl"] == 4081.56
    assert events[0]["evidence_grade"] == "BEST_EFFORT"
    assert adapter.poll(now=second) == []
