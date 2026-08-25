from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = (
    ROOT / "deploy" / "vps-docker-independent" / "compose.yaml"
)
PACKAGE = ROOT / "scripts" / "package_independent_demo.ps1"
DEPLOY = ROOT / "scripts" / "deploy_independent_demo_vps.ps1"
ENTRYPOINT = ROOT / "deploy" / "vps-docker" / "entrypoint.sh"
MONITOR = (
    ROOT / "scripts" / "install_independent_demo_monitor_tasks.ps1"
)


def test_independent_container_has_unique_scope_and_loopback_vnc() -> None:
    compose = COMPOSE.read_text(encoding="utf-8")

    assert "straddle-fidelity-independent-demo" in compose
    assert "straddle-fidelity-independent-mt5:bookworm" in compose
    assert "/opt/straddle-fidelity-independent-demo:/data" in compose
    assert "127.0.0.1:15925:5900" in compose
    assert "independent-demo-commissioning.ini" in compose
    assert "straddle-fidelity-candidate-demo" not in compose
    assert "straddle-replica-demo-vps" not in compose


def test_vnc_is_reachable_through_loopback_only_docker_publish() -> None:
    compose = COMPOSE.read_text(encoding="utf-8")
    entrypoint = ENTRYPOINT.read_text(encoding="utf-8")

    assert "127.0.0.1:15925:5900" in compose
    assert "x11vnc -display \"$DISPLAY\" -forever -shared -nopw" in entrypoint
    assert "-localhost" not in entrypoint


def test_package_binds_login_and_rejects_shadow_or_source() -> None:
    package = PACKAGE.read_text(encoding="utf-8")

    assert "ExpectedDemoLogin" in package
    assert "latest_30_independent_demo.set" in package
    assert "RuntimeMode=0" in package
    assert "RequireDemoAccount=true" in package
    assert "RequireBoundAccount=true" in package
    assert "RuntimeMode=1|ShadowCommandFile|ShadowAckFile" in package
    assert "StraddleReplica.ex5" in package
    assert "SHA256SUMS.txt" in package
    assert "straddle_replica.portable_zip" in package
    assert "StraddleReplica.mq5" not in package
    assert "StraddleEngine.mqh" not in package


def test_deploy_preserves_both_existing_containers() -> None:
    deploy = DEPLOY.read_text(encoding="utf-8")

    assert "straddle-fidelity-candidate-demo" in deploy
    assert "straddle-replica-demo-vps" in deploy
    assert "/opt/straddle-fidelity-independent-demo" in deploy
    assert "straddle-fidelity-independent-demo" in deploy
    assert "StartTrading" in deploy
    assert "docker stop" not in deploy
    assert "docker restart" not in deploy
    assert "docker rm" not in deploy
    assert "127.0.0.1:15925" in deploy
    assert "MT5_START=0" in deploy


def test_deploy_preserves_an_already_missing_protected_container() -> None:
    deploy = DEPLOY.read_text(encoding="utf-8")

    assert "function Get-OptionalContainerFingerprint" in deploy
    assert 'return "MISSING"' in deploy
    assert (
        "$before[$name] = Get-OptionalContainerFingerprint -Name $name"
        in deploy
    )
    assert "$after = Get-OptionalContainerFingerprint -Name $name" in deploy
    assert "Protected container could not be inspected" not in deploy


def test_deploy_snapshots_every_unrelated_container_identity() -> None:
    deploy = DEPLOY.read_text(encoding="utf-8")

    assert "function Get-NonCandidateContainerSnapshot" in deploy
    assert "$allContainersBefore = @(" in deploy
    assert "$allContainersAfter = @(" in deploy
    assert "Compare-Object" in deploy
    assert "Unrelated VPS container identity changed" in deploy


def test_deploy_uses_state_only_health_check_for_new_container() -> None:
    deploy = DEPLOY.read_text(encoding="utf-8")

    assert "function Get-ContainerState" in deploy
    assert "$state = Get-ContainerState -Name $candidate" in deploy
    assert "$state = Get-ContainerFingerprint -Name $candidate" not in deploy


def test_staged_deploy_can_require_a_proven_frozen_flat_boundary() -> None:
    deploy = DEPLOY.read_text(encoding="utf-8")

    assert "[switch]$RequireFrozenBoundary" in deploy
    assert "flat-boundary-freezer-health.json" in deploy
    assert '"FLAT_BOUNDARY_FROZEN"' in deploy
    assert "ready_for_deployment" in deploy
    assert "positions_total" in deploy
    assert "orders_total" in deploy
    assert "read_only_verified" in deploy
    assert "staged_package_sha256" in deploy
    assert deploy.index("if ($RequireFrozenBoundary)") < deploy.index(
        "$allContainersBefore = @("
    )


def test_remote_package_scan_excludes_runtime_wine_prefix() -> None:
    deploy = DEPLOY.read_text(encoding="utf-8")

    assert (
        "find $RemoteRoot/candidate $RemoteRoot/image $RemoteRoot/docs -type f"
        in deploy
    )
    assert "find $RemoteRoot -type f" not in deploy


def test_deploy_installs_bound_ea_and_preset_into_terminal() -> None:
    deploy = DEPLOY.read_text(encoding="utf-8")

    assert "$RemoteRoot/candidate/StraddleReplica.ex5" in deploy
    assert (
        "$RemoteRoot/terminal/MQL5/Experts/StraddleReplica/"
        "StraddleReplica.ex5"
        in deploy
    )
    assert "$RemoteRoot/candidate/latest_30_independent_demo.set" in deploy
    assert (
        "$RemoteRoot/terminal/MQL5/Presets/"
        "latest_30_independent_demo.set"
        in deploy
    )


def test_independent_monitors_are_read_only_and_command_free() -> None:
    source = MONITOR.read_text(encoding="utf-8")

    assert "StraddleIndependentTargetCollector" in source
    assert "StraddleIndependentCandidateCollector" in source
    assert "StraddleIndependentTargetArchive" in source
    assert source.count("--require-read-only") == 2
    assert source.count('"--checkpoint-seconds", "1"') == 2
    assert "archive_independent_target.py" in source
    assert "run_shadow_coordinator.py" not in source
    assert "command.csv" not in source
    assert "ack.csv" not in source
    assert "--active" not in source
    assert "docker" not in source.lower()
    assert "ssh" not in source.lower()


def test_candidate_monitor_reconnects_transient_network_failures() -> None:
    source = MONITOR.read_text(encoding="utf-8")
    target_block = source.split("$targetArguments = @(", 1)[1].split(
        "$candidateArguments = @(",
        1,
    )[0]
    candidate_block = source.split("$candidateArguments = @(", 1)[1].split(
        "$archiveArguments = @(",
        1,
    )[0]

    assert '"--exit-on-connection-error"' in target_block
    assert '"--exit-on-connection-error"' not in candidate_block
    assert '"--history-seed-days", "1"' in target_block
