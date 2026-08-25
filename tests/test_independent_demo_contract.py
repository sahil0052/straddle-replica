from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRESET = ROOT / "profiles" / "latest_30_independent_demo.set"
COMMISSIONING = (
    ROOT / "monitor" / "independent-demo-commissioning.ini"
)
TRADING = ROOT / "monitor" / "independent-demo-startup.ini"


def test_independent_preset_is_normal_demo_bound_template() -> None:
    preset = PRESET.read_text(encoding="utf-8")

    assert "Profile=4" in preset
    assert "TradeSymbol=XAUUSD" in preset
    assert "MagicNumber=901018" in preset
    assert "TelemetryEnabled=true" in preset
    assert "RuntimeMode=0" in preset
    assert "RequireDemoAccount=true" in preset
    assert "RequireBoundAccount=true" in preset
    assert "ExpectedAccountLogin=0" in preset
    assert "SafetyEnabled=false" in preset
    assert "RuntimeMode=1" not in preset
    assert "ShadowCommandFile" not in preset
    assert "ShadowAckFile" not in preset
    assert "AllowShadowAdoptExistingCycle" not in preset


def test_commissioning_startup_cannot_trade_or_load_the_ea() -> None:
    startup = COMMISSIONING.read_text(encoding="utf-8")

    assert "[Experts]" in startup
    assert "Enabled=0" in startup
    assert "AllowLiveTrading=0" in startup
    assert "Symbol=XAUUSD" in startup
    assert "Expert=" not in startup
    assert "ExpertParameters=" not in startup


def test_trading_startup_loads_only_the_independent_preset() -> None:
    startup = TRADING.read_text(encoding="utf-8")

    assert "Enabled=1" in startup
    assert "AllowLiveTrading=1" in startup
    assert "AllowDllImport=0" in startup
    assert "Expert=StraddleReplica\\StraddleReplica" in startup
    assert (
        "ExpertParameters=latest_30_independent_demo.set"
        in startup
    )
    assert "Symbol=XAUUSD" in startup
    assert "shadow" not in startup.lower()
