param(
    [string]$Workspace = "",
    [string]$TerminalPath = "C:\Program Files\MetaTrader 5\terminal64.exe",
    [string]$StartupConfig = "",
    [switch]$PortableTerminal,
    [string]$OutputRoot = "",
    [string]$TaskName = "StraddleObserverMonitor"
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

$startScript = Join-Path $Workspace "scripts\start_live_monitor.ps1"
if (-not (Test-Path -LiteralPath $startScript -PathType Leaf)) {
    throw "Monitor start script was not found at '$startScript'."
}

$powerShell = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$arguments = (
    '-NoProfile -ExecutionPolicy Bypass -File "{0}" ' +
    '-Workspace "{1}" -TerminalPath "{2}" -StartupConfig "{3}" ' +
    '-OutputRoot "{4}"'
) -f $startScript, $Workspace, $TerminalPath, $StartupConfig, $OutputRoot
if ($PortableTerminal) {
    $arguments += " -PortableTerminal"
}

$action = New-ScheduledTaskAction -Execute $powerShell -Argument $arguments
$logonTrigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$watchdogTrigger = New-ScheduledTaskTrigger `
    -Once `
    -At ([DateTime]::Now.AddMinutes(1)) `
    -RepetitionInterval (New-TimeSpan -Minutes 1) `
    -RepetitionDuration (New-TimeSpan -Days 3650)
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive `
    -RunLevel Highest

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger @($logonTrigger, $watchdogTrigger) `
    -Settings $settings `
    -Principal $principal `
    -Description "Read-only MT5 forensic monitor for the straddle account." `
    -Force | Out-Null

Write-Host "Installed scheduled task '$TaskName'."
Write-Host "The task contains no account or VPS credentials."
