param(
    [int]$Minutes = 5
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "Watching cluster for $Minutes minute(s)..."
$end = (Get-Date).AddMinutes($Minutes)
$ok = $true

while ((Get-Date) -lt $end) {
    & (Join-Path $ScriptDir 'validate-cluster.ps1') > $null 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "$(Get-Date): OK"
    } else {
        Write-Host "$(Get-Date): MISMATCH"
        $ok = $false
    }
    Start-Sleep -Seconds 30
}

if ($ok) {
    Write-Host "Cluster remained in sync during watch period."
    exit 0
} else {
    Write-Error "Issues detected while watching cluster."
    exit 1
}
