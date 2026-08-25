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
    $OutputPath = Join-Path $Workspace "artifacts\StraddleReplicaDemoVPS.zip"
}

$artifactRoot = Join-Path $Workspace "artifacts"
$stage = Join-Path $artifactRoot "demo-vps-package-staging"
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

$files = @{
    "mql5\StraddleReplica.ex5" = "StraddleReplica.ex5"
    "profiles\latest_30.set" = "LATEST_30_exact.set"
    "monitor\demo-startup.ini" = "demo-startup.ini"
    "deploy\linux\run_mt5_demo.sh" = "run_mt5_demo.sh"
    "deploy\linux\straddle-demo-mt5.service" = "straddle-demo-mt5.service"
}
foreach ($entry in $files.GetEnumerator()) {
    $source = Join-Path $resolvedWorkspace $entry.Key
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "Required demo file is missing: '$source'."
    }
    Copy-Item -LiteralPath $source -Destination (
        Join-Path $resolvedStage $entry.Value
    ) -Force
}

$outputDirectory = Split-Path -Parent $OutputPath
New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null
if (Test-Path -LiteralPath $OutputPath) {
    Remove-Item -LiteralPath $OutputPath -Force
}
Compress-Archive -Path (Join-Path $resolvedStage "*") `
    -DestinationPath $OutputPath -CompressionLevel Optimal
Remove-Item -LiteralPath $resolvedStage -Recurse -Force

$archive = Get-Item -LiteralPath $OutputPath
Write-Host "Created isolated demo VPS package: $($archive.FullName)"
Write-Host "Archive size: $($archive.Length) bytes"
