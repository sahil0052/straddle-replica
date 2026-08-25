from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIDELITY = ROOT / "profiles" / "latest_30_fidelity.set"
REAL_SAFE = ROOT / "profiles" / "latest_30_real_safe.set"


def test_fidelity_and_real_safe_presets_are_explicitly_different() -> None:
    fidelity = FIDELITY.read_text(encoding="utf-8")
    safe = REAL_SAFE.read_text(encoding="utf-8")

    assert "Profile=4" in fidelity
    assert "RequireBoundAccount=true" in fidelity
    assert "SafetyEnabled=false" in fidelity

    assert "Profile=4" in safe
    assert "RequireBoundAccount=true" in safe
    assert "SafetyEnabled=true" in safe
    assert "MaxEquityLossPercent=10.0" in safe
    assert "MaxGrossLots=2.20" in safe
    assert "MaxSpreadPoints=1000.0" in safe
    assert "DailyLossLimit=500.0" in safe
