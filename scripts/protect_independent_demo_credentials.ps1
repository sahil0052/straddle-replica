param(
    [Parameter(Mandatory = $true)]
    [long]$Login,
    [Parameter(Mandatory = $true)]
    [string]$Server,
    [SecureString]$MasterPassword,
    [SecureString]$InvestorPassword,
    [string]$Workspace = "",
    [string]$OutputPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($Login -le 0) {
    throw "Login must be positive."
}
if ([string]::IsNullOrWhiteSpace($Server)) {
    throw "Server is required."
}
if ([string]::IsNullOrWhiteSpace($Workspace)) {
    $Workspace = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}
$privateRoot = Join-Path $Workspace "artifacts\private"
if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $OutputPath = Join-Path (
        $privateRoot
    ) "independent-demo-credentials.json"
}
$privateFull = [System.IO.Path]::GetFullPath($privateRoot).TrimEnd("\") + "\"
$outputFull = [System.IO.Path]::GetFullPath($OutputPath)
if (-not $outputFull.StartsWith(
    $privateFull,
    [System.StringComparison]::OrdinalIgnoreCase
)) {
    throw "Credential output must remain under artifacts\private."
}
if ($null -eq $MasterPassword) {
    $MasterPassword = Read-Host "Master password" -AsSecureString
}
if ($null -eq $InvestorPassword) {
    $InvestorPassword = Read-Host "Investor password" -AsSecureString
}

New-Item -ItemType Directory -Force -Path $privateRoot | Out-Null
$temporary = "$outputFull.tmp"
$payload = @{
    schema_version = 1
    login = $Login
    server = $Server
    created_utc = [DateTime]::UtcNow.ToString("o")
    master_cipher = ConvertFrom-SecureString $MasterPassword
    investor_cipher = ConvertFrom-SecureString $InvestorPassword
}
$payload |
    ConvertTo-Json |
    Set-Content -LiteralPath $temporary -Encoding UTF8
Move-Item -LiteralPath $temporary -Destination $outputFull -Force

$identityName = (
    [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
)
$identity = New-Object System.Security.Principal.NTAccount($identityName)
$acl = New-Object System.Security.AccessControl.FileSecurity
$acl.SetOwner($identity)
$acl.SetAccessRuleProtection($true, $false)
$rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
    $identity,
    [System.Security.AccessControl.FileSystemRights]::FullControl,
    [System.Security.AccessControl.AccessControlType]::Allow
)
$acl.AddAccessRule($rule)
Set-Acl -LiteralPath $outputFull -AclObject $acl

Write-Host "Protected credential file created."
Write-Host "Login: $Login"
Write-Host "Server: $Server"
Write-Host "Passwords were not printed."
