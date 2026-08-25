param(
    [Parameter(Mandatory = $true)]
    [long]$ExpectedDemoLogin,
    [Parameter(Mandatory = $true)]
    [string]$Mt5InstallerPath,
    [string]$Workspace = "",
    [string]$MetaEditorPath = "C:\Program Files\MetaTrader 5\MetaEditor64.exe",
    [string]$PythonPath = "",
    [string]$OutputPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($ExpectedDemoLogin -le 0) {
    throw "ExpectedDemoLogin must be a positive demo login."
}
$forbiddenLogins = @(901018, 5054216668, 5054283907)
if ($ExpectedDemoLogin -in $forbiddenLogins) {
    throw "ExpectedDemoLogin must be a newly created dedicated demo login."
}
if (-not (Test-Path -LiteralPath $Mt5InstallerPath -PathType Leaf)) {
    throw "Mt5InstallerPath must reference an operator-supplied installer."
}
if ([string]::IsNullOrWhiteSpace($Workspace)) {
    $Workspace = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}
if ([string]::IsNullOrWhiteSpace($PythonPath)) {
    $pathCommand = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($null -ne $pathCommand) {
        $PythonPath = $pathCommand.Source
    }
    else {
        $PythonPath = (
            "$env:USERPROFILE\.cache\codex-runtimes\" +
            "codex-primary-runtime\dependencies\python\python.exe"
        )
    }
}
if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
    throw "Python runtime was not found: $PythonPath"
}

$Workspace = [System.IO.Path]::GetFullPath($Workspace)
$artifactRoot = Join-Path $Workspace "artifacts"
if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $OutputPath = Join-Path $artifactRoot (
        "StraddleReplica-INDEPENDENT-DEMO.zip"
    )
}

& (Join-Path $Workspace "scripts\build.ps1") `
    -Workspace $Workspace `
    -MetaEditorPath $MetaEditorPath

$stage = Join-Path $artifactRoot "independent-demo-staging"
$artifactFull = [System.IO.Path]::GetFullPath($artifactRoot).TrimEnd("\") + "\"
$stageFull = [System.IO.Path]::GetFullPath($stage)
if (-not $stageFull.StartsWith(
    $artifactFull,
    [System.StringComparison]::OrdinalIgnoreCase
)) {
    throw "Unsafe independent-demo staging path."
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
        Source = "profiles\latest_30_independent_demo.set"
        Destination = "candidate\latest_30_independent_demo.set"
    },
    @{
        Source = "monitor\independent-demo-commissioning.ini"
        Destination = "candidate\independent-demo-commissioning.ini"
    },
    @{
        Source = "monitor\independent-demo-startup.ini"
        Destination = "candidate\independent-demo-startup.ini"
    },
    @{
        Source = "deploy\vps-docker-independent\compose.yaml"
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
        Source = "docs\FIDELITY.md"
        Destination = "docs\FIDELITY.md"
    }
)
foreach ($entry in $files) {
    $source = Join-Path $Workspace $entry.Source
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "Required independent-demo file is missing: $($entry.Source)"
    }
    $destination = Join-Path $stageFull $entry.Destination
    New-Item -ItemType Directory -Force `
        -Path (Split-Path -Parent $destination) | Out-Null
    Copy-Item -LiteralPath $source -Destination $destination -Force
}
Copy-Item `
    -LiteralPath $Mt5InstallerPath `
    -Destination (Join-Path $stageFull "candidate\mt5-installer.exe") `
    -Force

$presetPath = Join-Path (
    $stageFull
) "candidate\latest_30_independent_demo.set"
$preset = Get-Content -LiteralPath $presetPath -Raw
foreach ($requiredLine in @(
    "RuntimeMode=0",
    "RequireDemoAccount=true",
    "RequireBoundAccount=true",
    "ExpectedAccountLogin=0"
)) {
    if ($preset -notmatch (
        "(?m)^" + [regex]::Escape($requiredLine) + "\s*$"
    )) {
        throw "Independent preset is not a fail-closed template: $requiredLine"
    }
}
if ($preset -match "(?im)RuntimeMode=1|ShadowCommandFile|ShadowAckFile") {
    throw "Independent preset contains forbidden shadow configuration."
}
$preset = $preset.Replace(
    "ExpectedAccountLogin=0",
    "ExpectedAccountLogin=$ExpectedDemoLogin"
)
Set-Content -LiteralPath $presetPath -Value $preset -Encoding Ascii

$configurationFiles = Get-ChildItem `
    -LiteralPath $stageFull `
    -Recurse `
    -File |
    Where-Object { $_.Extension -in @(".set", ".ini") }
foreach ($configuration in $configurationFiles) {
    $text = Get-Content -LiteralPath $configuration.FullName -Raw
    if ($text -match "(?im)RuntimeMode=1|ShadowCommandFile|ShadowAckFile") {
        throw "Package contains forbidden shadow configuration."
    }
}

$forbidden = Get-ChildItem -LiteralPath $stageFull -Recurse -File |
    Where-Object {
        $_.Extension.ToLowerInvariant() -in @(".mq5", ".mqh") -or
        $_.Name -match "(?i)password|credential|secret"
    }
if ($forbidden) {
    throw "Independent package contains source or credential files."
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
    throw "Independent package output must remain under artifacts."
}
New-Item -ItemType Directory -Force `
    -Path (Split-Path -Parent $outputFull) | Out-Null
if (Test-Path -LiteralPath $outputFull) {
    Remove-Item -LiteralPath $outputFull -Force
}
& $PythonPath -m straddle_replica.portable_zip `
    --source $stageFull `
    --output $outputFull
if ($LASTEXITCODE -ne 0) {
    throw "Portable independent-demo ZIP creation failed."
}
Remove-Item -LiteralPath $stageFull -Recurse -Force

$archive = Get-Item -LiteralPath $outputFull
$archiveHash = (
    Get-FileHash -LiteralPath $outputFull -Algorithm SHA256
).Hash
Write-Host "Created independent demo package: $($archive.FullName)"
Write-Host "Archive size: $($archive.Length) bytes"
Write-Host "ZIP SHA256: $archiveHash"
