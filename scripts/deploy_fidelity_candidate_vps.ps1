param(
    [string]$SshAlias = "nishahomes-vps",
    [Parameter(Mandatory = $true)]
    [string]$PackagePath,
    [string]$Workspace = "",
    [string]$RemoteRoot = "/opt/straddle-fidelity-candidate"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($Workspace)) {
    $Workspace = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}
if ($RemoteRoot -ne "/opt/straddle-fidelity-candidate") {
    throw "RemoteRoot must be /opt/straddle-fidelity-candidate."
}
if (-not (Test-Path -LiteralPath $PackagePath -PathType Leaf)) {
    throw "Candidate package was not found: $PackagePath"
}

$composePath = Join-Path $Workspace "deploy\vps-docker-candidate\compose.yaml"
$dockerfilePath = Join-Path $Workspace "deploy\vps-docker\Dockerfile"
$entrypointPath = Join-Path $Workspace "deploy\vps-docker\entrypoint.sh"
foreach ($required in @($composePath, $dockerfilePath, $entrypointPath)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Required deployment file was not found: $required"
    }
}

function Invoke-CandidateSsh {
    param([Parameter(Mandatory = $true)][string]$Command)
    $output = & ssh $SshAlias $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Remote candidate command failed: $Command"
    }
    return (($output | Out-String).Trim())
}

$existingContainer = "straddle-replica-demo-vps"
$existingInspect = (
    "docker inspect --format " +
    "'{{.Id}}|{{.State.Status}}|{{.RestartCount}}|{{.State.OOMKilled}}' " +
    $existingContainer
)
$before = Invoke-CandidateSsh -Command $existingInspect
if ([string]::IsNullOrWhiteSpace($before)) {
    throw "Existing replica container could not be inspected."
}

Invoke-CandidateSsh -Command (
    "mkdir -p " +
    "$RemoteRoot/image $RemoteRoot/candidate $RemoteRoot/docs"
) | Out-Null
& scp $PackagePath "${SshAlias}:$RemoteRoot/candidate-package.zip"
if ($LASTEXITCODE -ne 0) {
    throw "Candidate package upload failed."
}
& scp $composePath "${SshAlias}:$RemoteRoot/compose.yaml"
if ($LASTEXITCODE -ne 0) {
    throw "Candidate compose upload failed."
}
& scp $dockerfilePath "${SshAlias}:$RemoteRoot/image/Dockerfile"
if ($LASTEXITCODE -ne 0) {
    throw "Candidate Dockerfile upload failed."
}
& scp $entrypointPath "${SshAlias}:$RemoteRoot/image/entrypoint.sh"
if ($LASTEXITCODE -ne 0) {
    throw "Candidate entrypoint upload failed."
}

Invoke-CandidateSsh -Command (
    "cd $RemoteRoot && " +
    "unzip -o candidate-package.zip -d $RemoteRoot >/dev/null && " +
    "chmod 0755 $RemoteRoot/image/entrypoint.sh && " +
    "chown -R 1000:1000 $RemoteRoot"
) | Out-Null
Invoke-CandidateSsh -Command (
    "docker build -t straddle-fidelity-mt5:bookworm " +
    "/opt/straddle-fidelity-candidate/image"
) | Out-Null
Invoke-CandidateSsh -Command (
    "cd /opt/straddle-fidelity-candidate && " +
    "docker compose -p straddle-fidelity-candidate up -d"
) | Out-Null

$after = Invoke-CandidateSsh -Command $existingInspect
if ($after -ne $before) {
    throw "Existing replica container changed during candidate deployment."
}

$candidate = "straddle-fidelity-candidate-demo"
$candidateState = Invoke-CandidateSsh -Command (
    "docker inspect --format " +
    "'{{.State.Status}}|{{.RestartCount}}|{{.State.OOMKilled}}' " +
    $candidate
)
if ($candidateState -ne "running|0|false") {
    throw "Candidate container health is not clean: $candidateState"
}
$vncBinding = Invoke-CandidateSsh -Command (
    "docker port $candidate 5900/tcp"
)
if ($vncBinding -ne "127.0.0.1:15915") {
    throw "Candidate VNC is not loopback-only: $vncBinding"
}
$candidateEnvironment = Invoke-CandidateSsh -Command (
    "docker inspect --format " +
    "'{{range .Config.Env}}{{println .}}{{end}}' " +
    $candidate
)
$candidateEnvironmentLines = $candidateEnvironment -split "\r?\n"
if ("MT5_START=0" -notin $candidateEnvironmentLines) {
    throw "Candidate must remain in commissioning mode with MT5_START=0."
}

Write-Host "Candidate container: $candidate"
Write-Host "Candidate VNC: 127.0.0.1:15915"
Write-Host "Existing replica container remained unchanged."
