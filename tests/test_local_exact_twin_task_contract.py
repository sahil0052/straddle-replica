from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "install_local_exact_twin_tasks.ps1"


def test_local_exact_twin_tasks_are_supervised_and_read_only() -> None:
    assert SCRIPT.exists()
    source = SCRIPT.read_text(encoding="utf-8")

    assert "StraddleTargetCollector" in source
    assert "StraddleNextCycleSync" in source
    assert "--require-read-only" in source
    assert "--exit-on-connection-error" in source
    assert "--health-path" in source
    assert "--active" in source
    assert "New-ScheduledTaskSettingsSet" in source
    assert "-RestartCount 999" in source
    assert "-ExecutionTimeLimit ([TimeSpan]::Zero)" in source
    assert "read_only_verified" in source
    assert "Register-ScheduledTask" in source
    assert "order_send" not in source
