param(
    [string]$Workspace = "",
    [string]$TerminalDataPath = "C:\Program Files\MetaTrader 5",
    [switch]$SkipBuild
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($Workspace)) {
    $Workspace = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

if (-not $SkipBuild) {
    & (Join-Path $PSScriptRoot "build.ps1") -Workspace $Workspace
}

$sourceRoot = Join-Path $Workspace "mql5"
$profileRoot = Join-Path $Workspace "profiles"
$expertTarget = Join-Path $TerminalDataPath "MQL5\Experts\StraddleReplica"
$includeTarget = Join-Path $expertTarget "include"
$testerProfileTarget = Join-Path $TerminalDataPath "MQL5\Profiles\Tester"

$requiredFiles = @(
    (Join-Path $sourceRoot "StraddleReplica.mq5"),
    (Join-Path $sourceRoot "StraddleReplica.ex5")
)
foreach ($requiredFile in $requiredFiles) {
    if (-not (Test-Path -LiteralPath $requiredFile -PathType Leaf)) {
        throw "Required EA artifact was not found: '$requiredFile'."
    }
}
if (-not (Test-Path -LiteralPath (Join-Path $TerminalDataPath "MQL5") -PathType Container)) {
    throw "'$TerminalDataPath' is not an MT5 data directory. Expected an MQL5 subdirectory."
}

New-Item -ItemType Directory -Force -Path $expertTarget, $includeTarget, $testerProfileTarget | Out-Null

Copy-Item -LiteralPath (Join-Path $sourceRoot "StraddleReplica.mq5") -Destination $expertTarget -Force
Copy-Item -LiteralPath (Join-Path $sourceRoot "StraddleReplica.ex5") -Destination $expertTarget -Force
Get-ChildItem -LiteralPath (Join-Path $sourceRoot "include") -Filter "*.mqh" -File |
    Copy-Item -Destination $includeTarget -Force
Get-ChildItem -LiteralPath $profileRoot -Filter "*.set" -File |
    Copy-Item -Destination $testerProfileTarget -Force

$installedBinary = Join-Path $expertTarget "StraddleReplica.ex5"
Write-Host "Installed EA: $installedBinary"
Write-Host "Installed tester presets: $testerProfileTarget"
Write-Host "No terminal was launched and no EA was attached to a chart."
