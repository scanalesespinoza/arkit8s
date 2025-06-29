#!/bin/bash
set -euo pipefail

NAMESPACES=(business-domain support-domain shared-components)

echo "🔍 Verificando namespaces..."
for ns in "${NAMESPACES[@]}"; do
  if ! oc get ns "$ns" >/dev/null 2>&1; then
    echo "Namespace $ns no existe" >&2
    exit 1
  fi
done

echo "📦 Verificando deployments en estado Running..."
unready=$(oc get deploy -A --no-headers | awk '$4!=$5 {print $1"/"$2}')
if [ -n "$unready" ]; then
  echo "Deployments no listos:" >&2
  echo "$unready" >&2
  exit 1
fi

echo "🚨 Verificando pods sin errores ni reinicios..."
bad_pods=$(oc get pods -A --no-headers | grep -vE 'Running|Completed' || true)
if [ -n "$bad_pods" ]; then
  echo "Pods en estado no válido:" >&2
  echo "$bad_pods" >&2
  exit 1
fi

restarts=$(oc get pods -A --no-headers | awk '$5>0')
if [ -n "$restarts" ]; then
  echo "Pods con reinicios:" >&2
  echo "$restarts" >&2
  exit 1
fi

echo "🔄 Verificando sincronización de manifiestos..."
if ! oc diff -f . --recursive >/tmp/diff.txt 2>&1; then
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

