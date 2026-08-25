param(
    [string]$Workspace = "",
    [string]$MetaEditorPath = "C:\Program Files\MetaTrader 5\MetaEditor64.exe"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($Workspace)) {
    $Workspace = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

$sourcePath = Join-Path $Workspace "mql5\StraddleReplicaReal.mq5"
$outputPath = Join-Path $Workspace "mql5\StraddleReplicaReal.ex5"
$logPath = Join-Path $Workspace "artifacts\compile-real.log"

if (-not (Test-Path -LiteralPath $MetaEditorPath -PathType Leaf)) {
    throw "MetaEditor64.exe was not found at '$MetaEditorPath'."
}
if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
    throw "Real EA source was not found at '$sourcePath'."
}

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $logPath) |
    Out-Null
if (Test-Path -LiteralPath $logPath) {
    Remove-Item -LiteralPath $logPath -Force
}

$arguments = @(
    "/compile:`"$sourcePath`"",
    "/log:`"$logPath`""
)
$process = Start-Process `
    -FilePath $MetaEditorPath `
    -ArgumentList $arguments `
    -Wait `
    -PassThru `
    -WindowStyle Hidden

if (-not (Test-Path -LiteralPath $logPath -PathType Leaf)) {
    throw "MetaEditor did not produce the real compile log '$logPath' (exit code $($process.ExitCode))."
}

$compileLog = Get-Content -LiteralPath $logPath -Raw
if ($compileLog -notmatch "Result:\s+0 errors,\s+0 warnings") {
    throw "Real EA compilation failed. Review '$logPath'."
}
if (-not (Test-Path -LiteralPath $outputPath -PathType Leaf)) {
    throw "MetaEditor reported success but '$outputPath' was not produced."
}

$artifact = Get-Item -LiteralPath $outputPath
Write-Host "Compiled StraddleReplicaReal: $($artifact.FullName) ($($artifact.Length) bytes)"
Write-Host "Compiler result: 0 errors, 0 warnings"
