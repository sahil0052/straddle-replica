param(
    [string]$Workspace = "",
    [string]$PythonPath = "",
    [string]$SshAlias = "nishahomes-vps",
    [string]$RemoteRoot = "/opt/straddle-fidelity-candidate",
    [int]$HeartbeatMaxAgeSeconds = 5,
    [int]$StartupTimeoutSeconds = 120
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($Workspace)) {
    $Workspace = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}
if ([string]::IsNullOrWhiteSpace($PythonPath)) {
    $PythonPath = (Get-Command python.exe -ErrorAction Stop).Source
}
if ($RemoteRoot -ne "/opt/straddle-fidelity-candidate") {
    throw "RemoteRoot must be /opt/straddle-fidelity-candidate."
}
if ($HeartbeatMaxAgeSeconds -lt 1) {
    throw "HeartbeatMaxAgeSeconds must be positive."
}
if ($StartupTimeoutSeconds -lt 5) {
    throw "StartupTimeoutSeconds must be at least five seconds."
}

$targetTerminal = "D:\MT5ObserverTerminal\terminal64.exe"
$targetOutput = "D:\MT5ObserverData\isolated-live"
$coordinatorTool = Join-Path $Workspace "tools\run_shadow_coordinator.py"
foreach ($required in @($PythonPath, $targetTerminal, $coordinatorTool)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Required file was not found: $required"
    }
}

$existingOwner = Get-CimInstance Win32_Process |
    Where-Object {
        $_.Name -eq "python.exe" -and
        $_.CommandLine -like "*straddle_replica.monitor_cli*" -and
        $_.CommandLine -like "*D:\MT5ObserverTerminal\terminal64.exe*"
    }
if ($existingOwner) {
    throw "A target collector owner is already running."
}

$collectorTaskName = "StraddleFidelityTargetCollector"
$coordinatorTaskName = "StraddleFidelityCycleSync"
$runtimeRoot = Join-Path $Workspace "artifacts\live\independent-fidelity"
New-Item -ItemType Directory -Force -Path $runtimeRoot | Out-Null
New-Item -ItemType Directory -Force -Path $targetOutput | Out-Null

$collectorArguments = @(
    "-m", "straddle_replica.monitor_cli", "monitor-live",
    "--terminal", '"D:\MT5ObserverTerminal\terminal64.exe"',
    "--output", '"D:\MT5ObserverData\isolated-live"',
    "--account", "901018",
    "--server", '"AchieverGlobalMarkets-Server"',
    "--symbol", "XAUUSD",
    "--poll-ms", "50",
    "--checkpoint-seconds", "30",
    "--exit-on-connection-error",
    "--require-read-only"
) -join " "
$commonRoot = (
    "$RemoteRoot/wineprefix/drive_c/users/mt5/AppData/Roaming/" +
    "MetaQuotes/Terminal/Common/Files"
)
$coordinatorArguments = @(
    '"tools\run_shadow_coordinator.py"',
    "--target-observer-root", '"D:\MT5ObserverData\isolated-live"',
    "--observer-state-path",
    ('"' + (Join-Path $runtimeRoot "observer-state.json") + '"'),
    "--state-path",
    ('"' + (Join-Path $runtimeRoot "coordinator-state.json") + '"'),
    "--target-archive-path",
    ('"' + (Join-Path $runtimeRoot "target-cycles.jsonl") + '"'),
    "--health-path",
    ('"' + (Join-Path $runtimeRoot "coordinator-health.json") + '"'),
    "--remote-ssh-alias", $SshAlias,
    "--remote-root", $RemoteRoot,
    "--remote-command-path",
    "$commonRoot/StraddleShadow/command.csv",
    "--remote-ack-path",
    "$commonRoot/StraddleShadow/ack.csv",
    "--active"
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
$collectorAction = New-ScheduledTaskAction `
    -Execute $PythonPath `
    -Argument $collectorArguments `
    -WorkingDirectory $Workspace
$coordinatorAction = New-ScheduledTaskAction `
    -Execute $PythonPath `
    -Argument $coordinatorArguments `
    -WorkingDirectory $Workspace

Register-ScheduledTask `
    -TaskName $collectorTaskName `
    -Action $collectorAction `
    -Settings $settings `
    -Principal $principal `
    -Description "Read-only fidelity target collector." `
    -Force | Out-Null
Register-ScheduledTask `
    -TaskName $coordinatorTaskName `
    -Action $coordinatorAction `
    -Settings $settings `
    -Principal $principal `
    -Description "Candidate-scoped fidelity cycle synchronizer." `
    -Force | Out-Null

function Wait-ForReadOnlyHeartbeat {
    param([Parameter(Mandatory = $true)][DateTime]$Deadline)
    do {
        $pointerPath = Join-Path $targetOutput "current-session.json"
        if (Test-Path -LiteralPath $pointerPath -PathType Leaf) {
            try {
                $pointer = Get-Content -LiteralPath $pointerPath -Raw |
                    ConvertFrom-Json
                $sessionDirectory = if ($pointer.session_dir) {
                    [string]$pointer.session_dir
                }
                else {
                    Join-Path $targetOutput ([string]$pointer.session_id)
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
                        [int]$heartbeat.dropped_transactions -eq 0 -and
                        $age -ge -1 -and
                        $age -le $HeartbeatMaxAgeSeconds
                    ) {
                        return $heartbeat
                    }
                }
            }
            catch {
                # The collector may be atomically replacing these files.
            }
        }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $Deadline)
    throw "A fresh read_only_verified target heartbeat was not observed."
}

Start-ScheduledTask -TaskName $collectorTaskName
$heartbeat = Wait-ForReadOnlyHeartbeat `
    -Deadline ([DateTime]::UtcNow.AddSeconds($StartupTimeoutSeconds))

Write-Host "Collector task: $collectorTaskName"
Write-Host "Collector read_only_verified: $($heartbeat.read_only_verified)"
Write-Host "Coordinator task registered but not started: $coordinatorTaskName"
