param(
    [Parameter(Mandatory = $true)]
    [long]$ExpectedDemoLogin,
    [Parameter(Mandatory = $true)]
    [string]$Mt5InstallerPath,
    [string]$Workspace = "",
    [string]$MetaEditorPath = "C:\Program Files\MetaTrader 5\MetaEditor64.exe",
    [string]$OutputPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($ExpectedDemoLogin -le 0) {
    throw "ExpectedDemoLogin must be a positive demo login."
}
if ($ExpectedDemoLogin -eq 5054216668) {
    throw "The existing replica demo login cannot be reused."
}
if (-not (Test-Path -LiteralPath $Mt5InstallerPath -PathType Leaf)) {
    throw "Mt5InstallerPath must reference an operator-supplied installer."
}
if ([string]::IsNullOrWhiteSpace($Workspace)) {
    $Workspace = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}
$Workspace = [System.IO.Path]::GetFullPath($Workspace)
$artifactRoot = Join-Path $Workspace "artifacts"
if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $OutputPath = Join-Path $artifactRoot (
        "StraddleReplica-FIDELITY-CANDIDATE.zip"
    )
}

& (Join-Path $Workspace "scripts\build.ps1") `
    -Workspace $Workspace `
    -MetaEditorPath $MetaEditorPath

$stage = Join-Path $artifactRoot "fidelity-candidate-staging"
$artifactFull = [System.IO.Path]::GetFullPath($artifactRoot).TrimEnd("\") + "\"
$stageFull = [System.IO.Path]::GetFullPath($stage)
if (-not $stageFull.StartsWith(
    $artifactFull,
    [System.StringComparison]::OrdinalIgnoreCase
)) {
    throw "Unsafe candidate staging path."
}
if (Test-Path -LiteralPath $stageFull) {
    Remove-Item -LiteralPath $stageFull -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $stageFull | Out-Null

$files = @(
    @{
        Source = "mql5\StraddleReplica.ex5"
        Destination = "candidate\StraddleReplica.ex5"
    },
    @{
        Source = "profiles\latest_30_shadow.set"
        Destination = "candidate\latest_30_shadow.set"
    },
    @{
        Source = "profiles\latest_30_fidelity.set"
        Destination = "candidate\latest_30_fidelity.set"
    },
    @{
        Source = "profiles\latest_30_real_safe.set"
        Destination = "candidate\latest_30_real_safe.set"
    },
    @{
        Source = "monitor\fidelity-candidate-startup.ini"
        Destination = "candidate\fidelity-candidate-startup.ini"
    },
    @{
        Source = "deploy\vps-docker-candidate\compose.yaml"
        Destination = "compose.yaml"
    },
    @{
        Source = "deploy\vps-docker\Dockerfile"
        Destination = "image\Dockerfile"
    },
    @{
        Source = "deploy\vps-docker\entrypoint.sh"
        Destination = "image\entrypoint.sh"
    },
    @{
        Source = "docs\LIVE_TWIN.md"
        Destination = "docs\LIVE_TWIN.md"
    },
    @{
        Source = "docs\FIDELITY.md"
        Destination = "docs\FIDELITY.md"
    }
)
foreach ($entry in $files) {
    $source = Join-Path $Workspace $entry.Source
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "Required candidate file is missing: $($entry.Source)"
    }
    $destination = Join-Path $stageFull $entry.Destination
    New-Item -ItemType Directory -Force `
        -Path (Split-Path -Parent $destination) | Out-Null
    Copy-Item -LiteralPath $source -Destination $destination -Force
}

$installerDestination = Join-Path $stageFull "candidate\mt5-installer.exe"
Copy-Item `
    -LiteralPath $Mt5InstallerPath `
    -Destination $installerDestination `
    -Force

$shadowPreset = Join-Path $stageFull "candidate\latest_30_shadow.set"
$shadowText = Get-Content -LiteralPath $shadowPreset -Raw
if ($shadowText -notmatch "(?m)^ExpectedAccountLogin=0\s*$") {
    throw "Shadow preset is not an unbound template."
}
$shadowText = $shadowText.Replace(
    "ExpectedAccountLogin=0",
    "ExpectedAccountLogin=$ExpectedDemoLogin"
)
Set-Content -LiteralPath $shadowPreset -Value $shadowText -Encoding Ascii

foreach ($template in @(
    "candidate\latest_30_fidelity.set",
    "candidate\latest_30_real_safe.set"
)) {
    $text = Get-Content -LiteralPath (Join-Path $stageFull $template) -Raw
    if (
        $text -notmatch "(?m)^RequireBoundAccount=true\s*$" -or
        $text -notmatch "(?m)^ExpectedAccountLogin=0\s*$"
    ) {
        throw "A real-account preset template is not fail-closed."
    }
}

$forbidden = Get-ChildItem $stageFull -Recurse -File |
    Where-Object {
        $_.Extension.ToLowerInvariant() -in @(".mq5", ".mqh") -or
        $_.Name -match "(?i)password|credential|secret"
    }
if ($forbidden) {
    throw "Candidate package contains forbidden source or secret files."
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
    throw "Candidate output must remain under the artifacts directory."
}
New-Item -ItemType Directory -Force `
    -Path (Split-Path -Parent $outputFull) | Out-Null
if (Test-Path -LiteralPath $outputFull) {
    Remove-Item -LiteralPath $outputFull -Force
}
& python -m straddle_replica.portable_zip `
    --source $stageFull `
    --output $outputFull
if ($LASTEXITCODE -ne 0) {
    throw "Portable candidate ZIP creation failed."
}
Remove-Item -LiteralPath $stageFull -Recurse -Force

$archive = Get-Item -LiteralPath $outputFull
$archiveHash = (
    Get-FileHash -LiteralPath $outputFull -Algorithm SHA256
).Hash
Write-Host "Created fidelity candidate: $($archive.FullName)"
Write-Host "Archive size: $($archive.Length) bytes"
Write-Host "ZIP SHA256: $archiveHash"
