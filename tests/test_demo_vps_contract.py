from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "deploy" / "linux" / "run_mt5_demo.sh"
SERVICE = ROOT / "deploy" / "linux" / "straddle-demo-mt5.service"
STARTUP = ROOT / "monitor" / "demo-startup.ini"
PACKAGE = ROOT / "scripts" / "package_demo_vps.ps1"
EXACT_SET = ROOT / "profiles" / "latest_30.set"
MANUAL_DEMO_SET = ROOT / "profiles" / "latest_30_manual_demo.set"
ANALYSIS_RUNNER = ROOT / "deploy" / "linux" / "run_demo_analysis.sh"
ANALYSIS_SERVICE = (
    ROOT / "deploy" / "linux" / "straddle-demo-daily-analysis.service"
)
ANALYSIS_TIMER = (
    ROOT / "deploy" / "linux" / "straddle-demo-daily-analysis.timer"
)


def test_demo_runtime_is_isolated_from_the_target_monitor():
    runner = RUNNER.read_text(encoding="utf-8")
    service = SERVICE.read_text(encoding="utf-8")

    assert "WINEPREFIX=/home/ubuntu/.wine-straddle-demo" in runner
    assert "/home/ubuntu/mt5-straddle-demo/terminal64.exe" in runner
    assert "/home/ubuntu/straddle-demo/demo-startup.ini" in runner
    assert "systemctl stop straddle-" not in runner
    assert "systemctl restart straddle-" not in runner
    assert "Requires=straddle-xvfb.service" in service
    assert "PartOf=straddle-mt5.service" not in service
    assert "ExecStart=/home/ubuntu/straddle-demo/run_mt5_demo.sh" in service


def test_demo_runner_survives_mt5_liveupdate_process_handoff():
    runner = RUNNER.read_text(encoding="utf-8")

    assert "find_related_mt5_pid" in runner
    assert '[[ "$(<"$candidate/comm")" == "main" ]] || continue' in runner
    assert "terminal_directory_windows=" in runner
    assert 'grep -Fqx "/update"' in runner
    assert 'grep -Fqx "/path:$terminal_directory_windows"' in runner
    assert "transition_grace_seconds=" in runner
    assert 'kill -0 "$terminal_pid"' not in runner


def test_demo_startup_uses_the_demo_locked_latest_profile():
    startup = STARTUP.read_text(encoding="utf-8")
    exact_set = EXACT_SET.read_text(encoding="utf-8")

    assert "Expert=StraddleReplica\\StraddleReplica" in startup
    assert "ExpertParameters=LATEST_30_exact.set" in startup
    assert "Symbol=XAUUSD" in startup
    assert "RequireDemoAccount=true" in exact_set
    assert "ExpectedAccountLogin=0" in exact_set


def test_manual_demo_preset_is_demo_only_without_a_stale_login_lock():
    preset = MANUAL_DEMO_SET.read_text(encoding="utf-8")

    assert "Profile=4" in preset
    assert "TradeSymbol=XAUUSD" in preset
    assert "MagicNumber=901018" in preset
    assert "RuntimeMode=0" in preset
    assert "RequireDemoAccount=true" in preset
    assert "RequireBoundAccount=false" in preset
    assert "ExpectedAccountLogin=0" in preset
    assert "SafetyEnabled=false" in preset


def test_demo_vps_package_contains_no_credentials():
    source = PACKAGE.read_text(encoding="utf-8")

    assert "StraddleReplica.ex5" in source
    assert "latest_30.set" in source
    assert "run_mt5_demo.sh" in source
    assert "straddle-demo-mt5.service" in source
    assert "Password" not in source


def test_demo_daily_analysis_is_read_only_and_independent():
    runner = ANALYSIS_RUNNER.read_text(encoding="utf-8")
    service = ANALYSIS_SERVICE.read_text(encoding="utf-8")
    timer = ANALYSIS_TIMER.read_text(encoding="utf-8")

    assert "compare_live_target_demo.py" in runner
    assert "check_monitor_health.py" in runner
    assert "systemctl is-active --quiet straddle-demo-mt5.service" in runner
    assert "systemctl stop" not in runner
    assert "systemctl restart" not in runner
    assert "ExecStart=/home/ubuntu/straddle-monitor/bin/run_demo_analysis.sh" in service
    assert "OnCalendar=*-*-* 00:20:00 UTC" in timer
    assert "Persistent=true" in timer
