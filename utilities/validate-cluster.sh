#!/bin/bash
set -euo pipefail

# Determine namespaces from bootstrap manifests
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BOOTSTRAP_DIR="$SCRIPT_DIR/../architecture/bootstrap"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENVIRONMENT="${1:-sandbox}"
ENV_DIR="$REPO_ROOT/environments/$ENVIRONMENT"
NAMESPACES=()
for f in "$BOOTSTRAP_DIR"/00-namespace-*.yaml; do
  ns=$(basename "$f" | sed -e 's/00-namespace-\(.*\)\.yaml/\1/')
  NAMESPACES+=("$ns")
done

echo "🔍 Verificando namespaces..."
for ns in "${NAMESPACES[@]}"; do
  if ! oc get ns "$ns" >/dev/null 2>&1; then
    echo "Namespace $ns no existe" >&2
    exit 1
  fi
done

echo "📦 Verificando deployments en estado Running..."
for ns in "${NAMESPACES[@]}"; do
  unready=$(oc get deploy -n "$ns" --no-headers | awk '$4!=$5 {print $1"/"$2}')
  if [ -n "$unready" ]; then
    echo "Deployments no listos en $ns:" >&2
    echo "$unready" >&2
    exit 1
  fi
done

echo "🚨 Verificando pods sin errores ni reinicios..."
for ns in "${NAMESPACES[@]}"; do
  bad_pods=$(oc get pods -n "$ns" --no-headers | grep -vE 'Running|Completed' || true)
  if [ -n "$bad_pods" ]; then
    echo "Pods en estado no válido en $ns:" >&2
    echo "$bad_pods" >&2
    exit 1
  fi

  restarts=$(oc get pods -n "$ns" --no-headers | awk '$5>0')
  if [ -n "$restarts" ]; then
    echo "Pods con reinicios en $ns:" >&2
    echo "$restarts" >&2
    exit 1
  fi
done

echo "🔄 Verificando sincronización de manifiestos para $ENVIRONMENT..."
if ! oc diff -k "$ENV_DIR" >/tmp/diff.txt 2>&1; then
  status=$?
  if [ $status -eq 1 ]; then
    echo "Manifiestos desincronizados:" >&2
    cat /tmp/diff.txt >&2
    exit 1
  else
    cat /tmp/diff.txt >&2
    exit $status
  fi
fi

echo "✅ Validación completada exitosamente."


