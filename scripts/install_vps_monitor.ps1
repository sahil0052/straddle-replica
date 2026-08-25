param(
    [string]$PackageRoot = "",
    [Parameter(Mandatory = $true)]
    [string]$TerminalDataPath,
    [Parameter(Mandatory = $true)]
    [string]$TerminalPath,
    [string]$OutputRoot = "C:\MT5ObserverData\live",
    [string]$PythonPath = "python.exe",
    [switch]$SkipDependencyInstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($PackageRoot)) {
    $PackageRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}
if (-not (Test-Path -LiteralPath $TerminalPath -PathType Leaf)) {
    throw "Monitoring terminal executable was not found at '$TerminalPath'."
}
if (-not (Test-Path -LiteralPath (Join-Path $TerminalDataPath "MQL5") -PathType Container)) {
    throw "Monitoring terminal data directory is invalid: '$TerminalDataPath'."
}

if (-not $SkipDependencyInstall) {
    & $PythonPath -m pip install `
        --disable-pip-version-check `
        -r (Join-Path $PackageRoot "requirements-monitor.txt")
    if ($LASTEXITCODE -ne 0) {
        throw "Monitor dependency installation failed."
    }
}

& (Join-Path $PackageRoot "scripts\install_observer.ps1") `
    -Workspace $PackageRoot `
    -TerminalDataPath $TerminalDataPath `
    -SkipBuild

$startupConfig = Join-Path $PackageRoot "monitor\observer-startup.ini"
& (Join-Path $PackageRoot "scripts\install_monitor_task.ps1") `
    -Workspace $PackageRoot `
    -TerminalPath $TerminalPath `
    -StartupConfig $startupConfig `
    -OutputRoot $OutputRoot `
    -PortableTerminal

& (Join-Path $PackageRoot "scripts\start_live_monitor.ps1") `
    -Workspace $PackageRoot `
    -TerminalPath $TerminalPath `
    -StartupConfig $startupConfig `
    -OutputRoot $OutputRoot `
    -PortableTerminal

Write-Host "VPS read-only monitor installation completed."
Write-Host "Disconnect the RDP session; do not sign out of Windows."
