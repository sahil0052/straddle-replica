from pathlib import Path
import subprocess
import zipfile


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "scripts" / "package_real_bound_release.ps1"
TESTER_PRESET = (
    ROOT / "scripts" / "prepare_real_bound_tester_preset.ps1"
)


def _run_validation(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(PACKAGE),
            "-Workspace",
            str(ROOT),
            "-MetaEditorPath",
            str(ROOT / "missing-metaeditor.exe"),
            *arguments,
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def test_real_bound_release_is_source_free_and_uses_safe_preset() -> None:
    assert PACKAGE.exists(), f"Missing account-bound release packager: {PACKAGE}"
    script = PACKAGE.read_text(encoding="utf-8")

    assert "latest_30_real_safe.set" in script
    assert "StraddleReplicaReal.ex5" in script
    assert "RequireBoundAccount" in script
    assert "ExpectedAccountLogin" in script
    assert "SafetyEnabled" in script
    assert "SHA256SUMS.txt" in script
    assert "Compress-Archive" in script
    assert "prepare_real_bound_tester_preset.ps1" in script
    assert "StraddleReplicaReal.mq5" not in script
    assert "StraddleEngine.mqh" not in script


def test_real_bound_release_rejects_zero_login_before_compilation() -> None:
    result = _run_validation(
        "-AccountLogin",
        "0",
        "-BrokerServer",
        "AchieverGlobalMarkets-Server",
        "-TradeSymbol",
        "XAUUSD",
    )

    assert result.returncode != 0
    assert "AccountLogin must be a non-zero account number." in (
        result.stdout + result.stderr
    )


def test_real_bound_release_requires_server_and_symbol_before_compilation() -> None:
    missing_server = _run_validation(
        "-AccountLogin",
        "901111",
        "-BrokerServer",
        "",
        "-TradeSymbol",
        "XAUUSD",
    )
    missing_symbol = _run_validation(
        "-AccountLogin",
        "901111",
        "-BrokerServer",
        "AchieverGlobalMarkets-Server",
        "-TradeSymbol",
        "",
    )

    assert missing_server.returncode != 0
    assert "BrokerServer is required." in (
        missing_server.stdout + missing_server.stderr
    )
    assert missing_symbol.returncode != 0
    assert "TradeSymbol is required." in (
        missing_symbol.stdout + missing_symbol.stderr
    )


def test_tester_matching_preset_disables_shared_telemetry(
    tmp_path: Path,
) -> None:
    assert TESTER_PRESET.exists(), (
        f"Missing safe tester preset helper: {TESTER_PRESET}"
    )
    release_preset = tmp_path / "release.set"
    tester_preset = tmp_path / "tester.set"
    release_preset.write_text(
        "\n".join(
            [
                "Profile=4",
                "TradeSymbol=XAUUSD",
                "TelemetryEnabled=true",
                "RequireDemoAccount=false",
                "RequireBoundAccount=true",
                "ExpectedAccountLogin=901114",
                "SafetyEnabled=true",
            ]
        )
        + "\n",
        encoding="ascii",
    )

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(TESTER_PRESET),
            "-ReleasePreset",
            str(release_preset),
            "-TesterAccountLogin",
            "901111",
            "-OutputPreset",
            str(tester_preset),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0, (
        completed.stdout + completed.stderr
    )
    content = tester_preset.read_text(encoding="ascii")
    assert "TelemetryEnabled=false" in content
    assert "ExpectedAccountLogin=901111" in content
    assert "RequireDemoAccount=false" in content
    assert "RequireBoundAccount=true" in content
    assert "SafetyEnabled=true" in content


def test_real_bound_bundle_uses_account_specific_delivery_names(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    scripts = workspace / "scripts"
    profiles = workspace / "profiles"
    mql5 = workspace / "mql5"
    output = workspace / "release"
    for directory in (scripts, profiles, mql5, output):
        directory.mkdir(parents=True, exist_ok=True)

    (scripts / "build_real.ps1").write_text(
        "\n".join(
            [
                "param([string]$Workspace,[string]$MetaEditorPath)",
                "$output = Join-Path $Workspace 'mql5\\StraddleReplicaReal.ex5'",
                "Set-Content -LiteralPath $output -Value 'fake-ex5' -Encoding Ascii",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (scripts / "prepare_real_bound_tester_preset.ps1").write_text(
        "param()\n",
        encoding="utf-8",
    )
    (profiles / "latest_30_real_safe.set").write_text(
        "\n".join(
            [
                "Profile=4",
                "TradeSymbol=XAUUSD",
                "TelemetryEnabled=true",
                "RequireDemoAccount=false",
                "RequireBoundAccount=true",
                "ExpectedAccountLogin=0",
                "SafetyEnabled=true",
            ]
        )
        + "\n",
        encoding="ascii",
    )

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(PACKAGE),
            "-Workspace",
            str(workspace),
            "-MetaEditorPath",
            str(workspace / "unused-metaeditor.exe"),
            "-AccountLogin",
            "901114",
            "-BrokerServer",
            "AchieverGlobalMarkets-Server",
            "-TradeSymbol",
            "XAUUSD",
            "-OutputDirectory",
            str(output),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    archives = list(output.glob("StraddleReplica-REAL-901114-20S-*.zip"))
    assert len(archives) == 1
    with zipfile.ZipFile(archives[0]) as bundle:
        names = set(bundle.namelist())
        assert "StraddleReplica-901114.ex5" in names
        assert "StraddleReplica-901114.set" in names
        assert "START-HERE.txt" in names
        assert "RELEASE.json" in names
        assert "SHA256SUMS.txt" in names
        instructions = bundle.read("START-HERE.txt").decode("ascii")
        assert "901114" in instructions
        assert "AchieverGlobalMarkets-Server" in instructions
        assert "XAUUSD" in instructions
        assert "Experts" in instructions
        assert "account binding mismatch" in instructions.lower()
        assert "remove every older straddlereplica ex5 and set" in (
            instructions.lower()
        )
        assert "trade > orders tab" in instructions.lower()
