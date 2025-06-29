Write-Host "🔍 Verificando namespaces..."
$namespaces = @("business-domain", "support-domain", "shared-components")

foreach ($ns in $namespaces) {
    if (-not (oc get ns $ns -ErrorAction SilentlyContinue)) {
        Write-Error "❌ Namespace '$ns' no existe"
        exit 1
    }
}

Write-Host "📦 Verificando pods en estado Running o Completed..."
$badPods = oc get pods --all-namespaces | Select-String -NotMatch "Running|Completed|NAME"
if ($badPods) {
    Write-Error "❌ Existen pods que no están en estado válido:"
    $badPods | ForEach-Object { Write-Host $_ }
    exit 1
}

Write-Host "📊 Verificando que todos los Deployments estén listos..."
$deployments = oc get deployments --all-namespaces --no-headers
foreach ($line in $deployments) {
    $cols = $line -split "\s+"
    $ns = $cols[0]
    $name = $cols[1]
    $ready = $cols[4] # Formato: 1/1

    if (-not ($ready -match "^(\d+)\/\1$")) {
        Write-Error "❌ Deployment $ns/$name no listo ($ready)"
        exit 1
    }
}

Write-Host "✅ Validación completada exitosamente."

