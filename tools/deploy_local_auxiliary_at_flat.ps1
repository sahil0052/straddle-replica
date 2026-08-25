param(
    [Parameter(Mandatory = $true)]
    [string]$TelemetryPath,
    [Parameter(Mandatory = $true)]
    [string]$CycleId,
    [Parameter(Mandatory = $true)]
    [string]$TerminalPath,
    [Parameter(Mandatory = $true)]
    [string]$StartupConfigPath,
    [Parameter(Mandatory = $true)]
    [string]$StagedEx5Path,
    [Parameter(Mandatory = $true)]
    [string]$ExpectedStagedEx5Sha256,
    [Parameter(Mandatory = $true)]
    [string]$ActiveEx5Path,
    [Parameter(Mandatory = $true)]
    [string]$ExpectedActiveEx5Sha256,
    [Parameter(Mandatory = $true)]
    [string]$HealthPath,
    [double]$PollSeconds = 0.25
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-ExistingFile([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Required file is missing: $Path"
    }
    return (Resolve-Path -LiteralPath $Path).Path
}

function Write-Health([hashtable]$Payload) {
    $Payload["updated_at_utc"] = (
        Get-Date
    ).ToUniversalTime().ToString("o")
    $directory = Split-Path -Parent $HealthPath
    New-Item -ItemType Directory -Force -Path $directory | Out-Null
    $temporary = "$HealthPath.tmp"
    $Payload | ConvertTo-Json -Depth 8 |
        Set-Content -LiteralPath $temporary -Encoding UTF8
    Move-Item -LiteralPath $temporary -Destination $HealthPath -Force
}

function Get-CycleLines {
    if (-not (Test-Path -LiteralPath $TelemetryPath -PathType Leaf)) {
        return @()
    }
    return @(
        Get-Content -LiteralPath $TelemetryPath -Tail 5000 |
            Where-Object { $_ -like "*,$CycleId,*" }
    )
}

function Has-Event([string[]]$Lines, [string]$Kind) {
    return @(
        $Lines | Where-Object { $_ -like "*,$Kind,*" }
    ).Count -gt 0
}

if ($PollSeconds -lt 0.1) {
    throw "PollSeconds must be at least 0.1."
}

$TelemetryPath = Resolve-ExistingFile $TelemetryPath
$TerminalPath = Resolve-ExistingFile $TerminalPath
$StartupConfigPath = Resolve-ExistingFile $StartupConfigPath
$StagedEx5Path = Resolve-ExistingFile $StagedEx5Path
$ActiveEx5Path = Resolve-ExistingFile $ActiveEx5Path
$HealthPath = [System.IO.Path]::GetFullPath($HealthPath)

$stagedHash = (
    Get-FileHash -LiteralPath $StagedEx5Path -Algorithm SHA256
).Hash
if ($stagedHash -ne $ExpectedStagedEx5Sha256.ToUpperInvariant()) {
    throw "Staged EX5 SHA256 mismatch."
}
$activeHash = (
    Get-FileHash -LiteralPath $ActiveEx5Path -Algorithm SHA256
).Hash
if ($activeHash -ne $ExpectedActiveEx5Sha256.ToUpperInvariant()) {
    throw "Active EX5 SHA256 mismatch."
}

Write-Health @{
    status = "WAITING_FOR_EXACT_FLAT_BOUNDARY"
    cycle_id = $CycleId
    active_ex5_sha256 = $activeHash
    staged_ex5_sha256 = $stagedHash
}
$lastHealthWriteUtc = [DateTime]::UtcNow

while ($true) {
    $cycleLines = Get-CycleLines
    if (Has-Event $cycleLines "cycle_restart") {
        Write-Health @{
            status = "ABORTED_CYCLE_ALREADY_RESTARTED"
            cycle_id = $CycleId
        }
        exit 2
    }
    if (-not (Has-Event $cycleLines "cycle_complete")) {
        if (
            ([DateTime]::UtcNow - $lastHealthWriteUtc).TotalSeconds -ge 1.0
        ) {
            Write-Health @{
                status = "WAITING_FOR_EXACT_FLAT_BOUNDARY"
                cycle_id = $CycleId
                active_ex5_sha256 = $activeHash
                staged_ex5_sha256 = $stagedHash
            }
            $lastHealthWriteUtc = [DateTime]::UtcNow
        }
        Start-Sleep -Milliseconds ([int]($PollSeconds * 1000))
        continue
    }

    Start-Sleep -Milliseconds 250
    $cycleLines = Get-CycleLines
    if (Has-Event $cycleLines "cycle_restart") {
        Write-Health @{
            status = "ABORTED_RESTART_RACE"
            cycle_id = $CycleId
        }
        exit 3
    }

    $terminalFullPath = [System.IO.Path]::GetFullPath($TerminalPath)
    $terminalProcesses = @(
        Get-CimInstance Win32_Process |
            Where-Object {
                $_.Name -eq "terminal64.exe" -and
                $_.ExecutablePath -eq $terminalFullPath
            }
    )
    if ($terminalProcesses.Count -ne 1) {
        throw (
            "Expected exactly one auxiliary terminal process, found " +
            $terminalProcesses.Count
        )
    }

    $process = Get-Process -Id $terminalProcesses[0].ProcessId
    [void]$process.CloseMainWindow()
    if (-not $process.WaitForExit(10000)) {
        Stop-Process -Id $process.Id -Force
        Wait-Process -Id $process.Id -Timeout 10 -ErrorAction SilentlyContinue
    }

    Copy-Item -LiteralPath $StagedEx5Path -Destination $ActiveEx5Path -Force
    $deployedHash = (
        Get-FileHash -LiteralPath $ActiveEx5Path -Algorithm SHA256
    ).Hash
    if ($deployedHash -ne $stagedHash) {
        throw "Deployed EX5 SHA256 mismatch."
    }

    $started = Start-Process `
        -FilePath $TerminalPath `
        -ArgumentList @(
            "/portable",
            "/config:$StartupConfigPath"
        ) `
        -PassThru `
        -WindowStyle Hidden

    Write-Health @{
        status = "DEPLOYED_AT_FLAT_BOUNDARY"
        cycle_id = $CycleId
        process_id = $started.Id
        deployed_ex5_sha256 = $deployedHash
    }
    exit 0
}
