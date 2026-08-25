param(
    [string]$Workspace = "",
    [string]$MetaEditorPath = "C:\Program Files\MetaTrader 5\MetaEditor64.exe"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($Workspace)) {
    $Workspace = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}
$Workspace = [System.IO.Path]::GetFullPath($Workspace)

$buildScript = Join-Path $Workspace "scripts\build_real.ps1"
& $buildScript -Workspace $Workspace -MetaEditorPath $MetaEditorPath

$artifactsRoot = Join-Path $Workspace "artifacts"
$realRoot = Join-Path $artifactsRoot "real"
$bundleName = "StraddleReplica-REAL-CANDIDATE-20260810"
$bundlePath = Join-Path $realRoot $bundleName
$sourcePath = Join-Path $bundlePath "Source"
$includePath = Join-Path $sourcePath "include"
$zipPath = Join-Path $artifactsRoot "StraddleReplica-REAL-CANDIDATE-20260810.zip"

$realRootFull = [System.IO.Path]::GetFullPath($realRoot).TrimEnd("\") + "\"
$bundleFull = [System.IO.Path]::GetFullPath($bundlePath)
if (-not $bundleFull.StartsWith(
    $realRootFull,
    [System.StringComparison]::OrdinalIgnoreCase
)) {
    throw "Refusing to recreate bundle outside '$realRootFull'."
}

if (Test-Path -LiteralPath $bundleFull) {
    Remove-Item -LiteralPath $bundleFull -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $includePath | Out-Null

Copy-Item `
    -LiteralPath (Join-Path $Workspace "mql5\StraddleReplicaReal.ex5") `
    -Destination (Join-Path $bundlePath "StraddleReplica_REAL_EXACT.ex5")
Copy-Item `
    -LiteralPath (Join-Path $Workspace "profiles\latest_30_real_exact.set") `
    -Destination (Join-Path $bundlePath "LATEST_30_REAL_EXACT.set")
Copy-Item `
    -LiteralPath (Join-Path $Workspace "docs\REAL_EXACT.md") `
    -Destination (Join-Path $bundlePath "README-REAL-EXACT.md")
Copy-Item `
    -LiteralPath (Join-Path $Workspace "monitor\real-vps-startup.ini") `
    -Destination (Join-Path $bundlePath "real-vps-startup.ini")
Copy-Item `
    -LiteralPath (Join-Path $Workspace "mql5\StraddleReplicaReal.mq5") `
    -Destination (Join-Path $sourcePath "StraddleReplicaReal.mq5")

foreach ($name in @(
    "StraddleReplicaApp.mqh",
    "StraddleTypes.mqh",
    "StraddleEngine.mqh",
    "ProfileCatalog.mqh",
    "TradeGateway.mqh"
)) {
    Copy-Item `
        -LiteralPath (Join-Path $Workspace "mql5\include\$name") `
        -Destination (Join-Path $includePath $name)
}

$hashLines = Get-ChildItem -LiteralPath $bundlePath -Recurse -File |
    Sort-Object FullName |
    ForEach-Object {
        $relative = $_.FullName.Substring($bundleFull.Length + 1).Replace("\", "/")
        $hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
        "$hash  $relative"
    }
Set-Content `
    -LiteralPath (Join-Path $bundlePath "SHA256SUMS.txt") `
    -Value $hashLines `
    -Encoding Ascii

$zipFull = [System.IO.Path]::GetFullPath($zipPath)
$artifactsFull = [System.IO.Path]::GetFullPath($artifactsRoot).TrimEnd("\") + "\"
if (-not $zipFull.StartsWith(
    $artifactsFull,
    [System.StringComparison]::OrdinalIgnoreCase
)) {
    throw "Refusing to create ZIP outside '$artifactsFull'."
}
if (Test-Path -LiteralPath $zipFull) {
    Remove-Item -LiteralPath $zipFull -Force
}
Compress-Archive `
    -Path (Join-Path $bundlePath "*") `
    -DestinationPath $zipFull `
    -CompressionLevel Optimal

$zip = Get-Item -LiteralPath $zipFull
$zipHash = (Get-FileHash -LiteralPath $zipFull -Algorithm SHA256).Hash
Write-Host "Packaged real-account candidate: $($zip.FullName) ($($zip.Length) bytes)"
Write-Host "ZIP SHA256: $zipHash"
