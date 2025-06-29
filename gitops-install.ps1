Write-Host "\nApplying bootstrap namespaces..."
oc apply -f bootstrap/

Write-Host "\nSynchronizing repository manifests..."
oc apply -f . --recursive

Write-Host "\nRunning validation..."
& ./validate-cluster.ps1
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "\nInstall completed successfully."
