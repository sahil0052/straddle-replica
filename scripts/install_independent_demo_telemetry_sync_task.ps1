param(
    [string]$SshAlias = "nishahomes-vps",
    [string]$RemoteRoot = "/opt/straddle-fidelity-independent-demo",
    [string]$Workspace = "",
    [string]$PythonPath = "",
    [double]$PollSeconds = 2.0
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($RemoteRoot -ne "/opt/straddle-fidelity-independent-demo") {
    throw "RemoteRoot must be /opt/straddle-fidelity-independent-demo."
}
if ($PollSeconds -lt 0.5) {
    throw "PollSeconds must be at least 0.5."
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
$tool = Join-Path (
    $Workspace
) "tools\sync_independent_candidate_telemetry.py"
foreach ($required in @($PythonPath, $tool)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Required telemetry sync file was not found: $required"
    }
}
foreach ($command in @("ssh.exe", "scp.exe")) {
    if ($null -eq (Get-Command $command -ErrorAction SilentlyContinue)) {
        throw "Required OpenSSH command was not found: $command"
    }
}

$runtimeRoot = Join-Path (
    $Workspace
) "artifacts\live\independent-demo-fidelity"
New-Item -ItemType Directory -Force -Path $runtimeRoot | Out-Null
$telemetry = Join-Path $runtimeRoot "candidate-telemetry.csv"
$manifest = Join-Path $runtimeRoot "candidate-manifest.csv"
$health = Join-Path (
    $runtimeRoot
) "candidate-telemetry-sync-health.json"
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
    '"tools\sync_independent_candidate_telemetry.py"',
    "--ssh-alias", ('"' + $SshAlias + '"'),
    "--remote-root", ('"' + $RemoteRoot + '"'),
    "--telemetry-output", ('"' + $telemetry + '"'),
    "--manifest-output", ('"' + $manifest + '"'),
    "--health", ('"' + $health + '"'),
    "--poll-seconds", $PollSeconds.ToString(
        [System.Globalization.CultureInfo]::InvariantCulture
    )
) -join " "

$taskName = "StraddleIndependentTelemetrySync"
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
    -Description "Read-only independent candidate telemetry sync." `
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
            $payload.status -eq "RUNNING" -and
            $updated -ne $beforeUpdated -and
            $age -ge -1 -and
            $age -le 10 -and
            (Test-Path -LiteralPath $telemetry -PathType Leaf) -and
            (Test-Path -LiteralPath $manifest -PathType Leaf)
        )
    }
    catch {
        $healthy = $false
    }
} while (-not $healthy -and [DateTime]::UtcNow -lt $deadline)

if (-not $healthy) {
    throw "Telemetry sync task did not become healthy."
}
Write-Host "Started $taskName"
Write-Host "Candidate telemetry sync is healthy."
