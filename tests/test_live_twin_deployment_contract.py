from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SHADOW_SET = ROOT / "profiles" / "latest_30_shadow.set"
STARTUP = ROOT / "monitor" / "shadow-startup.ini"
RUNNER = ROOT / "deploy" / "linux" / "run_mt5_shadow.sh"
ENVIRONMENT = ROOT / "deploy" / "linux" / "shadow.env.example"
MT5_SERVICE = ROOT / "deploy" / "linux" / "straddle-shadow-mt5.service"
COORDINATOR_RUNNER = (
    ROOT / "deploy" / "linux" / "run_shadow_coordinator.sh"
)
COORDINATOR_SERVICE = (
    ROOT / "deploy" / "linux" / "straddle-shadow-coordinator.service"
)
ANALYSIS_RUNNER = ROOT / "deploy" / "linux" / "run_live_twin_analysis.sh"
ANALYSIS_SERVICE = (
    ROOT / "deploy" / "linux" / "straddle-live-twin-analysis.service"
)
ANALYSIS_TIMER = (
    ROOT / "deploy" / "linux" / "straddle-live-twin-analysis.timer"
)
PACKAGE = ROOT / "scripts" / "package_live_twin.ps1"
DOCS = ROOT / "docs" / "LIVE_TWIN.md"


def test_shadow_preset_is_demo_locked_and_command_driven() -> None:
    preset = SHADOW_SET.read_text(encoding="utf-8")
    startup = STARTUP.read_text(encoding="utf-8")

    assert "RuntimeMode=1" in preset
    assert "RequireDemoAccount=true" in preset
    assert "ExpectedAccountLogin=0" in preset
    assert "AllowShadowAdoptExistingCycle=true" in preset
    assert "ShadowCommandFile=StraddleShadow\\command.csv" in preset
    assert "ShadowAckFile=StraddleShadow\\ack.csv" in preset
    assert "ExpertParameters=latest_30_shadow.set" in startup
    assert "[Experts]" in startup
    assert "Enabled=1" in startup
    assert "AllowLiveTrading=1" in startup
    assert "AllowDllImport=0" in startup


def test_shadow_runtime_is_isolated_from_existing_terminals() -> None:
    runner = RUNNER.read_text(encoding="utf-8")
    environment = ENVIRONMENT.read_text(encoding="utf-8")
    service = MT5_SERVICE.read_text(encoding="utf-8")

    assert "WINEPREFIX=/home/ubuntu/.wine-straddle-shadow" in runner
    assert "/home/ubuntu/mt5-straddle-shadow/terminal64.exe" in runner
    assert (
        "profile_linux=/home/ubuntu/straddle-live-twin/latest_30_shadow.set"
        in runner
    )
    assert 'test -f "$profile_linux"' in runner
    assert (
        "SHADOW_PROFILE_PATH=/home/ubuntu/straddle-live-twin/"
        "latest_30_shadow.set"
        in environment
    )
    assert "systemctl stop straddle-" not in runner
    assert "systemctl restart straddle-" not in runner
    assert "PartOf=straddle-mt5.service" not in service
    assert "PartOf=straddle-demo-mt5.service" not in service


def test_coordinator_defaults_to_observation_only_and_never_controls_target():
    runner = COORDINATOR_RUNNER.read_text(encoding="utf-8")
    environment = ENVIRONMENT.read_text(encoding="utf-8")
    service = COORDINATOR_SERVICE.read_text(encoding="utf-8")

    assert 'SHADOW_ACTIVE:-0' in runner
    assert "--active" in runner
    assert "TARGET_SOURCE" in runner
    assert "TARGET_PROBE_ROOT" in runner
    assert "TARGET_OBSERVER_ROOT" in runner
    assert "OBSERVER_ADAPTER_STATE" in runner
    assert "TARGET_SOURCE=observer" in environment
    assert (
        "TARGET_OBSERVER_ROOT=/home/ubuntu/straddle-data/python"
        in environment
    )
    assert (
        "OBSERVER_ADAPTER_STATE=/home/ubuntu/straddle-live-twin/"
        "state/observer-adapter.json"
        in environment
    )
    assert "StraddleShadow/command.csv" in runner
    assert "systemctl stop straddle-mt5" not in runner
    assert "systemctl restart straddle-mt5" not in runner
    assert "EnvironmentFile=" in service


def test_live_twin_analysis_is_read_only_and_runs_every_minute() -> None:
    runner = ANALYSIS_RUNNER.read_text(encoding="utf-8")
    service = ANALYSIS_SERVICE.read_text(encoding="utf-8")
    timer = ANALYSIS_TIMER.read_text(encoding="utf-8")

    assert "compare_account_terms.py" in runner
    assert "analyze_probe_health.py" in runner
    assert "compare_live_twin.py" in runner
    assert "evaluate_live_twin_gate.py" in runner
    assert "certification.state" in runner
    assert "coordinator.json" in runner
    assert "--operational-guard-failures" in runner
    assert "EXPECTED_PROBE_BUILD_ID" in runner
    assert "probe_build_id" in runner
    assert "sha256sum" in runner
    assert '"$demo_manifest"' in runner
    assert "--output-dir" in runner
    assert "--tick-value-per-lot" in runner
    assert "reset_required" in runner
    assert "systemctl stop" not in runner
    assert "systemctl restart" not in runner
    assert "run_live_twin_analysis.sh" in service
    assert "OnUnitActiveSec=60" in timer


def test_observer_analysis_reports_best_effort_without_probe_requirement():
    runner = ANALYSIS_RUNNER.read_text(encoding="utf-8")
    environment = ENVIRONMENT.read_text(encoding="utf-8")

    observer_branch = 'if [[ "$TARGET_SOURCE" == "observer" ]]; then'
    probe_requirement = ': "${TARGET_PROBE_ROOT:?TARGET_PROBE_ROOT is required}"'

    assert observer_branch in runner
    assert runner.index(observer_branch) < runner.index(probe_requirement)
    assert "report_best_effort_status.py" in runner
    assert "--source-mode observer" in runner
    assert "--operational-guard-report" in runner
    assert 'if [[ -s "$target_events" && -s "$demo_telemetry" ]]' in runner
    assert 'best_effort_root="$output_root/best-effort"' in runner
    assert 'status_output="$best_effort_root/status.json"' in runner
    assert (
        "ACCOUNT_TERMS_REPORT=/home/ubuntu/straddle-live-twin/"
        "reports/commissioning/account-terms-901018-vs-901111.json"
        in environment
    )
    assert (
        "COMMISSIONING_GUARD_REPORT=/home/ubuntu/straddle-live-twin/"
        "state/commissioning-guard.json"
        in environment
    )


def test_live_twin_package_contains_probe_shadow_and_tools_without_secrets():
    source = PACKAGE.read_text(encoding="utf-8")

    for required in (
        "StraddleReplica.ex5",
        "StraddleTargetProbe.ex5",
        "latest_30_shadow.set",
        "run_mt5_shadow.sh",
        "run_shadow_coordinator.sh",
        "compare_live_twin.py",
        "analyze_probe_health.py",
        "evaluate_live_twin_gate.py",
        "report_best_effort_status.py",
        "LIVE_TWIN.md",
    ):
        assert required in source
    assert "Password" not in source
    assert ".pem" not in source
    assert "CreateEntryFromFile" in source
    assert ".Replace(" in source
    assert "Compress-Archive" not in source


def test_live_twin_documentation_states_hard_prerequisites_and_gate():
    docs = DOCS.read_text(encoding="utf-8")

    assert "Achiever" in docs
    assert "same terminal" in docs
    assert "observation-only" in docs
    assert "20 consecutive" in docs
    assert "48 market-open hours" in docs
    assert "one tick" in docs
    assert "one second" in docs
