from __future__ import annotations

import importlib
import json
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = (
    ROOT
    / "scripts"
    / "install_independent_demo_telemetry_sync_task.ps1"
)
TELEMETRY_HEADER = (
    "utc_time,server_time,cycle_id,command_seq,kind,comment,side,"
    "volume,price,sl,tp,state,level,ticket,request_id,retcode,"
    "commission,swap,profit,schema_version,event_sequence,event_id,"
    "deal_ticket,order_ticket,position_ticket,cycle_realized,"
    "floating_profit,cycle_net,basket_target,evidence_grade\n"
)


def test_sync_once_uses_one_bounded_incremental_ssh_stream(
    tmp_path: Path,
    monkeypatch,
) -> None:
    tool = importlib.import_module(
        "tools.sync_independent_candidate_telemetry"
    )
    telemetry_output = tmp_path / "candidate-telemetry.csv"
    manifest_output = tmp_path / "candidate-manifest.csv"
    telemetry = (
        TELEMETRY_HEADER
        + "2026-08-12T18:45:16Z,2026.08.12 21:45:16,"
        "cycle-1,0,fill,STR B1,buy,0.01,4410.92,0,0,"
        "CYCLE_RUNNING,STR B1,1,0,0,0,0,0,4,1,event-1,"
        "1,1,1,0,0,0,30,FORMAL_CANDIDATE\n"
    ).encode()
    manifest = (
        b"key,value\r\n"
        b"runtime_expected_account_login,110971967\r\n"
    )
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        header = (
            f"SRP1 full {len(telemetry)} {len(telemetry)} "
            f"{len(manifest)}\n"
        ).encode()
        kwargs["stdout"].write(header + telemetry + manifest)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(tool.subprocess, "run", fake_run)

    result = tool.sync_once(
        ssh_alias="nishahomes-vps",
        remote_root="/opt/straddle-fidelity-independent-demo",
        telemetry_output=telemetry_output,
        manifest_output=manifest_output,
    )

    assert result == {
        "telemetry_bytes": len(telemetry),
        "manifest_bytes": len(manifest),
        "transferred_telemetry_bytes": len(telemetry),
        "transfer_mode": "full",
    }
    assert telemetry_output.read_bytes() == telemetry
    assert manifest_output.read_bytes() == manifest
    assert len(calls) == 1
    command, kwargs = calls[0]
    assert command[0] == "ssh"
    assert "BatchMode=yes" in command
    assert "ConnectTimeout=10" in command
    assert "ConnectionAttempts=1" in command
    assert command[-2:] == ["sh", "-s"]
    assert kwargs["timeout"] == 45
    assert kwargs["stderr"] is subprocess.DEVNULL
    assert b"tail -c" in kwargs["input"]
    assert "capture_output" not in kwargs


def test_sync_once_appends_only_new_telemetry_bytes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    tool = importlib.import_module(
        "tools.sync_independent_candidate_telemetry"
    )
    telemetry_output = tmp_path / "candidate-telemetry.csv"
    manifest_output = tmp_path / "candidate-manifest.csv"
    existing = (
        TELEMETRY_HEADER
        + "2026-08-12T18:45:16Z,2026.08.12 21:45:16,"
        "cycle-1,0,fill,STR B1,buy,0.01,4410.92,0,0,"
        "CYCLE_RUNNING,STR B1,1,0,0,0,0,0,4,1,event-1,"
        "1,1,1,0,0,0,30,FORMAL_CANDIDATE\n"
    ).encode()
    delta = (
        "2026-08-12T18:45:17Z,2026.08.12 21:45:17,"
        "cycle-1,0,fill,STR B2,buy,0.01,4412.39,0,0,"
        "CYCLE_RUNNING,STR B2,2,0,0,0,0,0,4,2,event-2,"
        "2,2,2,0,0,0,30,FORMAL_CANDIDATE\n"
    ).encode()
    telemetry_output.write_bytes(existing)
    manifest_output.write_text("old manifest\n", encoding="utf-8")
    manifest = (
        b"key,value\r\n"
        b"runtime_expected_account_login,110971967\r\n"
    )
    commands: list[list[str]] = []

    def fake_run(command, **kwargs):
        commands.append(command)
        remote_size = len(existing) + len(delta)
        header = (
            f"SRP1 append {remote_size} {len(delta)} "
            f"{len(manifest)}\n"
        ).encode()
        kwargs["stdout"].write(
            header + delta + manifest
        )
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(tool.subprocess, "run", fake_run)

    result = tool.sync_once(
        ssh_alias="nishahomes-vps",
        remote_root="/opt/straddle-fidelity-independent-demo",
        telemetry_output=telemetry_output,
        manifest_output=manifest_output,
    )

    assert result == {
        "telemetry_bytes": len(existing) + len(delta),
        "manifest_bytes": len(manifest),
        "transferred_telemetry_bytes": len(delta),
        "transfer_mode": "append",
    }
    assert telemetry_output.read_bytes() == existing + delta
    assert manifest_output.read_bytes() == manifest
    assert len(commands) == 1
    assert all("BatchMode=yes" in command for command in commands)
    assert not list(tmp_path.glob("*.sync.tmp"))


def test_sync_once_rejects_partial_csv_without_replacing_evidence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    tool = importlib.import_module(
        "tools.sync_independent_candidate_telemetry"
    )
    telemetry_output = tmp_path / "candidate-telemetry.csv"
    manifest_output = tmp_path / "candidate-manifest.csv"
    telemetry_output.write_text("last good telemetry\n", encoding="utf-8")
    manifest_output.write_text("last good manifest\n", encoding="utf-8")

    def fake_run(command, **kwargs):
        telemetry = (TELEMETRY_HEADER + "partial row").encode()
        manifest = (
            b"key,value\n"
            b"runtime_expected_account_login,110971967\n"
        )
        header = (
            f"SRP1 full {len(telemetry)} {len(telemetry)} "
            f"{len(manifest)}\n"
        ).encode()
        kwargs["stdout"].write(header + telemetry + manifest)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(tool.subprocess, "run", fake_run)

    with pytest.raises(ValueError, match="complete newline"):
        tool.sync_once(
            ssh_alias="nishahomes-vps",
            remote_root="/opt/straddle-fidelity-independent-demo",
            telemetry_output=telemetry_output,
            manifest_output=manifest_output,
        )

    assert telemetry_output.read_text(encoding="utf-8") == (
        "last good telemetry\n"
    )
    assert manifest_output.read_text(encoding="utf-8") == (
        "last good manifest\n"
    )
    assert not list(tmp_path.glob("*.sync.tmp"))


def test_main_once_writes_running_health(
    tmp_path: Path,
    monkeypatch,
) -> None:
    tool = importlib.import_module(
        "tools.sync_independent_candidate_telemetry"
    )
    health = tmp_path / "sync-health.json"

    monkeypatch.setattr(
        tool,
        "sync_once",
        lambda **kwargs: {
            "telemetry_bytes": 1234,
            "manifest_bytes": 567,
            "transferred_telemetry_bytes": 89,
            "transfer_mode": "append",
        },
    )

    exit_code = tool.main(
        [
            "--ssh-alias",
            "nishahomes-vps",
            "--remote-root",
            "/opt/straddle-fidelity-independent-demo",
            "--telemetry-output",
            str(tmp_path / "candidate-telemetry.csv"),
            "--manifest-output",
            str(tmp_path / "candidate-manifest.csv"),
            "--health",
            str(health),
            "--once",
        ]
    )

    payload = json.loads(health.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["status"] == "RUNNING"
    assert payload["telemetry_bytes"] == 1234
    assert payload["manifest_bytes"] == 567
    assert payload["updated_at_utc"].endswith("+00:00")


def test_installer_registers_only_read_only_candidate_sync() -> None:
    source = INSTALLER.read_text(encoding="utf-8")

    assert "StraddleIndependentTelemetrySync" in source
    assert "sync_independent_candidate_telemetry.py" in source
    assert "/opt/straddle-fidelity-independent-demo" in source
    assert "candidate-telemetry.csv" in source
    assert "candidate-manifest.csv" in source
    assert "candidate-telemetry-sync-health.json" in source
    assert "-MultipleInstances IgnoreNew" in source
    assert "Start-ScheduledTask" in source
    assert "docker" not in source.lower()
    assert "terminal64.exe" not in source.lower()
    assert "order_send" not in source.lower()
