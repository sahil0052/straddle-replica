from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "install_auxiliary_cycle_alignment_task.ps1"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _fixture_arguments(tmp_path: Path) -> list[str]:
    controller = tmp_path / "align_local_auxiliary_cycle.py"
    telemetry = tmp_path / "candidate.csv"
    target_events = tmp_path / "target.jsonl"
    terminal = tmp_path / "terminal64.exe"
    startup = tmp_path / "startup.ini"
    preset = tmp_path / "candidate.set"
    active = tmp_path / "active.ex5"
    staged = tmp_path / "staged.ex5"
    package = tmp_path / "staged.zip"
    qualification = tmp_path / "qualification.json"
    hold = tmp_path / "alignment-hold.json"
    health = tmp_path / "health.json"

    controller.write_text("raise SystemExit(0)\n", encoding="utf-8")
    telemetry.write_text("time,kind\n", encoding="utf-8")
    target_events.write_text("", encoding="utf-8")
    terminal.write_bytes(b"terminal")
    startup.write_text(
        "\n".join(
            [
                "[Experts]",
                "Enabled=1",
                "AllowLiveTrading=1",
                "[StartUp]",
                "Expert=StraddleReplica\\StraddleReplica",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    preset.write_text(
        "\n".join(
            [
                "RequireDemoAccount=true",
                "RequireBoundAccount=true",
                "ExpectedAccountLogin=901111",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    active.write_bytes(b"active-build")
    staged.write_bytes(b"corrected-20-second-build")
    package.write_bytes(b"corrected-package")
    qualification.write_text(
        json.dumps(
            {
                "active_cycle_id": "local-901111-excluded",
                "active_cycle_eligible": False,
            }
        ),
        encoding="utf-8",
    )

    return [
        "-Workspace",
        str(ROOT),
        "-TaskName",
        f"StraddleAuxiliaryCycleAlignmentTest-{tmp_path.name}",
        "-PythonPath",
        sys.executable,
        "-ControllerPath",
        str(controller),
        "-CandidateTelemetry",
        str(telemetry),
        "-CandidateCycleId",
        "local-901111-excluded",
        "-TargetEvents",
        str(target_events),
        "-TerminalPath",
        str(terminal),
        "-StartupConfig",
        str(startup),
        "-PresetPath",
        str(preset),
        "-ExpectedDemoLogin",
        "901111",
        "-ActiveEx5Path",
        str(active),
        "-ExpectedActiveEx5Sha256",
        _sha256(active),
        "-StagedEx5Path",
        str(staged),
        "-ExpectedStagedEx5Sha256",
        _sha256(staged),
        "-StagedPackagePath",
        str(package),
        "-ExpectedStagedPackageSha256",
        _sha256(package),
        "-QualificationState",
        str(qualification),
        "-AlignmentHoldPath",
        str(hold),
        "-HealthPath",
        str(health),
    ]


def _run_script(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            *arguments,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if "-TaskName" in arguments:
        task_name = arguments[arguments.index("-TaskName") + 1]
        if task_name.startswith(
            "StraddleAuxiliaryCycleAlignmentTest-"
        ):
            subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    (
                        "$task=Get-ScheduledTask -TaskName "
                        f"'{task_name}' -ErrorAction SilentlyContinue; "
                        "if($task){$task | Unregister-ScheduledTask "
                        "-Confirm:$false}"
                    ),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
    return completed


def _write_flat_proof(
    path: Path,
    *,
    flat: bool,
    terminal_trade_allowed: bool = False,
) -> None:
    positions_total = 0 if flat else 1
    path.write_text(
        json.dumps(
            {
                "assessed_at_utc": datetime.now(timezone.utc).isoformat(),
                "account": {"login": 901111},
                "read_only_broker_sync": {
                    "sync_time_utc": datetime.now(
                        timezone.utc
                    ).isoformat(),
                    "positions_total": positions_total,
                    "orders_total": 0,
                    "flat": flat,
                    "terminal_trade_allowed": terminal_trade_allowed,
                    "start_config_experts_enabled": False,
                    "start_config_allow_live_trading": False,
                },
                "process_safety": {
                    "read_only_tester_terminal_stopped": True,
                    "exact_auxiliary_trading_terminal_stopped": True,
                    "alignment_controller_process_running": False,
                    "orders_or_positions_modified": False,
                    "trade_methods_invoked": False,
                },
            }
        ),
        encoding="utf-8",
    )


def test_preview_builds_complete_manual_only_alignment_action(
    tmp_path: Path,
) -> None:
    assert SCRIPT.exists()
    source = SCRIPT.read_text(encoding="utf-8")
    assert "Start-ScheduledTask" not in source
    assert "Disable-ScheduledTask" in source

    completed = _run_script(_fixture_arguments(tmp_path))

    assert completed.returncode == 0, completed.stdout + completed.stderr
    plan = json.loads(completed.stdout)
    arguments = plan["arguments"]
    for flag in (
        "--candidate-telemetry",
        "--candidate-cycle-id",
        "--target-events",
        "--terminal-path",
        "--startup-config",
        "--preset-path",
        "--expected-demo-login",
        "--active-ex5-path",
        "--expected-active-ex5-sha256",
        "--staged-ex5-path",
        "--expected-staged-ex5-sha256",
        "--staged-package-path",
        "--expected-staged-package-sha256",
        "--qualification-state",
        "--alignment-hold-path",
        "--health",
    ):
        assert flag in arguments
    assert "local-901111-excluded" in arguments
    assert plan["register_requested"] is False
    assert plan["task_will_be_started"] is False
    assert plan["automatic_trigger_count"] == 0


def test_preview_can_bind_fresh_independent_flat_proof(
    tmp_path: Path,
) -> None:
    flat_proof = tmp_path / "flat-proof.json"
    _write_flat_proof(flat_proof, flat=True)

    completed = _run_script(
        [
            *_fixture_arguments(tmp_path),
            "-FlatProofPath",
            str(flat_proof),
            "-FlatProofMaxAgeSeconds",
            "60",
        ]
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    plan = json.loads(completed.stdout)
    assert "--independent-flat-proof" in plan["arguments"]
    assert str(flat_proof) in plan["arguments"]
    assert "--flat-proof-max-age-seconds" in plan["arguments"]


def test_apply_refuses_nonflat_read_only_proof(
    tmp_path: Path,
) -> None:
    flat_proof = tmp_path / "flat-proof.json"
    _write_flat_proof(flat_proof, flat=False)

    completed = _run_script(
        [
            *_fixture_arguments(tmp_path),
            "-Apply",
            "-FlatProofPath",
            str(flat_proof),
        ]
    )

    assert completed.returncode != 0
    assert "independent flat proof" in (
        completed.stdout + completed.stderr
    ).lower()


def test_apply_refuses_flat_proof_that_allowed_live_trading(
    tmp_path: Path,
) -> None:
    flat_proof = tmp_path / "unsafe-flat-proof.json"
    _write_flat_proof(
        flat_proof,
        flat=True,
        terminal_trade_allowed=True,
    )

    completed = _run_script(
        [
            *_fixture_arguments(tmp_path),
            "-Apply",
            "-FlatProofPath",
            str(flat_proof),
        ]
    )

    assert completed.returncode != 0
    assert "terminal trade_allowed" in (
        completed.stdout + completed.stderr
    ).lower()


def test_apply_refuses_flat_proof_with_missing_counts(
    tmp_path: Path,
) -> None:
    flat_proof = tmp_path / "missing-counts-flat-proof.json"
    _write_flat_proof(flat_proof, flat=True)
    payload = json.loads(flat_proof.read_text(encoding="utf-8"))
    del payload["read_only_broker_sync"]["orders_total"]
    flat_proof.write_text(json.dumps(payload), encoding="utf-8")

    completed = _run_script(
        [
            *_fixture_arguments(tmp_path),
            "-Apply",
            "-FlatProofPath",
            str(flat_proof),
        ]
    )

    assert completed.returncode != 0
    assert "zero positions and zero orders" in (
        completed.stdout + completed.stderr
    ).lower()
