from datetime import datetime, timezone

from straddle_replica.profiles import ProfileName, get_profile
from straddle_replica.replay import build_deployment_events


UTC = timezone.utc


def test_replay_events_preserve_grid_order_contract():
    events = build_deployment_events(
        profile=get_profile(ProfileName.LATEST_30),
        anchor=4100.0,
        tick_size=0.01,
        start=datetime(2026, 7, 30, 12, 0, tzinfo=UTC),
        inter_order_delay_ms=100,
    )

    assert len(events) == 60
    assert events[0].comment == "STR B1"
    assert events[1].comment == "STR S1"
    assert events[-1].comment == "STR S30"
    assert (events[-1].time - events[0].time).total_seconds() == 5.9
