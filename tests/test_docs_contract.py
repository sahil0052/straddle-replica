from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_operator_documentation_covers_installation_testing_and_fidelity_limits():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    installation = (ROOT / "docs" / "INSTALLATION.md").read_text(encoding="utf-8")
    fidelity = (ROOT / "docs" / "FIDELITY.md").read_text(encoding="utf-8")

    assert "17,638 total trades" in readme
    assert "284 detected" in readme
    assert "613" in readme
    assert "LATEST_30" in readme
    assert "scripts\\build.ps1" in installation
    assert "scripts\\install_ea.ps1" in installation
    assert "Strategy Tester" in installation
    assert "Never attach" in installation
    assert "structural replica" in fidelity
    assert "HISTORICAL_50" in fidelity
    assert "HISTORICAL_60" in fidelity
    assert "not 100%" in fidelity
    assert "$0.20" in fidelity
    assert "604 of 1,200" in fidelity


def test_fidelity_gate_documentation_uses_approved_qualification_terms():
    live_twin = (ROOT / "docs" / "LIVE_TWIN.md").read_text(
        encoding="utf-8"
    )
    fidelity = (ROOT / "docs" / "FIDELITY.md").read_text(
        encoding="utf-8"
    )

    for content in (live_twin, fidelity):
        assert "20 consecutive complete paired cycles" in content
        assert "48 market-open hours" in content
        assert "BEST_EFFORT_PASS" in content
        assert "identical broker profit" in content
