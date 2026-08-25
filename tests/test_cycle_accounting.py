from straddle_replica.cycle_accounting import calculate_cycle_realized


def test_cycle_realized_counts_each_owned_exit_deal_once() -> None:
    deals = [
        {
            "ticket": 1001,
            "time_msc": 1_700_000_000_100,
            "magic": 901018,
            "symbol": "XAUUSD",
            "entry": 1,
            "profit": 5.00,
            "swap": -0.10,
            "commission": -0.20,
            "fee": 0.0,
        },
        {
            "ticket": 1001,
            "time_msc": 1_700_000_000_100,
            "magic": 901018,
            "symbol": "XAUUSD",
            "entry": 1,
            "profit": 5.00,
            "swap": -0.10,
            "commission": -0.20,
            "fee": 0.0,
        },
        {
            "ticket": 1002,
            "time_msc": 1_700_000_000_200,
            "magic": 901018,
            "symbol": "XAUUSD",
            "entry": 2,
            "profit": -1.00,
            "swap": 0.0,
            "commission": -0.05,
            "fee": -0.01,
        },
    ]

    result = calculate_cycle_realized(
        deals,
        cycle_started_msc=1_700_000_000_000,
        magic=901018,
        symbol="XAUUSD",
    )

    assert result.unique_exit_deals == 2
    assert result.duplicate_deal_tickets == (1001,)
    assert result.net == 3.64


def test_cycle_realized_filters_time_magic_symbol_and_entry() -> None:
    base = {
        "time_msc": 1_700_000_000_100,
        "magic": 901018,
        "symbol": "XAUUSD",
        "entry": 1,
        "profit": 1.0,
        "swap": 0.0,
        "commission": 0.0,
        "fee": 0.0,
    }
    deals = [
        {"ticket": 1, **base},
        {"ticket": 2, **base, "time_msc": 1_699_999_999_999},
        {"ticket": 3, **base, "magic": 7},
        {"ticket": 4, **base, "symbol": "EURUSD"},
        {"ticket": 5, **base, "entry": 0},
    ]

    result = calculate_cycle_realized(
        deals,
        cycle_started_msc=1_700_000_000_000,
        magic=901018,
        symbol="XAUUSD",
    )

    assert result.net == 1.0
    assert result.unique_exit_deals == 1
