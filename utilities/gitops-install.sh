#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ARCH_DIR="$REPO_ROOT/architecture"
ENVIRONMENT="${1:-sandbox}"
ENV_DIR="$REPO_ROOT/environments/$ENVIRONMENT"

printf '\n📦 Applying bootstrap namespaces...\n'
oc apply -k "$ARCH_DIR/bootstrap/"

printf '\n🔄 Synchronizing repository manifests for %s...\n' "$ENVIRONMENT"
oc apply -k "$ENV_DIR"

printf '\n✅ Running validation...\n'
"$SCRIPT_DIR/validate-cluster.sh" "$ENVIRONMENT"

printf '\n🎉 Install completed successfully.\n'

