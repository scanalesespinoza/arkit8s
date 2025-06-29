$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..")
$ArchDir = Join-Path $RepoRoot "architecture"

Write-Host "\nApplying bootstrap namespaces..."
oc apply -f (Join-Path $ArchDir "bootstrap")

Write-Host "\nSynchronizing repository manifests..."
oc apply -f $ArchDir --recursive

Write-Host "\nRunning validation..."
& (Join-Path $ScriptDir "validate-cluster.ps1")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "\nInstall completed successfully."
