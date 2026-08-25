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
    & (Join-Path $PSScriptRoot "build_observer.ps1") -Workspace $Workspace
}

$sourcePath = Join-Path $Workspace "mql5\StraddleObserver.mq5"
$binaryPath = Join-Path $Workspace "mql5\StraddleObserver.ex5"
$target = Join-Path $TerminalDataPath "MQL5\Experts\StraddleObserver"

foreach ($required in @($sourcePath, $binaryPath)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Required observer artifact was not found: '$required'."
    }
}
if (-not (Test-Path -LiteralPath (Join-Path $TerminalDataPath "MQL5") -PathType Container)) {
    throw "'$TerminalDataPath' is not an MT5 data directory."
}

New-Item -ItemType Directory -Force -Path $target | Out-Null
Copy-Item -LiteralPath $sourcePath -Destination $target -Force
Copy-Item -LiteralPath $binaryPath -Destination $target -Force

Write-Host "Installed read-only observer: $target"
Write-Host "No chart was changed and no trading operation was requested."

