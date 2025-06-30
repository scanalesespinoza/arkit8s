$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..")
$ArchDir = Join-Path $RepoRoot "architecture"
$Environment = $args[0]
if (-not $Environment) { $Environment = 'sandbox' }
$EnvDir = Join-Path $RepoRoot "environments/$Environment"

Write-Host "\nApplying bootstrap namespaces..."
oc apply -f (Join-Path $ArchDir "bootstrap")

Write-Host "\nSynchronizing repository manifests for $Environment..."
oc apply -k $EnvDir

Write-Host "\nRunning validation..."
& (Join-Path $ScriptDir "validate-cluster.ps1") $Environment
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "\nInstall completed successfully."

