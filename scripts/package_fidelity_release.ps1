param(
    [Parameter(Mandatory = $true)]
    [long]$ExpectedRealLogin,
    [string]$Workspace = "",
    [string]$MetaEditorPath = "C:\Program Files\MetaTrader 5\MetaEditor64.exe",
    [string]$OutputPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($ExpectedRealLogin -le 0) {
    throw "ExpectedRealLogin must be a positive real-account login."
}
if ([string]::IsNullOrWhiteSpace($Workspace)) {
    $Workspace = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}
$Workspace = [System.IO.Path]::GetFullPath($Workspace)
$artifactRoot = Join-Path $Workspace "artifacts"
if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $OutputPath = Join-Path $artifactRoot (
        "StraddleReplica-FIDELITY-RELEASE.zip"
    )
}

& (Join-Path $Workspace "scripts\build_real.ps1") `
    -Workspace $Workspace `
    -MetaEditorPath $MetaEditorPath

$stage = Join-Path $artifactRoot "fidelity-release-staging"
$artifactFull = [System.IO.Path]::GetFullPath($artifactRoot).TrimEnd("\") + "\"
$stageFull = [System.IO.Path]::GetFullPath($stage)
if (-not $stageFull.StartsWith(
    $artifactFull,
    [System.StringComparison]::OrdinalIgnoreCase
)) {
    throw "Unsafe release staging path."
}
if (Test-Path -LiteralPath $stageFull) {
    Remove-Item -LiteralPath $stageFull -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $stageFull | Out-Null

$files = @(
    @{
        Source = "mql5\StraddleReplicaReal.ex5"
        Destination = "StraddleReplicaReal.ex5"
    },
    @{
        Source = "profiles\latest_30_fidelity.set"
        Destination = "latest_30_fidelity.set"
    },
    @{
        Source = "profiles\latest_30_real_safe.set"
        Destination = "latest_30_real_safe.set"
    },
    @{
        Source = "docs\FIDELITY.md"
        Destination = "FIDELITY.md"
    },
    @{
        Source = "docs\REAL_EXACT.md"
        Destination = "REAL_ACCOUNT_NOTES.md"
    }
)
foreach ($entry in $files) {
    $source = Join-Path $Workspace $entry.Source
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "Required release file is missing: $($entry.Source)"
    }
    Copy-Item `
        -LiteralPath $source `
        -Destination (Join-Path $stageFull $entry.Destination) `
        -Force
}

foreach ($presetName in @(
    "latest_30_fidelity.set",
    "latest_30_real_safe.set"
)) {
    $presetPath = Join-Path $stageFull $presetName
    $text = Get-Content -LiteralPath $presetPath -Raw
    if (
        $text -notmatch "(?m)^RequireBoundAccount=true\s*$" -or
        $text -notmatch "(?m)^ExpectedAccountLogin=0\s*$"
    ) {
        throw "Release preset is not an unbound fail-closed template."
    }
    $text = $text.Replace(
        "ExpectedAccountLogin=0",
        "ExpectedAccountLogin=$ExpectedRealLogin"
    )
    Set-Content -LiteralPath $presetPath -Value $text -Encoding Ascii
}

$forbidden = Get-ChildItem $stageFull -Recurse -File |
    Where-Object {
        $_.Extension.ToLowerInvariant() -in @(".mq5", ".mqh") -or
        $_.Name -match "(?i)password|credential|secret"
    }
if ($forbidden) {
    throw "Release package contains forbidden source or secret files."
}

$hashLines = Get-ChildItem -LiteralPath $stageFull -Recurse -File |
    Sort-Object FullName |
    ForEach-Object {
        $relative = $_.FullName.Substring($stageFull.Length + 1).
            Replace("\", "/")
        $hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
        "$hash  $relative"
    }
Set-Content `
    -LiteralPath (Join-Path $stageFull "SHA256SUMS.txt") `
    -Value $hashLines `
    -Encoding Ascii

$outputFull = [System.IO.Path]::GetFullPath($OutputPath)
if (-not $outputFull.StartsWith(
    $artifactFull,
    [System.StringComparison]::OrdinalIgnoreCase
)) {
    throw "Release output must remain under the artifacts directory."
}
if (Test-Path -LiteralPath $outputFull) {
    Remove-Item -LiteralPath $outputFull -Force
}
Compress-Archive `
    -Path (Join-Path $stageFull "*") `
    -DestinationPath $outputFull `
    -CompressionLevel Optimal
Remove-Item -LiteralPath $stageFull -Recurse -Force

$archive = Get-Item -LiteralPath $outputFull
$archiveHash = (
    Get-FileHash -LiteralPath $outputFull -Algorithm SHA256
).Hash
Write-Host "Created fidelity release: $($archive.FullName)"
Write-Host "Archive size: $($archive.Length) bytes"
Write-Host "ZIP SHA256: $archiveHash"
