from straddle_replica.canonical_events import canonicalize_events


def test_deal_ticket_is_the_primary_execution_identity() -> None:
    raw = [
        {
            "cycle_id": "cycle-1",
            "sequence": 1,
            "time_utc": "2026-08-11T00:00:00Z",
            "kind": "stop_exit",
            "comment": "STR B1",
            "deal_ticket": 7001,
            "position_ticket": 9001,
            "volume": 0.01,
            "accepted_price": 4400.0,
        },
        {
            "cycle_id": "cycle-1",
            "sequence": 2,
            "time_utc": "2026-08-11T00:00:00Z",
            "kind": "stop_exit",
            "comment": "STR B1",
            "deal_ticket": 7001,
            "position_ticket": 9001,
            "volume": 0.01,
            "accepted_price": 4400.0,
        },
    ]

    result = canonicalize_events(
        raw,
        source="candidate",
        evidence_grade="FORMAL_CANDIDATE",
        session_id="candidate-session",
    )

    assert len(result.events) == 1
    assert result.duplicate_event_ids == (
        "candidate:candidate-session:cycle-1:deal:7001:stop_exit",
    )
    assert result.events[0]["side"] == "buy"
    assert result.events[0]["level"] == 1


def test_legacy_price_and_ticket_fields_remain_supported() -> None:
    result = canonicalize_events(
        [
            {
                "cycle_id": "cycle-1",
                "sequence": 3,
                "time_utc": "2026-08-11T00:00:01Z",
                "kind": "fill",
                "comment": "STR S2",
                "deal": 8001,
                "ticket": 9002,
                "price": 4398.0,
                "volume": 0.01,
            }
        ],
        source="observer",
        evidence_grade="BEST_EFFORT",
        session_id="observer-session",
    )

    event = result.events[0]
    assert event["deal_ticket"] == 8001
    assert event["position_ticket"] == 9002
    assert event["accepted_price"] == 4398.0
    assert event["side"] == "sell"
    assert event["level"] == 2


def test_level_scoped_lifecycle_event_uses_level_identity_not_reason() -> None:
    result = canonicalize_events(
        [
            {
                "cycle_id": "cycle-1",
                "event_sequence": 4,
                "utc_time": "2026-08-12T16:56:42Z",
                "kind": "rearm_eligible",
                "comment": "stop_exit",
                "level": "STR S4",
                "side": "sell",
            }
        ],
        source="candidate",
        evidence_grade="FORMAL_CANDIDATE",
        session_id="candidate-session",
    )

    event = result.events[0]
    assert event["comment"] == "STR S4"
    assert event["side"] == "sell"
    assert event["level"] == 4
    assert event["reason"] == "stop_exit"
