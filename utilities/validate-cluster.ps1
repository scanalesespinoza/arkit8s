$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..")
$BootstrapDir = Join-Path $RepoRoot "architecture/bootstrap"
$Environment = $args[0]
if (-not $Environment) { $Environment = 'sandbox' }
$EnvDir = Join-Path $RepoRoot "environments/$Environment"

Write-Host "Verificando namespaces..."
$namespaces = Get-ChildItem -Path $BootstrapDir -Filter "00-namespace-*.yaml" |
    ForEach-Object { $_.BaseName -replace '^00-namespace-', '' }

foreach ($ns in $namespaces) {
    $result = oc get ns $ns 2>$null
    if (-not $result) {
        Write-Error "Namespace '$ns' no existe"
        exit 1
    }
}

Write-Host "Verificando pods en estado Running o Completed..."
foreach ($ns in $namespaces) {
    $badPods = oc get pods -n $ns --no-headers | Select-String -NotMatch "Running|Completed"
    if ($badPods) {
        Write-Error "Existen pods en estado no válido en '$ns':"
        $badPods | ForEach-Object { Write-Host $_ }
        exit 1
    }
}

Write-Host "Verificando que todos los Deployments estén listos..."
foreach ($ns in $namespaces) {
    $deployments = oc get deployments -n $ns --no-headers
    foreach ($line in $deployments) {
        $cols = $line -split "\s+"
        if ($cols.Count -lt 5) { continue }

        $name = $cols[0]
        $ready = $cols[1] # Formato 1/1 (READY column)

        if (-not ($ready -match "^(\d+)/\1$")) {
            Write-Error "Deployment $ns/$name no listo ($ready)"
            exit 1
        }
    }
}

Write-Host "Verificando sincronización de manifiestos para $Environment..."
$diff = oc diff -k $EnvDir 2>&1
if ($LASTEXITCODE -ne 0) {
    if ($LASTEXITCODE -eq 1) {
        Write-Error "Manifiestos desincronizados:"
        Write-Host $diff
        exit 1
    } else {
        Write-Host $diff
        exit $LASTEXITCODE
    }
}

Write-Host "Validación completada exitosamente."

