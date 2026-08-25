import json
import sys
from collections import namedtuple
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import straddle_replica.live_monitor as live_monitor_module
from straddle_replica.monitor_cli import main as monitor_cli_main
from straddle_replica.live_monitor import (
    HourlyCaptureStore,
    LiveMonitor,
    LiveMonitorConfig,
    MetaTrader5ReadAdapter,
    MonitorConnectionError,
    MonitorSafetyError,
    TickDeduplicator,
    atomic_write_json,
    hourly_path,
    read_monitor_status,
    state_fingerprint,
    tick_identity,
    validate_read_only_account,
)


UTC = timezone.utc
Tick = namedtuple(
    "Tick",
    "time bid ask last volume time_msc flags volume_real",
)
Account = namedtuple("Account", "login server trade_allowed")


def make_tick(time_msc: int, bid: float = 4044.5) -> object:
    return Tick(
        time_msc // 1000,
        bid,
        bid + 0.3,
        0.0,
        0,
        time_msc,
        6,
        0.0,
    )


def test_tick_deduplicator_removes_overlap_but_keeps_distinct_ticks():
    deduplicator = TickDeduplicator(max_seen=10)
    first = make_tick(1_785_538_640_100, 4044.50)
    duplicate = make_tick(1_785_538_640_100, 4044.50)
    same_millisecond_new_price = make_tick(1_785_538_640_100, 4044.51)

    assert deduplicator.filter([first, duplicate, same_millisecond_new_price]) == [
        first,
        same_millisecond_new_price,
    ]
    assert deduplicator.filter([first, same_millisecond_new_price]) == []


def test_tick_deduplicator_reads_numpy_structured_flags_field():
    ticks = np.array(
        [
            (
                1_785_732_141,
                4059.50,
                4059.80,
                0.0,
                0,
                1_785_732_141_797,
                6,
                0.0,
            )
        ],
        dtype=[
            ("time", "<i8"),
            ("bid", "<f8"),
            ("ask", "<f8"),
            ("last", "<f8"),
            ("volume", "<u8"),
            ("time_msc", "<i8"),
            ("flags", "<u4"),
            ("volume_real", "<f8"),
        ],
    )

    unique = TickDeduplicator().filter(ticks)

    assert len(unique) == 1
    assert tick_identity(unique[0])[-1] == 6


def test_state_fingerprint_is_stable_across_record_order():
    positions = [
        {"ticket": 2, "sl": 0.0, "comment": "STR S4"},
        {"ticket": 1, "sl": 4045.34, "comment": "STR S2"},
    ]
    orders = [
        {"ticket": 11, "price_open": 4053.89},
        {"ticket": 10, "price_open": 4052.54},
    ]

    assert state_fingerprint(positions, orders) == state_fingerprint(
        list(reversed(positions)),
        list(reversed(orders)),
    )
    assert state_fingerprint(positions, orders) != state_fingerprint(
        [{**positions[0], "sl": 4044.0}, positions[1]],
        orders,
    )


def test_state_fingerprint_ignores_tick_driven_price_and_profit_changes():
    positions = [
        {
            "ticket": 1,
            "sl": 4045.34,
            "price_current": 4044.59,
            "profit": 3.47,
            "swap": 0.0,
            "comment": "STR S2",
        }
    ]
    orders = [
        {
            "ticket": 10,
            "price_open": 4052.54,
            "price_current": 4044.59,
            "comment": "STR B1",
        }
    ]

    assert state_fingerprint(positions, orders) == state_fingerprint(
        [
            {
                **positions[0],
                "price_current": 4051.25,
                "profit": -2.19,
                "swap": -0.01,
            }
        ],
        [{**orders[0], "price_current": 4051.25}],
    )


def test_mt5_adapter_initializes_the_observer_terminal_in_portable_mode(
    monkeypatch,
):
    calls = {}
    module = SimpleNamespace(
        initialize=lambda **kwargs: calls.update(kwargs) or True,
        symbol_info=lambda symbol: SimpleNamespace(visible=True),
    )
    monkeypatch.setitem(sys.modules, "MetaTrader5", module)
    terminal_path = Path(r"D:\MT5ObserverTerminal\terminal64.exe")

    MetaTrader5ReadAdapter(
        terminal_path,
        "XAUUSD",
        expected_login=901018,
        expected_server="AchieverGlobalMarkets-Server",
    ).connect()

    assert calls == {
        "path": str(terminal_path),
        "portable": True,
        "login": 901018,
        "server": "AchieverGlobalMarkets-Server",
    }


def test_hourly_path_uses_utc_hour():
    when = datetime(2026, 8, 2, 18, 42, tzinfo=UTC)

    assert hourly_path(
        root="capture",
        prefix="ticks",
        when=when,
        suffix=".csv",
    ).as_posix().endswith("capture/ticks-20260802-18.csv")


def test_atomic_write_json_replaces_complete_document(tmp_path):
    target = tmp_path / "heartbeat.json"

    atomic_write_json(target, {"sequence": 1})
    atomic_write_json(target, {"sequence": 2, "healthy": True})

    assert json.loads(target.read_text(encoding="utf-8")) == {
        "healthy": True,
        "sequence": 2,
    }
    assert not target.with_suffix(".json.tmp").exists()


def test_atomic_write_json_retries_windows_sharing_violation(
    tmp_path,
    monkeypatch,
):
    target = tmp_path / "heartbeat.json"
    real_replace = live_monitor_module.os.replace
    attempts = 0

    def flaky_replace(source, destination):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise PermissionError(5, "Access is denied")
        return real_replace(source, destination)

    monkeypatch.setattr(
        live_monitor_module.os,
        "replace",
        flaky_replace,
    )

    atomic_write_json(target, {"healthy": True, "sequence": 7})

    assert attempts == 3
    assert json.loads(target.read_text(encoding="utf-8")) == {
        "healthy": True,
        "sequence": 7,
    }


def test_atomic_write_json_survives_extended_windows_sharing_violation(
    tmp_path,
    monkeypatch,
):
    target = tmp_path / "heartbeat.json"
    real_replace = live_monitor_module.os.replace
    elapsed = 0.0

    def advance_time(seconds):
        nonlocal elapsed
        elapsed += seconds

    def locked_replace(source, destination):
        if elapsed < 0.25:
            raise PermissionError(5, "Access is denied")
        return real_replace(source, destination)

    monkeypatch.setattr(live_monitor_module.time, "sleep", advance_time)
    monkeypatch.setattr(live_monitor_module.os, "replace", locked_replace)

    atomic_write_json(target, {"healthy": True, "sequence": 8})

    assert elapsed >= 0.25
    assert json.loads(target.read_text(encoding="utf-8")) == {
        "healthy": True,
        "sequence": 8,
    }


def test_validate_read_only_account_accepts_expected_investor_account():
    account = Account(901018, "AchieverGlobalMarkets-Server", False)

    validate_read_only_account(
        account,
        expected_login=901018,
        expected_server="AchieverGlobalMarkets-Server",
        require_read_only=True,
    )


@pytest.mark.parametrize(
    ("account", "message"),
    [
        (
            Account(901019, "AchieverGlobalMarkets-Server", False),
            "Unexpected account login",
        ),
        (Account(901018, "Other-Server", False), "Unexpected account server"),
        (
            Account(901018, "AchieverGlobalMarkets-Server", True),
            "trading is allowed",
        ),
    ],
)
def test_validate_read_only_account_fails_closed(account, message):
    with pytest.raises(MonitorSafetyError, match=message):
        validate_read_only_account(
            account,
            expected_login=901018,
            expected_server="AchieverGlobalMarkets-Server",
            require_read_only=True,
        )


def test_live_monitor_writes_initial_forensic_capture(tmp_path):
    Position = namedtuple(
        "Position",
        "ticket time_msc time_update_msc type magic identifier reason volume "
        "price_open sl tp price_current swap profit symbol comment",
    )
    Order = namedtuple(
        "Order",
        "ticket time_setup_msc time_done_msc type state magic position_id "
        "position_by_id reason volume_initial volume_current price_open sl tp "
        "price_current price_stoplimit symbol comment",
    )
    Deal = namedtuple(
        "Deal",
        "ticket order time_msc type entry magic position_id reason volume "
        "price commission swap profit fee symbol comment",
    )
    Terminal = namedtuple("Terminal", "connected trade_allowed build path data_path")
    Symbol = namedtuple(
        "Symbol",
        "name visible digits trade_tick_size time",
    )

    position = Position(
        20975632,
        1_785_538_402_680,
        1_785_538_500_000,
        1,
        26011001,
        20975632,
        3,
        0.01,
        4048.06,
        4045.34,
        0.0,
        4044.59,
        0.0,
        3.47,
        "XAUUSD",
        "STR S2",
    )
    order = Order(
        20975629,
        1_785_537_436_193,
        0,
        4,
        1,
        26011001,
        0,
        0,
        3,
        0.01,
        0.01,
        4052.54,
        0.0,
        0.0,
        4044.59,
        0.0,
        "XAUUSD",
        "STR B1",
    )
    deal = Deal(
        300,
        200,
        1_785_538_402_680,
        1,
        0,
        26011001,
        20975632,
        3,
        0.01,
        4048.06,
        0.0,
        0.0,
        0.0,
        0.0,
        "XAUUSD",
        "STR S2",
    )

    class FakeAdapter:
        def __init__(self):
            self.connected = False

        def connect(self):
            self.connected = True

        def disconnect(self):
            self.connected = False

        def account_info(self):
            return Account(901018, "AchieverGlobalMarkets-Server", False)

        def terminal_info(self):
            return Terminal(True, False, 6090, "terminal", "data")

        def symbol_info(self):
            return Symbol(
                "XAUUSD",
                True,
                2,
                0.01,
                int(datetime.now(tz=UTC).timestamp()) + 7200,
            )

        def positions(self):
            return [position]

        def orders(self):
            return [order]

        def ticks(self, start, end):
            return [make_tick(1_785_538_640_100)]

        def history_orders(self, start, end):
            return [order]

        def history_deals(self, start, end):
            return [deal]

    output = tmp_path / "live"
    store = HourlyCaptureStore(output, "test-session")
    adapter = FakeAdapter()
    monitor = LiveMonitor(
        LiveMonitorConfig(
            terminal_path=tmp_path / "terminal64.exe",
            output_root=output,
        ),
        adapter,
        store,
    )

    monitor.initialize()
    store.close()

    status = read_monitor_status(output)
    assert monitor._history_server_offset == timedelta(hours=2)
    assert status["healthy"] is True
    assert status["read_only_verified"] is True
    assert status["positions_total"] == 1
    assert status["orders_total"] == 1
    assert status["tick_count"] == 1
    assert status["snapshot_count"] == 1
    assert status["history_order_count"] == 1
    assert status["history_deal_count"] == 1
    assert list((output / "test-session").glob("ticks-*.csv"))
    assert list((output / "test-session").glob("snapshots-*.jsonl"))
    assert list((output / "test-session").glob("history-orders-*.jsonl"))
    assert list((output / "test-session").glob("history-deals-*.jsonl"))


def test_live_monitor_restores_previous_offset_when_symbol_time_is_stale(
    tmp_path,
    monkeypatch,
):
    started = datetime(2026, 8, 17, 1, 51, 58, tzinfo=UTC)
    monkeypatch.setattr(live_monitor_module, "utc_now", lambda: started)
    output = tmp_path / "live"
    previous = output / "20260813T072501Z_901018_XAUUSD"
    previous.mkdir(parents=True)
    (previous / "manifest.json").write_text(
        json.dumps(
            {
                "account": {
                    "login": 901018,
                    "server": "AchieverGlobalMarkets-Server",
                },
                "symbol": {"name": "XAUUSD"},
                "time_domains": {
                    "history_server_offset_seconds": 7_200,
                },
            }
        ),
        encoding="utf-8",
    )
    interrupted = output / "20260817T015158Z_901018_XAUUSD"
    interrupted.mkdir()
    (interrupted / "manifest.json").write_text(
        json.dumps(
            {
                "account": {
                    "login": 901018,
                    "server": "AchieverGlobalMarkets-Server",
                },
                "symbol": {"name": "XAUUSD"},
                "time_domains": {
                    "history_server_offset_seconds": 0,
                },
            }
        ),
        encoding="utf-8",
    )

    class StaleSymbolAdapter:
        def connect(self):
            return None

        def disconnect(self):
            return None

        def account_info(self):
            return Account(901018, "AchieverGlobalMarkets-Server", False)

        def terminal_info(self):
            return SimpleNamespace(connected=True, trade_allowed=False)

        def symbol_info(self):
            return SimpleNamespace(
                name="XAUUSD",
                visible=True,
                time=int(
                    datetime(
                        2026,
                        8,
                        14,
                        2,
                        19,
                        38,
                        tzinfo=UTC,
                    ).timestamp()
                ),
            )

        def positions(self):
            return []

        def orders(self):
            return []

        def ticks(self, start, end):
            return []

        def history_orders(self, start, end):
            return []

        def history_deals(self, start, end):
            return []

    store = HourlyCaptureStore(output, "20260817T030929Z_901018_XAUUSD")
    monitor = LiveMonitor(
        LiveMonitorConfig(
            terminal_path=tmp_path / "terminal64.exe",
            output_root=output,
        ),
        StaleSymbolAdapter(),
        store,
    )

    monitor.initialize()
    manifest = json.loads(
        (store.session_dir / "manifest.json").read_text(encoding="utf-8")
    )
    store.close()

    assert monitor._history_server_offset == timedelta(hours=2)
    assert (
        manifest["time_domains"]["history_server_offset_seconds"]
        == 7_200
    )


def test_monitor_status_cli_reads_current_session(tmp_path, capsys):
    output = tmp_path / "live"
    session = output / "session"
    session.mkdir(parents=True)
    atomic_write_json(
        output / "current-session.json",
        {"session_id": "session", "session_dir": str(session)},
    )
    atomic_write_json(
        session / "heartbeat.json",
        {
            "healthy": True,
            "stopped": False,
            "read_only_verified": True,
            "positions_total": 4,
            "orders_total": 54,
        },
    )

    assert monitor_cli_main(["monitor-status", "--output", str(output)]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["healthy"] is True
    assert status["positions_total"] == 4
    assert status["orders_total"] == 54


def test_supervised_monitor_exits_on_connection_error(tmp_path):
    class FailingAdapter:
        def account_info(self):
            raise MonitorConnectionError("terminal unavailable")

        def disconnect(self):
            return None

    store = HourlyCaptureStore(tmp_path / "live", "failed-session")
    monitor = LiveMonitor(
        LiveMonitorConfig(
            terminal_path=tmp_path / "terminal64.exe",
            output_root=tmp_path / "live",
            exit_on_connection_error=True,
        ),
        FailingAdapter(),
        store,
    )

    with pytest.raises(MonitorConnectionError, match="terminal unavailable"):
        monitor.run()


def test_unsupervised_reconnect_failure_does_not_stop_monitor(tmp_path):
    class FailingReconnectAdapter:
        def __init__(self):
            self.connect_calls = 0

        def disconnect(self):
            return None

        def connect(self):
            self.connect_calls += 1
            raise MonitorConnectionError("terminal still unavailable")

    adapter = FailingReconnectAdapter()
    store = HourlyCaptureStore(tmp_path / "live", "retry-session")
    monitor = LiveMonitor(
        LiveMonitorConfig(
            terminal_path=tmp_path / "terminal64.exe",
            output_root=tmp_path / "live",
            exit_on_connection_error=False,
        ),
        adapter,
        store,
    )

    assert monitor._reconnect() is False
    assert adapter.connect_calls == 1
    assert monitor._reconnect_count == 0
    assert monitor._last_error == (
        "MonitorConnectionError: terminal still unavailable"
    )
    store.close()


def test_history_poll_looks_ahead_for_broker_server_timestamps(tmp_path):
    class RecordingAdapter:
        def __init__(self):
            self.ends = []

        def history_orders(self, start, end):
            self.ends.append(end)
            return []

        def history_deals(self, start, end):
            self.ends.append(end)
            return []

    now = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)
    store = HourlyCaptureStore(tmp_path / "live", "history-lookahead")
    adapter = RecordingAdapter()
    monitor = LiveMonitor(
        LiveMonitorConfig(
            terminal_path=tmp_path / "terminal64.exe",
            output_root=tmp_path / "live",
        ),
        adapter,
        store,
    )
    monitor._history_server_offset = timedelta(hours=2)

    monitor._capture_history(now)
    store.close()

    assert adapter.ends
    assert all(
        end == now + timedelta(hours=2, seconds=1)
        for end in adapter.ends
    )


def test_history_poll_recovers_deals_delayed_by_a_connection_gap(tmp_path):
    cursor = int(
        datetime(2026, 8, 17, 12, 32, 27, tzinfo=UTC).timestamp() * 1000
    )
    newest = {"ticket": 2, "time_msc": cursor}
    delayed = {"ticket": 1, "time_msc": cursor - 60_000}

    class DelayedHistoryAdapter:
        def __init__(self):
            self.deal_polls = 0

        def history_orders(self, start, end):
            return []

        def history_deals(self, start, end):
            self.deal_polls += 1
            available = [newest]
            if self.deal_polls >= 2:
                available.insert(0, delayed)
            start_msc = int(start.timestamp() * 1000)
            return [
                deal
                for deal in available
                if int(deal["time_msc"]) >= start_msc
            ]

    store = HourlyCaptureStore(tmp_path / "live", "history-delay")
    monitor = LiveMonitor(
        LiveMonitorConfig(
            terminal_path=tmp_path / "terminal64.exe",
            output_root=tmp_path / "live",
        ),
        DelayedHistoryAdapter(),
        store,
    )
    monitor._history_from_msc = cursor - 120_000

    now = datetime(2026, 8, 17, 10, 32, 27, tzinfo=UTC)
    monitor._capture_history(now)
    monitor._capture_history(now + timedelta(seconds=1))
    store.close()

    assert monitor._history_deal_count == 2
    assert monitor._seen_history_deals == {1, 2}


def test_history_seed_days_expands_only_the_initial_history_window(tmp_path):
    store = HourlyCaptureStore(tmp_path / "live", "history-seed")
    monitor = LiveMonitor(
        LiveMonitorConfig(
            terminal_path=tmp_path / "terminal64.exe",
            output_root=tmp_path / "live",
            history_seed_days=60,
        ),
        SimpleNamespace(),
        store,
    )

    expected = int(
        (monitor.started_at - timedelta(days=60)).timestamp() * 1000
    )

    assert monitor._history_from_msc == expected
    store.close()


def test_monitor_cli_maps_history_seed_days(monkeypatch, tmp_path):
    captured = {}

    def fake_run(config):
        captured["config"] = config
        return tmp_path / "session"

    monkeypatch.setattr(
        "straddle_replica.monitor_cli.run_live_monitor",
        fake_run,
    )

    assert (
        monitor_cli_main(
            [
                "monitor-live",
                "--output",
                str(tmp_path / "live"),
                "--history-seed-days",
                "60",
                "--duration-hours",
                "0.001",
            ]
        )
        == 0
    )
    assert captured["config"].history_seed_days == 60


def test_history_rates_seed_requires_a_timeframe(tmp_path):
    with pytest.raises(
        ValueError,
        match="history_rates_timeframe",
    ):
        LiveMonitorConfig(
            terminal_path=tmp_path / "terminal64.exe",
            output_root=tmp_path / "live",
            history_rates_seed_days=60,
        ).validate()


def test_mt5_adapter_reads_named_timeframe_rates(tmp_path):
    calls = {}
    module = SimpleNamespace(
        TIMEFRAME_H1=16_385,
        copy_rates_range=lambda symbol, timeframe, start, end: (
            calls.update(
                {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "start": start,
                    "end": end,
                }
            )
            or [{"time": 1, "open": 2.0}]
        ),
        last_error=lambda: (0, "ok"),
    )
    adapter = MetaTrader5ReadAdapter(
        tmp_path / "terminal64.exe",
        "XAUUSD",
        expected_login=901018,
        expected_server="AchieverGlobalMarkets-Server",
    )
    adapter._mt5 = module
    start = datetime(2026, 7, 1, tzinfo=UTC)
    end = datetime(2026, 8, 1, tzinfo=UTC)

    assert adapter.rates("H1", start, end) == [{"time": 1, "open": 2.0}]
    assert calls == {
        "symbol": "XAUUSD",
        "timeframe": 16_385,
        "start": start,
        "end": end,
    }
    with pytest.raises(ValueError, match="Unsupported MT5 timeframe"):
        adapter.rates("H7", start, end)


def test_history_rates_seed_writes_normalized_h1_rows(tmp_path):
    class RatesAdapter:
        def rates(self, timeframe, start, end):
            assert timeframe == "H1"
            assert end > start
            return [
                {
                    "time": 1_786_000_000,
                    "open": 4_400.0,
                    "high": 4_410.0,
                    "low": 4_390.0,
                    "close": 4_405.0,
                    "tick_volume": 123,
                    "spread": 30,
                    "real_volume": 0,
                }
            ]

    store = HourlyCaptureStore(tmp_path / "live", "rates-seed")
    monitor = LiveMonitor(
        LiveMonitorConfig(
            terminal_path=tmp_path / "terminal64.exe",
            output_root=tmp_path / "live",
            history_rates_timeframe="H1",
            history_rates_seed_days=60,
        ),
        RatesAdapter(),
        store,
    )

    monitor._capture_history_rates()
    store.close()

    paths = list(
        (tmp_path / "live" / "rates-seed").glob(
            "history-rates-H1-*.jsonl"
        )
    )
    assert len(paths) == 1
    payload = json.loads(paths[0].read_text(encoding="utf-8"))
    assert payload["timeframe"] == "H1"
    assert payload["open"] == 4_400.0
    assert payload["capture_time_utc"]


def test_monitor_cli_maps_history_rates_seed(monkeypatch, tmp_path):
    captured = {}

    def fake_run(config):
        captured["config"] = config
        return tmp_path / "session"

    monkeypatch.setattr(
        "straddle_replica.monitor_cli.run_live_monitor",
        fake_run,
    )

    assert (
        monitor_cli_main(
            [
                "monitor-live",
                "--output",
                str(tmp_path / "live"),
                "--history-rates-timeframe",
                "H1",
                "--history-rates-seed-days",
                "60",
                "--duration-hours",
                "0.001",
            ]
        )
        == 0
    )
    assert captured["config"].history_rates_timeframe == "H1"
    assert captured["config"].history_rates_seed_days == 60


def test_initial_tick_poll_uses_broker_server_time_window(tmp_path):
    class RecordingAdapter:
        def __init__(self):
            self.windows = []

        def ticks(self, start, end):
            self.windows.append((start, end))
            return []

    now = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)
    store = HourlyCaptureStore(tmp_path / "live", "tick-lookahead")
    adapter = RecordingAdapter()
    monitor = LiveMonitor(
        LiveMonitorConfig(
            terminal_path=tmp_path / "terminal64.exe",
            output_root=tmp_path / "live",
        ),
        adapter,
        store,
    )
    monitor._history_server_offset = timedelta(hours=2)

    monitor._capture_ticks(now)
    store.close()

    assert adapter.windows == [
        (
            now + timedelta(hours=2, seconds=-10),
            now + timedelta(hours=2, seconds=1),
        )
    ]


def test_followup_tick_poll_resumes_from_broker_tick_timestamp(tmp_path):
    broker_tick_msc = int(
        datetime(2026, 8, 3, 14, 0, tzinfo=UTC).timestamp() * 1000
    )

    class RecordingAdapter:
        def __init__(self):
            self.windows = []

        def ticks(self, start, end):
            self.windows.append((start, end))
            return [make_tick(broker_tick_msc)]

    now = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)
    store = HourlyCaptureStore(tmp_path / "live", "tick-resume")
    adapter = RecordingAdapter()
    monitor = LiveMonitor(
        LiveMonitorConfig(
            terminal_path=tmp_path / "terminal64.exe",
            output_root=tmp_path / "live",
        ),
        adapter,
        store,
    )
    monitor._history_server_offset = timedelta(hours=2)

    monitor._capture_ticks(now)
    monitor._capture_ticks(now + timedelta(seconds=1))
    store.close()

    assert adapter.windows[1] == (
        datetime.fromtimestamp(
            (broker_tick_msc - 1_000) / 1000,
            tz=UTC,
        ),
        now + timedelta(hours=2, seconds=2),
    )
