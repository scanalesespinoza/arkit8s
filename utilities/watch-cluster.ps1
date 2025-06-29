param(
    [int]$Minutes = 5,
    [ValidateSet('default','detailed','all')]
    [string]$Detail = 'default'
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "Watching cluster for $Minutes minute(s) with detail '$Detail'..."
$end = (Get-Date).AddMinutes($Minutes)
$ok = $true

while ((Get-Date) -lt $end) {
    $status = 0
    switch ($Detail) {
        'all' {
            & (Join-Path $ScriptDir 'validate-cluster.ps1')
            $status = $LASTEXITCODE
        }
        'detailed' {
            $output = & (Join-Path $ScriptDir 'validate-cluster.ps1') 2>&1
            $status = $LASTEXITCODE
            if ($status -ne 0) { $output }
        }
        Default {
            & (Join-Path $ScriptDir 'validate-cluster.ps1') > $null 2>&1
            $status = $LASTEXITCODE
        }
    }

    if ($status -eq 0) {
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
