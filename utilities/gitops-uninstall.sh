#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ARCH_DIR="$REPO_ROOT/architecture"

printf '\n🗑️ Deleting manifests...\n'
oc delete -f "$ARCH_DIR" --recursive || true

printf '\n🗑️ Deleting bootstrap namespaces...\n'
oc delete -f "$ARCH_DIR/bootstrap/" || true

printf '\nCleanup completed.\n'
