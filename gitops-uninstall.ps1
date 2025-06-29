Write-Host "\nDeleting manifests..."
oc delete -f . --recursive | Out-Null

Write-Host "\nDeleting bootstrap namespaces..."
oc delete -f bootstrap/ | Out-Null

Write-Host "\nCleanup completed."
