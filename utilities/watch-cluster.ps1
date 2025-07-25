param(
    [int]$Minutes = 5,
    [ValidateSet('default','detailed','all')]
    [string]$Detail = 'default',
    [string]$Environment = 'sandbox'
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BootstrapDir = Join-Path $ScriptDir ".." | Join-Path -ChildPath "architecture/bootstrap" | Resolve-Path

function Show-DetailedInfo {
    $nsFiles = Get-ChildItem -Path $BootstrapDir -Filter '00-namespace-*.yaml'
    $namespaces = @()
    Write-Host "Namespaces (bootstrap):"
    foreach ($f in $nsFiles) {
        $ns = $f.BaseName -replace '^00-namespace-', ''
        $namespaces += $ns
        Write-Host "  - $ns"
    }

    Write-Host "Deployments:"
    foreach ($ns in $namespaces) {
        oc get deploy -n $ns --no-headers | ForEach-Object {
            ($_.Split()[0]) | ForEach-Object { Write-Host "  $ns/$_" }
        }
    }

    Write-Host "Namespace status:"
    foreach ($ns in $namespaces) {
        oc get ns $ns --no-headers | ForEach-Object { Write-Host "  $_" }
    }

    Write-Host "Deployment status:"
    foreach ($ns in $namespaces) {
        oc get deploy -n $ns --no-headers | ForEach-Object { Write-Host "  $ns/$_" }
    }

    Write-Host "Pod status:"
    foreach ($ns in $namespaces) {
        oc get pods -n $ns --no-headers | ForEach-Object { Write-Host "  $ns/$_" }
    }

    Write-Host "Bootstrap manifests:"
    Get-ChildItem -Path $BootstrapDir -Filter '*.yaml' | ForEach-Object {
        Write-Host "  - $($_.Name)"
    }
}

Write-Host "Watching cluster for $Minutes minute(s) in $Environment with detail '$Detail'..."
$end = (Get-Date).AddMinutes($Minutes)
$ok = $true

while ((Get-Date) -lt $end) {
    $status = 0
    if ($Detail -ne 'default') { Show-DetailedInfo }
    switch ($Detail) {
        'all' {
            & (Join-Path $ScriptDir 'validate-cluster.ps1') $Environment
            $status = $LASTEXITCODE
        }
        'detailed' {
            $output = & (Join-Path $ScriptDir 'validate-cluster.ps1') $Environment 2>&1
            $status = $LASTEXITCODE
            if ($status -ne 0) { $output }
        }
        Default {
            & (Join-Path $ScriptDir 'validate-cluster.ps1') $Environment > $null 2>&1
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

