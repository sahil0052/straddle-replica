from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REAL_MAIN = ROOT / "mql5" / "StraddleReplicaReal.mq5"
APP = ROOT / "mql5" / "include" / "StraddleReplicaApp.mqh"
PRESET = ROOT / "profiles" / "latest_30_real_exact.set"
BUILD = ROOT / "scripts" / "build_real.ps1"
PACKAGE = ROOT / "scripts" / "package_real_exact.ps1"
DOC = ROOT / "docs" / "REAL_EXACT.md"
STARTUP = ROOT / "monitor" / "real-vps-startup.ini"


def test_real_entrypoint_defaults_to_bound_account_and_safety():
    real = REAL_MAIN.read_text(encoding="utf-8")
    app = APP.read_text(encoding="utf-8")

    assert "#define STR_REQUIRE_DEMO_DEFAULT false" in real
    assert "#define STR_REQUIRE_BOUND_DEFAULT false" in real
    assert "#define STR_SAFETY_ENABLED_DEFAULT false" in real
    assert '#include "include/StraddleReplicaApp.mqh"' in real
    assert "input bool RequireDemoAccount = STR_REQUIRE_DEMO_DEFAULT" in app
    assert "input bool RequireBoundAccount = STR_REQUIRE_BOUND_DEFAULT" in app
    assert "input bool SafetyEnabled = STR_SAFETY_ENABLED_DEFAULT" in app


def test_real_exact_preset_preserves_replica_behavior_without_optional_safety():
    assert PRESET.exists(), f"Missing real-exact preset: {PRESET}"
    preset = PRESET.read_text(encoding="utf-8")

    for required in (
        "Profile=4",
        "TradeSymbol=XAUUSD",
        "ReplicaMode=true",
        "InterOrderDelayMs=100",
        "TelemetryEnabled=true",
        "RequireDemoAccount=false",
        "ExpectedAccountLogin=0",
        "SafetyEnabled=false",
    ):
        assert required in preset


def test_real_build_and_package_are_separate_from_demo_artifacts():
    for path in (BUILD, PACKAGE, DOC, STARTUP):
        assert path.exists(), f"Missing real-exact deliverable source: {path}"

    build = BUILD.read_text(encoding="utf-8")
    package = PACKAGE.read_text(encoding="utf-8")
    documentation = DOC.read_text(encoding="utf-8")
    startup = STARTUP.read_text(encoding="utf-8")

    assert "StraddleReplicaReal.mq5" in build
    assert "StraddleReplicaReal.ex5" in build
    assert "compile-real.log" in build
    assert "StraddleReplica_REAL_EXACT.ex5" in package
    assert "latest_30_real_exact.set" in package
    assert "real-vps-startup.ini" in package
    assert "StraddleReplica-REAL-CANDIDATE-20260810.zip" in package
    assert "not a trade copier" in documentation
    assert "demo validation gate" in documentation
    assert "[Experts]" in startup
    assert "Enabled=1" in startup
    assert "AllowLiveTrading=1" in startup
    assert "Expert=StraddleReplica_REAL_EXACT" in startup
    assert "ExpertParameters=LATEST_30_REAL_EXACT.set" in startup
