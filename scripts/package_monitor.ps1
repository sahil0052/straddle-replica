param(
    [string]$Workspace = "",
    [string]$OutputPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($Workspace)) {
    $Workspace = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}
if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $OutputPath = Join-Path $Workspace "artifacts\StraddleObserverMonitor.zip"
}

$artifactRoot = Join-Path $Workspace "artifacts"
$stage = Join-Path $artifactRoot "monitor-package-staging"
$resolvedWorkspace = (Resolve-Path -LiteralPath $Workspace).Path
$resolvedArtifactRoot = [System.IO.Path]::GetFullPath($artifactRoot)
$resolvedStage = [System.IO.Path]::GetFullPath($stage)
if (-not $resolvedStage.StartsWith(
    $resolvedArtifactRoot + [System.IO.Path]::DirectorySeparatorChar,
    [System.StringComparison]::OrdinalIgnoreCase
)) {
    throw "Unsafe staging path '$resolvedStage'."
}

if (Test-Path -LiteralPath $resolvedStage) {
    Remove-Item -LiteralPath $resolvedStage -Recurse -Force
}
New-Item -ItemType Directory -Force -Path `
    $resolvedStage, `
    (Join-Path $resolvedStage "mql5"), `
    (Join-Path $resolvedStage "monitor"), `
    (Join-Path $resolvedStage "scripts"), `
    (Join-Path $resolvedStage "straddle_replica"), `
    (Join-Path $resolvedStage "tools"), `
    (Join-Path $resolvedStage "docs") | Out-Null

$required = @(
    "mql5\StraddleObserver.mq5",
    "mql5\StraddleObserver.ex5",
    "monitor\observer-startup.ini",
    "requirements-monitor.txt",
    "scripts\install_observer.ps1",
    "scripts\start_live_monitor.ps1",
    "scripts\stop_live_monitor.ps1",
    "scripts\install_monitor_task.ps1",
    "scripts\create_monitor_terminal.ps1",
    "scripts\install_vps_monitor.ps1",
    "deploy\linux\check_monitor_health.py",
    "deploy\linux\monitor_watchdog.sh",
    "deploy\linux\requirements-wine.txt",
    "deploy\linux\run_daily_analysis.sh",
    "deploy\linux\run_demo_analysis.sh",
    "deploy\linux\run_mt5_observer.sh",
    "deploy\linux\run_python_monitor.sh",
    "deploy\linux\straddle-daily-analysis.service",
    "deploy\linux\straddle-daily-analysis.timer",
    "deploy\linux\straddle-demo-daily-analysis.service",
    "deploy\linux\straddle-demo-daily-analysis.timer",
    "deploy\linux\straddle-mt5.service",
    "deploy\linux\straddle-python.service",
    "deploy\linux\straddle-watchdog.service",
    "deploy\linux\straddle-watchdog.timer",
    "deploy\linux\straddle-xvfb.service",
    "deploy\linux\verify_wine_monitor.py",
    "tools\analyze_live_capture.py",
    "tools\compare_live_target_demo.py",
    "docs\LIVE_MONITORING.md"
)
foreach ($relative in $required) {
    $source = Join-Path $resolvedWorkspace $relative
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "Required monitor file is missing: '$source'."
    }
    $destination = Join-Path $resolvedStage $relative
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destination) |
        Out-Null
    Copy-Item -LiteralPath $source -Destination $destination -Force
}

Get-ChildItem -LiteralPath (Join-Path $resolvedWorkspace "straddle_replica") `
    -Filter "*.py" -File |
    Copy-Item -Destination (Join-Path $resolvedStage "straddle_replica") -Force

$outputDirectory = Split-Path -Parent $OutputPath
New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null
if (Test-Path -LiteralPath $OutputPath) {
    Remove-Item -LiteralPath $OutputPath -Force
}
Compress-Archive `
    -Path (Join-Path $resolvedStage "*") `
    -DestinationPath $OutputPath `
    -CompressionLevel Optimal

Remove-Item -LiteralPath $resolvedStage -Recurse -Force
$archive = Get-Item -LiteralPath $OutputPath
Write-Host "Created monitor package: $($archive.FullName)"
Write-Host "Archive size: $($archive.Length) bytes"
