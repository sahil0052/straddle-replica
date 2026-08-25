param(
    [string]$Workspace = "",
    [string]$MetaEditorPath = "C:\Program Files\MetaTrader 5\MetaEditor64.exe",
    [UInt64]$AccountLogin = 0,
    [string]$BrokerServer = "",
    [string]$TradeSymbol = "",
    [string]$OutputDirectory = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($AccountLogin -eq 0) {
    throw "AccountLogin must be a non-zero account number."
}
if ([string]::IsNullOrWhiteSpace($BrokerServer)) {
    throw "BrokerServer is required."
}
if ([string]::IsNullOrWhiteSpace($TradeSymbol)) {
    throw "TradeSymbol is required."
}

$BrokerServer = $BrokerServer.Trim()
$TradeSymbol = $TradeSymbol.Trim()
if ($BrokerServer -match "[`r`n]") {
    throw "BrokerServer must be a single line."
}
if ($TradeSymbol -match "[`r`n]") {
    throw "TradeSymbol must be a single line."
}

if ([string]::IsNullOrWhiteSpace($Workspace)) {
    $Workspace = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}
$Workspace = [System.IO.Path]::GetFullPath($Workspace)

if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $OutputDirectory = Join-Path $Workspace "artifacts"
}
$OutputDirectory = [System.IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null

$buildScript = Join-Path $Workspace "scripts\build_real.ps1"
$testerPresetHelper = Join-Path `
    $Workspace `
    "scripts\prepare_real_bound_tester_preset.ps1"
$safePreset = Join-Path $Workspace "profiles\latest_30_real_safe.set"
$compiledExpert = Join-Path $Workspace "mql5\StraddleReplicaReal.ex5"

foreach ($requiredPath in @(
    $buildScript,
    $testerPresetHelper,
    $safePreset
)) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
        throw "Required release input was not found: $requiredPath"
    }
}

& $buildScript -Workspace $Workspace -MetaEditorPath $MetaEditorPath
if (-not (Test-Path -LiteralPath $compiledExpert -PathType Leaf)) {
    throw "Compiled real-account expert was not produced: $compiledExpert"
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
        throw "Expected exactly one '$Name' setting in the safe preset."
    }
    return [regex]::Replace($Content, $pattern, "$Name=$Value")
}

$presetContent = Get-Content -LiteralPath $safePreset -Raw
$presetContent = Set-RequiredSetting $presetContent "TradeSymbol" $TradeSymbol
$presetContent = Set-RequiredSetting $presetContent "RequireDemoAccount" "false"
$presetContent = Set-RequiredSetting $presetContent "RequireBoundAccount" "true"
$presetContent = Set-RequiredSetting `
    $presetContent `
    "ExpectedAccountLogin" `
    ([string]$AccountLogin)
$presetContent = Set-RequiredSetting $presetContent "SafetyEnabled" "true"

$stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
$bundleName = "StraddleReplica-REAL-$AccountLogin-20S-$stamp"
$bundlePath = Join-Path $OutputDirectory $bundleName
$zipPath = Join-Path $OutputDirectory "$bundleName.zip"

$outputPrefix = $OutputDirectory.TrimEnd("\") + "\"
$bundleFull = [System.IO.Path]::GetFullPath($bundlePath)
$zipFull = [System.IO.Path]::GetFullPath($zipPath)
foreach ($target in @($bundleFull, $zipFull)) {
    if (-not $target.StartsWith(
        $outputPrefix,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Refusing to create a release outside '$OutputDirectory'."
    }
}
if ((Test-Path -LiteralPath $bundleFull) -or
    (Test-Path -LiteralPath $zipFull)) {
    throw "Release output already exists: $bundleName"
}

New-Item -ItemType Directory -Path $bundleFull | Out-Null
$expertFileName = "StraddleReplica-$AccountLogin.ex5"
$presetFileName = "StraddleReplica-$AccountLogin.set"
$expertPath = Join-Path $bundleFull $expertFileName
$presetPath = Join-Path $bundleFull $presetFileName
$instructionsPath = Join-Path $bundleFull "START-HERE.txt"
$manifestPath = Join-Path $bundleFull "RELEASE.json"
$hashPath = Join-Path $bundleFull "SHA256SUMS.txt"

Copy-Item -LiteralPath $compiledExpert -Destination $expertPath
Set-Content -LiteralPath $presetPath -Value $presetContent -Encoding Ascii
$instructions = @(
    "STRADDLE REPLICA - ACCOUNT-BOUND DELIVERY"
    ""
    "Bound account: $AccountLogin"
    "Broker server: $BrokerServer"
    "Trading symbol: $TradeSymbol"
    ""
    "Use only the EX5 and SET files from this ZIP together."
    "Do not mix either file with an older delivery."
    "Remove every older StraddleReplica EX5 and SET from the terminal folders,"
    "or move them outside MT5, before installing this delivery."
    ""
    "Installation:"
    "1. In MetaTrader 5, open File > Open Data Folder."
    "2. Copy $expertFileName into MQL5\Experts."
    "3. Refresh Navigator or restart MetaTrader 5."
    "4. Attach $expertFileName to a $TradeSymbol chart."
    "5. Load $presetFileName from the EA Inputs tab."
    "6. Verify the displayed ExpectedAccountLogin is $AccountLogin."
    "7. Verify Algo Trading and the EA's algorithmic-trading permission are enabled."
    ""
    "Expected startup behavior:"
    "- The EA first creates 60 pending stop orders: B1,S1 through B30,S30."
    "- It does not open an immediate market position."
    "- Positions appear only when price reaches a pending stop level."
    "- Open the Trade > Orders tab and confirm the pending orders are present."
    ""
    "If no pending orders appear, open the Experts and Journal tabs."
    "The first [STR] message identifies the gate, including an account binding mismatch,"
    "a non-hedging account, an order limit below 60, or an unavailable symbol."
    ""
    "This package contains no password and no source code."
)
Set-Content -LiteralPath $instructionsPath -Value $instructions -Encoding Ascii

$manifest = [ordered]@{
    schema_version = 1
    generated_at_utc = [DateTime]::UtcNow.ToString("o")
    expected_account_login = [string]$AccountLogin
    expected_broker_server = $BrokerServer
    trade_symbol = $TradeSymbol
    lifecycle = [ordered]@{
        close_interval_seconds = 20
        restart_delay_ms = 20000
        basket_target_money = 30.0
    }
    artifacts = [ordered]@{
        expert = $expertFileName
        preset = $presetFileName
        instructions = "START-HERE.txt"
    }
    safety = [ordered]@{
        require_demo_account = $false
        require_bound_account = $true
        safety_enabled = $true
        password_included = $false
        source_included = $false
    }
}
$manifest |
    ConvertTo-Json -Depth 4 |
    Set-Content -LiteralPath $manifestPath -Encoding UTF8

$hashLines = @(
    $expertPath,
    $presetPath,
    $instructionsPath,
    $manifestPath
) |
    ForEach-Object {
        $item = Get-Item -LiteralPath $_
        $hash = (Get-FileHash -LiteralPath $item.FullName -Algorithm SHA256).Hash
        "$hash  $($item.Name)"
    }
Set-Content -LiteralPath $hashPath -Value $hashLines -Encoding Ascii

Compress-Archive `
    -Path (Join-Path $bundleFull "*") `
    -DestinationPath $zipFull `
    -CompressionLevel Optimal

$zipHash = (Get-FileHash -LiteralPath $zipFull -Algorithm SHA256).Hash
Write-Host "Packaged account-bound real release: $zipFull"
Write-Host "ZIP SHA256: $zipHash"
Write-Host (
    "For matching-account Strategy Tester checks, first run " +
    "scripts\prepare_real_bound_tester_preset.ps1 so shared telemetry " +
    "remains disabled."
)
