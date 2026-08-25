# Independent Demo Fidelity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a new demo account, run `StraddleReplica` independently in a new isolated VPS container, expose only investor credentials, and measure complete-cycle deterministic fidelity against target account `901018`.

**Architecture:** A dedicated normal-mode preset is bound to the new demo login at package time and deployed only to `/opt/straddle-fidelity-independent-demo`. Target and candidate evidence are collected through separate investor-only MT5 terminals; target snapshots are converted into cycle events without any command transport, while candidate decisions come from EA telemetry. Independent cycles are paired by nearest start time on Achiever or by ordinal order on MetaQuotes, normalized for anchor/step differences, and scored separately for deterministic logic and broker execution.

**Tech Stack:** MQL5/EX5, PowerShell 5.1, Python 3.11+, pytest, MetaTrader5 Python package, Docker Compose, Wine, OpenSSH, CSV/JSONL telemetry.

---

## Scope and fixed safety boundaries

- Demo account only. This plan does not authorize a real-account deployment.
- Primary broker: AchieverGlobalMarkets demo.
- Fallback broker: MetaQuotes-Demo only if Achiever does not offer demo registration.
- New container: `straddle-fidelity-independent-demo`.
- New remote root: `/opt/straddle-fidelity-independent-demo`.
- New image: `straddle-fidelity-independent-mt5:bookworm`.
- New loopback-only VNC port: `127.0.0.1:15925`.
- Protected containers that must not be stopped, restarted, removed, recreated, or edited:
  - `straddle-fidelity-candidate-demo`
  - `straddle-replica-demo-vps`
- EA runtime must be `RuntimeMode=0`.
- No `command.csv`, `ack.csv`, shadow coordinator, trade copier, or signal mirroring is permitted.
- Master credentials may exist only in process memory, MT5's saved-login store, and one temporary DPAPI-protected local file.
- Only the new login, server, and investor password may be returned to the user.
- The target remains investor/read-only at all times.
- The workspace is not a Git repository. Every task ends with a SHA-256 checkpoint instead of a commit.

## Command prerequisite

At the start of every implementation PowerShell session, resolve the bundled
Python runtime once:

```powershell
$python=(
  'C:\Users\HPUSER\.cache\codex-runtimes\codex-primary-runtime\' +
  'dependencies\python\python.exe'
)
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
  throw "Bundled Python runtime was not found: $python"
}
```

## File structure

### New runtime and deployment files

- `profiles/latest_30_independent_demo.set`
  - Unbound normal-mode template. Packaging replaces only `ExpectedAccountLogin=0`.
- `monitor/independent-demo-commissioning.ini`
  - Opens XAUUSD with automated trading disabled for account and symbol checks.
- `monitor/independent-demo-startup.ini`
  - Loads the bound independent preset with automated trading enabled.
- `deploy/vps-docker-independent/compose.yaml`
  - Defines only the new isolated container, root, image, and VNC binding.
- `scripts/package_independent_demo.ps1`
  - Builds a source-free, credential-free, login-bound ZIP and rejects shadow configuration.
- `scripts/deploy_independent_demo_vps.ps1`
  - Deploys only the new project and verifies protected container fingerprints are unchanged.
- `scripts/protect_independent_demo_credentials.ps1`
  - Stores master and investor passwords with Windows DPAPI and a current-user-only ACL.
- `scripts/install_independent_demo_monitor_tasks.ps1`
  - Registers separate target collector, candidate collector, and target cycle archiver tasks.

### New evidence and comparison files

- `straddle_replica/independent_cycle_archive.py`
  - Segments target investor evidence into complete target cycles without writing commands.
- `tools/archive_independent_target.py`
  - Continuously polls the target observer adapter and feeds the target cycle archive.
- `straddle_replica/independent_fidelity.py`
  - Pairs different cycle IDs and compares normalized lifecycle decisions.
- `tools/compare_independent_cycles.py`
  - Writes one report per paired cycle and returns nonzero for deterministic mismatch.
- `straddle_replica/independent_readiness.py`
  - Validates fresh read-only heartbeats, normal-mode manifest, fresh telemetry, and account binding.
- `tools/check_independent_demo_readiness.py`
  - CLI for the readiness gate.

### Existing files modified

- `straddle_replica/observer_adapter.py`
  - Detects target position stop-loss changes from investor snapshots.
- `tests/test_observer_adapter.py`
  - Covers inferred stop updates without replay or duplicate events.
- `docs/FIDELITY.md`
  - Records the measured independent-demo evidence and explicitly separates logic from profit.

### New tests

- `tests/test_independent_demo_contract.py`
- `tests/test_independent_demo_deployment.py`
- `tests/test_independent_demo_credentials.py`
- `tests/test_independent_cycle_archive.py`
- `tests/test_independent_fidelity.py`
- `tests/test_independent_readiness.py`

## Task 1: Add a fail-closed independent demo preset and two startup modes

**Files:**

- Create: `profiles/latest_30_independent_demo.set`
- Create: `monitor/independent-demo-commissioning.ini`
- Create: `monitor/independent-demo-startup.ini`
- Create: `tests/test_independent_demo_contract.py`

- [ ] **Step 1: Write the failing preset and startup contract tests**

Create `tests/test_independent_demo_contract.py`:

```python
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRESET = ROOT / "profiles" / "latest_30_independent_demo.set"
COMMISSIONING = (
    ROOT / "monitor" / "independent-demo-commissioning.ini"
)
TRADING = ROOT / "monitor" / "independent-demo-startup.ini"


def test_independent_preset_is_normal_demo_bound_template() -> None:
    preset = PRESET.read_text(encoding="utf-8")

    assert "Profile=4" in preset
    assert "TradeSymbol=XAUUSD" in preset
    assert "MagicNumber=901018" in preset
    assert "TelemetryEnabled=true" in preset
    assert "RuntimeMode=0" in preset
    assert "RequireDemoAccount=true" in preset
    assert "RequireBoundAccount=true" in preset
    assert "ExpectedAccountLogin=0" in preset
    assert "SafetyEnabled=false" in preset
    assert "RuntimeMode=1" not in preset
    assert "ShadowCommandFile" not in preset
    assert "ShadowAckFile" not in preset
    assert "AllowShadowAdoptExistingCycle" not in preset


def test_commissioning_startup_cannot_trade_or_load_the_ea() -> None:
    startup = COMMISSIONING.read_text(encoding="utf-8")

    assert "[Experts]" in startup
    assert "Enabled=0" in startup
    assert "AllowLiveTrading=0" in startup
    assert "Symbol=XAUUSD" in startup
    assert "Expert=" not in startup
    assert "ExpertParameters=" not in startup


def test_trading_startup_loads_only_the_independent_preset() -> None:
    startup = TRADING.read_text(encoding="utf-8")

    assert "Enabled=1" in startup
    assert "AllowLiveTrading=1" in startup
    assert "AllowDllImport=0" in startup
    assert "Expert=StraddleReplica\\StraddleReplica" in startup
    assert (
        "ExpertParameters=latest_30_independent_demo.set"
        in startup
    )
    assert "Symbol=XAUUSD" in startup
    assert "shadow" not in startup.lower()
```

- [ ] **Step 2: Run the new test and verify RED**

Run:

```powershell
& $python -m pytest tests\test_independent_demo_contract.py -q
```

Expected: three failures because the preset and startup files do not exist.

- [ ] **Step 3: Create the unbound normal-mode preset**

Create `profiles/latest_30_independent_demo.set`:

```ini
Profile=4
TradeSymbol=XAUUSD
MagicNumber=901018
ReplicaMode=true
ReplicaStartTime=0
InterOrderDelayMs=100
DeviationPoints=100
TelemetryEnabled=true
RuntimeMode=0
RequireDemoAccount=true
RequireBoundAccount=true
ExpectedAccountLogin=0
SafetyEnabled=false
```

- [ ] **Step 4: Create the non-trading commissioning startup**

Create `monitor/independent-demo-commissioning.ini`:

```ini
[Experts]
Enabled=0
AllowLiveTrading=0
AllowDllImport=0

[StartUp]
Symbol=XAUUSD
Period=M1
ShutdownTerminal=0
```

- [ ] **Step 5: Create the normal trading startup**

Create `monitor/independent-demo-startup.ini`:

```ini
[Experts]
Enabled=1
AllowLiveTrading=1
AllowDllImport=0

[StartUp]
Expert=StraddleReplica\StraddleReplica
ExpertParameters=latest_30_independent_demo.set
Symbol=XAUUSD
Period=M1
ShutdownTerminal=0
```

- [ ] **Step 6: Run the contract test and verify GREEN**

Run:

```powershell
& $python -m pytest tests\test_independent_demo_contract.py -q
```

Expected: `3 passed`.

- [ ] **Step 7: Write the Task 1 checkpoint**

Run:

```powershell
$root='artifacts\checkpoints\2026-08-12-independent-demo'
New-Item -ItemType Directory -Force $root | Out-Null
Get-FileHash `
  profiles\latest_30_independent_demo.set,`
  monitor\independent-demo-commissioning.ini,`
  monitor\independent-demo-startup.ini `
  -Algorithm SHA256 |
  ConvertTo-Json |
  Set-Content "$root\task-01-contract.json"
```

## Task 2: Build a source-free package and isolated Docker deployment

**Files:**

- Create: `deploy/vps-docker-independent/compose.yaml`
- Create: `scripts/package_independent_demo.ps1`
- Create: `scripts/deploy_independent_demo_vps.ps1`
- Create: `tests/test_independent_demo_deployment.py`

- [ ] **Step 1: Write failing deployment isolation tests**

Create `tests/test_independent_demo_deployment.py`:

```python
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = (
    ROOT / "deploy" / "vps-docker-independent" / "compose.yaml"
)
PACKAGE = ROOT / "scripts" / "package_independent_demo.ps1"
DEPLOY = ROOT / "scripts" / "deploy_independent_demo_vps.ps1"


def test_independent_container_has_unique_scope_and_loopback_vnc() -> None:
    compose = COMPOSE.read_text(encoding="utf-8")

    assert "straddle-fidelity-independent-demo" in compose
    assert "straddle-fidelity-independent-mt5:bookworm" in compose
    assert "/opt/straddle-fidelity-independent-demo:/data" in compose
    assert "127.0.0.1:15925:5900" in compose
    assert "independent-demo-commissioning.ini" in compose
    assert "straddle-fidelity-candidate-demo" not in compose
    assert "straddle-replica-demo-vps" not in compose


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
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```powershell
& $python -m pytest tests\test_independent_demo_deployment.py -q
```

Expected: failures because the compose, package, and deployment files do not exist.

- [ ] **Step 3: Create the isolated compose definition**

Create `deploy/vps-docker-independent/compose.yaml`:

```yaml
services:
  fidelity-independent:
    image: straddle-fidelity-independent-mt5:bookworm
    container_name: straddle-fidelity-independent-demo
    restart: unless-stopped
    environment:
      MT5_START: "${MT5_START:-0}"
      MT5_CONFIG_WINDOWS: "${MT5_CONFIG_WINDOWS:-Z:\\data\\candidate\\independent-demo-commissioning.ini}"
    ports:
      - "127.0.0.1:15925:5900"
    volumes:
      - "/opt/straddle-fidelity-independent-demo:/data"
    cpus: 0.75
    mem_limit: 1536m
    pids_limit: 256
    cap_drop:
      - ALL
    security_opt:
      - no-new-privileges:true
```

- [ ] **Step 4: Implement the login-bound package script**

Create `scripts/package_independent_demo.ps1`:

```powershell
param(
    [Parameter(Mandatory = $true)]
    [long]$ExpectedDemoLogin,
    [Parameter(Mandatory = $true)]
    [string]$Mt5InstallerPath,
    [string]$Workspace = "",
    [string]$MetaEditorPath = "C:\Program Files\MetaTrader 5\MetaEditor64.exe",
    [string]$PythonPath = "",
    [string]$OutputPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($ExpectedDemoLogin -le 0) {
    throw "ExpectedDemoLogin must be a positive demo login."
}
$forbiddenLogins = @(901018, 5054216668, 5054283907)
if ($ExpectedDemoLogin -in $forbiddenLogins) {
    throw "ExpectedDemoLogin must be a newly created dedicated demo login."
}
if (-not (Test-Path -LiteralPath $Mt5InstallerPath -PathType Leaf)) {
    throw "Mt5InstallerPath must reference an operator-supplied installer."
}
if ([string]::IsNullOrWhiteSpace($Workspace)) {
    $Workspace = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}
if ([string]::IsNullOrWhiteSpace($PythonPath)) {
    $PythonPath = (
        "$env:USERPROFILE\.cache\codex-runtimes\" +
        "codex-primary-runtime\dependencies\python\python.exe"
    )
}
if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
    throw "Python runtime was not found: $PythonPath"
}
$Workspace = [System.IO.Path]::GetFullPath($Workspace)
$artifactRoot = Join-Path $Workspace "artifacts"
if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $OutputPath = Join-Path $artifactRoot (
        "StraddleReplica-INDEPENDENT-DEMO.zip"
    )
}

& (Join-Path $Workspace "scripts\build.ps1") `
    -Workspace $Workspace `
    -MetaEditorPath $MetaEditorPath

$stage = Join-Path $artifactRoot "independent-demo-staging"
$artifactFull = [System.IO.Path]::GetFullPath($artifactRoot).TrimEnd("\") + "\"
$stageFull = [System.IO.Path]::GetFullPath($stage)
if (-not $stageFull.StartsWith(
    $artifactFull,
    [System.StringComparison]::OrdinalIgnoreCase
)) {
    throw "Unsafe independent-demo staging path."
}
if (Test-Path -LiteralPath $stageFull) {
    Remove-Item -LiteralPath $stageFull -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $stageFull | Out-Null

$files = @(
    @{
        Source = "mql5\StraddleReplica.ex5"
        Destination = "candidate\StraddleReplica.ex5"
    },
    @{
        Source = "profiles\latest_30_independent_demo.set"
        Destination = "candidate\latest_30_independent_demo.set"
    },
    @{
        Source = "monitor\independent-demo-commissioning.ini"
        Destination = "candidate\independent-demo-commissioning.ini"
    },
    @{
        Source = "monitor\independent-demo-startup.ini"
        Destination = "candidate\independent-demo-startup.ini"
    },
    @{
        Source = "deploy\vps-docker-independent\compose.yaml"
        Destination = "compose.yaml"
    },
    @{
        Source = "deploy\vps-docker\Dockerfile"
        Destination = "image\Dockerfile"
    },
    @{
        Source = "deploy\vps-docker\entrypoint.sh"
        Destination = "image\entrypoint.sh"
    },
    @{
        Source = "docs\FIDELITY.md"
        Destination = "docs\FIDELITY.md"
    }
)
foreach ($entry in $files) {
    $source = Join-Path $Workspace $entry.Source
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "Required independent-demo file is missing: $($entry.Source)"
    }
    $destination = Join-Path $stageFull $entry.Destination
    New-Item -ItemType Directory -Force `
        -Path (Split-Path -Parent $destination) | Out-Null
    Copy-Item -LiteralPath $source -Destination $destination -Force
}
Copy-Item `
    -LiteralPath $Mt5InstallerPath `
    -Destination (Join-Path $stageFull "candidate\mt5-installer.exe") `
    -Force

$presetPath = Join-Path (
    $stageFull
) "candidate\latest_30_independent_demo.set"
$preset = Get-Content -LiteralPath $presetPath -Raw
foreach ($requiredLine in @(
    "RuntimeMode=0",
    "RequireDemoAccount=true",
    "RequireBoundAccount=true",
    "ExpectedAccountLogin=0"
)) {
    if ($preset -notmatch (
        "(?m)^" + [regex]::Escape($requiredLine) + "\s*$"
    )) {
        throw "Independent preset is not a fail-closed template: $requiredLine"
    }
}
if ($preset -match "(?im)RuntimeMode=1|ShadowCommandFile|ShadowAckFile") {
    throw "Independent preset contains forbidden shadow configuration."
}
$preset = $preset.Replace(
    "ExpectedAccountLogin=0",
    "ExpectedAccountLogin=$ExpectedDemoLogin"
)
Set-Content -LiteralPath $presetPath -Value $preset -Encoding Ascii

$configurationFiles = Get-ChildItem `
    -LiteralPath $stageFull `
    -Recurse `
    -File |
    Where-Object { $_.Extension -in @(".set", ".ini") }
foreach ($configuration in $configurationFiles) {
    $text = Get-Content -LiteralPath $configuration.FullName -Raw
    if ($text -match "(?im)RuntimeMode=1|ShadowCommandFile|ShadowAckFile") {
        throw "Package contains forbidden shadow configuration."
    }
}

$forbidden = Get-ChildItem -LiteralPath $stageFull -Recurse -File |
    Where-Object {
        $_.Extension.ToLowerInvariant() -in @(".mq5", ".mqh") -or
        $_.Name -match "(?i)password|credential|secret"
    }
if ($forbidden) {
    throw "Independent package contains source or credential files."
}

$hashLines = Get-ChildItem -LiteralPath $stageFull -Recurse -File |
    Sort-Object FullName |
    ForEach-Object {
        $relative = $_.FullName.Substring($stageFull.Length + 1).
            Replace("\", "/")
        $hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
        "$hash  $relative"
    }
Set-Content `
    -LiteralPath (Join-Path $stageFull "SHA256SUMS.txt") `
    -Value $hashLines `
    -Encoding Ascii

$outputFull = [System.IO.Path]::GetFullPath($OutputPath)
if (-not $outputFull.StartsWith(
    $artifactFull,
    [System.StringComparison]::OrdinalIgnoreCase
)) {
    throw "Independent package output must remain under artifacts."
}
New-Item -ItemType Directory -Force `
    -Path (Split-Path -Parent $outputFull) | Out-Null
if (Test-Path -LiteralPath $outputFull) {
    Remove-Item -LiteralPath $outputFull -Force
}
& $PythonPath -m straddle_replica.portable_zip `
    --source $stageFull `
    --output $outputFull
if ($LASTEXITCODE -ne 0) {
    throw "Portable independent-demo ZIP creation failed."
}
Remove-Item -LiteralPath $stageFull -Recurse -Force

$archive = Get-Item -LiteralPath $outputFull
$archiveHash = (
    Get-FileHash -LiteralPath $outputFull -Algorithm SHA256
).Hash
Write-Host "Created independent demo package: $($archive.FullName)"
Write-Host "Archive size: $($archive.Length) bytes"
Write-Host "ZIP SHA256: $archiveHash"
```

- [ ] **Step 5: Implement candidate-only deployment with protected-container fingerprints**

Create `scripts/deploy_independent_demo_vps.ps1`:

```powershell
param(
    [string]$SshAlias = "nishahomes-vps",
    [Parameter(Mandatory = $true)]
    [string]$PackagePath,
    [string]$RemoteRoot = "/opt/straddle-fidelity-independent-demo",
    [switch]$StartTrading
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($RemoteRoot -ne "/opt/straddle-fidelity-independent-demo") {
    throw "RemoteRoot must be /opt/straddle-fidelity-independent-demo."
}
if (-not (Test-Path -LiteralPath $PackagePath -PathType Leaf)) {
    throw "Independent demo package was not found: $PackagePath"
}

function Invoke-IndependentSsh {
    param([Parameter(Mandatory = $true)][string]$Command)
    $output = & ssh $SshAlias $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Remote independent-demo command failed: $Command"
    }
    return (($output | Out-String).Trim())
}

function Get-ContainerFingerprint {
    param([Parameter(Mandatory = $true)][string]$Name)
    return Invoke-IndependentSsh -Command (
        "docker inspect --format " +
        "'{{.Id}}|{{.State.Status}}|{{.RestartCount}}|{{.State.OOMKilled}}' " +
        $Name
    )
}

$protectedNames = @(
    "straddle-fidelity-candidate-demo",
    "straddle-replica-demo-vps"
)
$before = @{}
foreach ($name in $protectedNames) {
    $before[$name] = Get-ContainerFingerprint -Name $name
    if ([string]::IsNullOrWhiteSpace($before[$name])) {
        throw "Protected container could not be inspected: $name"
    }
}

Invoke-IndependentSsh -Command "mkdir -p $RemoteRoot" | Out-Null
& scp $PackagePath "${SshAlias}:$RemoteRoot/package.zip"
if ($LASTEXITCODE -ne 0) {
    throw "Independent demo package upload failed."
}
Invoke-IndependentSsh -Command (
    "cd $RemoteRoot && " +
    "unzip -o package.zip -d $RemoteRoot >/dev/null && " +
    "chmod 0755 $RemoteRoot/image/entrypoint.sh && " +
    "chown -R 1000:1000 $RemoteRoot"
) | Out-Null
$remoteForbidden = Invoke-IndependentSsh -Command (
    "find $RemoteRoot -type f " +
    "\( -iname '*.mq5' -o -iname '*.mqh' " +
    "-o -iname '*password*' -o -iname '*credential*' " +
    "-o -iname '*secret*' \) -print"
)
if (-not [string]::IsNullOrWhiteSpace($remoteForbidden)) {
    throw "Remote independent root contains source or credential files."
}
$remoteShadow = Invoke-IndependentSsh -Command (
    "grep -ERil " +
    "'RuntimeMode=1|ShadowCommandFile|ShadowAckFile' " +
    "$RemoteRoot/candidate --include='*.set' --include='*.ini' || true"
)
if (-not [string]::IsNullOrWhiteSpace($remoteShadow)) {
    throw "Remote independent root contains shadow configuration."
}
Invoke-IndependentSsh -Command (
    "docker build -t straddle-fidelity-independent-mt5:bookworm " +
    "$RemoteRoot/image"
) | Out-Null
$mt5StartAssignment = if ($StartTrading) {
    "MT5_START=1"
}
else {
    "MT5_START=0"
}
$mt5ConfigAssignment = if ($StartTrading) {
    "MT5_CONFIG_WINDOWS='Z:\data\candidate\independent-demo-startup.ini'"
}
else {
    "MT5_CONFIG_WINDOWS='Z:\data\candidate\independent-demo-commissioning.ini'"
}
$composeSuffix = if ($StartTrading) {
    " --force-recreate fidelity-independent"
}
else {
    ""
}
Invoke-IndependentSsh -Command (
    "cd $RemoteRoot && " +
    "$mt5StartAssignment $mt5ConfigAssignment docker compose " +
    "-p straddle-fidelity-independent-demo up -d$composeSuffix"
) | Out-Null

foreach ($name in $protectedNames) {
    $after = Get-ContainerFingerprint -Name $name
    if ($after -ne $before[$name]) {
        throw "Protected container changed during deployment: $name"
    }
}

$candidate = "straddle-fidelity-independent-demo"
$state = Get-ContainerFingerprint -Name $candidate
if ($state -ne "running|0|false") {
    throw "Independent container health is not clean: $state"
}
$vnc = Invoke-IndependentSsh -Command "docker port $candidate 5900/tcp"
if ($vnc -ne "127.0.0.1:15925") {
    throw "Independent VNC is not loopback-only: $vnc"
}
$environment = Invoke-IndependentSsh -Command (
    "docker inspect --format " +
    "'{{range .Config.Env}}{{println .}}{{end}}' " +
    $candidate
)
$environmentLines = $environment -split "\r?\n"
$expectedStart = if ($StartTrading) {
    "MT5_START=1"
}
else {
    "MT5_START=0"
}
if ($expectedStart -notin $environmentLines) {
    throw "Independent container start mode is incorrect."
}

Write-Host "Independent container: $candidate"
Write-Host "Independent VNC: 127.0.0.1:15925"
Write-Host "Independent start mode: $expectedStart"
Write-Host "Protected containers remained unchanged."
```

- [ ] **Step 6: Run deployment tests and verify GREEN**

Run:

```powershell
& $python -m pytest `
  tests\test_independent_demo_deployment.py `
  tests\test_independent_demo_contract.py -q
```

Expected: `6 passed`.

- [ ] **Step 7: Write the Task 2 checkpoint**

Run:

```powershell
$root='artifacts\checkpoints\2026-08-12-independent-demo'
Get-FileHash `
  deploy\vps-docker-independent\compose.yaml,`
  scripts\package_independent_demo.ps1,`
  scripts\deploy_independent_demo_vps.ps1 `
  -Algorithm SHA256 |
  ConvertTo-Json |
  Set-Content "$root\task-02-deployment.json"
```

## Task 3: Protect temporary account credentials and prevent log leakage

**Files:**

- Create: `scripts/protect_independent_demo_credentials.ps1`
- Create: `tests/test_independent_demo_credentials.py`

- [ ] **Step 1: Write the failing credential-handling contract**

Create `tests/test_independent_demo_credentials.py`:

```python
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
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```powershell
& $python -m pytest tests\test_independent_demo_credentials.py -q
```

Expected: failure because the protection script does not exist.

- [ ] **Step 3: Implement DPAPI protection with a current-user-only ACL**

Create `scripts/protect_independent_demo_credentials.ps1`:

```powershell
param(
    [Parameter(Mandatory = $true)]
    [long]$Login,
    [Parameter(Mandatory = $true)]
    [string]$Server,
    [SecureString]$MasterPassword,
    [SecureString]$InvestorPassword,
    [string]$Workspace = "",
    [string]$OutputPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($Login -le 0) {
    throw "Login must be positive."
}
if ([string]::IsNullOrWhiteSpace($Server)) {
    throw "Server is required."
}
if ([string]::IsNullOrWhiteSpace($Workspace)) {
    $Workspace = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}
$privateRoot = Join-Path $Workspace "artifacts\private"
if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $OutputPath = Join-Path (
        $privateRoot
    ) "independent-demo-credentials.json"
}
$privateFull = [System.IO.Path]::GetFullPath($privateRoot).TrimEnd("\") + "\"
$outputFull = [System.IO.Path]::GetFullPath($OutputPath)
if (-not $outputFull.StartsWith(
    $privateFull,
    [System.StringComparison]::OrdinalIgnoreCase
)) {
    throw "Credential output must remain under artifacts\private."
}
if ($null -eq $MasterPassword) {
    $MasterPassword = Read-Host "Master password" -AsSecureString
}
if ($null -eq $InvestorPassword) {
    $InvestorPassword = Read-Host "Investor password" -AsSecureString
}

New-Item -ItemType Directory -Force -Path $privateRoot | Out-Null
$temporary = "$outputFull.tmp"
$payload = @{
    schema_version = 1
    login = $Login
    server = $Server
    created_utc = [DateTime]::UtcNow.ToString("o")
    master_cipher = ConvertFrom-SecureString $MasterPassword
    investor_cipher = ConvertFrom-SecureString $InvestorPassword
}
$payload |
    ConvertTo-Json |
    Set-Content -LiteralPath $temporary -Encoding UTF8
Move-Item -LiteralPath $temporary -Destination $outputFull -Force

$identityName = (
    [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
)
$identity = New-Object System.Security.Principal.NTAccount($identityName)
$acl = New-Object System.Security.AccessControl.FileSecurity
$acl.SetOwner($identity)
$acl.SetAccessRuleProtection($true, $false)
$rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
    $identity,
    [System.Security.AccessControl.FileSystemRights]::FullControl,
    [System.Security.AccessControl.AccessControlType]::Allow
)
$acl.AddAccessRule($rule)
Set-Acl -LiteralPath $outputFull -AclObject $acl

Write-Host "Protected credential file created."
Write-Host "Login: $Login"
Write-Host "Server: $Server"
Write-Host "Passwords were not printed."
```

- [ ] **Step 4: Run credential tests and verify GREEN**

Run:

```powershell
& $python -m pytest tests\test_independent_demo_credentials.py -q
```

Expected: `2 passed`.

- [ ] **Step 5: Write the Task 3 checkpoint**

Run:

```powershell
$root='artifacts\checkpoints\2026-08-12-independent-demo'
Get-FileHash scripts\protect_independent_demo_credentials.ps1 `
  -Algorithm SHA256 |
  ConvertTo-Json |
  Set-Content "$root\task-03-credentials.json"
```

Do not hash, copy, print, or include the generated protected credential file in a checkpoint.

## Task 4: Capture inferred target stop changes and archive complete target cycles

**Files:**

- Modify: `straddle_replica/observer_adapter.py`
- Modify: `tests/test_observer_adapter.py`
- Create: `straddle_replica/independent_cycle_archive.py`
- Create: `tools/archive_independent_target.py`
- Create: `tests/test_independent_cycle_archive.py`

- [ ] **Step 1: Add a failing observer stop-change test**

Append to `tests/test_observer_adapter.py`:

```python
def test_position_sl_change_emits_one_inferred_stop_request(
    tmp_path: Path,
) -> None:
    started = datetime(2026, 8, 5, 0, 0, tzinfo=UTC)
    root = tmp_path / "observer"
    session = _write_session(root, now=started)
    adapter = ObserverEventAdapter(
        ObserverAdapterConfig(
            observer_root=root,
            state_path=tmp_path / "adapter.json",
        )
    )
    assert adapter.poll(now=started) == []

    opened = {
        "ticket": 1001,
        "comment": "STR B1",
        "volume": 0.01,
        "price_open": 4081.36,
        "sl": 0.0,
    }
    first = started + timedelta(seconds=1)
    _append_snapshot(
        session,
        now=first,
        sequence=11,
        positions=[opened],
    )
    assert adapter.poll(now=first) == []

    second = started + timedelta(seconds=2)
    _append_snapshot(
        session,
        now=second,
        sequence=12,
        positions=[{**opened, "sl": 4081.56}],
    )
    events = adapter.poll(now=second)

    assert len(events) == 1
    assert events[0]["kind"] == "stop_request"
    assert events[0]["comment"] == "STR B1"
    assert events[0]["position_ticket"] == 1001
    assert events[0]["price"] == 4081.56
    assert events[0]["sl"] == 4081.56
    assert events[0]["evidence_grade"] == "BEST_EFFORT"
    assert adapter.poll(now=second) == []
```

- [ ] **Step 2: Run the focused observer test and verify RED**

Run:

```powershell
& $python -m pytest `
  tests\test_observer_adapter.py::test_position_sl_change_emits_one_inferred_stop_request `
  -q
```

Expected: failure because snapshots do not currently emit stop updates.

- [ ] **Step 3: Add persisted stop state and inferred stop events**

In `ObserverEventAdapter._default_state`, add:

```python
"position_stop_losses": {},
```

In `_initialize`, add this entry to the state update:

```python
"position_stop_losses": {
    str(ticket): float(row.get("sl") or 0.0)
    for row in positions
    if (ticket := self._ticket(row)) > 0
},
```

Add this method immediately before `_process_snapshot`:

```python
def _position_stop_events(
    self,
    positions: list[dict[str, Any]],
    snapshot: Mapping[str, Any],
) -> list[dict[str, Any]]:
    previous = {
        str(ticket): float(value)
        for ticket, value in dict(
            self._state.get("position_stop_losses") or {}
        ).items()
    }
    current: dict[str, float] = {}
    events: list[dict[str, Any]] = []
    for position in positions:
        ticket = self._ticket(position)
        if ticket <= 0:
            continue
        key = str(ticket)
        stop_loss = float(position.get("sl") or 0.0)
        current[key] = stop_loss
        if key not in previous:
            continue
        if abs(stop_loss - previous[key]) <= 1e-9:
            continue
        comment = str(position.get("comment") or "")
        if COMMENT_RE.fullmatch(comment) is None:
            continue
        event = self._base_event(
            time_utc=str(snapshot["capture_time_utc"]),
            kind="stop_request",
            comment=comment,
        )
        event.update(
            {
                "ticket": ticket,
                "position_ticket": ticket,
                "volume": float(position.get("volume") or 0.0),
                "price": stop_loss,
                "sl": stop_loss,
            }
        )
        events.append(event)
    self._state["position_stop_losses"] = current
    return events
```

In `_process_snapshot`, seed or clear `position_stop_losses` while suppressing the current cycle, and append stop events only in the normal active-cycle branch:

```python
if self._state["suppress_current_cycle"]:
    self._state["position_stop_losses"] = {
        str(ticket): float(row.get("sl") or 0.0)
        for row in positions
        if (ticket := self._ticket(row)) > 0
    }
    # Existing suppression logic remains unchanged.
elif not active:
    self._state["position_stop_losses"] = {}
    # Existing flat-transition logic remains unchanged.
else:
    # Existing new-order logic remains unchanged.
    events.extend(self._position_stop_events(positions, snapshot))
```

- [ ] **Step 4: Run all observer adapter tests and verify GREEN**

Run:

```powershell
& $python -m pytest tests\test_observer_adapter.py -q
```

Expected: all observer adapter tests pass.

- [ ] **Step 5: Write failing target cycle archive tests**

Create `tests/test_independent_cycle_archive.py`:

```python
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from straddle_replica.independent_cycle_archive import (
    IndependentCycleArchive,
    IndependentCycleArchiveConfig,
)


UTC = timezone.utc


def event(
    sequence: int,
    time: datetime,
    kind: str,
    comment: str = "",
    price: float = 0.0,
) -> dict:
    return {
        "session_id": "target-session",
        "sequence": sequence,
        "time_utc": time.isoformat(),
        "kind": kind,
        "comment": comment,
        "side": "buy" if " B" in comment else "sell" if " S" in comment else "",
        "volume": 0.01 if comment else 0.0,
        "price": price,
        "sl": price if kind == "stop_request" else 0.0,
        "retcode": 10008 if kind == "pending_request" else 0,
        "evidence_grade": "BEST_EFFORT",
    }


def read_rows(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_archives_cycle_without_writing_shadow_commands(
    tmp_path: Path,
) -> None:
    archive_path = tmp_path / "target-cycles.jsonl"
    service = IndependentCycleArchive(
        IndependentCycleArchiveConfig(
            state_path=tmp_path / "state.json",
            archive_path=archive_path,
        )
    )
    started = datetime(2026, 8, 12, 0, 0, tzinfo=UTC)

    service.process_events(
        [
            event(1, started, "pending_request", "STR B1", 4081.36),
            event(
                2,
                started + timedelta(milliseconds=100),
                "pending_request",
                "STR S1",
                4078.64,
            ),
            event(
                3,
                started + timedelta(seconds=1),
                "stop_request",
                "STR B1",
                4081.56,
            ),
            event(
                4,
                started + timedelta(seconds=2),
                "cancel_request",
                "STR S30",
            ),
            event(
                5,
                started + timedelta(seconds=3),
                "cancel_request",
                "",
            ),
        ]
    )

    rows = read_rows(archive_path)
    assert rows[0]["kind"] == "cycle_start"
    assert [row["comment"] for row in rows if row["kind"] == "pending_request"] == [
        "STR B1",
        "STR S1",
    ]
    assert any(row["kind"] == "basket_trigger" for row in rows)
    assert any(row["kind"] == "stop_request" for row in rows)
    assert rows[-1]["kind"] == "cycle_complete"
    assert not (tmp_path / "command.csv").exists()
    assert not (tmp_path / "ack.csv").exists()


def test_next_cycle_adds_restart_to_the_completed_cycle(
    tmp_path: Path,
) -> None:
    archive_path = tmp_path / "target-cycles.jsonl"
    service = IndependentCycleArchive(
        IndependentCycleArchiveConfig(
            state_path=tmp_path / "state.json",
            archive_path=archive_path,
        )
    )
    started = datetime(2026, 8, 12, 0, 0, tzinfo=UTC)
    service.process_events(
        [
            event(1, started, "pending_request", "STR B1", 4081.36),
            event(2, started, "pending_request", "STR S1", 4078.64),
            event(3, started + timedelta(seconds=1), "cancel_request"),
        ]
    )
    service.process_events(
        [
            event(
                4,
                started + timedelta(seconds=5),
                "pending_request",
                "STR B1",
                4082.36,
            ),
            event(
                5,
                started + timedelta(seconds=5, milliseconds=100),
                "pending_request",
                "STR S1",
                4079.64,
            ),
        ]
    )

    rows = read_rows(archive_path)
    cycle_ids = []
    for row in rows:
        if row["cycle_id"] not in cycle_ids:
            cycle_ids.append(row["cycle_id"])
    assert len(cycle_ids) == 2
    assert any(
        row["cycle_id"] == cycle_ids[0]
        and row["kind"] == "cycle_restart"
        for row in rows
    )
```

- [ ] **Step 6: Run the archive tests and verify RED**

Run:

```powershell
& $python -m pytest tests\test_independent_cycle_archive.py -q
```

Expected: import failure because the cycle archive module does not exist.

- [ ] **Step 7: Implement a command-free target cycle archive**

Create `straddle_replica/independent_cycle_archive.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any


UTC = timezone.utc


def _parse_time(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _accepted(event: dict[str, Any]) -> bool:
    return int(event.get("retcode") or 0) in {0, 10008, 10009, 10010}


@dataclass(frozen=True)
class IndependentCycleArchiveConfig:
    state_path: Path
    archive_path: Path
    pair_window_seconds: float = 2.0

    def __post_init__(self) -> None:
        if self.pair_window_seconds <= 0:
            raise ValueError("pair_window_seconds must be positive")


class IndependentCycleArchive:
    def __init__(self, config: IndependentCycleArchiveConfig) -> None:
        self.config = config
        self._state = self._load_state()

    def _default_state(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "session_id": "",
            "last_sequence": 0,
            "sequence_gaps": 0,
            "session_restarts": 0,
            "current_cycle_id": "",
            "last_completed_cycle_id": "",
            "pending_start": [],
            "basket_triggered": False,
        }

    def _load_state(self) -> dict[str, Any]:
        if not self.config.state_path.exists():
            return self._default_state()
        payload = json.loads(
            self.config.state_path.read_text(encoding="utf-8")
        )
        return {**self._default_state(), **payload}

    def _persist(self) -> None:
        path = self.config.state_path
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(self._state, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        os.replace(temporary, path)

    def _append(
        self,
        event: dict[str, Any],
        cycle_id: str,
    ) -> None:
        self.config.archive_path.parent.mkdir(parents=True, exist_ok=True)
        with self.config.archive_path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {**event, "cycle_id": cycle_id},
                    sort_keys=True,
                )
                + "\n"
            )

    def _synthetic(
        self,
        source: dict[str, Any],
        kind: str,
    ) -> dict[str, Any]:
        return {
            "session_id": str(source.get("session_id") or ""),
            "sequence": int(source.get("sequence") or 0),
            "time_utc": str(source.get("time_utc") or ""),
            "kind": kind,
            "comment": "",
            "side": "",
            "volume": 0.0,
            "price": 0.0,
            "sl": 0.0,
            "tp": 0.0,
            "retcode": 0,
            "evidence_grade": "BEST_EFFORT",
            "source": "observer_inferred",
        }

    def _accept_cursor(self, event: dict[str, Any]) -> bool:
        session_id = str(event.get("session_id") or "legacy")
        active_session = str(self._state["session_id"])
        if active_session and active_session != session_id:
            cycle_id = str(self._state["current_cycle_id"])
            if cycle_id:
                invalid = self._synthetic(event, "cycle_invalid")
                invalid["reason"] = "observer_session_changed"
                self._append(invalid, cycle_id)
            self._state.update(
                {
                    "session_restarts": int(
                        self._state["session_restarts"]
                    )
                    + 1,
                    "last_sequence": 0,
                    "current_cycle_id": "",
                    "pending_start": [],
                    "basket_triggered": False,
                }
            )
        self._state["session_id"] = session_id
        sequence = int(event.get("sequence") or 0)
        previous = int(self._state["last_sequence"])
        if sequence <= previous:
            return False
        if previous and sequence > previous + 1:
            self._state["sequence_gaps"] = int(
                self._state["sequence_gaps"]
            ) + sequence - previous - 1
        self._state["last_sequence"] = sequence
        return True

    def _try_start(self) -> int:
        pending = list(self._state["pending_start"])
        b1 = next(
            (
                event
                for event in pending
                if event.get("comment") == "STR B1" and _accepted(event)
            ),
            None,
        )
        s1 = next(
            (
                event
                for event in pending
                if event.get("comment") == "STR S1" and _accepted(event)
            ),
            None,
        )
        if b1 is None or s1 is None:
            return 0
        first = min(_parse_time(b1["time_utc"]), _parse_time(s1["time_utc"]))
        last = max(_parse_time(b1["time_utc"]), _parse_time(s1["time_utc"]))
        if (last - first).total_seconds() > self.config.pair_window_seconds:
            self._state["pending_start"] = []
            return 0
        cycle_id = (
            first.strftime("%Y%m%dT%H%M%S")
            + f"{first.microsecond // 1000:03d}Z"
            + f"-target-{max(int(b1['sequence']), int(s1['sequence']))}"
        )
        previous = str(self._state["last_completed_cycle_id"])
        if previous:
            self._append(self._synthetic(b1, "cycle_restart"), previous)
        start_event = self._synthetic(b1, "cycle_start")
        start_event["price"] = (
            float(b1.get("price") or 0.0)
            + float(s1.get("price") or 0.0)
        ) / 2.0
        self._append(start_event, cycle_id)
        for event in sorted(
            pending,
            key=lambda item: (
                str(item.get("time_utc") or ""),
                int(item.get("sequence") or 0),
            ),
        ):
            self._append(event, cycle_id)
        self._state.update(
            {
                "current_cycle_id": cycle_id,
                "last_completed_cycle_id": "",
                "pending_start": [],
                "basket_triggered": False,
            }
        )
        return len(pending) + 1

    def process_events(self, events: list[dict[str, Any]]) -> dict[str, int]:
        archived = 0
        for event in sorted(
            events,
            key=lambda item: (
                str(item.get("time_utc") or ""),
                int(item.get("sequence") or 0),
            ),
        ):
            if not self._accept_cursor(event):
                continue
            kind = str(event.get("kind") or "")
            comment = str(event.get("comment") or "")
            cycle_id = str(self._state["current_cycle_id"])
            is_start = kind == "pending_request" and comment in {
                "STR B1",
                "STR S1",
            }
            if not cycle_id:
                if is_start:
                    self._state["pending_start"].append(event)
                    archived += self._try_start()
                continue

            if (
                kind in {"cancel_request", "close_request", "close_fill"}
                and not self._state["basket_triggered"]
            ):
                self._append(
                    self._synthetic(event, "basket_trigger"),
                    cycle_id,
                )
                self._state["basket_triggered"] = True
                archived += 1
            if kind == "close_fill":
                close_request = self._synthetic(event, "close_request")
                close_request.update(
                    {
                        "comment": str(event.get("comment") or ""),
                        "side": str(event.get("side") or ""),
                        "volume": float(event.get("volume") or 0.0),
                        "price": float(event.get("price") or 0.0),
                        "position_ticket": int(
                            event.get("position_ticket")
                            or event.get("ticket")
                            or 0
                        ),
                    }
                )
                self._append(close_request, cycle_id)
                archived += 1
            if kind == "cancel_request" and not comment:
                self._append(
                    self._synthetic(event, "cycle_complete"),
                    cycle_id,
                )
                self._state.update(
                    {
                        "last_completed_cycle_id": cycle_id,
                        "current_cycle_id": "",
                        "pending_start": [],
                        "basket_triggered": False,
                    }
                )
                archived += 1
                continue
            self._append(event, cycle_id)
            archived += 1
        self._persist()
        return {
            "archived_events": archived,
            "sequence_gaps": int(self._state["sequence_gaps"]),
            "session_restarts": int(self._state["session_restarts"]),
        }
```

- [ ] **Step 8: Implement the continuous archive CLI**

Create `tools/archive_independent_target.py`:

```python
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from straddle_replica.independent_cycle_archive import (  # noqa: E402
    IndependentCycleArchive,
    IndependentCycleArchiveConfig,
)
from straddle_replica.observer_adapter import (  # noqa: E402
    ObserverAdapterConfig,
    ObserverEventAdapter,
)


def _write_health(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--observer-root", required=True, type=Path)
    parser.add_argument("--observer-state", required=True, type=Path)
    parser.add_argument("--archive-state", required=True, type=Path)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--health", required=True, type=Path)
    parser.add_argument("--poll-ms", type=int, default=100)
    parser.add_argument("--heartbeat-max-age-seconds", type=float, default=5.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    if args.poll_ms < 20:
        parser.error("--poll-ms must be at least 20")

    adapter = ObserverEventAdapter(
        ObserverAdapterConfig(
            observer_root=args.observer_root,
            state_path=args.observer_state,
            heartbeat_max_age_seconds=args.heartbeat_max_age_seconds,
        )
    )
    archive = IndependentCycleArchive(
        IndependentCycleArchiveConfig(
            state_path=args.archive_state,
            archive_path=args.archive,
        )
    )
    while True:
        try:
            result = archive.process_events(adapter.poll())
            _write_health(
                args.health,
                {
                    "status": "RUNNING",
                    "updated_at_utc": datetime.now(
                        tz=timezone.utc
                    ).isoformat(),
                    **result,
                },
            )
        except (
            FileNotFoundError,
            OSError,
            RuntimeError,
            json.JSONDecodeError,
        ) as error:
            _write_health(
                args.health,
                {
                    "status": "WAITING_FOR_TARGET",
                    "updated_at_utc": datetime.now(
                        tz=timezone.utc
                    ).isoformat(),
                    "error_type": type(error).__name__,
                    "error": str(error),
                },
            )
            if args.once:
                raise
        if args.once:
            print(json.dumps(result, sort_keys=True))
            return 0
        time.sleep(args.poll_ms / 1000.0)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 9: Run archive and observer tests**

Run:

```powershell
& $python -m pytest `
  tests\test_observer_adapter.py `
  tests\test_independent_cycle_archive.py -q
```

Expected: all tests pass.

- [ ] **Step 10: Write the Task 4 checkpoint**

Run:

```powershell
$root='artifacts\checkpoints\2026-08-12-independent-demo'
Get-FileHash `
  straddle_replica\observer_adapter.py,`
  straddle_replica\independent_cycle_archive.py,`
  tools\archive_independent_target.py `
  -Algorithm SHA256 |
  ConvertTo-Json |
  Set-Content "$root\task-04-target-archive.json"
```

## Task 5: Compare different independent cycle IDs using normalized lifecycle evidence

**Files:**

- Create: `straddle_replica/independent_fidelity.py`
- Create: `tools/compare_independent_cycles.py`
- Create: `tests/test_independent_fidelity.py`

- [ ] **Step 1: Write failing normalized fidelity tests**

Create `tests/test_independent_fidelity.py`:

```python
from datetime import datetime, timedelta, timezone

from straddle_replica.independent_fidelity import (
    compare_independent_cycle_pair,
    pair_complete_cycles,
)


UTC = timezone.utc


def deployment(
    cycle_id: str,
    started: datetime,
    anchor: float,
    step: float,
) -> list[dict]:
    events = [
        {
            "cycle_id": cycle_id,
            "time_utc": started.isoformat(),
            "kind": "cycle_start",
            "comment": "",
            "side": "",
            "level": 0,
            "volume": 0.0,
            "requested_price": 0.0,
            "accepted_price": 0.0,
            "sl": 0.0,
            "retcode": 0,
        }
    ]
    for level in range(1, 31):
        volume = 0.01 if level <= 10 else 0.06 if level <= 20 else 0.15
        for side in ("B", "S"):
            index = (level - 1) * 2 + (0 if side == "B" else 1)
            events.append(
                {
                    "cycle_id": cycle_id,
                    "time_utc": (
                        started + timedelta(milliseconds=index * 100)
                    ).isoformat(),
                    "kind": "pending_request",
                    "comment": f"STR {side}{level}",
                    "side": "buy" if side == "B" else "sell",
                    "level": level,
                    "volume": volume,
                    "requested_price": anchor
                    + (1 if side == "B" else -1) * level * step,
                    "accepted_price": 0.0,
                    "sl": 0.0,
                    "retcode": 10008,
                }
            )
    return events


def complete(events: list[dict], at: datetime) -> None:
    cycle_id = events[0]["cycle_id"]
    for kind in ("basket_trigger", "cycle_complete", "cycle_restart"):
        events.append(
            {
                "cycle_id": cycle_id,
                "time_utc": at.isoformat(),
                "kind": kind,
                "comment": "",
                "side": "",
                "level": 0,
                "volume": 0.0,
                "requested_price": 0.0,
                "accepted_price": 0.0,
                "sl": 0.0,
                "retcode": 0,
            }
        )


def test_different_ids_and_anchors_can_have_exact_logic_parity() -> None:
    started = datetime(2026, 8, 12, tzinfo=UTC)
    target = deployment("target-1", started, 4380.0, 1.46)
    candidate = deployment(
        "candidate-9",
        started + timedelta(milliseconds=400),
        4395.0,
        1.465,
    )
    complete(target, started + timedelta(minutes=1))
    complete(candidate, started + timedelta(minutes=1, milliseconds=400))

    report = compare_independent_cycle_pair(
        target,
        candidate,
        start_tolerance_seconds=2.0,
        normalized_price_tolerance=0.02,
    )

    assert report["status"] == "PASS"
    assert report["target_cycle_id"] == "target-1"
    assert report["candidate_cycle_id"] == "candidate-9"
    assert report["fidelity"]["strict"]["f1_percent"] == 100.0
    assert report["deterministic_mismatch_count"] == 0


def test_missing_level_fails_independent_logic() -> None:
    started = datetime(2026, 8, 12, tzinfo=UTC)
    target = deployment("target-1", started, 4380.0, 1.46)
    candidate = deployment("candidate-1", started, 4380.0, 1.46)
    candidate = [
        event for event in candidate if event["comment"] != "STR B7"
    ]
    complete(target, started + timedelta(minutes=1))
    complete(candidate, started + timedelta(minutes=1))

    report = compare_independent_cycle_pair(
        target,
        candidate,
        start_tolerance_seconds=2.0,
        normalized_price_tolerance=0.02,
    )

    assert report["status"] == "FAIL"
    assert "STR B7" in report["deployment"]["candidate_missing_slots"]


def test_different_stop_transition_fails_deterministic_logic() -> None:
    started = datetime(2026, 8, 12, tzinfo=UTC)
    target = deployment("target-1", started, 4380.0, 1.46)
    candidate = deployment("candidate-1", started, 4380.0, 1.46)
    stop = {
        "cycle_id": "target-1",
        "time_utc": (started + timedelta(seconds=30)).isoformat(),
        "kind": "stop_request",
        "comment": "STR B1",
        "side": "buy",
        "level": 1,
        "volume": 0.01,
        "requested_price": 4381.66,
        "accepted_price": 0.0,
        "sl": 4381.66,
        "retcode": 10009,
    }
    target.append(stop)
    candidate.append(
        {
            **stop,
            "cycle_id": "candidate-1",
            "requested_price": 4381.86,
            "sl": 4381.86,
        }
    )
    complete(target, started + timedelta(minutes=1))
    complete(candidate, started + timedelta(minutes=1))

    report = compare_independent_cycle_pair(
        target,
        candidate,
        start_tolerance_seconds=2.0,
        normalized_price_tolerance=0.02,
    )

    assert report["status"] == "FAIL"
    assert any(
        mismatch["category"] == "normalized_decision"
        for mismatch in report["deterministic_mismatches"]
    )


def test_pairing_uses_nearest_start_without_requiring_equal_ids() -> None:
    started = datetime(2026, 8, 12, tzinfo=UTC)
    target_one = deployment("target-1", started, 4380.0, 1.46)
    target_two = deployment(
        "target-2",
        started + timedelta(hours=1),
        4390.0,
        1.463,
    )
    candidate_one = deployment(
        "candidate-a",
        started + timedelta(seconds=1),
        4381.0,
        1.4603,
    )
    candidate_two = deployment(
        "candidate-b",
        started + timedelta(hours=1, seconds=1),
        4391.0,
        1.4636,
    )
    for events in (
        target_one,
        target_two,
        candidate_one,
        candidate_two,
    ):
        complete(
            events,
            datetime.fromisoformat(events[0]["time_utc"])
            + timedelta(minutes=1),
        )

    pairs = pair_complete_cycles(
        [*target_one, *target_two],
        [*candidate_one, *candidate_two],
        pairing="nearest",
        max_start_gap_seconds=5.0,
    )

    assert [
        (pair[0][0]["cycle_id"], pair[1][0]["cycle_id"])
        for pair in pairs
    ] == [
        ("target-1", "candidate-a"),
        ("target-2", "candidate-b"),
    ]
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```powershell
& $python -m pytest tests\test_independent_fidelity.py -q
```

Expected: import failure because the independent fidelity module does not exist.

- [ ] **Step 3: Implement cycle splitting, pairing, normalization, and scoring**

Create `straddle_replica/independent_fidelity.py` with these public interfaces:

```python
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable

from .fidelity_score import score_lifecycle


UTC = timezone.utc
COMPLETE_KINDS = {"cycle_complete", "cycle_restart"}
EXECUTION_KINDS = {"fill", "stop_exit", "close_fill"}
DECISION_KINDS = {
    "pending_request",
    "stop_request",
    "cancel_request",
    "close_request",
    "basket_trigger",
    "cycle_complete",
    "cycle_restart",
}


def _parse_time(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _price(event: dict[str, Any]) -> float:
    for key in ("requested_price", "price", "accepted_price"):
        value = event.get(key)
        if value not in (None, ""):
            return float(value)
    return 0.0


def _accepted(event: dict[str, Any]) -> bool:
    return int(event.get("retcode") or 0) in {0, 10008, 10009, 10010}


def _cycle_groups(events: Iterable[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    grouped: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        cycle_id = str(event.get("cycle_id") or "")
        if cycle_id:
            grouped[cycle_id].append(dict(event))
    cycles = [
        sorted(
            rows,
            key=lambda event: (
                _parse_time(event["time_utc"]),
                int(event.get("sequence") or 0),
            ),
        )
        for rows in grouped.values()
    ]
    return sorted(cycles, key=lambda rows: _parse_time(rows[0]["time_utc"]))


def _complete(cycle: list[dict[str, Any]]) -> bool:
    kinds = {str(event.get("kind") or "") for event in cycle}
    return "cycle_complete" in kinds and "cycle_restart" in kinds


def pair_complete_cycles(
    target_events: list[dict[str, Any]],
    candidate_events: list[dict[str, Any]],
    *,
    pairing: str,
    max_start_gap_seconds: float,
) -> list[tuple[list[dict[str, Any]], list[dict[str, Any]]]]:
    if pairing not in {"nearest", "ordinal"}:
        raise ValueError("pairing must be nearest or ordinal")
    if max_start_gap_seconds < 0:
        raise ValueError("max_start_gap_seconds must be non-negative")
    target = [cycle for cycle in _cycle_groups(target_events) if _complete(cycle)]
    candidate = [
        cycle for cycle in _cycle_groups(candidate_events) if _complete(cycle)
    ]
    if pairing == "ordinal":
        return list(zip(target, candidate))
    remaining = list(candidate)
    pairs = []
    for target_cycle in target:
        if not remaining:
            break
        target_start = _parse_time(target_cycle[0]["time_utc"])
        closest = min(
            remaining,
            key=lambda cycle: abs(
                (
                    _parse_time(cycle[0]["time_utc"]) - target_start
                ).total_seconds()
            ),
        )
        gap = abs(
            (
                _parse_time(closest[0]["time_utc"]) - target_start
            ).total_seconds()
        )
        if gap <= max_start_gap_seconds:
            pairs.append((target_cycle, closest))
            remaining.remove(closest)
    return pairs


def _geometry(events: list[dict[str, Any]]) -> tuple[float, float]:
    initial: dict[str, dict[str, Any]] = {}
    for event in events:
        if str(event.get("kind") or "") != "pending_request":
            continue
        comment = str(event.get("comment") or "")
        if comment and comment not in initial and _accepted(event):
            initial[comment] = event
    buy = initial.get("STR B1")
    sell = initial.get("STR S1")
    if buy is None or sell is None:
        raise ValueError("Cycle is missing accepted STR B1/STR S1 geometry")
    buy_price = _price(buy)
    sell_price = _price(sell)
    step = (buy_price - sell_price) / 2.0
    if step <= 0:
        raise ValueError("Cycle step must be positive")
    return (buy_price + sell_price) / 2.0, step


def _normalized_events(
    events: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    anchor, step = _geometry(events)
    seen_pending: set[str] = set()
    eligible_rearms: Counter[str] = Counter()
    used_rearms: Counter[str] = Counter()
    duplicate_slots: list[str] = []
    normalized: list[dict[str, Any]] = []
    initial_comments: list[str] = []
    for event in events:
        kind = str(event.get("kind") or "")
        if kind not in DECISION_KINDS | EXECUTION_KINDS | {"cycle_start"}:
            continue
        row = dict(event)
        comment = str(row.get("comment") or "")
        if kind == "stop_exit" and comment:
            eligible_rearms[comment] += 1
        if kind == "pending_request":
            if comment not in seen_pending:
                row["kind"] = "initial_pending_request"
                if _accepted(row):
                    seen_pending.add(comment)
                    initial_comments.append(comment)
            else:
                row["kind"] = "rearm_request"
                if _accepted(row):
                    if used_rearms[comment] >= eligible_rearms[comment]:
                        duplicate_slots.append(comment)
                    used_rearms[comment] += 1
        if row["kind"] in {
            "cycle_start",
            "basket_trigger",
            "cycle_complete",
            "cycle_restart",
        }:
            row["comment"] = ""
            row["side"] = ""
            row["level"] = 0
        event_price = _price(row)
        if row["kind"] in {
            "initial_pending_request",
            "rearm_request",
            "stop_request",
        }:
            row["requested_price"] = round(
                (event_price - anchor) / step,
                6,
            )
            row["sl"] = (
                round((float(row.get("sl") or 0.0) - anchor) / step, 6)
                if float(row.get("sl") or 0.0)
                else 0.0
            )
        else:
            row["requested_price"] = 0.0
            row["sl"] = 0.0
        row["tp"] = 0.0
        normalized.append(row)
    expected = [
        f"STR {side}{level}"
        for level in range(1, 31)
        for side in ("B", "S")
    ]
    deployment = {
        "count": len(initial_comments),
        "missing_slots": sorted(set(expected) - set(initial_comments)),
        "duplicate_slots": sorted(set(duplicate_slots)),
        "sequence_match": initial_comments == expected,
        "anchor": anchor,
        "step": step,
    }
    return normalized, deployment


def _rounded_signature(event: dict[str, Any]) -> tuple[Any, ...]:
    kind = str(event.get("kind") or "")
    return (
        kind,
        str(event.get("comment") or ""),
        str(event.get("side") or ""),
        int(event.get("level") or 0),
        round(float(event.get("volume") or 0.0), 8),
        round(float(event.get("requested_price") or 0.0), 4),
        round(float(event.get("sl") or 0.0), 4),
        int(_accepted(event)) if kind.endswith("request") else 1,
    )


def compare_independent_cycle_pair(
    target_events: list[dict[str, Any]],
    candidate_events: list[dict[str, Any]],
    *,
    start_tolerance_seconds: float,
    normalized_price_tolerance: float,
) -> dict[str, Any]:
    if start_tolerance_seconds < 0 or normalized_price_tolerance < 0:
        raise ValueError("Tolerances must be non-negative")
    target_cycle_id = str(target_events[0].get("cycle_id") or "")
    candidate_cycle_id = str(candidate_events[0].get("cycle_id") or "")
    target, target_deployment = _normalized_events(target_events)
    candidate, candidate_deployment = _normalized_events(candidate_events)
    deterministic_mismatches: list[dict[str, Any]] = []
    expected_count = 60
    for source, deployment in (
        ("target", target_deployment),
        ("candidate", candidate_deployment),
    ):
        if (
            deployment["count"] != expected_count
            or deployment["missing_slots"]
            or deployment["duplicate_slots"]
            or not deployment["sequence_match"]
        ):
            deterministic_mismatches.append(
                {
                    "category": "deployment_structure",
                    "source": source,
                    **deployment,
                }
            )

    target_decisions = [
        event
        for event in target
        if str(event.get("kind") or "") not in EXECUTION_KINDS
    ]
    candidate_decisions = [
        event
        for event in candidate
        if str(event.get("kind") or "") not in EXECUTION_KINDS
    ]
    target_signatures = [_rounded_signature(event) for event in target_decisions]
    candidate_signatures = [
        _rounded_signature(event) for event in candidate_decisions
    ]
    if len(target_signatures) != len(candidate_signatures):
        deterministic_mismatches.append(
            {
                "category": "decision_sequence",
                "target_count": len(target_signatures),
                "candidate_count": len(candidate_signatures),
            }
        )
    for index, (target_signature, candidate_signature) in enumerate(
        zip(target_signatures, candidate_signatures)
    ):
        structural_target = target_signature[:5] + target_signature[7:]
        structural_candidate = (
            candidate_signature[:5] + candidate_signature[7:]
        )
        price_delta = abs(target_signature[5] - candidate_signature[5])
        sl_delta = abs(target_signature[6] - candidate_signature[6])
        if (
            structural_target != structural_candidate
            or price_delta > normalized_price_tolerance
            or sl_delta > normalized_price_tolerance
        ):
            deterministic_mismatches.append(
                {
                    "category": "normalized_decision",
                    "index": index,
                    "target": target_signature,
                    "candidate": candidate_signature,
                    "normalized_price_delta": price_delta,
                    "normalized_sl_delta": sl_delta,
                }
            )
            break

    target_execution = [
        _rounded_signature(event)
        for event in target
        if str(event.get("kind") or "") in EXECUTION_KINDS
    ]
    candidate_execution = [
        _rounded_signature(event)
        for event in candidate
        if str(event.get("kind") or "") in EXECUTION_KINDS
    ]
    execution_mismatches = []
    if target_execution != candidate_execution:
        execution_mismatches.append(
            {
                "category": "execution_sequence",
                "target": target_execution,
                "candidate": candidate_execution,
            }
        )

    start_delta = abs(
        (
            _parse_time(candidate_events[0]["time_utc"])
            - _parse_time(target_events[0]["time_utc"])
        ).total_seconds()
    )
    if start_delta > start_tolerance_seconds:
        execution_mismatches.append(
            {
                "category": "cycle_start_timing",
                "delta_seconds": start_delta,
            }
        )

    fidelity = score_lifecycle(target, candidate)
    status = "FAIL" if deterministic_mismatches else "PASS"
    return {
        "status": status,
        "logic_status": status,
        "execution_status": (
            "DIFFERENT" if execution_mismatches else "PASS"
        ),
        "target_cycle_id": target_cycle_id,
        "candidate_cycle_id": candidate_cycle_id,
        "cycle_id": f"{target_cycle_id}__{candidate_cycle_id}",
        "deployment": {
            "target_count": target_deployment["count"],
            "candidate_count": candidate_deployment["count"],
            "target_missing_slots": target_deployment["missing_slots"],
            "candidate_missing_slots": candidate_deployment[
                "missing_slots"
            ],
            "target_duplicate_slots": target_deployment[
                "duplicate_slots"
            ],
            "candidate_duplicate_slots": candidate_deployment[
                "duplicate_slots"
            ],
            "target_sequence_match": target_deployment[
                "sequence_match"
            ],
            "candidate_sequence_match": candidate_deployment[
                "sequence_match"
            ],
        },
        "geometry": {
            "target_anchor": target_deployment["anchor"],
            "target_step": target_deployment["step"],
            "candidate_anchor": candidate_deployment["anchor"],
            "candidate_step": candidate_deployment["step"],
        },
        "deterministic_mismatch_count": len(
            deterministic_mismatches
        ),
        "execution_mismatch_count": len(execution_mismatches),
        "deterministic_mismatches": deterministic_mismatches,
        "execution_mismatches": execution_mismatches,
        "fidelity": fidelity,
        "evidence_grade": "BEST_EFFORT",
        "tolerances": {
            "start_seconds": start_tolerance_seconds,
            "normalized_price": normalized_price_tolerance,
        },
    }
```

The implementation must preserve the exact public signatures above. It may split private helpers into smaller functions, but it must not compare absolute target and candidate cycle IDs or absolute anchor prices as deterministic requirements.

- [ ] **Step 4: Implement the comparison CLI**

Create `tools/compare_independent_cycles.py`:

```python
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from straddle_replica.independent_fidelity import (  # noqa: E402
    compare_independent_cycle_pair,
    pair_complete_cycles,
)
from straddle_replica.live_twin import (  # noqa: E402
    load_demo_telemetry_events,
    load_jsonl_events,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-events", required=True, type=Path)
    parser.add_argument("--candidate-telemetry", required=True, type=Path)
    parser.add_argument(
        "--pairing",
        choices=("nearest", "ordinal"),
        required=True,
    )
    parser.add_argument("--max-start-gap-seconds", type=float, default=5.0)
    parser.add_argument(
        "--normalized-price-tolerance",
        type=float,
        default=0.02,
    )
    parser.add_argument("--build-id", required=True)
    parser.add_argument("--certification-started-utc", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)

    target = load_jsonl_events(args.target_events)
    candidate = load_demo_telemetry_events(args.candidate_telemetry)
    pairs = pair_complete_cycles(
        target,
        candidate,
        pairing=args.pairing,
        max_start_gap_seconds=args.max_start_gap_seconds,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    reports = []
    for index, (target_cycle, candidate_cycle) in enumerate(pairs, start=1):
        report = compare_independent_cycle_pair(
            target_cycle,
            candidate_cycle,
            start_tolerance_seconds=args.max_start_gap_seconds,
            normalized_price_tolerance=args.normalized_price_tolerance,
        )
        report.update(
            {
                "pair_index": index,
                "build_id": args.build_id,
                "certification_started_utc": (
                    args.certification_started_utc
                ),
                "generated_utc": datetime.now(
                    tz=timezone.utc
                ).isoformat(),
            }
        )
        safe_id = re.sub(
            r"[^A-Za-z0-9_.-]+",
            "_",
            str(report["cycle_id"]),
        )
        destination = args.output_dir / f"{index:04d}-{safe_id}.json"
        destination.write_text(
            json.dumps(report, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        reports.append(report)
    summary = {
        "pair_count": len(reports),
        "pass_count": sum(report["status"] == "PASS" for report in reports),
        "fail_count": sum(report["status"] == "FAIL" for report in reports),
        "outputs": [
            str(path)
            for path in sorted(args.output_dir.glob("*.json"))
        ],
    }
    print(json.dumps(summary, sort_keys=True))
    if not reports:
        return 2
    return 0 if summary["fail_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run the normalized fidelity tests and verify GREEN**

Run:

```powershell
& $python -m pytest `
  tests\test_independent_fidelity.py `
  tests\test_fidelity_score.py `
  tests\test_live_twin.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Write the Task 5 checkpoint**

Run:

```powershell
$root='artifacts\checkpoints\2026-08-12-independent-demo'
Get-FileHash `
  straddle_replica\independent_fidelity.py,`
  tools\compare_independent_cycles.py `
  -Algorithm SHA256 |
  ConvertTo-Json |
  Set-Content "$root\task-05-comparison.json"
```

## Task 6: Add read-only collectors and a telemetry freshness gate

**Files:**

- Create: `straddle_replica/independent_readiness.py`
- Create: `tools/check_independent_demo_readiness.py`
- Create: `scripts/install_independent_demo_monitor_tasks.ps1`
- Create: `tests/test_independent_readiness.py`
- Extend: `tests/test_independent_demo_deployment.py`

- [ ] **Step 1: Write failing readiness tests**

Create `tests/test_independent_readiness.py`:

```python
from datetime import datetime, timedelta, timezone
import csv
import json
from pathlib import Path

import pytest

from straddle_replica.independent_readiness import (
    evaluate_independent_readiness,
)


UTC = timezone.utc
LOGIN = 5_054_999_999


def write_heartbeat(
    path: Path,
    now: datetime,
    *,
    read_only: bool = True,
    dropped: int = 0,
) -> None:
    path.write_text(
        json.dumps(
            {
                "capture_time_utc": now.isoformat(),
                "healthy": True,
                "stopped": False,
                "read_only_verified": read_only,
                "dropped_transactions": dropped,
            }
        ),
        encoding="utf-8",
    )


def write_manifest(
    path: Path,
    *,
    runtime_mode: str = "0",
    login: int = LOGIN,
) -> None:
    rows = {
        "runtime_mode": runtime_mode,
        "runtime_magic": "901018",
        "runtime_require_demo_account": "1",
        "runtime_expected_account_login": str(login),
        "profile": "4",
        "profile_levels_per_side": "30",
    }
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("key", "value"))
        writer.writerows(rows.items())


def write_telemetry(
    path: Path,
    now: datetime,
    *,
    slots: int = 60,
) -> None:
    fields = (
        "utc_time",
        "cycle_id",
        "kind",
        "comment",
        "retcode",
    )
    rows = [
        {
            "utc_time": now.isoformat(),
            "cycle_id": "candidate-cycle",
            "kind": "cycle_start",
            "comment": "",
            "retcode": "0",
        }
    ]
    comments = [
        f"STR {side}{level}"
        for level in range(1, 31)
        for side in ("B", "S")
    ]
    rows.extend(
        {
            "utc_time": now.isoformat(),
            "cycle_id": "candidate-cycle",
            "kind": "pending_request",
            "comment": comment,
            "retcode": "10008",
        }
        for comment in comments[:slots]
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def paths(tmp_path: Path, now: datetime) -> dict[str, Path]:
    values = {
        "target": tmp_path / "target-heartbeat.json",
        "candidate": tmp_path / "candidate-heartbeat.json",
        "manifest": tmp_path / "candidate-manifest.csv",
        "telemetry": tmp_path / "candidate-telemetry.csv",
    }
    write_heartbeat(values["target"], now)
    write_heartbeat(values["candidate"], now)
    write_manifest(values["manifest"])
    write_telemetry(values["telemetry"], now)
    return values


def evaluate(
    values: dict[str, Path],
    now: datetime,
) -> dict:
    return evaluate_independent_readiness(
        target_heartbeat=values["target"],
        candidate_heartbeat=values["candidate"],
        candidate_manifest=values["manifest"],
        candidate_telemetry=values["telemetry"],
        expected_login=LOGIN,
        max_age_seconds=10.0,
        now=now,
    )


def test_fresh_read_only_normal_mode_candidate_is_ready(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 8, 12, tzinfo=UTC)
    result = evaluate(paths(tmp_path, now), now)

    assert result["ready"] is True
    assert result["failures"] == []
    assert result["accepted_initial_slots"] == 60


@pytest.mark.parametrize(
    ("runtime_mode", "login", "failure"),
    [
        ("1", LOGIN, "manifest_runtime_mode"),
        ("0", LOGIN + 1, "manifest_runtime_expected_account_login"),
    ],
)
def test_manifest_mismatch_blocks_readiness(
    tmp_path: Path,
    runtime_mode: str,
    login: int,
    failure: str,
) -> None:
    now = datetime(2026, 8, 12, tzinfo=UTC)
    values = paths(tmp_path, now)
    write_manifest(
        values["manifest"],
        runtime_mode=runtime_mode,
        login=login,
    )

    result = evaluate(values, now)

    assert result["ready"] is False
    assert failure in result["failures"]


@pytest.mark.parametrize(
    ("read_only", "dropped", "failure"),
    [
        (False, 0, "candidate_read_only_not_verified"),
        (True, 1, "candidate_dropped_transactions"),
    ],
)
def test_candidate_collector_safety_failure_blocks_readiness(
    tmp_path: Path,
    read_only: bool,
    dropped: int,
    failure: str,
) -> None:
    now = datetime(2026, 8, 12, tzinfo=UTC)
    values = paths(tmp_path, now)
    write_heartbeat(
        values["candidate"],
        now,
        read_only=read_only,
        dropped=dropped,
    )

    result = evaluate(values, now)

    assert result["ready"] is False
    assert failure in result["failures"]


def test_stale_target_heartbeat_blocks_readiness(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 8, 12, tzinfo=UTC)
    values = paths(tmp_path, now)
    write_heartbeat(values["target"], now - timedelta(seconds=11))

    result = evaluate(values, now)

    assert result["ready"] is False
    assert "target_heartbeat_stale" in result["failures"]


def test_stale_telemetry_blocks_readiness(tmp_path: Path) -> None:
    now = datetime(2026, 8, 12, tzinfo=UTC)
    values = paths(tmp_path, now)
    write_telemetry(
        values["telemetry"],
        now - timedelta(seconds=11),
    )

    result = evaluate(values, now)

    assert result["ready"] is False
    assert "telemetry_stale" in result["failures"]


def test_incomplete_initial_grid_blocks_readiness(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 8, 12, tzinfo=UTC)
    values = paths(tmp_path, now)
    write_telemetry(values["telemetry"], now, slots=59)

    result = evaluate(values, now)

    assert result["ready"] is False
    assert "telemetry_initial_slots_incomplete" in result["failures"]
```

- [ ] **Step 2: Run readiness tests and verify RED**

Run:

```powershell
& $python -m pytest tests\test_independent_readiness.py -q
```

Expected: import failure because the readiness module does not exist.

- [ ] **Step 3: Implement the readiness evaluator**

Create `straddle_replica/independent_readiness.py` with:

```python
from __future__ import annotations

import csv
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


UTC = timezone.utc


def _parse_time(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _manifest(path: Path) -> dict[str, str]:
    with path.open(encoding="utf-8", newline="") as handle:
        return {
            str(row["key"]): str(row["value"])
            for row in csv.DictReader(handle)
        }


def _heartbeat(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate_independent_readiness(
    *,
    target_heartbeat: Path,
    candidate_heartbeat: Path,
    candidate_manifest: Path,
    candidate_telemetry: Path,
    expected_login: int,
    max_age_seconds: float,
    now: datetime | None = None,
) -> dict[str, Any]:
    if expected_login <= 0 or max_age_seconds <= 0:
        raise ValueError("Expected login and max age must be positive")
    current = (now or datetime.now(tz=UTC)).astimezone(UTC)
    failures: list[str] = []
    for name, path in (
        ("target", target_heartbeat),
        ("candidate", candidate_heartbeat),
    ):
        payload = _heartbeat(path)
        captured = _parse_time(payload["capture_time_utc"])
        age = (current - captured).total_seconds()
        if age < -1 or age > max_age_seconds:
            failures.append(f"{name}_heartbeat_stale")
        if not payload.get("healthy"):
            failures.append(f"{name}_heartbeat_unhealthy")
        if payload.get("stopped"):
            failures.append(f"{name}_collector_stopped")
        if not payload.get("read_only_verified"):
            failures.append(f"{name}_read_only_not_verified")
        if int(payload.get("dropped_transactions") or 0) != 0:
            failures.append(f"{name}_dropped_transactions")

    manifest = _manifest(candidate_manifest)
    required = {
        "runtime_mode": "0",
        "runtime_magic": "901018",
        "runtime_require_demo_account": "1",
        "runtime_expected_account_login": str(expected_login),
        "profile": "4",
        "profile_levels_per_side": "30",
    }
    for key, expected in required.items():
        if manifest.get(key) != expected:
            failures.append(f"manifest_{key}")

    with candidate_telemetry.open(
        encoding="utf-8",
        errors="ignore",
        newline="",
    ) as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        failures.append("telemetry_empty")
        telemetry_age = None
        accepted_slots = []
    else:
        latest = max(
            _parse_time(row.get("utc_time") or row.get("time"))
            for row in rows
            if row.get("utc_time") or row.get("time")
        )
        telemetry_age = (current - latest).total_seconds()
        if telemetry_age < -1 or telemetry_age > max_age_seconds:
            failures.append("telemetry_stale")
        accepted_slots = [
            str(row.get("comment") or "")
            for row in rows
            if row.get("kind") == "pending_request"
            and int(row.get("retcode") or 0) in {0, 10008, 10009, 10010}
        ]
        if not any(row.get("kind") == "cycle_start" for row in rows):
            failures.append("telemetry_cycle_start_missing")
        if len(set(accepted_slots)) < 60:
            failures.append("telemetry_initial_slots_incomplete")

    return {
        "ready": not failures,
        "failures": sorted(set(failures)),
        "expected_login": expected_login,
        "telemetry_age_seconds": telemetry_age,
        "accepted_initial_slots": len(set(accepted_slots)),
    }
```

- [ ] **Step 4: Implement the readiness CLI**

Create `tools/check_independent_demo_readiness.py`:

```python
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from straddle_replica.independent_readiness import (  # noqa: E402
    evaluate_independent_readiness,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-heartbeat", required=True, type=Path)
    parser.add_argument("--candidate-heartbeat", required=True, type=Path)
    parser.add_argument("--candidate-manifest", required=True, type=Path)
    parser.add_argument("--candidate-telemetry", required=True, type=Path)
    parser.add_argument("--expected-login", required=True, type=int)
    parser.add_argument("--max-age-seconds", type=float, default=10.0)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    result = evaluate_independent_readiness(
        target_heartbeat=args.target_heartbeat,
        candidate_heartbeat=args.candidate_heartbeat,
        candidate_manifest=args.candidate_manifest,
        candidate_telemetry=args.candidate_telemetry,
        expected_login=args.expected_login,
        max_age_seconds=args.max_age_seconds,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Implement three isolated scheduled tasks**

Create `scripts/install_independent_demo_monitor_tasks.ps1`:

```powershell
param(
    [Parameter(Mandatory = $true)]
    [long]$CandidateLogin,
    [Parameter(Mandatory = $true)]
    [string]$CandidateServer,
    [string]$Workspace = "",
    [string]$PythonPath = "",
    [string]$TargetTerminal = "D:\MT5ObserverTerminal\terminal64.exe",
    [string]$CandidateTerminal = "D:\MT5IndependentCandidateObserver\terminal64.exe",
    [string]$TargetOutput = "D:\MT5ObserverData\isolated-live",
    [string]$CandidateOutput = "D:\MT5IndependentCandidateData\isolated-live"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($CandidateLogin -le 0) {
    throw "CandidateLogin must be positive."
}
if ([string]::IsNullOrWhiteSpace($CandidateServer)) {
    throw "CandidateServer is required."
}
if ([string]::IsNullOrWhiteSpace($Workspace)) {
    $Workspace = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}
if ([string]::IsNullOrWhiteSpace($PythonPath)) {
    $PythonPath = (
        "$env:USERPROFILE\.cache\codex-runtimes\" +
        "codex-primary-runtime\dependencies\python\python.exe"
    )
}
if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
    throw "Python runtime was not found: $PythonPath"
}
$archiveTool = Join-Path $Workspace "tools\archive_independent_target.py"
foreach ($required in @(
    $PythonPath,
    $TargetTerminal,
    $CandidateTerminal,
    $archiveTool
)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Required monitoring file was not found: $required"
    }
}

$existingOwners = Get-CimInstance Win32_Process |
    Where-Object {
        $_.Name -eq "python.exe" -and
        (
            $_.CommandLine -like "*$TargetTerminal*" -or
            $_.CommandLine -like "*$CandidateTerminal*"
        )
    }
if ($existingOwners) {
    throw "A collector already owns a selected terminal."
}

$targetTaskName = "StraddleIndependentTargetCollector"
$candidateTaskName = "StraddleIndependentCandidateCollector"
$archiveTaskName = "StraddleIndependentTargetArchive"
$runtimeRoot = Join-Path (
    $Workspace
) "artifacts\live\independent-demo-fidelity"
New-Item -ItemType Directory -Force -Path `
    $runtimeRoot, `
    $TargetOutput, `
    $CandidateOutput | Out-Null

$targetArguments = @(
    "-m", "straddle_replica.monitor_cli", "monitor-live",
    "--terminal", ('"' + $TargetTerminal + '"'),
    "--output", ('"' + $TargetOutput + '"'),
    "--account", "901018",
    "--server", '"AchieverGlobalMarkets-Server"',
    "--symbol", "XAUUSD",
    "--poll-ms", "50",
    "--checkpoint-seconds", "30",
    "--exit-on-connection-error",
    "--require-read-only"
) -join " "

$candidateArguments = @(
    "-m", "straddle_replica.monitor_cli", "monitor-live",
    "--terminal", ('"' + $CandidateTerminal + '"'),
    "--output", ('"' + $CandidateOutput + '"'),
    "--account", [string]$CandidateLogin,
    "--server", ('"' + $CandidateServer + '"'),
    "--symbol", "XAUUSD",
    "--poll-ms", "50",
    "--checkpoint-seconds", "30",
    "--exit-on-connection-error",
    "--require-read-only"
) -join " "

$archiveArguments = @(
    '"tools\archive_independent_target.py"',
    "--observer-root", ('"' + $TargetOutput + '"'),
    "--observer-state",
    ('"' + (Join-Path $runtimeRoot "observer-state.json") + '"'),
    "--archive-state",
    ('"' + (Join-Path $runtimeRoot "archive-state.json") + '"'),
    "--archive",
    ('"' + (Join-Path $runtimeRoot "target-cycles.jsonl") + '"'),
    "--health",
    ('"' + (Join-Path $runtimeRoot "archive-health.json") + '"'),
    "--poll-ms", "100"
) -join " "

$settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable
$principal = New-ScheduledTaskPrincipal `
    -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -LogonType Interactive `
    -RunLevel Limited
$targetAction = New-ScheduledTaskAction `
    -Execute $PythonPath `
    -Argument $targetArguments `
    -WorkingDirectory $Workspace
$candidateAction = New-ScheduledTaskAction `
    -Execute $PythonPath `
    -Argument $candidateArguments `
    -WorkingDirectory $Workspace
$archiveAction = New-ScheduledTaskAction `
    -Execute $PythonPath `
    -Argument $archiveArguments `
    -WorkingDirectory $Workspace

Register-ScheduledTask `
    -TaskName $targetTaskName `
    -Action $targetAction `
    -Settings $settings `
    -Principal $principal `
    -Description "Independent fidelity target read-only collector." `
    -Force | Out-Null
Register-ScheduledTask `
    -TaskName $candidateTaskName `
    -Action $candidateAction `
    -Settings $settings `
    -Principal $principal `
    -Description "Independent fidelity candidate read-only collector." `
    -Force | Out-Null
Register-ScheduledTask `
    -TaskName $archiveTaskName `
    -Action $archiveAction `
    -Settings $settings `
    -Principal $principal `
    -Description "Independent fidelity target cycle archive." `
    -Force | Out-Null

function Wait-ForReadOnlySession {
    param(
        [Parameter(Mandatory = $true)]
        [string]$OutputRoot,
        [Parameter(Mandatory = $true)]
        [long]$ExpectedLogin,
        [Parameter(Mandatory = $true)]
        [string]$ExpectedServer,
        [Parameter(Mandatory = $true)]
        [DateTime]$Deadline
    )
    do {
        $pointerPath = Join-Path $OutputRoot "current-session.json"
        if (Test-Path -LiteralPath $pointerPath -PathType Leaf) {
            try {
                $pointer = Get-Content -LiteralPath $pointerPath -Raw |
                    ConvertFrom-Json
                $session = if ($pointer.session_dir) {
                    [string]$pointer.session_dir
                }
                else {
                    Join-Path $OutputRoot ([string]$pointer.session_id)
                }
                $heartbeatPath = Join-Path $session "heartbeat.json"
                $manifestPath = Join-Path $session "manifest.json"
                if (
                    (Test-Path -LiteralPath $heartbeatPath -PathType Leaf) -and
                    (Test-Path -LiteralPath $manifestPath -PathType Leaf)
                ) {
                    $heartbeat = Get-Content `
                        -LiteralPath $heartbeatPath `
                        -Raw |
                        ConvertFrom-Json
                    $manifest = Get-Content `
                        -LiteralPath $manifestPath `
                        -Raw |
                        ConvertFrom-Json
                    $captured = [DateTimeOffset]::Parse(
                        [string]$heartbeat.capture_time_utc
                    ).UtcDateTime
                    $age = ([DateTime]::UtcNow - $captured).TotalSeconds
                    if (
                        $age -ge -1 -and
                        $age -le 5 -and
                        $heartbeat.healthy -eq $true -and
                        $heartbeat.stopped -ne $true -and
                        $heartbeat.read_only_verified -eq $true -and
                        [int]($heartbeat.dropped_transactions) -eq 0 -and
                        [long]$manifest.account.login -eq $ExpectedLogin -and
                        [string]$manifest.account.server -eq $ExpectedServer -and
                        $manifest.account.trade_allowed -eq $false -and
                        $manifest.terminal.trade_allowed -eq $false
                    ) {
                        return
                    }
                }
            }
            catch {
                # Files may be replaced atomically while being read.
            }
        }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $Deadline)
    throw "A fresh read-only collector session was not observed."
}

Start-ScheduledTask -TaskName $targetTaskName
Wait-ForReadOnlySession `
    -OutputRoot $TargetOutput `
    -ExpectedLogin 901018 `
    -ExpectedServer "AchieverGlobalMarkets-Server" `
    -Deadline ([DateTime]::UtcNow.AddSeconds(120))

Start-ScheduledTask -TaskName $candidateTaskName
Wait-ForReadOnlySession `
    -OutputRoot $CandidateOutput `
    -ExpectedLogin $CandidateLogin `
    -ExpectedServer $CandidateServer `
    -Deadline ([DateTime]::UtcNow.AddSeconds(120))

Start-ScheduledTask -TaskName $archiveTaskName
Write-Host "Started $targetTaskName"
Write-Host "Started $candidateTaskName"
Write-Host "Started $archiveTaskName"
```

- [ ] **Step 6: Extend the deployment contract for read-only tasks**

Append to `tests/test_independent_demo_deployment.py`:

```python
MONITOR = ROOT / "scripts" / "install_independent_demo_monitor_tasks.ps1"


def test_independent_monitors_are_read_only_and_command_free() -> None:
    source = MONITOR.read_text(encoding="utf-8")

    assert "StraddleIndependentTargetCollector" in source
    assert "StraddleIndependentCandidateCollector" in source
    assert "StraddleIndependentTargetArchive" in source
    assert source.count("--require-read-only") == 2
    assert "archive_independent_target.py" in source
    assert "run_shadow_coordinator.py" not in source
    assert "command.csv" not in source
    assert "ack.csv" not in source
    assert "--active" not in source
    assert "docker" not in source.lower()
    assert "ssh" not in source.lower()
```

- [ ] **Step 7: Run readiness and monitoring contract tests**

Run:

```powershell
& $python -m pytest `
  tests\test_independent_readiness.py `
  tests\test_independent_demo_deployment.py -q
```

Expected: all tests pass.

- [ ] **Step 8: Write the Task 6 checkpoint**

Run:

```powershell
$root='artifacts\checkpoints\2026-08-12-independent-demo'
Get-FileHash `
  straddle_replica\independent_readiness.py,`
  tools\check_independent_demo_readiness.py,`
  scripts\install_independent_demo_monitor_tasks.ps1 `
  -Algorithm SHA256 |
  ConvertTo-Json |
  Set-Content "$root\task-06-readiness.json"
```

## Task 7: Create the new demo account and commission the isolated VPS terminal

**Files and state created during operation:**

- Temporary protected credential file:
  `artifacts/private/independent-demo-credentials.json`
- Package:
  `artifacts/StraddleReplica-INDEPENDENT-DEMO.zip`
- Remote root:
  `/opt/straddle-fidelity-independent-demo`
- Local investor terminal:
  `D:\MT5IndependentCandidateObserver`
- Runtime evidence:
  `artifacts/live/independent-demo-fidelity/`

- [ ] **Step 1: Confirm protected runtime state before account creation**

Run read-only checks:

```powershell
ssh nishahomes-vps `
  "docker inspect --format '{{.Name}}|{{.Id}}|{{.State.Status}}|{{.RestartCount}}|{{.State.OOMKilled}}' straddle-fidelity-candidate-demo straddle-replica-demo-vps"
Get-ScheduledTask |
  Where-Object TaskName -like 'Straddle*' |
  Select-Object TaskName,State
```

Save the two protected container fingerprints:

```powershell
$root='artifacts\checkpoints\2026-08-12-independent-demo'
ssh nishahomes-vps `
  "docker inspect --format '{{.Name}}|{{.Id}}|{{.State.Status}}|{{.RestartCount}}|{{.State.OOMKilled}}' straddle-fidelity-candidate-demo straddle-replica-demo-vps" |
  Set-Content "$root\pre-deployment-protected-containers.txt"
```

- [ ] **Step 2: Attempt AchieverGlobalMarkets demo registration**

Use a dedicated MT5 registration terminal, not the target observer terminal and not either existing VPS terminal.

In MT5:

1. Open `File -> Open an Account`.
2. Search for `AchieverGlobalMarkets`.
3. Select an Achiever demo server if the broker presents one.
4. Create a new personal demo account using the already approved registration identity.
5. Select:
   - account currency `USD`;
   - hedging mode;
   - leverage `1:1000` if offered, matching the target manifest;
   - initial deposit `100000 USD`.
6. Record the generated login, exact server, master password, and investor password.
7. Do not reuse `901018`, `5054216668`, or `5054283907`.

Achiever is considered unavailable only if the MT5 account wizard does not offer a demo server/account after a fresh broker search. A login error is not sufficient reason to skip Achiever.

- [ ] **Step 3: Use MetaQuotes-Demo only if Achiever registration is unavailable**

If Step 2 proves Achiever demo unavailable:

1. select `MetaQuotes-Demo`;
2. create a new USD hedging demo;
3. choose the highest available leverage;
4. choose an initial deposit of `100000 USD`;
5. record the generated login, exact server, master password, and investor password.

Set the comparison pairing later to:

```text
ordinal
```

Do not claim execution-price or profit parity against Achiever when MetaQuotes is used.

- [ ] **Step 4: Protect the generated credentials without printing passwords**

Capture the non-secret account identifiers in the current PowerShell session:

```powershell
$newDemoLogin=[long](Read-Host 'New demo login')
$newDemoServer=Read-Host 'Exact demo server'
```

Run interactively:

```powershell
& .\scripts\protect_independent_demo_credentials.ps1 `
  -Login $newDemoLogin `
  -Server $newDemoServer
```

Enter master and investor passwords only into the two secure prompts.

Verify:

```powershell
$credentialPath='artifacts\private\independent-demo-credentials.json'
Get-Acl $credentialPath |
  Select-Object Owner,AccessToString
```

Expected: only the current Windows identity has access. Do not display the JSON file.

- [ ] **Step 5: Package the bound EA**

Run:

```powershell
& .\scripts\package_independent_demo.ps1 `
  -ExpectedDemoLogin $newDemoLogin `
  -Mt5InstallerPath `
    '.\artifacts\downloads\mt5setup-official.exe'
```

Inspect ZIP names without extracting credentials:

```powershell
$zipAudit=@'
import zipfile
from pathlib import Path

path = Path("artifacts/StraddleReplica-INDEPENDENT-DEMO.zip")
with zipfile.ZipFile(path) as archive:
    names = archive.namelist()
assert not any(name.lower().endswith((".mq5", ".mqh")) for name in names)
assert not any(
    token in name.lower()
    for name in names
    for token in ("password", "credential", "secret")
)
print("\n".join(names))
'@
$zipAudit | & $python -
```

- [ ] **Step 6: Deploy only the new commissioning container**

Run:

```powershell
& .\scripts\deploy_independent_demo_vps.ps1 `
  -SshAlias nishahomes-vps `
  -PackagePath .\artifacts\StraddleReplica-INDEPENDENT-DEMO.zip
```

Expected:

- new container is running with zero restarts and no OOM;
- VNC is bound only to `127.0.0.1:15925`;
- `MT5_START=0`;
- both protected container fingerprints are unchanged.

- [ ] **Step 7: Install and log into MT5 through the isolated VNC**

Open an SSH tunnel:

```powershell
ssh -N -L 15925:127.0.0.1:15925 nishahomes-vps
```

Connect the local VNC viewer to:

```text
127.0.0.1:15925
```

Inside the new container only:

1. run `Z:\data\candidate\mt5-installer.exe`;
2. install into `Z:\data\terminal`;
3. open the terminal in portable mode;
4. log into the new demo using the master password;
5. enable password saving;
6. verify the exact login and server;
7. verify account trade mode is demo;
8. verify margin mode is hedging;
9. verify XAUUSD exists;
10. verify the account supports at least 60 pending orders and at least 4.40 gross lots;
11. close the commissioning terminal cleanly.

Do not open or interact with another container.

- [ ] **Step 8: Prepare a separate local investor terminal**

Create it from an installed MT5 binary:

```powershell
& .\scripts\create_monitor_terminal.ps1 `
  -SourceTerminalPath 'C:\Program Files\MetaTrader 5\terminal64.exe' `
  -TargetRoot 'D:\MT5IndependentCandidateObserver'
```

Launch:

```powershell
Start-Process `
  'D:\MT5IndependentCandidateObserver\terminal64.exe' `
  -ArgumentList '/portable'
```

Log into the new demo using only the investor password. Verify manually that trade buttons and Algo Trading remain unavailable for the account.

- [ ] **Step 9: Start the read-only collectors and target archive**

Run:

```powershell
& .\scripts\install_independent_demo_monitor_tasks.ps1 `
  -CandidateLogin $newDemoLogin `
  -CandidateServer $newDemoServer
```

Verify both collector heartbeats contain:

```text
healthy=true
stopped=false
read_only_verified=true
dropped_transactions=0
```

The target heartbeat must also show:

```text
login=901018
server=AchieverGlobalMarkets-Server
```

- [ ] **Step 10: Start the EA once at a clean target cycle boundary**

Keep the new container in commissioning mode while the target is in an existing active cycle.

When the target target-cycle archive reports a clean `cycle_complete`:

1. switch only the new project to the trading startup;
2. recreate only `straddle-fidelity-independent-demo`;
3. do not copy the target anchor, step, orders, or positions.

Run:

```powershell
& .\scripts\deploy_independent_demo_vps.ps1 `
  -SshAlias nishahomes-vps `
  -PackagePath .\artifacts\StraddleReplica-INDEPENDENT-DEMO.zip `
  -StartTrading
```

This one-time synchronized start is allowed because it only aligns observation windows. It does not transmit target trade decisions or prices.

- [ ] **Step 11: Fetch candidate telemetry and manifest read-only**

Run:

```powershell
$runtime='artifacts\live\independent-demo-fidelity'
New-Item -ItemType Directory -Force $runtime | Out-Null
$common='/opt/straddle-fidelity-independent-demo/wineprefix/drive_c/users/mt5/AppData/Roaming/MetaQuotes/Terminal/Common/Files'
scp `
  "nishahomes-vps:$common/StraddleReplicaV2_901018_XAUUSD.csv" `
  "$runtime\candidate-telemetry.csv.tmp"
Move-Item `
  "$runtime\candidate-telemetry.csv.tmp" `
  "$runtime\candidate-telemetry.csv" `
  -Force
scp `
  "nishahomes-vps:$common/StraddleReplicaV2_901018_XAUUSD_manifest.csv" `
  "$runtime\candidate-manifest.csv.tmp"
Move-Item `
  "$runtime\candidate-manifest.csv.tmp" `
  "$runtime\candidate-manifest.csv" `
  -Force
```

- [ ] **Step 12: Require readiness before any fidelity claim**

Resolve current target and candidate heartbeat paths, then run:

```powershell
& $python tools\check_independent_demo_readiness.py `
  --target-heartbeat $targetHeartbeat `
  --candidate-heartbeat $candidateHeartbeat `
  --candidate-manifest artifacts\live\independent-demo-fidelity\candidate-manifest.csv `
  --candidate-telemetry artifacts\live\independent-demo-fidelity\candidate-telemetry.csv `
  --expected-login $newDemoLogin `
  --max-age-seconds 10 `
  --output artifacts\live\independent-demo-fidelity\readiness.json
```

Expected:

```json
{
  "ready": true,
  "failures": [],
  "accepted_initial_slots": 60
}
```

If readiness is false, do not report that the EA is working correctly.

- [ ] **Step 13: Remove temporary credential artifacts after successful commissioning**

After:

- VPS master login is saved;
- local investor login is verified read-only;
- investor login/server/password have been handed to the user;

remove the temporary protected file:

```powershell
$path=Resolve-Path `
  'artifacts\private\independent-demo-credentials.json'
$privateRoot=[System.IO.Path]::GetFullPath(
  'artifacts\private'
).TrimEnd('\') + '\'
if (-not $path.Path.StartsWith(
  $privateRoot,
  [System.StringComparison]::OrdinalIgnoreCase
)) {
  throw 'Credential cleanup path is outside artifacts\private.'
}
Remove-Item -LiteralPath $path.Path -Force
```

Verify no credential file was uploaded:

```powershell
ssh nishahomes-vps `
  "find /opt/straddle-fidelity-independent-demo -type f \( -iname '*password*' -o -iname '*credential*' -o -iname '*secret*' \) -print"
```

Expected: no output.

## Task 8: Run the iterative full-cycle fidelity loop

**Files and evidence:**

- Target archive:
  `artifacts/live/independent-demo-fidelity/target-cycles.jsonl`
- Candidate telemetry:
  `artifacts/live/independent-demo-fidelity/candidate-telemetry.csv`
- Per-cycle reports:
  `artifacts/analysis/independent-demo-fidelity/cycles/`
- Summary:
  `artifacts/analysis/independent-demo-fidelity/latest/`
- Modify after measurement: `docs/FIDELITY.md`

- [ ] **Step 1: Run the full focused regression suite**

Run:

```powershell
& $python -m pytest `
  tests\test_independent_demo_contract.py `
  tests\test_independent_demo_deployment.py `
  tests\test_independent_demo_credentials.py `
  tests\test_observer_adapter.py `
  tests\test_independent_cycle_archive.py `
  tests\test_independent_fidelity.py `
  tests\test_independent_readiness.py `
  tests\test_fidelity_score.py `
  tests\test_live_twin.py `
  tests\test_mql5_contract.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Build and fingerprint the exact candidate**

Run:

```powershell
& .\scripts\build.ps1
$buildId=(
  Get-FileHash .\mql5\StraddleReplica.ex5 -Algorithm SHA256
).Hash.ToLowerInvariant()
$runStart=(Get-Date).ToUniversalTime().ToString('o')
@{
  build_id=$buildId
  certification_started_utc=$runStart
  candidate_login=$newDemoLogin
  candidate_server=$newDemoServer
} |
  ConvertTo-Json |
  Set-Content `
    artifacts\live\independent-demo-fidelity\qualification-state.json
```

- [ ] **Step 3: Compare each complete independent cycle**

For an Achiever demo:

```powershell
$pairing='nearest'
$maxGap=5
```

For MetaQuotes-Demo:

```powershell
$pairing='ordinal'
$maxGap=86400
```

Run:

```powershell
& $python tools\compare_independent_cycles.py `
  --target-events artifacts\live\independent-demo-fidelity\target-cycles.jsonl `
  --candidate-telemetry artifacts\live\independent-demo-fidelity\candidate-telemetry.csv `
  --pairing $pairing `
  --max-start-gap-seconds $maxGap `
  --normalized-price-tolerance 0.02 `
  --build-id $buildId `
  --certification-started-utc $runStart `
  --output-dir artifacts\analysis\independent-demo-fidelity\cycles
```

- [ ] **Step 4: Build the fidelity report**

Run:

```powershell
& $python tools\build_fidelity_report.py `
  --comparisons-dir artifacts\analysis\independent-demo-fidelity\cycles `
  --output-dir artifacts\analysis\independent-demo-fidelity\latest
```

The report must list:

- strict lifecycle fidelity;
- conditional logic fidelity;
- coverage;
- deployment slot matches;
- stop-transition matches;
- rearm matches;
- basket close and restart matches;
- execution differences;
- evidence grade;
- earliest deterministic mismatch.

- [ ] **Step 5: Fix only proven deterministic mismatches**

For each failed cycle:

1. select the earliest deterministic mismatch from `mismatch-register.json`;
2. add one failing test reproducing that mismatch;
3. run the test and verify RED;
4. make the smallest source correction;
5. run the focused test and verify GREEN;
6. run the full Task 8 Step 1 regression suite;
7. compile a new EX5;
8. package it with the same new demo login;
9. redeploy only `straddle-fidelity-independent-demo`:

   ```powershell
   & .\scripts\deploy_independent_demo_vps.ps1 `
     -SshAlias nishahomes-vps `
     -PackagePath .\artifacts\StraddleReplica-INDEPENDENT-DEMO.zip `
     -StartTrading
   ```

10. reset `qualification-state.json` with the new EX5 SHA-256 and UTC start.

Never tune the EA from profit alone. A source change requires paired lifecycle evidence.

- [ ] **Step 6: Apply the initial deterministic parity gate**

The first valid “100% deterministic parity” statement requires one complete paired cycle where:

- both cycles are complete;
- both deploy exactly 60 unique levels;
- comments, side, level, lot, and normalized grid geometry match;
- deterministic request sequence matches;
- every observed stop transition matches;
- rearm decisions match;
- basket trigger/cancel/close sequence matches;
- cycle restart decision matches;
- strict lifecycle fidelity is `100.0`;
- deterministic mismatch count is zero;
- target and candidate collectors remain read-only and gap-free.

This is a logic statement only. It is not a guarantee of identical entry price, exit price, or profit.

- [ ] **Step 7: Apply the real-account-readiness qualification gate**

Before recommending the EA for any real account, require the same unmodified build to record:

- 20 consecutive complete paired cycles;
- 48 market-open hours;
- zero deterministic mismatches;
- zero missing or duplicate level identities;
- zero target or candidate dropped transactions;
- zero observer sequence gaps or session restarts;
- fresh candidate telemetry and manifest;
- documented maximum gross lots and floating drawdown.

Use `tools/evaluate_live_twin_gate.py` with the independent cycle reports and target observer health. Because target request evidence is investor-inferred, the highest valid evidence grade remains `BEST_EFFORT_PASS`, even when measured deterministic fidelity is 100%.

- [ ] **Step 8: Update measured documentation**

Generate the documentation block directly from measured JSON:

```powershell
$summary=Get-Content `
  'artifacts\analysis\independent-demo-fidelity\latest\fidelity-summary.json' `
  -Raw |
  ConvertFrom-Json
$reports=Get-ChildItem `
  'artifacts\analysis\independent-demo-fidelity\cycles' `
  -Filter '*.json' |
  Sort-Object Name |
  ForEach-Object {
    Get-Content $_.FullName -Raw | ConvertFrom-Json
  }
$deterministicMismatchCount=(
  $reports |
  Measure-Object -Property deterministic_mismatch_count -Sum
).Sum
$executionMismatchCount=(
  $reports |
  Measure-Object -Property execution_mismatch_count -Sum
).Sum
$evidenceGrades=(
  $reports.evidence_grade |
  Sort-Object -Unique
) -join ', '
$strict=$summary.strict_lifecycle_fidelity_percent.mean
$conditional=$summary.conditional_logic_fidelity_percent.mean
$coverage=$summary.conditional_logic_fidelity_percent.minimum_coverage
$brokerPairing=if (
  $newDemoServer -like '*Achiever*'
) {
  'Achiever-to-Achiever'
}
else {
  'Achiever-to-MetaQuotes'
}
$block=@"
## Independent demo validation — August 2026

- Candidate account: $newDemoLogin
- Candidate server: $newDemoServer
- Runtime mode: NORMAL (0)
- Broker pairing: $brokerPairing
- Complete paired cycles: $($summary.comparison_count)
- Strict lifecycle fidelity: $strict%
- Conditional logic fidelity: $conditional%
- Conditional coverage: $coverage%
- Deterministic mismatches: $deterministicMismatchCount
- Execution differences: $executionMismatchCount
- Evidence grade: $evidenceGrades

Exact broker profit is not claimed unless comments, side, lot, entry,
exit, commission, swap, and timing are all paired.
"@
Add-Content -LiteralPath 'docs\FIDELITY.md' -Value $block
```

Maximum gross lots and floating drawdown remain in the machine-readable
telemetry/report artifacts until dedicated measured fields exist; do not invent
those values in prose.

- [ ] **Step 9: Write the final checkpoint**

Run:

```powershell
$root='artifacts\checkpoints\2026-08-12-independent-demo'
Get-FileHash `
  mql5\StraddleReplica.ex5,`
  profiles\latest_30_independent_demo.set,`
  artifacts\analysis\independent-demo-fidelity\latest\fidelity-summary.json,`
  artifacts\analysis\independent-demo-fidelity\latest\mismatch-register.json `
  -Algorithm SHA256 |
  ConvertTo-Json |
  Set-Content "$root\final-independent-demo.json"
```

## Final handoff

Return to the user:

- new demo login;
- exact server;
- investor/read-only password;
- container name `straddle-fidelity-independent-demo`;
- current measured deterministic fidelity percentage;
- number of complete paired cycles;
- whether the account used Achiever or MetaQuotes fallback;
- a concise list of any remaining deterministic mismatch;
- a separate list of broker execution/profit differences.

Never return:

- master password;
- protected credential file;
- MT5 saved-login files;
- VPS password;
- another account's credentials.
