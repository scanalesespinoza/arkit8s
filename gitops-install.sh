#!/bin/bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"

printf '\n📦 Applying bootstrap namespaces...\n'
oc apply -f "$REPO_ROOT/bootstrap/"

printf '\n🔄 Synchronizing repository manifests...\n'
oc apply -f "$REPO_ROOT" --recursive

printf '\n✅ Running validation...\n'
"$REPO_ROOT/validate-cluster.sh"

printf '\n🎉 Install completed successfully.\n'
