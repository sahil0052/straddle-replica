import csv
import json
import importlib.util
from pathlib import Path
import sys


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "tools"
    / "analyze_live_capture.py"
)
SPEC = importlib.util.spec_from_file_location(
    "straddle_live_analysis",
    MODULE_PATH,
)
assert SPEC is not None and SPEC.loader is not None
analysis = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = analysis
SPEC.loader.exec_module(analysis)


def test_trade_request_analysis_preserves_typed_request_result_sequence(
    tmp_path,
):
    session = tmp_path / "mql-session"
    session.mkdir()
    fieldnames = [
        "server_time",
        "local_time",
        "capture_micros",
        "sequence",
        "trans_type",
        "trans_deal",
        "trans_order",
        "trans_symbol",
        "trans_price",
        "trans_price_sl",
        "trans_volume",
        "trans_position",
        "request_action",
        "request_magic",
        "request_order",
        "request_symbol",
        "request_volume",
        "request_price",
        "request_stoplimit",
        "request_sl",
        "request_tp",
        "request_deviation",
        "request_type",
        "request_type_filling",
        "request_type_time",
        "request_expiration",
        "request_comment",
        "request_position",
        "request_position_by",
        "result_retcode",
        "result_deal",
        "result_order",
        "result_volume",
        "result_price",
        "result_bid",
        "result_ask",
        "result_comment",
        "result_request_id",
        "result_retcode_external",
    ]
    rows = [
        {
            "server_time": "2026.08.04 08:00:00",
            "local_time": "2026.08.04 05:00:00",
            "capture_micros": "100",
            "sequence": "1",
            "trans_type": "2",
            "trans_order": "700",
            "trans_symbol": "XAUUSD",
        },
        {
            "server_time": "2026.08.04 08:00:01",
            "local_time": "2026.08.04 05:00:01",
            "capture_micros": "200",
            "sequence": "2",
            "trans_type": "10",
            "request_action": "6",
            "request_magic": "901018",
            "request_order": "701",
            "request_symbol": "XAUUSD",
            "request_volume": "0.15",
            "request_price": "4035.12",
            "request_stoplimit": "0",
            "request_sl": "4031.07",
            "request_tp": "0",
            "request_deviation": "25",
            "request_type": "4",
            "request_type_filling": "2",
            "request_type_time": "0",
            "request_expiration": "1970.01.01 00:00:00",
            "request_comment": "STR B21",
            "request_position": "801",
            "request_position_by": "0",
            "result_retcode": "10009",
            "result_deal": "901",
            "result_order": "701",
            "result_volume": "0.15",
            "result_price": "4035.13",
            "result_bid": "4035.10",
            "result_ask": "4035.13",
            "result_comment": "Request completed",
            "result_request_id": "41",
            "result_retcode_external": "0",
        },
        {
            "server_time": "2026.08.04 08:00:02",
            "local_time": "2026.08.04 05:00:02",
            "capture_micros": "300",
            "sequence": "4",
            "trans_type": "10",
            "request_action": "7",
            "request_magic": "901018",
            "request_order": "702",
            "request_symbol": "XAUUSD",
            "request_volume": "0.06",
            "request_price": "4036.47",
            "request_sl": "4032.42",
            "request_position": "802",
            "result_retcode": "10008",
            "result_order": "702",
            "result_request_id": "42",
        },
    ]
    with (session / "transactions-20260804-08.csv").open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    transactions = analysis.load_transactions(session)
    report = analysis.analyze_trade_requests(transactions)

    assert transactions[1]["request_magic"] == 901018
    assert transactions[1]["request_sl"] == 4031.07
    assert transactions[1]["result_request_id"] == 41
    assert report["count"] == 2
    assert report["sequence_numbers"] == [2, 4]
    assert report["request_id_sequence"] == [41, 42]
    assert report["transaction_type_counts"] == {"10": 2}
    assert report["action_counts"] == {"6": 1, "7": 1}
    assert report["retcode_counts"] == {"10008": 1, "10009": 1}
    assert report["nonzero_sl_count"] == 2
    assert report["direct_request_evidence_available"] is True
    assert report["events"][0] == {
        "server_time": "2026.08.04 08:00:01",
        "local_time": "2026.08.04 05:00:01",
        "capture_micros": 200,
        "sequence": 2,
        "trans_type": 10,
        "trans_deal": 0,
        "trans_order": 0,
        "trans_symbol": "",
        "trans_price": 0.0,
        "trans_price_sl": 0.0,
        "trans_volume": 0.0,
        "trans_position": 0,
        "request_action": 6,
        "request_magic": 901018,
        "request_order": 701,
        "request_symbol": "XAUUSD",
        "request_volume": 0.15,
        "request_price": 4035.12,
        "request_stoplimit": 0.0,
        "request_sl": 4031.07,
        "request_tp": 0.0,
        "request_deviation": 25,
        "request_type": 4,
        "request_type_filling": 2,
        "request_type_time": 0,
        "request_expiration": "1970.01.01 00:00:00",
        "request_comment": "STR B21",
        "request_position": 801,
        "request_position_by": 0,
        "result_retcode": 10009,
        "result_deal": 901,
        "result_order": 701,
        "result_volume": 0.15,
        "result_price": 4035.13,
        "result_bid": 4035.1,
        "result_ask": 4035.13,
        "result_comment": "Request completed",
        "result_request_id": 41,
        "result_retcode_external": 0,
    }


def test_trade_request_analysis_marks_remote_only_stream_unavailable():
    report = analysis.analyze_trade_requests(
        [
            {
                "capture_micros": 100,
                "sequence": 1,
                "trans_type": 9,
                "trans_position": 801,
                "trans_price_sl": 4031.07,
            }
        ]
    )

    assert report["count"] == 0
    assert report["direct_request_evidence_available"] is False
    assert report["events"] == []


def test_latest_tick_at_or_before_never_uses_a_future_tick():
    ticks = [
        {"capture_micros": 100, "bid": 10.0},
        {"capture_micros": 106, "bid": 20.0},
    ]

    selected = analysis.latest_tick_at_or_before(
        ticks,
        [100, 106],
        105,
    )

    assert selected == ticks[0]
    assert analysis.latest_tick_at_or_before(ticks, [100, 106], 99) is None


def test_tick_analysis_excludes_closed_market_gaps_from_active_hours():
    report = analysis.analyze_ticks(
        [
            {"time_msc": 1_000, "server_time": "", "local_time": ""},
            {"time_msc": 61_000, "server_time": "", "local_time": ""},
            {"time_msc": 3_661_000, "server_time": "", "local_time": ""},
            {"time_msc": 3_721_000, "server_time": "", "local_time": ""},
        ],
        server_offset_ms=0,
    )

    assert report["market_active_gap_threshold_ms"] == 300_000
    assert report["market_pause_count"] == 1
    assert report["market_active_hours"] == 0.0333


def test_latest_profile_step_is_recovered_from_pending_order_geometry():
    assert analysis.latest_profile_grid_step("STR B2", 4038.34) == 1.35
    assert analysis.latest_profile_grid_step("STR S3", 4031.59) == 1.35
    assert analysis.latest_profile_grid_step("STR CLOSE", 4035.0) is None

    steps = analysis.history_position_steps(
        [
            {
                "comment": "STR B2",
                "position_id": 10,
                "price_open": 4038.34,
            },
            {
                "comment": "STR S3",
                "position_id": 11,
                "price_open": 4031.59,
            },
        ]
    )

    assert steps == {10: 1.35, 11: 1.35}


def test_level_context_tracks_newest_open_grid_level():
    metadata = {
        10: {"ticket": 10, "type": 0, "comment": "STR B2"},
        11: {"ticket": 11, "type": 0, "comment": "STR B3"},
    }
    added = [
        analysis.StateEvent(100, "time", 11, metadata[11]),
    ]
    changes = [
        {"capture_micros": 50, "ticket": 10, "side": "buy"},
        {"capture_micros": 150, "ticket": 10, "side": "buy"},
        {"capture_micros": 150, "ticket": 11, "side": "buy"},
    ]

    annotated = analysis.annotate_level_context(
        changes,
        metadata,
        added,
        [],
        tolerance_micros=0,
    )

    assert [
        row["level_gap_from_highest_open"] for row in annotated
    ] == [0, 1, 0]


def test_stop_sequence_annotations_track_ticket_history_and_bursts():
    changes = [
        {
            "capture_micros": 100,
            "ticket": 10,
            "trailing_distance": 2.78,
            "favorable_move": 2.8,
            "favorable_move_steps": 2.8,
            "activation": True,
        },
        {
            "capture_micros": 200,
            "ticket": 10,
            "trailing_distance": 2.75,
            "favorable_move": 4.1,
            "favorable_move_steps": 4.1,
            "activation": False,
        },
        {
            "capture_micros": 300,
            "ticket": 11,
            "trailing_distance": 1.43,
            "favorable_move": 3.0,
            "favorable_move_steps": 3.0,
            "activation": True,
        },
        {
            "capture_micros": 900_000,
            "ticket": 10,
            "trailing_distance": 1.43,
            "favorable_move": 3.5,
            "favorable_move_steps": 3.5,
            "activation": False,
        },
    ]

    annotated = analysis.annotate_stop_sequence(
        changes,
        maximum_gap=500_000,
    )

    assert [row["distance_band"] for row in annotated] == [
        "activation",
        "two_step",
        "activation",
        "one_step",
    ]
    assert [row["ticket_update_index"] for row in annotated] == [1, 2, 1, 3]
    assert [row["burst_index"] for row in annotated] == [1, 1, 1, 2]
    assert [row["burst_position"] for row in annotated] == [1, 2, 3, 1]
    assert [row["burst_size"] for row in annotated] == [3, 3, 3, 1]
    assert [row["previous_distance_band"] for row in annotated] == [
        None,
        "activation",
        None,
        "two_step",
    ]
    assert [row["distance_band_transition"] for row in annotated] == [
        "start->activation",
        "activation->two_step",
        "start->activation",
        "two_step->one_step",
    ]
    assert [row["max_favorable_move"] for row in annotated] == [
        2.8,
        4.1,
        3.0,
        4.1,
    ]
    assert [row["previous_max_favorable_move"] for row in annotated] == [
        None,
        2.8,
        None,
        4.1,
    ]
    assert [row["max_favorable_move_steps"] for row in annotated] == [
        2.8,
        4.1,
        3.0,
        4.1,
    ]


def test_stop_phase_uses_lock_position_when_tick_distance_is_delayed():
    annotated = analysis.annotate_stop_sequence(
        [
            {
                "capture_micros": 100,
                "ticket": 10,
                "activation": False,
                "trailing_distance": 1.70,
                "lock_offset_steps": 0.47,
            }
        ]
    )

    assert annotated[0]["observed_distance_band"] == "one_step"
    assert annotated[0]["distance_band"] == "two_step"


def test_categorical_band_predictor_scores_chronological_holdout():
    rows = [
        {
            "level_gap_from_highest_open": gap,
            "distance_band": band,
        }
        for gap, band in [
            (2, "two_step"),
            (3, "one_step"),
            (2, "two_step"),
            (3, "one_step"),
            (2, "two_step"),
            (3, "one_step"),
            (2, "two_step"),
            (3, "one_step"),
            (2, "two_step"),
            (3, "one_step"),
        ]
    ]

    result = analysis.evaluate_categorical_band_predictor(
        rows,
        "level_gap_from_highest_open",
        train_fraction=0.6,
    )

    assert result["train_count"] == 6
    assert result["holdout_count"] == 4
    assert result["seen_holdout_count"] == 4
    assert result["holdout_coverage"] == 1.0
    assert result["holdout_accuracy"] == 1.0
    assert result["holdout_baseline_accuracy"] == 0.5
    assert result["exact_holdout"] is True


def test_numeric_threshold_predictor_fits_and_scores_chronological_holdout():
    rows = [
        {"favorable_move": value, "distance_band": band}
        for value, band in [
            (1.0, "two_step"),
            (4.0, "one_step"),
            (2.0, "two_step"),
            (5.0, "one_step"),
            (3.0, "two_step"),
            (6.0, "one_step"),
            (2.5, "two_step"),
            (4.5, "one_step"),
            (3.4, "two_step"),
            (3.6, "one_step"),
        ]
    ]

    result = analysis.evaluate_numeric_threshold_predictor(
        rows,
        "favorable_move",
        train_fraction=0.6,
    )

    assert result["train_count"] == 6
    assert result["holdout_count"] == 4
    assert result["direction"] == "greater_or_equal"
    assert result["threshold"] == 3.5
    assert result["train_accuracy"] == 1.0
    assert result["holdout_accuracy"] == 1.0
    assert result["holdout_baseline_accuracy"] == 0.5
    assert result["exact_holdout"] is True
    assert result["train_mismatches"] == []
    assert result["holdout_mismatches"] == []


def test_stop_analysis_reports_band_switch_context_and_predictor_scores():
    metadata = {
        10: {
            "ticket": 10,
            "type": 0,
            "comment": "STR B2",
            "price_open": 100.0,
        },
        11: {
            "ticket": 11,
            "type": 0,
            "comment": "STR B3",
            "price_open": 100.0,
        },
    }
    transactions = [
        {
            "trans_type": 9,
            "trans_price_sl": stop,
            "trans_position": ticket,
            "capture_micros": capture,
            "server_time": f"time-{capture}",
        }
        for capture, ticket, stop in [
            (100, 10, 100.20),
            (200, 10, 100.80),
            (300, 11, 100.20),
            (900_000, 10, 102.20),
        ]
    ]
    ticks = [
        {"capture_micros": capture, "bid": bid, "ask": bid + 0.1}
        for capture, bid in [
            (100, 102.2),
            (200, 102.8),
            (300, 102.2),
            (900_000, 103.2),
        ]
    ]

    result = analysis.analyze_stops(
        transactions,
        metadata,
        {10: 0.0, 11: 0.0},
        ticks,
        [
            analysis.StateEvent(0, "start", 10, metadata[10]),
            analysis.StateEvent(0, "start", 11, metadata[11]),
        ],
        [],
        position_steps={10: 1.0, 11: 1.0},
    )

    assert len(result["change_rows"]) == 4
    assert [row["distance_band"] for row in result["change_rows"]] == [
        "activation",
        "two_step",
        "activation",
        "one_step",
    ]
    assert result["distance_band_transitions"] == {
        "start->activation": 2,
        "activation->two_step": 1,
        "two_step->one_step": 1,
    }
    assert result["phase_transition_evidence"] == {
        "threshold_steps": 3.0,
        "transition_count": 1,
        "previous_implied_decision_steps": {
            "count": 1,
            "min": 2.8,
            "p10": 2.8,
            "median": 2.8,
            "mean": 2.8,
            "p90": 2.8,
            "max": 2.8,
        },
        "switch_implied_decision_steps": {
            "count": 1,
            "min": 3.2,
            "p10": 3.2,
            "median": 3.2,
            "mean": 3.2,
            "p90": 3.2,
            "max": 3.2,
        },
        "previous_below_threshold_count": 1,
        "switch_at_or_above_threshold_count": 1,
        "boundary_accuracy": 1.0,
    }
    assert result["activation_favorable_move_steps"] == {
        "count": 2,
        "min": 2.2,
        "p10": 2.2,
        "median": 2.2,
        "mean": 2.2,
        "p90": 2.2,
        "max": 2.2,
    }
    assert result["trailing_distance_steps"]["count"] == 2
    assert result["trailing_distance_steps"]["median"] == 1.5
    assert result["distance_band_switches"] == [
        {
            "server_time": "time-900000",
            "ticket": 10,
            "comment": "STR B2",
            "side": "buy",
            "level": 2,
            "same_side_open_count": 2,
            "highest_open_level": 3,
            "level_gap_from_highest_open": 1,
            "from_band": "two_step",
            "to_band": "one_step",
            "ticket_update_index": 3,
            "burst_index": 2,
            "burst_position": 1,
            "burst_size": 1,
            "trailing_distance": 1.0,
            "favorable_move": 3.2,
            "lock_offset": 2.2,
            "increment": 1.4,
            "previous_sl": 100.8,
            "new_sl": 102.2,
            "grid_step": 1.0,
            "favorable_move_steps": 3.2,
            "lock_offset_steps": 2.2,
            "trailing_distance_steps": 1.0,
        }
    ]
    assert set(result["categorical_predictor_holdout"]) == {
        "burst_position",
        "level",
        "level_gap_from_highest_open",
        "previous_distance_band",
        "same_side_open_count",
        "side",
        "ticket_update_index",
    }
    assert set(result["numeric_threshold_holdout"]) == {
        "favorable_move",
        "favorable_move_steps",
        "increment",
        "level_gap_from_highest_open",
        "lock_offset",
        "max_favorable_move_steps",
        "ticket_update_index",
    }


def test_load_history_merges_sessions_and_keeps_first_capture(tmp_path):
    first = tmp_path / "session-a"
    second = tmp_path / "session-b"
    first.mkdir()
    second.mkdir()
    (first / "history-orders-1.jsonl").write_text(
        json.dumps(
            {
                "ticket": 100,
                "capture_time_utc": "2026-08-03T10:00:00+00:00",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (second / "history-orders-2.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "ticket": 100,
                        "capture_time_utc": "2026-08-03T10:05:00+00:00",
                    }
                ),
                json.dumps(
                    {
                        "ticket": 101,
                        "capture_time_utc": "2026-08-03T10:06:00+00:00",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    orders, deals = analysis.load_history([first, second])

    assert deals == []
    assert [row["ticket"] for row in orders] == [100, 101]
    assert orders[0]["capture_time_utc"] == "2026-08-03T10:00:00+00:00"


def test_detect_history_deployments_requires_complete_alternating_grid():
    rows = []
    start = 1_000_000
    ticket = 200
    for level in range(1, 31):
        for side in ("B", "S"):
            rows.append(
                {
                    "ticket": ticket,
                    "time_setup_msc": start + len(rows) * 100,
                    "comment": f"STR {side}{level}",
                    "volume_initial": (
                        0.01 if level <= 10
                        else 0.06 if level <= 20
                        else 0.15
                    ),
                    "price_open": 4000 + level * (1 if side == "B" else -1),
                }
            )
            ticket += 1

    deployments = analysis.detect_history_deployments(rows)

    assert len(deployments) == 1
    assert deployments[0]["order_count"] == 60
    assert deployments[0]["sequence_exact"] is True


def test_lifecycle_does_not_count_cycle_deployment_as_level_rearm():
    orders = []
    for level in range(1, 31):
        for side in ("B", "S"):
            orders.append(
                {
                    "ticket": 1_000 + len(orders),
                    "state": 0,
                    "type": 4 if side == "B" else 5,
                    "time_setup_msc": 2_000 + len(orders) * 100,
                    "time_done_msc": 0,
                    "volume_initial": (
                        0.01 if level <= 10
                        else 0.06 if level <= 20
                        else 0.15
                    ),
                    "price_open": 100 + level if side == "B" else 100 - level,
                    "comment": f"STR {side}{level}",
                }
            )
    orders.append(
        {
            "ticket": 2_000,
            "state": 0,
            "type": 4,
            "time_setup_msc": 25_000,
            "time_done_msc": 0,
            "volume_initial": 0.01,
            "price_open": 101.0,
            "comment": "STR B1",
        }
    )
    deals = [
        {
            "ticket": 10,
            "order": 9,
            "time_msc": 500,
            "entry": 0,
            "reason": 3,
            "position_id": 9,
            "volume": 0.01,
            "price": 101.0,
            "comment": "STR B1",
        },
        {
            "ticket": 11,
            "order": 9,
            "time_msc": 1_000,
            "entry": 1,
            "reason": 4,
            "position_id": 9,
            "volume": 0.01,
            "price": 101.2,
            "comment": "[sl 101.20]",
        },
    ]

    result = analysis.analyze_lifecycle(
        orders,
        deals,
        deployments=[],
        summaries=[],
        ticks=[],
        server_offset_ms=0,
    )

    assert result["rearm_count"] == 1
    assert result["first_20_rearms"] == [
        {
            "stop_deal": 11,
            "comment": "STR B1",
            "delay_ms": 24_000,
            "new_order": 2_000,
        }
    ]


def test_lifecycle_uses_each_rearm_order_at_most_once():
    orders = [
        {
            "ticket": 2_000,
            "state": 0,
            "type": 4,
            "time_setup_msc": 4_000,
            "time_done_msc": 0,
            "volume_initial": 0.01,
            "price_open": 101.0,
            "comment": "STR B1",
        }
    ]
    deals = [
        {
            "ticket": 10,
            "time_msc": 500,
            "entry": 0,
            "reason": 3,
            "position_id": 9,
            "comment": "STR B1",
        },
        {
            "ticket": 11,
            "time_msc": 1_000,
            "entry": 1,
            "reason": 4,
            "position_id": 9,
            "comment": "[sl 101.20]",
        },
        {
            "ticket": 12,
            "time_msc": 1_500,
            "entry": 0,
            "reason": 3,
            "position_id": 10,
            "comment": "STR B1",
        },
        {
            "ticket": 13,
            "time_msc": 3_000,
            "entry": 1,
            "reason": 4,
            "position_id": 10,
            "comment": "[sl 101.20]",
        },
    ]

    result = analysis.analyze_lifecycle(
        orders,
        deals,
        deployments=[],
        summaries=[],
        ticks=[],
        server_offset_ms=0,
    )

    assert result["rearm_count"] == 1
