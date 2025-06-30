#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

printf '🔍 Validando manifiestos YAML...\n'

mapfile -t yaml_files < <(find "$REPO_ROOT" -name '*.yaml' ! -name 'kustomization.yaml' | sort)
status=0

for file in "${yaml_files[@]}"; do
  if oc apply --dry-run=client -f "$file" >/dev/null 2>&1; then
    printf '✅ %s\n' "$file"
  else
    printf '❌ Error al validar %s\n' "$file" >&2
    status=1
  fi
done

if [ $status -eq 0 ]; then
  printf '🎉 Todos los manifiestos YAML son válidos.\n'
else
  printf '⚠️  Se encontraron errores de validación.\n' >&2
  exit $status
fi
