from pathlib import Path
import subprocess
import sys
import zipfile


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "deploy" / "vps-docker-candidate" / "compose.yaml"
PACKAGE = ROOT / "scripts" / "package_fidelity_candidate.ps1"
RELEASE = ROOT / "scripts" / "package_fidelity_release.ps1"
DEPLOY = ROOT / "scripts" / "deploy_fidelity_candidate_vps.ps1"
MONITOR = ROOT / "scripts" / "install_fidelity_monitor_tasks.ps1"
STARTUP = ROOT / "monitor" / "fidelity-candidate-startup.ini"


def test_candidate_container_is_isolated_from_existing_vps_runtime() -> None:
    compose = COMPOSE.read_text(encoding="utf-8")
    deploy = DEPLOY.read_text(encoding="utf-8")

    assert "straddle-fidelity-candidate-demo" in compose
    assert "/opt/straddle-fidelity-candidate:/data" in compose
    assert "127.0.0.1:15915:5900" in compose
    assert "straddle-fidelity-mt5:bookworm" in compose
    assert "straddle-replica-demo-vps" not in compose
    assert "docker stop" not in deploy
    assert "docker restart" not in deploy
    assert "docker rm" not in deploy
    assert "straddle-replica-demo-vps" in deploy
    assert "docker inspect" in deploy
    assert "chown -R 1000:1000 $RemoteRoot" in deploy
    assert '$candidateEnvironment -split "\\r?\\n"' in deploy
    assert '"MT5_START=0" -notin $candidateEnvironmentLines' in deploy


def test_candidate_package_contains_ex5_presets_hashes_and_no_source() -> None:
    package = PACKAGE.read_text(encoding="utf-8")

    assert "StraddleReplica.ex5" in package
    assert "latest_30_shadow.set" in package
    assert "latest_30_fidelity.set" in package
    assert "latest_30_real_safe.set" in package
    assert "SHA256SUMS.txt" in package
    assert "StraddleEngine.mqh" not in package
    assert "StraddleReplica.mq5" not in package
    assert "Password" not in package
    assert "straddle_replica.portable_zip" in package
    assert "Compress-Archive" not in package


def test_candidate_zip_entries_are_portable_on_linux(tmp_path: Path) -> None:
    source = tmp_path / "stage"
    nested = source / "candidate"
    nested.mkdir(parents=True)
    (nested / "example.set").write_text("value=1\n", encoding="ascii")
    output = tmp_path / "candidate.zip"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "straddle_replica.portable_zip",
            "--source",
            str(source),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    with zipfile.ZipFile(output) as archive:
        assert archive.namelist() == ["candidate/example.set"]


def test_release_package_binds_login_and_excludes_source() -> None:
    release = RELEASE.read_text(encoding="utf-8")

    assert "ExpectedRealLogin" in release
    assert "StraddleReplicaReal.ex5" in release
    assert "latest_30_fidelity.set" in release
    assert "latest_30_real_safe.set" in release
    assert "SHA256SUMS.txt" in release
    assert "StraddleEngine.mqh" not in release
    assert "StraddleReplicaReal.mq5" not in release


def test_monitor_tasks_are_new_read_only_and_candidate_scoped() -> None:
    monitor = MONITOR.read_text(encoding="utf-8")

    assert "StraddleFidelityTargetCollector" in monitor
    assert "StraddleFidelityCycleSync" in monitor
    assert "--require-read-only" in monitor
    assert "--remote-ssh-alias" in monitor
    assert "/opt/straddle-fidelity-candidate" in monitor
    assert "Get-CimInstance Win32_Process" in monitor
    assert "target collector owner is already running" in monitor
    assert "Start-ScheduledTask -TaskName $collectorTaskName" in monitor
    assert (
        "Start-ScheduledTask -TaskName $coordinatorTaskName"
        not in monitor
    )
    assert "[int]$StartupTimeoutSeconds = 120" in monitor
