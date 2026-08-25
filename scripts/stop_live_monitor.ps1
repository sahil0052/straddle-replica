param(
    [string]$Workspace = "",
    [string]$OutputRoot = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($Workspace)) {
    $Workspace = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}
if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    $OutputRoot = Join-Path $Workspace "artifacts\live"
}

$pidPath = Join-Path $OutputRoot "monitor-process.json"
if (-not (Test-Path -LiteralPath $pidPath -PathType Leaf)) {
    Write-Host "No monitor PID record exists."
    exit 0
}

$record = Get-Content -LiteralPath $pidPath -Raw | ConvertFrom-Json
$resolvedWorkspace = (Resolve-Path -LiteralPath $Workspace).Path
$recordWorkspace = [System.IO.Path]::GetFullPath([string]$record.workspace)
if (-not $recordWorkspace.Equals(
    $resolvedWorkspace,
    [System.StringComparison]::OrdinalIgnoreCase
)) {
    throw "Monitor PID record workspace mismatch."
}
$process = Get-CimInstance Win32_Process -Filter "ProcessId=$($record.pid)" `
    -ErrorAction SilentlyContinue

if ($null -eq $process) {
    Remove-Item -LiteralPath $pidPath -Force
    Write-Host "The recorded monitor process is not running."
    exit 0
}
if ($process.CommandLine -notlike "*straddle_replica*monitor-live*") {
    throw "PID $($record.pid) is not the expected monitor-live process."
}
if (-not ([string]$process.ExecutablePath).Equals(
    [string]$record.executable,
    [System.StringComparison]::OrdinalIgnoreCase
)) {
    throw "PID $($record.pid) executable does not match its PID record."
}

Stop-Process -Id $record.pid
Remove-Item -LiteralPath $pidPath -Force
Write-Host "Stopped read-only monitor PID $($record.pid)."
