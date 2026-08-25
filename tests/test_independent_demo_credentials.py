from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROTECT = ROOT / "scripts" / "protect_independent_demo_credentials.ps1"
PACKAGE = ROOT / "scripts" / "package_independent_demo.ps1"
DEPLOY = ROOT / "scripts" / "deploy_independent_demo_vps.ps1"


def test_credentials_are_dpapi_protected_and_acl_restricted() -> None:
    source = PROTECT.read_text(encoding="utf-8")

    assert "Read-Host" in source
    assert "-AsSecureString" in source
    assert "ConvertFrom-SecureString" in source
    assert "SetAccessRuleProtection($true, $false)" in source
    assert "FileSystemAccessRule" in source
    assert "master_cipher" in source
    assert "investor_cipher" in source
    assert "Write-Host $master" not in source
    assert "Write-Host $investor" not in source


def test_packages_and_remote_commands_never_contain_credentials() -> None:
    combined = (
        PACKAGE.read_text(encoding="utf-8")
        + DEPLOY.read_text(encoding="utf-8")
    )

    assert "master_cipher" not in combined
    assert "investor_cipher" not in combined
    assert "MasterPassword" not in combined
    assert "InvestorPassword" not in combined
