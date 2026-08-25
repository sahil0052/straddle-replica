param(
    [string]$Workspace = "",
    [string]$PythonPath = "",
    [string]$TargetTerminal = "D:\MT5ObserverTerminal\terminal64.exe",
    [string]$TargetOutput = "D:\MT5ObserverData\isolated-live",
    [string]$CommandPath = "C:\Users\HPUSER\AppData\Roaming\MetaQuotes\Terminal\Common\Files\StraddleShadow\command.csv",
    [string]$AckPath = "C:\Users\HPUSER\AppData\Roaming\MetaQuotes\Terminal\Common\Files\StraddleShadow\ack.csv",
    [int]$HeartbeatMaxAgeSeconds = 5,
    [int]$StartupTimeoutSeconds = 45
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($Workspace)) {
    $Workspace = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}
if ([string]::IsNullOrWhiteSpace($PythonPath)) {
    $PythonPath = (Get-Command python.exe -ErrorAction Stop).Source
}

$collectorTaskName = "StraddleTargetCollector"
$coordinatorTaskName = "StraddleNextCycleSync"
$runtimeRoot = Join-Path $Workspace "artifacts\live\next-cycle-sync"
$adapterState = Join-Path $runtimeRoot "observer-adapter-state.json"
$coordinatorState = Join-Path $runtimeRoot "coordinator-state.json"
$coordinatorHealth = Join-Path $runtimeRoot "coordinator-health.json"
$targetArchive = Join-Path $runtimeRoot "target-cycles.jsonl"
$coordinatorTool = Join-Path $Workspace "tools\run_shadow_coordinator.py"

foreach ($requiredFile in @(
    $PythonPath,
    $TargetTerminal,
    $coordinatorTool
)) {
    if (-not (Test-Path -LiteralPath $requiredFile -PathType Leaf)) {
        throw "Required file was not found: $requiredFile"
    }
}
foreach ($requiredDirectory in @(
    $Workspace,
    (Split-Path -Parent $CommandPath),
    (Split-Path -Parent $AckPath)
)) {
    if (-not (Test-Path -LiteralPath $requiredDirectory -PathType Container)) {
        throw "Required directory was not found: $requiredDirectory"
    }
}
if ($HeartbeatMaxAgeSeconds -lt 1) {
    throw "HeartbeatMaxAgeSeconds must be positive."
}
if ($StartupTimeoutSeconds -lt 5) {
    throw "StartupTimeoutSeconds must be at least five seconds."
}

New-Item -ItemType Directory -Force -Path $TargetOutput | Out-Null
New-Item -ItemType Directory -Force -Path $runtimeRoot | Out-Null

function Quote-TaskArgument {
    param([Parameter(Mandatory = $true)][string]$Value)
    return '"' + $Value.Replace('"', '\"') + '"'
}

function Wait-ForReadOnlyHeartbeat {
    param(
        [Parameter(Mandatory = $true)][string]$OutputRoot,
        [Parameter(Mandatory = $true)][DateTime]$Deadline
    )

    do {
        $pointerPath = Join-Path $OutputRoot "current-session.json"
        if (Test-Path -LiteralPath $pointerPath -PathType Leaf) {
            try {
                $pointer = Get-Content -LiteralPath $pointerPath -Raw |
                    ConvertFrom-Json
                $sessionDirectory = if (
                    -not [string]::IsNullOrWhiteSpace($pointer.session_dir)
                ) {
                    [string]$pointer.session_dir
                }
                else {
                    Join-Path $OutputRoot ([string]$pointer.session_id)
                }
                $heartbeatPath = Join-Path $sessionDirectory "heartbeat.json"
                if (Test-Path -LiteralPath $heartbeatPath -PathType Leaf) {
                    $heartbeat = Get-Content -LiteralPath $heartbeatPath -Raw |
                        ConvertFrom-Json
                    $captured = [DateTimeOffset]::Parse(
                        [string]$heartbeat.capture_time_utc
                    ).UtcDateTime
                    $age = ([DateTime]::UtcNow - $captured).TotalSeconds
                    if (
                        $heartbeat.healthy -eq $true -and
                        $heartbeat.stopped -ne $true -and
                        $heartbeat.read_only_verified -eq $true -and
                        $age -ge -1 -and
                        $age -le $HeartbeatMaxAgeSeconds
                    ) {
                        return $heartbeat
                    }
                }
            }
            catch {
                # A writer may be atomically replacing the pointer/heartbeat.
            }
        }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $Deadline)

    throw "A fresh read_only_verified target heartbeat was not observed."
}

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

$collectorArguments = @(
    "-m",
    "straddle_replica.monitor_cli",
    "monitor-live",
    "--terminal",
    (Quote-TaskArgument $TargetTerminal),
    "--output",
    (Quote-TaskArgument $TargetOutput),
    "--account",
    "901018",
    "--server",
    (Quote-TaskArgument "AchieverGlobalMarkets-Server"),
    "--symbol",
    "XAUUSD",
    "--poll-ms",
    "50",
    "--checkpoint-seconds",
    "30",
    "--exit-on-connection-error",
    "--require-read-only"
) -join " "
$collectorAction = New-ScheduledTaskAction `
    -Execute $PythonPath `
    -Argument $collectorArguments `
    -WorkingDirectory $Workspace

$coordinatorArguments = @(
    (Quote-TaskArgument $coordinatorTool),
    "--target-observer-root",
    (Quote-TaskArgument $TargetOutput),
    "--observer-state-path",
    (Quote-TaskArgument $adapterState),
    "--command-path",
    (Quote-TaskArgument $CommandPath),
    "--ack-path",
    (Quote-TaskArgument $AckPath),
    "--state-path",
    (Quote-TaskArgument $coordinatorState),
    "--target-archive-path",
    (Quote-TaskArgument $targetArchive),
    "--health-path",
    (Quote-TaskArgument $coordinatorHealth),
    "--heartbeat-max-age-seconds",
    "$HeartbeatMaxAgeSeconds",
    "--retry-ms",
    "1000",
    "--poll-ms",
    "50",
    "--active"
) -join " "
$coordinatorAction = New-ScheduledTaskAction `
    -Execute $PythonPath `
    -Argument $coordinatorArguments `
    -WorkingDirectory $Workspace

Register-ScheduledTask `
    -TaskName $collectorTaskName `
    -Action $collectorAction `
    -Settings $settings `
    -Principal $principal `
    -Description "Read-only target MT5 collector; sole Python API owner." `
    -Force | Out-Null
Register-ScheduledTask `
    -TaskName $coordinatorTaskName `
    -Action $coordinatorAction `
    -Settings $settings `
    -Principal $principal `
    -Description "Fail-closed one-time demo cycle synchronizer." `
    -Force | Out-Null

Start-ScheduledTask -TaskName $collectorTaskName
$deadline = [DateTime]::UtcNow.AddSeconds($StartupTimeoutSeconds)
$heartbeat = Wait-ForReadOnlyHeartbeat `
    -OutputRoot $TargetOutput `
    -Deadline $deadline

Start-ScheduledTask -TaskName $coordinatorTaskName
do {
    Start-Sleep -Milliseconds 250
    $coordinatorTask = Get-ScheduledTask -TaskName $coordinatorTaskName
    if ($coordinatorTask.State -eq "Running") {
        break
    }
} while ([DateTime]::UtcNow -lt $deadline)

if ($coordinatorTask.State -ne "Running") {
    $taskInfo = Get-ScheduledTaskInfo -TaskName $coordinatorTaskName
    throw "Coordinator task failed to run. Result=$($taskInfo.LastTaskResult)"
}

Write-Host "Target collector task: Running"
Write-Host "Target read_only_verified: $($heartbeat.read_only_verified)"
Write-Host "Target dropped transactions: 0"
Write-Host "Coordinator task: Running"
Write-Host "Coordinator health: $coordinatorHealth"
