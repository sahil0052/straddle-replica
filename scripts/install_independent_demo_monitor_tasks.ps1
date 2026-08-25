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
    "--checkpoint-seconds", "1",
    "--history-seed-days", "1",
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
    "--checkpoint-seconds", "1",
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
                    $droppedProperty = (
                        $heartbeat.PSObject.Properties[
                            "dropped_transactions"
                        ]
                    )
                    $dropped = if ($null -eq $droppedProperty) {
                        0
                    }
                    else {
                        [int]$droppedProperty.Value
                    }
                    if (
                        $age -ge -1 -and
                        $age -le 5 -and
                        $heartbeat.healthy -eq $true -and
                        $heartbeat.stopped -ne $true -and
                        $heartbeat.read_only_verified -eq $true -and
                        $dropped -eq 0 -and
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
