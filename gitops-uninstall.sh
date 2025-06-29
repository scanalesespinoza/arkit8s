#!/bin/bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"

printf '\n🗑️ Deleting manifests...\n'
oc delete -f "$REPO_ROOT" --recursive || true

printf '\n🗑️ Deleting bootstrap namespaces...\n'
oc delete -f "$REPO_ROOT/bootstrap/" || true

printf '\nCleanup completed.\n'
