$ErrorActionPreference = 'Stop'

Write-Host "🔍 Verificando namespaces..."
$namespaces = @('business-domain','support-domain','shared-components')
foreach ($ns in $namespaces) {
    if (-not (oc get ns $ns -ErrorAction SilentlyContinue)) {
        Write-Error "Namespace $ns no existe"
        exit 1
    }
}

Write-Host "📦 Verificando deployments en estado Running..."
$deploys = oc get deployments -A -o json | ConvertFrom-Json
foreach ($d in $deploys.items) {
    $desired = if ($d.spec.replicas) { [int]$d.spec.replicas } else { 1 }
    $available = if ($d.status.availableReplicas) { [int]$d.status.availableReplicas } else { 0 }
    if ($available -lt $desired) {
        Write-Error "Deployment $($d.metadata.namespace)/$($d.metadata.name) no listo"
        exit 1
    }
}

Write-Host "🚨 Verificando pods sin errores ni reinicios..."
$pods = oc get pods -A -o json | ConvertFrom-Json
foreach ($p in $pods.items) {
    if ($p.status.phase -notin @('Running','Succeeded')) {
        Write-Error "Pod $($p.metadata.namespace)/$($p.metadata.name) en estado $($p.status.phase)"
        exit 1
    }
    foreach ($c in $p.status.containerStatuses) {
        if ($c.restartCount -gt 0) {
            Write-Error "Pod $($p.metadata.namespace)/$($p.metadata.name) tiene reinicios"
            exit 1
        }
    }
}

Write-Host "🔄 Verificando sincronización de manifiestos..."
$diffOutput = oc diff -f . --recursive 2>&1
if ($LASTEXITCODE -eq 1) {
    Write-Error "Manifiestos desincronizados:"
    Write-Host $diffOutput
    exit 1
} elseif ($LASTEXITCODE -gt 1) {
    exit $LASTEXITCODE
}

Write-Host "✅ Validación completada exitosamente."

