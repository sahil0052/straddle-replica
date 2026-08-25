from straddle_replica.basket_analysis import basket_candidates


def test_basket_candidates_report_first_crossing_and_trigger_delay() -> None:
    snapshots = [
        {"time_msc": 1_000, "realized": 10.0, "floating": 15.0},
        {"time_msc": 2_000, "realized": 12.0, "floating": 19.0},
        {"time_msc": 3_000, "realized": 14.0, "floating": 18.0},
    ]

    result = basket_candidates(
        snapshots,
        trigger_time_msc=3_500,
        fixed_targets=(30.0, 35.0),
    )

    assert result["fixed_30"]["first_crossing_msc"] == 2_000
    assert result["fixed_30"]["trigger_delay_ms"] == 1_500
    assert result["fixed_35"]["first_crossing_msc"] is None
