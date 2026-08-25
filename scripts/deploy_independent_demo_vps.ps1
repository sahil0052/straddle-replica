param(
    [string]$SshAlias = "nishahomes-vps",
    [Parameter(Mandatory = $true)]
    [string]$PackagePath,
    [string]$RemoteRoot = "/opt/straddle-fidelity-independent-demo",
    [string]$FlatBoundaryHealthPath = (
        "C:\websites\mt5 2\artifacts\live\" +
        "independent-demo-fidelity\flat-boundary-freezer-health.json"
    ),
    [string]$CandidateObserverRoot = (
        "D:\MT5IndependentCandidateData\isolated-live"
    ),
    [switch]$RequireFrozenBoundary,
    [switch]$StartTrading
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($RemoteRoot -ne "/opt/straddle-fidelity-independent-demo") {
    throw "RemoteRoot must be /opt/straddle-fidelity-independent-demo."
}
if (-not (Test-Path -LiteralPath $PackagePath -PathType Leaf)) {
    throw "Independent demo package was not found: $PackagePath"
}
if ($RequireFrozenBoundary) {
    if (-not (
        Test-Path -LiteralPath $FlatBoundaryHealthPath -PathType Leaf
    )) {
        throw "Frozen-boundary health was not found."
    }
    $boundary = Get-Content `
        -LiteralPath $FlatBoundaryHealthPath `
        -Raw |
        ConvertFrom-Json
    if (
        [string]$boundary.status -ne "FLAT_BOUNDARY_FROZEN" -or
        $boundary.ready_for_deployment -ne $true
    ) {
        throw "Candidate flat boundary is not frozen for deployment."
    }
    if (
        [int]$boundary.positions_total -ne 0 -or
        [int]$boundary.orders_total -ne 0
    ) {
        throw "Frozen-boundary health is not flat."
    }
    $packageHash = (
        Get-FileHash -LiteralPath $PackagePath -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    if (
        [string]$boundary.staged_package_sha256 -ne $packageHash
    ) {
        throw "Frozen-boundary package SHA256 does not match."
    }
    $boundaryAgeSeconds = (
        [DateTimeOffset]::UtcNow -
        [DateTimeOffset]::Parse(
            [string]$boundary.updated_at_utc
        ).ToUniversalTime()
    ).TotalSeconds
    if (
        $boundaryAgeSeconds -lt 0 -or
        $boundaryAgeSeconds -gt 3600
    ) {
        throw "Frozen-boundary health is stale."
    }

    $candidateRootFull = (
        [System.IO.Path]::GetFullPath($CandidateObserverRoot)
    ).TrimEnd("\")
    $currentSessionPath = Join-Path `
        $candidateRootFull `
        "current-session.json"
    if (-not (
        Test-Path -LiteralPath $currentSessionPath -PathType Leaf
    )) {
        throw "Candidate observer current session is missing."
    }
    $currentSession = Get-Content `
        -LiteralPath $currentSessionPath `
        -Raw |
        ConvertFrom-Json
    $sessionDirectory = [System.IO.Path]::GetFullPath(
        [string]$currentSession.session_dir
    )
    if (-not $sessionDirectory.StartsWith(
        $candidateRootFull + "\",
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Candidate observer session escaped its root."
    }
    $heartbeat = Get-Content `
        -LiteralPath (Join-Path $sessionDirectory "heartbeat.json") `
        -Raw |
        ConvertFrom-Json
    $manifest = Get-Content `
        -LiteralPath (Join-Path $sessionDirectory "manifest.json") `
        -Raw |
        ConvertFrom-Json
    $heartbeatAgeSeconds = (
        [DateTimeOffset]::UtcNow -
        [DateTimeOffset]::Parse(
            [string]$heartbeat.capture_time_utc
        ).ToUniversalTime()
    ).TotalSeconds
    if (
        $heartbeat.healthy -ne $true -or
        $heartbeat.stopped -eq $true -or
        $heartbeat.read_only_verified -ne $true -or
        $heartbeatAgeSeconds -lt 0 -or
        $heartbeatAgeSeconds -gt 10 -or
        [int]$heartbeat.positions_total -ne 0 -or
        [int]$heartbeat.orders_total -ne 0
    ) {
        throw "Candidate observer heartbeat is not fresh, safe, and flat."
    }
    if (
        [long]$manifest.account.login -ne 110971967 -or
        [string]$manifest.account.server -ne "MetaQuotes-Demo" -or
        $manifest.account.trade_allowed -ne $false -or
        $manifest.terminal.connected -ne $true -or
        $manifest.terminal.trade_allowed -ne $false -or
        $manifest.safety.account_trade_allowed -ne $false -or
        $manifest.safety.collector_has_trading_api -ne $false -or
        $manifest.safety.require_read_only -ne $true
    ) {
        throw "Candidate observer manifest failed read-only safety."
    }
    $snapshotFile = Get-ChildItem `
        -LiteralPath $sessionDirectory `
        -Filter "snapshots-*.jsonl" `
        -File |
        Sort-Object Name |
        Select-Object -Last 1
    if ($null -eq $snapshotFile) {
        throw "Candidate observer snapshot stream is missing."
    }
    $snapshot = Get-Content `
        -LiteralPath $snapshotFile.FullName `
        -Tail 1 |
        ConvertFrom-Json
    if (
        @($snapshot.positions).Count -ne 0 -or
        @($snapshot.orders).Count -ne 0
    ) {
        throw "Latest candidate observer snapshot is not flat."
    }
}

function Invoke-IndependentSsh {
    param([Parameter(Mandatory = $true)][string]$Command)
    $output = & ssh $SshAlias $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Remote independent-demo command failed: $Command"
    }
    return (($output | Out-String).Trim())
}

function Get-ContainerFingerprint {
    param([Parameter(Mandatory = $true)][string]$Name)
    return Invoke-IndependentSsh -Command (
        "docker inspect --format " +
        "'{{.Id}}|{{.State.Status}}|{{.RestartCount}}|{{.State.OOMKilled}}' " +
        $Name
    )
}

function Get-OptionalContainerFingerprint {
    param([Parameter(Mandatory = $true)][string]$Name)
    $containerNames = Invoke-IndependentSsh -Command (
        "docker ps -a --format '{{.Names}}'"
    )
    $nameLines = @(
        $containerNames -split "\r?\n" |
            Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    )
    if ($Name -notin $nameLines) {
        return "MISSING"
    }
    return Get-ContainerFingerprint -Name $Name
}

function Get-NonCandidateContainerSnapshot {
    param([Parameter(Mandatory = $true)][string]$CandidateName)
    $identities = Invoke-IndependentSsh -Command (
        "docker ps -a --no-trunc --format '{{.ID}}|{{.Names}}'"
    )
    return @(
        $identities -split "\r?\n" |
            Where-Object {
                -not [string]::IsNullOrWhiteSpace($_) -and
                -not $_.EndsWith("|$CandidateName")
            } |
            Sort-Object
    )
}

function Get-ContainerState {
    param([Parameter(Mandatory = $true)][string]$Name)
    return Invoke-IndependentSsh -Command (
        "docker inspect --format " +
        "'{{.State.Status}}|{{.RestartCount}}|{{.State.OOMKilled}}' " +
        $Name
    )
}

$candidate = "straddle-fidelity-independent-demo"
$allContainersBefore = @(
    Get-NonCandidateContainerSnapshot -CandidateName $candidate
)
$protectedNames = @(
    "straddle-fidelity-candidate-demo",
    "straddle-replica-demo-vps"
)
$before = @{}
foreach ($name in $protectedNames) {
    $before[$name] = Get-OptionalContainerFingerprint -Name $name
    if ([string]::IsNullOrWhiteSpace($before[$name])) {
        throw "Protected container state could not be determined: $name"
    }
}

Invoke-IndependentSsh -Command "mkdir -p $RemoteRoot" | Out-Null
& scp $PackagePath "${SshAlias}:$RemoteRoot/package.zip"
if ($LASTEXITCODE -ne 0) {
    throw "Independent demo package upload failed."
}
Invoke-IndependentSsh -Command (
    "cd $RemoteRoot && " +
    "unzip -o package.zip -d $RemoteRoot >/dev/null && " +
    "chmod 0755 $RemoteRoot/image/entrypoint.sh && " +
    "chown -R 1000:1000 $RemoteRoot"
) | Out-Null
$remoteForbidden = Invoke-IndependentSsh -Command (
    "find $RemoteRoot/candidate $RemoteRoot/image $RemoteRoot/docs -type f " +
    "\( -iname '*.mq5' -o -iname '*.mqh' " +
    "-o -iname '*password*' -o -iname '*credential*' " +
    "-o -iname '*secret*' \) -print"
)
if (-not [string]::IsNullOrWhiteSpace($remoteForbidden)) {
    throw "Remote independent root contains source or credential files."
}
$remoteShadow = Invoke-IndependentSsh -Command (
    "grep -ERil " +
    "'RuntimeMode=1|ShadowCommandFile|ShadowAckFile' " +
    "$RemoteRoot/candidate --include='*.set' --include='*.ini' || true"
)
if (-not [string]::IsNullOrWhiteSpace($remoteShadow)) {
    throw "Remote independent root contains shadow configuration."
}
$terminalArtifactSync = Invoke-IndependentSsh -Command (
    "if [ -f $RemoteRoot/terminal/terminal64.exe ]; then " +
    "install -d -m 0755 " +
    "$RemoteRoot/terminal/MQL5/Experts/StraddleReplica " +
    "$RemoteRoot/terminal/MQL5/Presets && " +
    "install -m 0644 " +
    "$RemoteRoot/candidate/StraddleReplica.ex5 " +
    "$RemoteRoot/terminal/MQL5/Experts/StraddleReplica/StraddleReplica.ex5 && " +
    "install -m 0644 " +
    "$RemoteRoot/candidate/latest_30_independent_demo.set " +
    "$RemoteRoot/terminal/MQL5/Presets/latest_30_independent_demo.set && " +
    "chown -R 1000:1000 " +
    "$RemoteRoot/terminal/MQL5/Experts/StraddleReplica " +
    "$RemoteRoot/terminal/MQL5/Presets && " +
    "cmp -s $RemoteRoot/candidate/StraddleReplica.ex5 " +
    "$RemoteRoot/terminal/MQL5/Experts/StraddleReplica/StraddleReplica.ex5 && " +
    "cmp -s $RemoteRoot/candidate/latest_30_independent_demo.set " +
    "$RemoteRoot/terminal/MQL5/Presets/latest_30_independent_demo.set && " +
    "echo installed; else echo deferred; fi"
)
Invoke-IndependentSsh -Command (
    "docker build -t straddle-fidelity-independent-mt5:bookworm " +
    "$RemoteRoot/image"
) | Out-Null

$mt5StartAssignment = if ($StartTrading) {
    "MT5_START=1"
}
else {
    "MT5_START=0"
}
$mt5ConfigAssignment = if ($StartTrading) {
    "MT5_CONFIG_WINDOWS='Z:\data\candidate\independent-demo-startup.ini'"
}
else {
    "MT5_CONFIG_WINDOWS='Z:\data\candidate\independent-demo-commissioning.ini'"
}
$composeSuffix = if ($StartTrading) {
    " --force-recreate fidelity-independent"
}
else {
    ""
}
Invoke-IndependentSsh -Command (
    "cd $RemoteRoot && " +
    "$mt5StartAssignment $mt5ConfigAssignment docker compose " +
    "-p straddle-fidelity-independent-demo up -d$composeSuffix"
) | Out-Null

foreach ($name in $protectedNames) {
    $after = Get-OptionalContainerFingerprint -Name $name
    if ($after -ne $before[$name]) {
        throw "Protected container changed during deployment: $name"
    }
}
$allContainersAfter = @(
    Get-NonCandidateContainerSnapshot -CandidateName $candidate
)
$containerIdentityChanges = @(
    Compare-Object `
        -ReferenceObject $allContainersBefore `
        -DifferenceObject $allContainersAfter
)
if ($containerIdentityChanges.Count -gt 0) {
    throw "Unrelated VPS container identity changed during deployment."
}

$state = Get-ContainerState -Name $candidate
if ($state -ne "running|0|false") {
    throw "Independent container health is not clean: $state"
}
$vnc = Invoke-IndependentSsh -Command "docker port $candidate 5900/tcp"
if ($vnc -ne "127.0.0.1:15925") {
    throw "Independent VNC is not loopback-only: $vnc"
}
$environment = Invoke-IndependentSsh -Command (
    "docker inspect --format " +
    "'{{range .Config.Env}}{{println .}}{{end}}' " +
    $candidate
)
$environmentLines = $environment -split "\r?\n"
$expectedStart = if ($StartTrading) {
    "MT5_START=1"
}
else {
    "MT5_START=0"
}
if ($expectedStart -notin $environmentLines) {
    throw "Independent container start mode is incorrect."
}

Write-Host "Independent container: $candidate"
Write-Host "Independent VNC: 127.0.0.1:15925"
Write-Host "Independent start mode: $expectedStart"
Write-Host "Independent terminal artifact sync: $terminalArtifactSync"
Write-Host "Protected containers remained unchanged."
