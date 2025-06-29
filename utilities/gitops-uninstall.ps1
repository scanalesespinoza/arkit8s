$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..")
$ArchDir = Join-Path $RepoRoot "architecture"

Write-Host "\nDeleting manifests..."
oc delete -f $ArchDir --recursive | Out-Null

Write-Host "\nDeleting bootstrap namespaces..."
oc delete -f (Join-Path $ArchDir "bootstrap") | Out-Null

Write-Host "\nCleanup completed."
