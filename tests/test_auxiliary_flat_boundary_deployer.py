from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import time


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "deploy_local_auxiliary_at_flat.ps1"
POWERSHELL = (
    Path("C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe")
)


def test_waiting_deployer_refreshes_health_heartbeat(
    tmp_path: Path,
) -> None:
    telemetry = tmp_path / "telemetry.csv"
    telemetry.write_text(
        "2026-08-13T00:00:00Z,server,test-cycle,0,pending\n",
        encoding="utf-8",
    )
    terminal = tmp_path / "terminal64.exe"
    startup = tmp_path / "startup.ini"
    staged = tmp_path / "staged.ex5"
    active = tmp_path / "active.ex5"
    health = tmp_path / "health.json"
    terminal.write_bytes(b"terminal-placeholder")
    startup.write_text("[StartUp]\n", encoding="utf-8")
    staged.write_bytes(b"verified-build")
    active.write_bytes(b"verified-build")
    build_hash = hashlib.sha256(b"verified-build").hexdigest().upper()

    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    process = subprocess.Popen(
        [
            str(POWERSHELL),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            "-TelemetryPath",
            str(telemetry),
            "-CycleId",
            "test-cycle",
            "-TerminalPath",
            str(terminal),
            "-StartupConfigPath",
            str(startup),
            "-StagedEx5Path",
            str(staged),
            "-ExpectedStagedEx5Sha256",
            build_hash,
            "-ActiveEx5Path",
            str(active),
            "-ExpectedActiveEx5Sha256",
            build_hash,
            "-HealthPath",
            str(health),
            "-PollSeconds",
            "0.1",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creation_flags,
    )
    try:
        deadline = time.monotonic() + 5.0
        while not health.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert health.exists()
        first = json.loads(health.read_text(encoding="utf-8-sig"))

        time.sleep(1.3)

        second = json.loads(health.read_text(encoding="utf-8-sig"))
        assert second["status"] == "WAITING_FOR_EXACT_FLAT_BOUNDARY"
        assert second["updated_at_utc"] != first["updated_at_utc"]
    finally:
        process.terminate()
        process.wait(timeout=5)
