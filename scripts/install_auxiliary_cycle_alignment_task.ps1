param(
    [string]$Workspace = "",
    [string]$PythonPath = "",
    [string]$ControllerPath = "",
    [string]$TaskName = "StraddleAuxiliaryCycleAlignment",
    [string]$CandidateTelemetry = "",
    [string]$CandidateCycleId = "",
    [string]$TargetEvents = "",
    [string]$TerminalPath = "",
    [string]$StartupConfig = "",
    [string]$PresetPath = "",
    [long]$ExpectedDemoLogin = 901111,
    [string]$ActiveEx5Path = "",
    [string]$ExpectedActiveEx5Sha256 = "",
    [string]$StagedEx5Path = "",
    [string]$ExpectedStagedEx5Sha256 = "",
    [string]$StagedPackagePath = "",
    [string]$ExpectedStagedPackageSha256 = "",
    [string]$QualificationState = "",
    [string]$AlignmentHoldPath = "",
    [string]$HealthPath = "",
    [double]$PollSeconds = 0.25,
    [double]$RaceGuardSeconds = 0.35,
    [double]$StartupLeadSeconds = 3.8,
    [double]$StartObservationSeconds = 240.0,
    [double]$StartToleranceSeconds = 2.0,
    [switch]$Apply,
    [string]$FlatProofPath = "",
    [int]$FlatProofMaxAgeSeconds = 30
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($Workspace)) {
    $Workspace = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}
$Workspace = [System.IO.Path]::GetFullPath($Workspace)
if ([string]::IsNullOrWhiteSpace($PythonPath)) {
    $PythonPath = (Get-Command python.exe -ErrorAction Stop).Source
}
if ([string]::IsNullOrWhiteSpace($ControllerPath)) {
    $ControllerPath = Join-Path `
        $Workspace `
        "tools\align_local_auxiliary_cycle.py"
}

function Resolve-RequiredFile {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Label
    )

    if ([string]::IsNullOrWhiteSpace($Path)) {
        throw "$Label is required."
    }
    $full = [System.IO.Path]::GetFullPath($Path)
    if (-not (Test-Path -LiteralPath $full -PathType Leaf)) {
        throw "$Label was not found: $full"
    }
    return $full
}

function Assert-Sha256 {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Expected,
        [Parameter(Mandatory = $true)][string]$Label
    )

    $normalized = $Expected.Trim().ToUpperInvariant()
    if ($normalized -notmatch "^[0-9A-F]{64}$") {
        throw "$Label expected SHA256 must contain 64 hexadecimal characters."
    }
    $actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
    if ($actual -ne $normalized) {
        throw "$Label SHA256 mismatch. Expected=$normalized Actual=$actual"
    }
    return $actual
}

function Quote-TaskArgument {
    param([Parameter(Mandatory = $true)][string]$Value)
    return '"' + $Value.Replace('"', '\"') + '"'
}

function Assert-BoundDemoPreset {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][long]$ExpectedLogin
    )

    $content = Get-Content -LiteralPath $Path -Raw
    foreach ($required in @(
        "RequireDemoAccount=true",
        "RequireBoundAccount=true",
        "ExpectedAccountLogin=$ExpectedLogin"
    )) {
        if ($content -notmatch (
            "(?m)^" + [regex]::Escape($required) + "\s*$"
        )) {
            throw "Preset is missing required binding: $required"
        }
    }
}

function Assert-IndependentFlatProof {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][long]$ExpectedLogin,
        [Parameter(Mandatory = $true)][int]$MaximumAgeSeconds
    )

    $proofPath = Resolve-RequiredFile $Path "Independent flat proof"
    $proof = Get-Content -LiteralPath $proofPath -Raw | ConvertFrom-Json
    $sync = $proof.read_only_broker_sync
    if (
        $null -eq $proof.account -or
        [long]$proof.account.login -ne $ExpectedLogin -or
        $null -eq $sync -or
        -not (
            $sync.PSObject.Properties.Name -contains "positions_total"
        ) -or
        -not (
            $sync.PSObject.Properties.Name -contains "orders_total"
        ) -or
        $sync.flat -ne $true -or
        [int]$sync.positions_total -ne 0 -or
        [int]$sync.orders_total -ne 0
    ) {
        throw (
            "Independent flat proof must show the expected login with " +
            "zero positions and zero orders."
        )
    }
    if (
        $sync.PSObject.Properties.Name -contains
            "start_config_experts_enabled" -and
        $sync.start_config_experts_enabled -ne $false
    ) {
        throw "Independent flat proof source had Experts enabled."
    }
    if (
        $sync.PSObject.Properties.Name -contains
            "start_config_allow_live_trading" -and
        $sync.start_config_allow_live_trading -ne $false
    ) {
        throw "Independent flat proof source allowed live trading."
    }
    if (
        -not (
            $sync.PSObject.Properties.Name -contains
                "terminal_trade_allowed"
        ) -or
        $sync.terminal_trade_allowed -ne $false
    ) {
        throw (
            "Independent flat proof terminal trade_allowed must be false."
        )
    }
    $processSafety = $proof.process_safety
    if (
        $null -eq $processSafety -or
        $processSafety.read_only_tester_terminal_stopped -ne $true -or
        $processSafety.exact_auxiliary_trading_terminal_stopped -ne $true -or
        $processSafety.alignment_controller_process_running -ne $false -or
        $processSafety.orders_or_positions_modified -ne $false -or
        $processSafety.trade_methods_invoked -ne $false
    ) {
        throw (
            "Independent flat proof process safety gates are incomplete."
        )
    }
    $capturedText = if (
        $sync.PSObject.Properties.Name -contains "sync_time_utc"
    ) {
        [string]$sync.sync_time_utc
    }
    else {
        [string]$proof.assessed_at_utc
    }
    $captured = [DateTimeOffset]::Parse($capturedText).UtcDateTime
    $age = ([DateTime]::UtcNow - $captured).TotalSeconds
    if ($age -lt -1 -or $age -gt $MaximumAgeSeconds) {
        throw (
            "Independent flat proof is stale. AgeSeconds=" +
            [Math]::Round($age, 3)
        )
    }
}

if ([string]::IsNullOrWhiteSpace($CandidateCycleId)) {
    throw "CandidateCycleId is required."
}
if ($ExpectedDemoLogin -le 0) {
    throw "ExpectedDemoLogin must be positive."
}
if ($FlatProofMaxAgeSeconds -lt 1) {
    throw "FlatProofMaxAgeSeconds must be positive."
}

$PythonPath = Resolve-RequiredFile $PythonPath "Python executable"
$ControllerPath = Resolve-RequiredFile $ControllerPath "Alignment controller"
$CandidateTelemetry = Resolve-RequiredFile `
    $CandidateTelemetry `
    "Candidate telemetry"
$TargetEvents = Resolve-RequiredFile $TargetEvents "Target event archive"
$TerminalPath = Resolve-RequiredFile $TerminalPath "Auxiliary terminal"
$StartupConfig = Resolve-RequiredFile $StartupConfig "Startup config"
$PresetPath = Resolve-RequiredFile $PresetPath "Bound demo preset"
$ActiveEx5Path = Resolve-RequiredFile $ActiveEx5Path "Active EX5"
$StagedEx5Path = Resolve-RequiredFile $StagedEx5Path "Staged EX5"
$StagedPackagePath = Resolve-RequiredFile `
    $StagedPackagePath `
    "Staged package"
$QualificationState = Resolve-RequiredFile `
    $QualificationState `
    "Qualification state"
$AlignmentHoldPath = [System.IO.Path]::GetFullPath($AlignmentHoldPath)
$HealthPath = [System.IO.Path]::GetFullPath($HealthPath)

if ([System.IO.Path]::GetFileName($TerminalPath) -ne "terminal64.exe") {
    throw "Auxiliary terminal must be named terminal64.exe."
}
$startup = Get-Content -LiteralPath $StartupConfig -Raw
if ($startup -notmatch "Expert=StraddleReplica\\StraddleReplica") {
    throw "Startup config does not load StraddleReplica."
}
Assert-BoundDemoPreset `
    -Path $PresetPath `
    -ExpectedLogin $ExpectedDemoLogin
$activeHash = Assert-Sha256 `
    -Path $ActiveEx5Path `
    -Expected $ExpectedActiveEx5Sha256 `
    -Label "Active EX5"
$stagedHash = Assert-Sha256 `
    -Path $StagedEx5Path `
    -Expected $ExpectedStagedEx5Sha256 `
    -Label "Staged EX5"
$packageHash = Assert-Sha256 `
    -Path $StagedPackagePath `
    -Expected $ExpectedStagedPackageSha256 `
    -Label "Staged package"

$resolvedFlatProofPath = ""
if (-not [string]::IsNullOrWhiteSpace($FlatProofPath)) {
    $resolvedFlatProofPath = Resolve-RequiredFile `
        $FlatProofPath `
        "Independent flat proof"
    Assert-IndependentFlatProof `
        -Path $resolvedFlatProofPath `
        -ExpectedLogin $ExpectedDemoLogin `
        -MaximumAgeSeconds $FlatProofMaxAgeSeconds
}

$qualification = Get-Content -LiteralPath $QualificationState -Raw |
    ConvertFrom-Json
if (
    $qualification.PSObject.Properties.Name -contains "active_cycle_id" -and
    [string]$qualification.active_cycle_id -ne $CandidateCycleId
) {
    throw (
        "Qualification state active cycle does not match CandidateCycleId."
    )
}
if (
    $qualification.PSObject.Properties.Name -contains
        "active_cycle_eligible" -and
    $qualification.active_cycle_eligible -ne $false
) {
    throw "CandidateCycleId must remain excluded from qualification."
}

$argumentParts = @(
    (Quote-TaskArgument $ControllerPath),
    "--candidate-telemetry",
    (Quote-TaskArgument $CandidateTelemetry),
    "--candidate-cycle-id",
    (Quote-TaskArgument $CandidateCycleId),
    "--target-events",
    (Quote-TaskArgument $TargetEvents),
    "--terminal-path",
    (Quote-TaskArgument $TerminalPath),
    "--startup-config",
    (Quote-TaskArgument $StartupConfig),
    "--preset-path",
    (Quote-TaskArgument $PresetPath),
    "--expected-demo-login",
    "$ExpectedDemoLogin",
    "--active-ex5-path",
    (Quote-TaskArgument $ActiveEx5Path),
    "--expected-active-ex5-sha256",
    $activeHash,
    "--staged-ex5-path",
    (Quote-TaskArgument $StagedEx5Path),
    "--expected-staged-ex5-sha256",
    $stagedHash,
    "--staged-package-path",
    (Quote-TaskArgument $StagedPackagePath),
    "--expected-staged-package-sha256",
    $packageHash,
    "--qualification-state",
    (Quote-TaskArgument $QualificationState),
    "--alignment-hold-path",
    (Quote-TaskArgument $AlignmentHoldPath),
    "--health",
    (Quote-TaskArgument $HealthPath),
    "--poll-seconds",
    "$PollSeconds",
    "--race-guard-seconds",
    "$RaceGuardSeconds",
    "--startup-lead-seconds",
    "$StartupLeadSeconds",
    "--start-observation-seconds",
    "$StartObservationSeconds",
    "--start-tolerance-seconds",
    "$StartToleranceSeconds"
)
if (-not [string]::IsNullOrWhiteSpace($resolvedFlatProofPath)) {
    $argumentParts += @(
        "--independent-flat-proof",
        (Quote-TaskArgument $resolvedFlatProofPath),
        "--flat-proof-max-age-seconds",
        "$FlatProofMaxAgeSeconds"
    )
}
$arguments = $argumentParts -join " "

$plan = [ordered]@{
    schema_version = 1
    task_name = $TaskName
    execute = $PythonPath
    arguments = $arguments
    working_directory = $Workspace
    candidate_cycle_id = $CandidateCycleId
    expected_demo_login = $ExpectedDemoLogin
    active_ex5_sha256 = $activeHash
    staged_ex5_sha256 = $stagedHash
    staged_package_sha256 = $packageHash
    alignment_hold_path = $AlignmentHoldPath
    independent_flat_proof_path = $resolvedFlatProofPath
    flat_proof_max_age_seconds = $FlatProofMaxAgeSeconds
    register_requested = [bool]$Apply
    task_will_be_started = $false
    automatic_trigger_count = 0
}

if (-not $Apply) {
    $plan | ConvertTo-Json -Depth 4
    exit 0
}

if ([string]::IsNullOrWhiteSpace($FlatProofPath)) {
    throw "Independent flat proof is required when Apply is requested."
}
Assert-IndependentFlatProof `
    -Path $resolvedFlatProofPath `
    -ExpectedLogin $ExpectedDemoLogin `
    -MaximumAgeSeconds $FlatProofMaxAgeSeconds

$processes = Get-CimInstance Win32_Process
$terminalProcesses = @(
    $processes | Where-Object {
        $_.ExecutablePath -and
        $_.ExecutablePath -ieq $TerminalPath
    }
)
if ($terminalProcesses.Count -ne 0) {
    throw "Auxiliary trading terminal must be stopped before registration."
}
$controllerProcesses = @(
    $processes | Where-Object {
        $_.Name -match "^python(w)?\.exe$" -and
        ([string]$_.CommandLine).IndexOf(
            [System.IO.Path]::GetFileName($ControllerPath),
            [System.StringComparison]::OrdinalIgnoreCase
        ) -ge 0
    }
)
if ($controllerProcesses.Count -ne 0) {
    throw "Alignment controller must be stopped before registration."
}

$action = New-ScheduledTaskAction `
    -Execute $PythonPath `
    -Argument $arguments `
    -WorkingDirectory $Workspace
$settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal `
    -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -LogonType Interactive `
    -RunLevel Limited
Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Settings $settings `
    -Principal $principal `
    -Description (
        "Manual-only auxiliary alignment controller. " +
        "Never start without a fresh independent flat proof."
    ) `
    -Force | Out-Null
Disable-ScheduledTask -TaskName $TaskName | Out-Null

$plan["registered"] = $true
$plan["task_enabled"] = $false
$plan | ConvertTo-Json -Depth 4
