from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OBSERVER = ROOT / "mql5" / "StraddleObserver.mq5"
PYTHON_MONITOR = ROOT / "straddle_replica" / "live_monitor.py"
BUILD_SCRIPT = ROOT / "scripts" / "build_observer.ps1"
INSTALL_SCRIPT = ROOT / "scripts" / "install_observer.ps1"
START_SCRIPT = ROOT / "scripts" / "start_live_monitor.ps1"
STOP_SCRIPT = ROOT / "scripts" / "stop_live_monitor.ps1"
TASK_SCRIPT = ROOT / "scripts" / "install_monitor_task.ps1"
PACKAGE_SCRIPT = ROOT / "scripts" / "package_monitor.ps1"
VPS_INSTALL_SCRIPT = ROOT / "scripts" / "install_vps_monitor.ps1"
CREATE_TERMINAL_SCRIPT = ROOT / "scripts" / "create_monitor_terminal.ps1"
STARTUP_CONFIG = ROOT / "monitor" / "observer-startup.ini"
MONITOR_REQUIREMENTS = ROOT / "requirements-monitor.txt"
LINUX_MT5_RUNNER = ROOT / "deploy" / "linux" / "run_mt5_observer.sh"
LINUX_PYTHON_RUNNER = ROOT / "deploy" / "linux" / "run_python_monitor.sh"
LINUX_DAILY_RUNNER = ROOT / "deploy" / "linux" / "run_daily_analysis.sh"
LINUX_DAILY_SERVICE = (
    ROOT / "deploy" / "linux" / "straddle-daily-analysis.service"
)
LINUX_DAILY_TIMER = (
    ROOT / "deploy" / "linux" / "straddle-daily-analysis.timer"
)


def test_observer_exposes_read_only_capture_handlers():
    source = OBSERVER.read_text(encoding="utf-8")

    for required in (
        "input ulong ExpectedLogin = 901018",
        'input string ExpectedServer = "AchieverGlobalMarkets-Server"',
        'input string MonitoredSymbol = "XAUUSD"',
        "ACCOUNT_TRADE_ALLOWED",
        "EventSetMillisecondTimer",
        "CopyTicks(",
        "FILE_COMMON",
        "input int FullCheckpointIntervalMs = 30000",
        "void OnTradeTransaction(",
        "void OnTimer()",
        "void OnDeinit(",
    ):
        assert required in source


def test_monitor_sources_contain_no_trading_operations():
    mql5 = OBSERVER.read_text(encoding="utf-8")
    python = PYTHON_MONITOR.read_text(encoding="utf-8")

    forbidden_mql5 = (
        "#include <Trade/",
        "OrderSend(",
        "OrderSendAsync(",
        "CTrade",
        "TRADE_ACTION_",
        "PositionModify(",
        "PositionClose(",
        "OrderDelete(",
    )
    forbidden_python = (
        ".order_send(",
        "mt5.order_send(",
        "TRADE_ACTION_",
    )

    assert not any(token in mql5 for token in forbidden_mql5)
    assert not any(token in python for token in forbidden_python)


def test_observer_queues_transactions_before_file_io():
    source = OBSERVER.read_text(encoding="utf-8")
    handler = source.split("void OnTradeTransaction(", 1)[1].split(
        "void OnTimer()", 1
    )[0]

    assert "EnqueueTransaction(" in handler
    assert "FileWrite(" not in handler
    assert "FileFlush(" not in handler


def test_observer_state_fingerprint_excludes_tick_driven_current_prices():
    source = OBSERVER.read_text(encoding="utf-8")
    fingerprint = source.split("string BuildStateFingerprint()", 1)[1].split(
        "string SnapshotPrefix(", 1
    )[0]

    assert "POSITION_PRICE_CURRENT" not in fingerprint
    assert "ORDER_PRICE_CURRENT" not in fingerprint


def test_monitor_scripts_preserve_read_only_guards():
    for path in (
        BUILD_SCRIPT,
        INSTALL_SCRIPT,
        START_SCRIPT,
        STOP_SCRIPT,
        TASK_SCRIPT,
        PACKAGE_SCRIPT,
        VPS_INSTALL_SCRIPT,
        CREATE_TERMINAL_SCRIPT,
    ):
        assert path.exists(), path

    install = INSTALL_SCRIPT.read_text(encoding="utf-8")
    start = START_SCRIPT.read_text(encoding="utf-8")
    stop = STOP_SCRIPT.read_text(encoding="utf-8")
    task = TASK_SCRIPT.read_text(encoding="utf-8")

    assert "StraddleObserver.ex5" in install
    assert "StraddleReplica" not in install
    assert "--require-read-only" in start
    assert "--exit-on-connection-error" in start
    assert "-WindowStyle Hidden" in start
    assert "observer-startup.ini" in start
    assert "/config:" in start
    assert "/portable" in start
    assert "Get-CimInstance Win32_Process" in stop
    assert "monitor-live" in stop
    assert "$record.workspace" in stop
    assert "does not belong to workspace" not in stop
    assert "Register-ScheduledTask" in task
    assert "-RepetitionInterval" in task
    assert "New-TimeSpan -Minutes 1" in task
    assert "-LogonType Interactive `" in task
    assert "InteractiveToken" not in task
    assert "Password" not in task


def test_observer_startup_config_attaches_only_the_read_only_observer():
    config = STARTUP_CONFIG.read_text(encoding="utf-8")

    assert "[StartUp]" in config
    assert "Expert=StraddleObserver\\StraddleObserver" in config
    assert "Symbol=XAUUSD" in config
    assert "Period=H1" in config
    assert "StraddleReplica" not in config
    assert "Login=" not in config
    assert "Password=" not in config


def test_vps_package_contains_only_monitor_dependencies_and_no_credentials():
    package = PACKAGE_SCRIPT.read_text(encoding="utf-8")
    installer = VPS_INSTALL_SCRIPT.read_text(encoding="utf-8")
    requirements = MONITOR_REQUIREMENTS.read_text(encoding="utf-8")

    assert "Compress-Archive" in package
    assert "StraddleObserver.ex5" in package
    assert "requirements-monitor.txt" in package
    assert "ReportHistory" not in package
    assert "StraddleReplica.ex5" not in package
    assert "Password" not in package
    assert "install_observer.ps1" in installer
    assert "install_monitor_task.ps1" in installer
    assert "start_live_monitor.ps1" in installer
    assert "Password" not in installer
    assert requirements.strip() == "MetaTrader5==5.0.5735"


def test_isolated_terminal_creator_copies_only_observer_runtime():
    source = CREATE_TERMINAL_SCRIPT.read_text(encoding="utf-8")

    assert ".straddle-observer-terminal.json" in source
    assert "StraddleObserver.ex5" in source
    assert "StraddleReplica" not in source
    assert "accounts.dat" not in source
    assert "Copy-Item" in source
    assert 'foreach ($directoryName in @("Config", "Profiles", "Sounds"))' in source


def test_linux_monitor_services_share_one_wine_runtime_directory():
    for path in (LINUX_MT5_RUNNER, LINUX_PYTHON_RUNNER):
        source = path.read_text(encoding="utf-8")
        assert 'runtime_dir="/run/user/$(id -u)"' in source
        assert 'export XDG_RUNTIME_DIR="$runtime_dir"' in source
        assert 'mkdir -p -m 700 "$runtime_dir"' in source


def test_linux_python_monitor_waits_for_current_mql_generation():
    source = LINUX_PYTHON_RUNNER.read_text(encoding="utf-8")

    assert "monitor_started_epoch=$(date +%s)" in source
    assert 'python3 - "$mql_root" "$monitor_started_epoch"' in source
    assert "started_epoch = float(sys.argv[2])" in source
    assert "heartbeat.stat().st_mtime < started_epoch" in source


def test_linux_daily_analysis_never_restarts_the_live_monitor():
    runner = LINUX_DAILY_RUNNER.read_text(encoding="utf-8")
    service = LINUX_DAILY_SERVICE.read_text(encoding="utf-8")
    timer = LINUX_DAILY_TIMER.read_text(encoding="utf-8")

    assert "check_monitor_health.py" in runner
    assert "analyze_live_capture.py" in runner
    assert "--mql-root" in runner
    assert "--python-root" in runner
    assert "systemctl stop" not in runner
    assert "systemctl restart" not in runner
    assert "ExecStart=/home/ubuntu/straddle-monitor/bin/run_daily_analysis.sh" in service
    assert "OnCalendar=*-*-* 00:15:00 UTC" in timer
    assert "Persistent=true" in timer
