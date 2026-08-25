param(
    [Parameter(Mandatory = $true)]
    [string]$ReleasePreset,

    [Parameter(Mandatory = $true)]
    [UInt64]$TesterAccountLogin,

    [Parameter(Mandatory = $true)]
    [string]$OutputPreset
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($TesterAccountLogin -eq 0) {
    throw "TesterAccountLogin must be a non-zero account number."
}

$releaseFull = [System.IO.Path]::GetFullPath($ReleasePreset)
$outputFull = [System.IO.Path]::GetFullPath($OutputPreset)
if (-not (Test-Path -LiteralPath $releaseFull -PathType Leaf)) {
    throw "Release preset was not found: $releaseFull"
}
if ($releaseFull.Equals(
    $outputFull,
    [System.StringComparison]::OrdinalIgnoreCase
)) {
    throw "OutputPreset must be separate from ReleasePreset."
}

function Set-RequiredSetting {
    param(
        [string]$Content,
        [string]$Name,
        [string]$Value
    )

    $pattern = "(?m)^" + [regex]::Escape($Name) + "=.*$"
    $matches = [regex]::Matches($Content, $pattern)
    if ($matches.Count -ne 1) {
        throw "Expected exactly one '$Name' setting in the release preset."
    }
    return [regex]::Replace($Content, $pattern, "$Name=$Value")
}

$content = Get-Content -LiteralPath $releaseFull -Raw
$content = Set-RequiredSetting `
    $content `
    "ExpectedAccountLogin" `
    ([string]$TesterAccountLogin)
$content = Set-RequiredSetting $content "TelemetryEnabled" "false"
$content = Set-RequiredSetting $content "RequireDemoAccount" "false"
$content = Set-RequiredSetting $content "RequireBoundAccount" "true"
$content = Set-RequiredSetting $content "SafetyEnabled" "true"

$parent = Split-Path -Parent $outputFull
if (-not [string]::IsNullOrWhiteSpace($parent)) {
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
}
Set-Content -LiteralPath $outputFull -Value $content -Encoding Ascii

Write-Host "Prepared telemetry-isolated tester preset: $outputFull"
