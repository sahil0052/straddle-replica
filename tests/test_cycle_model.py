from datetime import datetime, timedelta, timezone

import pytest

from straddle_replica.model import (
    CycleEngine,
    CycleState,
    PositionState,
    Tick,
)
from straddle_replica.profiles import ProfileName, get_profile


UTC = timezone.utc


def test_deployment_queue_schedules_one_order_every_100ms():
    start = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)
    engine = CycleEngine(
        profile=get_profile(ProfileName.LATEST_30),
        tick_size=0.01,
        inter_order_delay_ms=100,
    )

    actions = engine.start_cycle(Tick(start, bid=4099.85, ask=4100.15))

    assert engine.state == CycleState.DEPLOYING
    assert len(actions) == 60
    assert actions[0].scheduled_at == start
    assert actions[1].scheduled_at == start + timedelta(milliseconds=100)
    assert actions[-1].scheduled_at == start + timedelta(milliseconds=5900)


def test_closed_level_is_rearmed_at_original_grid_price():
    start = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)
    engine = CycleEngine(get_profile(ProfileName.LATEST_30), tick_size=0.01)
    actions = engine.start_cycle(Tick(start, bid=4099.85, ask=4100.15))
    first_buy = actions[0]

    engine.mark_deployment_complete()
    engine.on_level_filled("B1", ticket=101, fill_price=first_buy.price)
    rearm = engine.on_position_closed("B1", ticket=101)

    assert engine.state == CycleState.RUNNING
    assert rearm.comment == "STR B1"
    assert rearm.price == first_buy.price
    assert rearm.volume == pytest.approx(0.01)


def test_two_step_activation_then_tightened_trail_ratchets_only_forward():
    engine = CycleEngine(get_profile(ProfileName.LATEST_30), tick_size=0.01)
    position = PositionState(
        level_key="B1",
        ticket=101,
        side="buy",
        entry_price=4100.0,
        volume=0.01,
    )
    step = 1.35

    assert engine.next_stop(position, market_price=4102.0, step=step) is None

    first_stop = engine.next_stop(position, market_price=4103.1, step=step)
    assert first_stop == pytest.approx(4100.40)
    position.stop_loss = first_stop

    raised_stop = engine.next_stop(position, market_price=4105.4, step=step)
    assert raised_stop == pytest.approx(4104.05)
    position.stop_loss = raised_stop

    assert engine.next_stop(position, market_price=4104.0, step=step) is None


def test_latest_profile_trails_two_steps_before_three_step_tightening():
    engine = CycleEngine(get_profile(ProfileName.LATEST_30), tick_size=0.01)
    position = PositionState(
        level_key="B1",
        ticket=101,
        side="buy",
        entry_price=4100.0,
        volume=0.01,
        stop_loss=4100.20,
    )
    step = 1.35

    pre_tighten = engine.next_stop(
        position,
        market_price=4100.0 + 2.5 * step,
        step=step,
    )
    assert pre_tighten == pytest.approx(4100.68)
    position.stop_loss = pre_tighten

    tightened = engine.next_stop(
        position,
        market_price=4100.0 + 3.1 * step,
        step=step,
    )
    assert tightened == pytest.approx(4102.84)


def test_latest_cycle_cancels_then_closes_then_restarts():
    engine = CycleEngine(get_profile(ProfileName.LATEST_30), tick_size=0.01)
    engine.start_cycle(Tick(datetime.now(UTC), bid=4099.8, ask=4100.2))
    engine.mark_deployment_complete()

    assert engine.begin_close() == CycleState.CANCELING
    assert engine.mark_orders_canceled() == CycleState.CLOSING
    assert engine.mark_positions_flat() == CycleState.RESTARTING
    assert engine.mark_restart_ready() == CycleState.IDLE
