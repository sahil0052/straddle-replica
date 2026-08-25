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
    $OutputPath = Join-Path $Workspace "artifacts\StraddleLiveTwin.zip"
}

$artifactRoot = Join-Path $Workspace "artifacts"
$stage = Join-Path $artifactRoot "live-twin-package-staging"
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
New-Item -ItemType Directory -Force -Path $resolvedStage | Out-Null

$required = @(
    "mql5\StraddleReplica.ex5",
    "mql5\StraddleTargetProbe.mq5",
    "mql5\StraddleTargetProbe.ex5",
    "profiles\latest_30_shadow.set",
    "monitor\shadow-startup.ini",
    "deploy\linux\run_mt5_shadow.sh",
    "deploy\linux\run_shadow_coordinator.sh",
    "deploy\linux\run_live_twin_analysis.sh",
    "deploy\linux\shadow.env.example",
    "deploy\linux\straddle-shadow-mt5.service",
    "deploy\linux\straddle-shadow-coordinator.service",
    "deploy\linux\straddle-live-twin-analysis.service",
    "deploy\linux\straddle-live-twin-analysis.timer",
    "tools\run_shadow_coordinator.py",
    "tools\compare_live_twin.py",
    "tools\analyze_probe_health.py",
    "tools\compare_account_terms.py",
    "tools\evaluate_live_twin_gate.py",
    "tools\report_best_effort_status.py",
    "docs\LIVE_TWIN.md"
)
foreach ($relative in $required) {
    $source = Join-Path $resolvedWorkspace $relative
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "Required live-twin file is missing: '$source'."
    }
    $destination = Join-Path $resolvedStage $relative
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destination) |
        Out-Null
    Copy-Item -LiteralPath $source -Destination $destination -Force
}

$pythonStage = Join-Path $resolvedStage "straddle_replica"
New-Item -ItemType Directory -Force -Path $pythonStage | Out-Null
Get-ChildItem -LiteralPath (Join-Path $resolvedWorkspace "straddle_replica") `
    -Filter "*.py" -File |
    Copy-Item -Destination $pythonStage -Force

$outputDirectory = Split-Path -Parent $OutputPath
New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null
if (Test-Path -LiteralPath $OutputPath) {
    Remove-Item -LiteralPath $OutputPath -Force
}
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::Open(
    $OutputPath,
    [System.IO.Compression.ZipArchiveMode]::Create
)
try {
    Get-ChildItem -LiteralPath $resolvedStage -Recurse -File |
        Sort-Object FullName |
        ForEach-Object {
            $relative = $_.FullName.Substring($resolvedStage.Length)
            $relative = $relative.TrimStart("\", "/").Replace("\", "/")
            [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
                $zip,
                $_.FullName,
                $relative,
                [System.IO.Compression.CompressionLevel]::Optimal
            ) | Out-Null
        }
}
finally {
    $zip.Dispose()
}
Remove-Item -LiteralPath $resolvedStage -Recurse -Force

$archive = Get-Item -LiteralPath $OutputPath
Write-Host "Created live-twin package: $($archive.FullName)"
Write-Host "Archive size: $($archive.Length) bytes"
