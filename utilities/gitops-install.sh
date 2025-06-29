#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ARCH_DIR="$REPO_ROOT/architecture"

printf '\n📦 Applying bootstrap namespaces...\n'
oc apply -f "$ARCH_DIR/bootstrap/"

printf '\n🔄 Synchronizing repository manifests...\n'
oc apply -f "$ARCH_DIR" --recursive

printf '\n✅ Running validation...\n'
"$SCRIPT_DIR/validate-cluster.sh"

printf '\n🎉 Install completed successfully.\n'
