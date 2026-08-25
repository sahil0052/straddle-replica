param(
    [string]$Workspace = "",
    [string]$PythonPath = "",
    [string]$TerminalPath = "C:\Program Files\MetaTrader 5\terminal64.exe",
    [string]$StartupConfig = "",
    [switch]$PortableTerminal,
    [string]$OutputRoot = "",
    [int64]$Account = 901018,
    [string]$Server = "AchieverGlobalMarkets-Server",
    [string]$Symbol = "XAUUSD",
    [int]$PollMs = 50,
    [double]$CheckpointSeconds = 30
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($Workspace)) {
    $Workspace = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}
if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    $OutputRoot = Join-Path $Workspace "artifacts\live"
}
if ([string]::IsNullOrWhiteSpace($StartupConfig)) {
    $StartupConfig = Join-Path $Workspace "monitor\observer-startup.ini"
}
if (-not (Test-Path -LiteralPath $TerminalPath -PathType Leaf)) {
    throw "MT5 terminal was not found at '$TerminalPath'."
}
if (-not (Test-Path -LiteralPath $StartupConfig -PathType Leaf)) {
    throw "Observer startup config was not found at '$StartupConfig'."
}

$resolvedTerminal = (Resolve-Path -LiteralPath $TerminalPath).Path
$terminalProcess = Get-CimInstance Win32_Process |
    Where-Object { $_.ExecutablePath -eq $resolvedTerminal } |
    Select-Object -First 1
if ($null -eq $terminalProcess) {
    $terminalArguments = @("/config:`"$StartupConfig`"")
    if ($PortableTerminal) {
        $terminalArguments = @("/portable") + $terminalArguments
    }
    Start-Process `
        -FilePath $resolvedTerminal `
        -ArgumentList $terminalArguments `
        -WorkingDirectory (Split-Path -Parent $resolvedTerminal) `
        -WindowStyle Minimized | Out-Null

    $deadline = [DateTime]::UtcNow.AddSeconds(30)
    do {
        Start-Sleep -Milliseconds 500
        $terminalProcess = Get-CimInstance Win32_Process |
            Where-Object { $_.ExecutablePath -eq $resolvedTerminal } |
            Select-Object -First 1
    } while ($null -eq $terminalProcess -and [DateTime]::UtcNow -lt $deadline)

    if ($null -eq $terminalProcess) {
        throw "MT5 did not start from '$resolvedTerminal'."
    }
}

New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null
$pidPath = Join-Path $OutputRoot "monitor-process.json"
$stdoutPath = Join-Path $OutputRoot "monitor-stdout.log"
$stderrPath = Join-Path $OutputRoot "monitor-stderr.log"

if (Test-Path -LiteralPath $pidPath) {
    $existing = Get-Content -LiteralPath $pidPath -Raw | ConvertFrom-Json
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($existing.pid)" `
        -ErrorAction SilentlyContinue
    if ($null -ne $process -and
        $process.CommandLine -like "*straddle_replica*monitor-live*") {
        Write-Host "Read-only monitor is already running with PID $($existing.pid)."
        exit 0
    }
}

if ([string]::IsNullOrWhiteSpace($PythonPath)) {
    $foundPython = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($foundPython) {
        $PythonPath = $foundPython.Source
    } elseif (Test-Path "C:\websites\mt5 2\tmp\independent-demo-venv\Scripts\python.exe") {
        $PythonPath = "C:\websites\mt5 2\tmp\independent-demo-venv\Scripts\python.exe"
    } elseif (Test-Path "C:\Users\HPUSER\AppData\Roaming\uv\python\cpython-3.14.7-windows-x86_64-none\python.exe") {
        $PythonPath = "C:\Users\HPUSER\AppData\Roaming\uv\python\cpython-3.14.7-windows-x86_64-none\python.exe"
    } else {
        throw "Python executable was not found."
    }
}
$python = $PythonPath
$arguments = @(
    "-m",
    "straddle_replica.monitor_cli",
    "monitor-live",
    "--terminal",
    "`"$TerminalPath`"",
    "--output",
    "`"$OutputRoot`"",
    "--account",
    "$Account",
    "--server",
    "`"$Server`"",
    "--symbol",
    "`"$Symbol`"",
    "--poll-ms",
    "$PollMs",
    "--checkpoint-seconds",
    "$CheckpointSeconds",
    "--exit-on-connection-error",
    "--require-read-only"
)

$process = Start-Process `
    -FilePath $python `
    -ArgumentList $arguments `
    -WorkingDirectory $Workspace `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdoutPath `
    -RedirectStandardError $stderrPath `
    -PassThru

@{
    pid = $process.Id
    started_at_utc = [DateTime]::UtcNow.ToString("o")
    executable = $python
    workspace = $Workspace
    terminal = $TerminalPath
    startup_config = $StartupConfig
    portable_terminal = [bool]$PortableTerminal
    output = $OutputRoot
    mode = "read-only"
} | ConvertTo-Json | Set-Content -LiteralPath $pidPath -Encoding UTF8

Start-Sleep -Seconds 3
$process.Refresh()
if ($process.HasExited) {
    $errorText = ""
    if (Test-Path -LiteralPath $stderrPath) {
        $errorText = Get-Content -LiteralPath $stderrPath -Raw
    }
    throw "Monitor exited during startup. $errorText"
}

Write-Host "Started read-only monitor with PID $($process.Id)."
Write-Host "Output: $OutputRoot"
