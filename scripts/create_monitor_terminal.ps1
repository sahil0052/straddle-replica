param(
    [string]$Workspace = "",
    [string]$SourceTerminalPath = "C:\Program Files\MetaTrader 5\terminal64.exe",
    [string]$TargetRoot = "D:\MT5ObserverTerminal",
    [switch]$RecoverPartial
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($Workspace)) {
    $Workspace = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}
if (-not (Test-Path -LiteralPath $SourceTerminalPath -PathType Leaf)) {
    throw "Source terminal was not found at '$SourceTerminalPath'."
}

$sourceRoot = Split-Path -Parent (Resolve-Path -LiteralPath $SourceTerminalPath)
$targetFullPath = [System.IO.Path]::GetFullPath($TargetRoot)
$markerPath = Join-Path $targetFullPath ".straddle-observer-terminal.json"
$creatingMarkerPath = Join-Path $targetFullPath ".straddle-observer-creating.json"
if (Test-Path -LiteralPath $targetFullPath) {
    if (-not (Test-Path -LiteralPath $markerPath -PathType Leaf)) {
        if (-not (Test-Path -LiteralPath $creatingMarkerPath -PathType Leaf)) {
            if (-not $RecoverPartial) {
                throw "Target exists without the observer marker: '$targetFullPath'."
            }
            if (-not (Test-Path -LiteralPath (Join-Path $targetFullPath "terminal64.exe") -PathType Leaf)) {
                throw "Partial recovery refused because terminal64.exe is absent."
            }
            @{
                created_at_utc = [DateTime]::UtcNow.ToString("o")
                target = $targetFullPath
                recovered = $true
            } | ConvertTo-Json | Set-Content `
                -LiteralPath $creatingMarkerPath `
                -Encoding UTF8
        }
    }
} else {
    New-Item -ItemType Directory -Force -Path $targetFullPath | Out-Null
}

if (-not (Test-Path -LiteralPath $markerPath -PathType Leaf)) {
    @{
        created_at_utc = [DateTime]::UtcNow.ToString("o")
        target = $targetFullPath
    } | ConvertTo-Json | Set-Content `
        -LiteralPath $creatingMarkerPath `
        -Encoding UTF8

    foreach ($fileName in @(
        "terminal64.exe",
        "MetaEditor64.exe",
        "metatester64.exe",
        "Terminal.ico",
        "terminal.lic"
    )) {
        $source = Join-Path $sourceRoot $fileName
        if (Test-Path -LiteralPath $source -PathType Leaf) {
            Copy-Item -LiteralPath $source -Destination $targetFullPath -Force
        }
    }

    foreach ($directoryName in @("Config", "Profiles", "Sounds")) {
        $source = Join-Path $sourceRoot $directoryName
        $destination = Join-Path $targetFullPath $directoryName
        if ((Test-Path -LiteralPath $source -PathType Container) -and
            -not (Test-Path -LiteralPath $destination -PathType Container)) {
            Copy-Item -LiteralPath $source -Destination $targetFullPath -Recurse
        }
    }
    New-Item -ItemType Directory -Force -Path (Join-Path $targetFullPath "Bases") |
        Out-Null
}

$observerTarget = Join-Path $targetFullPath "MQL5\Experts\StraddleObserver"
New-Item -ItemType Directory -Force -Path `
    $observerTarget, `
    (Join-Path $targetFullPath "MQL5\Presets"), `
    (Join-Path $targetFullPath "MQL5\Files"), `
    (Join-Path $targetFullPath "MQL5\Logs") | Out-Null

foreach ($fileName in @("StraddleObserver.mq5", "StraddleObserver.ex5")) {
    $source = Join-Path $Workspace "mql5\$fileName"
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "Observer artifact was not found at '$source'."
    }
    Copy-Item -LiteralPath $source -Destination $observerTarget -Force
}

@{
    schema_version = 1
    created_at_utc = [DateTime]::UtcNow.ToString("o")
    source_terminal = $SourceTerminalPath
    mode = "isolated-read-only-observer"
} | ConvertTo-Json | Set-Content -LiteralPath $markerPath -Encoding UTF8
if (Test-Path -LiteralPath $creatingMarkerPath) {
    Remove-Item -LiteralPath $creatingMarkerPath -Force
}

Write-Host "Prepared isolated monitoring terminal: $targetFullPath"
Write-Host "Installed observer only; no strategy EA was copied."
