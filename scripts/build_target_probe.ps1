param(
    [string]$Workspace = "",
    [string]$MetaEditorPath = "C:\Program Files\MetaTrader 5\MetaEditor64.exe"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($Workspace)) {
    $Workspace = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

$sourcePath = Join-Path $Workspace "mql5\StraddleTargetProbe.mq5"
$outputPath = Join-Path $Workspace "mql5\StraddleTargetProbe.ex5"
$logPath = Join-Path $Workspace "artifacts\target-probe-compile.log"

if (-not (Test-Path -LiteralPath $MetaEditorPath -PathType Leaf)) {
    throw "MetaEditor64.exe was not found at '$MetaEditorPath'."
}
if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
    throw "Target probe source was not found at '$sourcePath'."
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
    throw "MetaEditor did not produce '$logPath' (exit $($process.ExitCode))."
}

$compileLog = Get-Content -LiteralPath $logPath -Raw
if ($compileLog -notmatch "Result:\s+0 errors,\s+0 warnings") {
    throw "Target probe compilation failed. Review '$logPath'."
}
if (-not (Test-Path -LiteralPath $outputPath -PathType Leaf)) {
    throw "Compilation passed but '$outputPath' was not produced."
}

$artifact = Get-Item -LiteralPath $outputPath
Write-Host "Compiled passive target probe: $($artifact.FullName)"
Write-Host "Compiler result: 0 errors, 0 warnings"
