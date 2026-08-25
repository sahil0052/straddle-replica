import pytest

from straddle_replica.profiles import (
    ProfileName,
    build_grid,
    get_profile,
    normalize_price,
)


@pytest.mark.parametrize(
    ("name", "levels", "expected_lots"),
    [
        (ProfileName.HISTORICAL_50, 50, {1: 0.01, 15: 0.01, 16: 0.03, 25: 0.03, 26: 0.06, 50: 0.06}),
        (ProfileName.HISTORICAL_60, 60, {1: 0.01, 15: 0.01, 16: 0.02, 45: 0.02, 46: 0.05, 60: 0.05}),
        (ProfileName.AGGRESSIVE_30, 30, {1: 0.08, 10: 0.08, 11: 0.41, 20: 0.41, 21: 0.82, 30: 0.82}),
        (ProfileName.LOW_RISK_30, 30, {1: 0.01, 10: 0.01, 11: 0.02, 20: 0.02, 21: 0.05, 30: 0.05}),
        (ProfileName.LATEST_30, 30, {1: 0.01, 10: 0.01, 11: 0.06, 20: 0.06, 21: 0.15, 30: 0.15}),
    ],
)
def test_observed_profile_lot_tiers(name, levels, expected_lots):
    profile = get_profile(name)
    assert profile.levels_per_side == levels
    for level, expected in expected_lots.items():
        assert profile.lot_for_level(level) == pytest.approx(expected)


def test_latest_profile_uses_anchor_divided_by_3000():
    profile = get_profile(ProfileName.LATEST_30)
    assert profile.calculate_step(anchor=4100.0, tick_size=0.01) == pytest.approx(1.37)


def test_latest_profile_uses_observed_twenty_second_basket_close_and_restart():
    profile = get_profile(ProfileName.LATEST_30)

    assert profile.cycle_target_money == pytest.approx(30.0)
    assert profile.cancel_before_close is True
    assert profile.deployment_fill_cooldown_seconds == 20
    assert profile.close_interval_seconds == 20
    assert profile.restart_delay_seconds == 20
    assert profile.rearm_delay_seconds == 20
    assert profile.stop_update_interval_seconds == 0
    assert profile.max_stop_updates_per_pass == 1
    assert profile.stop_scan_newest_first is True
    assert profile.stop_updates_on_timer is True
    assert profile.activation_uses_trailing_distance is True

    for name in (
        ProfileName.HISTORICAL_50,
        ProfileName.HISTORICAL_60,
        ProfileName.AGGRESSIVE_30,
        ProfileName.LOW_RISK_30,
    ):
        assert get_profile(name).deployment_fill_cooldown_seconds == 0


def test_aggressive_profile_uses_anchor_divided_by_6000():
    profile = get_profile(ProfileName.AGGRESSIVE_30)
    assert profile.calculate_step(anchor=4080.0, tick_size=0.01) == pytest.approx(0.68)


def test_historical_profiles_use_holdout_accepted_atr_models():
    historical_50 = get_profile(ProfileName.HISTORICAL_50)
    historical_60 = get_profile(ProfileName.HISTORICAL_60)

    assert historical_50.step_mode.value == "ATR"
    assert historical_50.atr_timeframe_minutes == 15
    assert historical_50.atr_period == 17
    assert historical_50.calculate_step(
        anchor=4100.0, tick_size=0.01, atr_value=10.0
    ) == pytest.approx(1.04)

    assert historical_60.step_mode.value == "ATR"
    assert historical_60.atr_timeframe_minutes == 5
    assert historical_60.atr_period == 44
    assert historical_60.calculate_step(
        anchor=4100.0, tick_size=0.01, atr_value=10.0
    ) == pytest.approx(0.92)


def test_30_level_profiles_use_one_step_trailing_after_profit_lock():
    for name in (
        ProfileName.AGGRESSIVE_30,
        ProfileName.LOW_RISK_30,
        ProfileName.LATEST_30,
    ):
        profile = get_profile(name)
        assert profile.lock_trigger_steps == pytest.approx(2.0)
        assert profile.lock_offset_price == pytest.approx(0.2)
        assert profile.pre_tighten_trail_distance_steps == pytest.approx(2.0)
        assert profile.tighten_trigger_steps == pytest.approx(3.0)
        assert profile.trail_distance_steps == pytest.approx(1.0)

    assert (
        get_profile(ProfileName.HISTORICAL_50).trail_distance_steps
        == pytest.approx(2.0)
    )
    assert (
        get_profile(ProfileName.HISTORICAL_60).trail_distance_steps
        == pytest.approx(2.0)
    )


def test_grid_is_symmetric_and_alternates_buy_then_sell():
    profile = get_profile(ProfileName.LATEST_30)
    orders = build_grid(profile, anchor=4100.0, tick_size=0.01)

    assert len(orders) == 60
    assert [order.comment for order in orders[:6]] == [
        "STR B1",
        "STR S1",
        "STR B2",
        "STR S2",
        "STR B3",
        "STR S3",
    ]
    assert orders[0].price == pytest.approx(4101.37)
    assert orders[1].price == pytest.approx(4098.63)
    assert orders[-2].price == pytest.approx(normalize_price(4100 + 30 * 1.37, 0.01))
    assert orders[-1].price == pytest.approx(normalize_price(4100 - 30 * 1.37, 0.01))
