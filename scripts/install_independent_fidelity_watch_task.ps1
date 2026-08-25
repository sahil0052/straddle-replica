param(
    [string]$Workspace = "",
    [string]$PythonPath = "",
    [double]$PollSeconds = 30.0
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($PollSeconds -lt 5.0) {
    throw "PollSeconds must be at least 5."
}
if ([string]::IsNullOrWhiteSpace($Workspace)) {
    $Workspace = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}
if ([string]::IsNullOrWhiteSpace($PythonPath)) {
    $workspaceRuntime = Join-Path (
        $Workspace
    ) "tmp\independent-demo-venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $workspaceRuntime -PathType Leaf) {
        $PythonPath = $workspaceRuntime
    }
    else {
        $PythonPath = (
            "$env:USERPROFILE\.cache\codex-runtimes\" +
            "codex-primary-runtime\dependencies\python\python.exe"
        )
    }
}
$tool = Join-Path $Workspace "tools\watch_independent_fidelity.py"
$runtimeRoot = Join-Path (
    $Workspace
) "artifacts\live\independent-demo-fidelity"
$qualification = Join-Path $runtimeRoot "qualification-state.json"
$targetEvents = Join-Path $runtimeRoot "target-cycles.jsonl"
$candidateTelemetry = Join-Path $runtimeRoot "candidate-telemetry.csv"
foreach ($required in @(
    $PythonPath,
    $tool,
    $qualification,
    $targetEvents,
    $candidateTelemetry
)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Required fidelity watch file was not found: $required"
    }
}

$reports = Join-Path (
    $runtimeRoot
) "formal-comparison-reports\continuous"
$health = Join-Path $runtimeRoot "fidelity-watch-health.json"
New-Item -ItemType Directory -Force -Path $reports | Out-Null
$beforeUpdated = ""
if (Test-Path -LiteralPath $health -PathType Leaf) {
    try {
        $beforeUpdated = [string](
            Get-Content -Raw -LiteralPath $health |
                ConvertFrom-Json
        ).updated_at_utc
    }
    catch {
        $beforeUpdated = ""
    }
}

$arguments = @(
    '"tools\watch_independent_fidelity.py"',
    "--qualification-state", ('"' + $qualification + '"'),
    "--target-events", ('"' + $targetEvents + '"'),
    "--candidate-telemetry", ('"' + $candidateTelemetry + '"'),
    "--reports-dir", ('"' + $reports + '"'),
    "--health", ('"' + $health + '"'),
    "--pairing", "ordinal",
    "--max-start-gap-seconds", "2.0",
    "--normalized-price-tolerance", "0.02",
    "--poll-seconds", $PollSeconds.ToString(
        [System.Globalization.CultureInfo]::InvariantCulture
    )
) -join " "

$taskName = "StraddleIndependentFidelityWatch"
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
$action = New-ScheduledTaskAction `
    -Execute $PythonPath `
    -Argument $arguments `
    -WorkingDirectory $Workspace

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Settings $settings `
    -Principal $principal `
    -Description "Read-only independent target/candidate fidelity watcher." `
    -Force | Out-Null
Start-ScheduledTask -TaskName $taskName

$deadline = [DateTime]::UtcNow.AddSeconds(45)
$healthy = $false
do {
    Start-Sleep -Milliseconds 250
    try {
        $task = Get-ScheduledTask -TaskName $taskName
        $payload = Get-Content -Raw -LiteralPath $health |
            ConvertFrom-Json
        $updated = [string]$payload.updated_at_utc
        $age = (
            [DateTimeOffset]::UtcNow -
            [DateTimeOffset]::Parse($updated)
        ).TotalSeconds
        $healthy = (
            $task.State -eq "Running" -and
            $updated -ne $beforeUpdated -and
            $age -ge -1 -and
            $age -le 15 -and
            [string]$payload.status -in @(
                "WAITING_FOR_CLEAN_CYCLE_START",
                "WAITING_FOR_COMPLETE_PAIR",
                "MISMATCH_DETECTED",
                "BELOW_95",
                "QUALIFIED_AT_OR_ABOVE_95",
                "QUALIFIED_AT_OR_ABOVE_99"
            )
        )
    }
    catch {
        $healthy = $false
    }
} while (-not $healthy -and [DateTime]::UtcNow -lt $deadline)

if (-not $healthy) {
    throw "Independent fidelity watch task did not become healthy."
}
Write-Host "Started $taskName"
Write-Host "Independent fidelity watch status: $($payload.status)"
