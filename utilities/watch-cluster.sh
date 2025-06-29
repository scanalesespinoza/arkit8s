#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DURATION_MINUTES="${1:-5}"
DETAIL_LEVEL="${2:-default}"
BOOTSTRAP_DIR="$SCRIPT_DIR/../architecture/bootstrap"
end=$((SECONDS + DURATION_MINUTES * 60))
result=0

show_detailed_info() {
  printf 'Namespaces (bootstrap):\n'
  namespaces=()
  for f in "$BOOTSTRAP_DIR"/00-namespace-*.yaml; do
    ns=$(basename "$f" | sed -e 's/00-namespace-\(.*\)\.yaml/\1/')
    namespaces+=("$ns")
    printf '  - %s\n' "$ns"
  done

  printf 'Deployments:\n'
  for ns in "${namespaces[@]}"; do
    oc get deploy -n "$ns" --no-headers -o custom-columns=NAME:.metadata.name 2>/dev/null | \
      sed "s/^/  $ns\//"
  done

  printf 'Bootstrap manifests:\n'
  for f in "$BOOTSTRAP_DIR"/*.yaml; do
    printf '  - %s\n' "$(basename "$f")"
  done
}

printf '🔎 Watching cluster for %s minute(s) (detail: %s)...\n' "$DURATION_MINUTES" "$DETAIL_LEVEL"

while [ $SECONDS -lt $end ]; do
  status=0
  if [ "$DETAIL_LEVEL" != "default" ]; then
    show_detailed_info
  fi
  case "$DETAIL_LEVEL" in
    all)
      "$SCRIPT_DIR/validate-cluster.sh" || status=$?
      ;;
    detailed)
      output=$("$SCRIPT_DIR/validate-cluster.sh" 2>&1) || status=$?
      if [ $status -ne 0 ]; then
        printf '%s\n' "$output"
      fi
      ;;
    *)
      "$SCRIPT_DIR/validate-cluster.sh" >/dev/null 2>&1 || status=$?
      ;;
  esac

  if [ $status -eq 0 ]; then
    printf '%s: ✅ cluster in sync\n' "$(date)"
  else
    printf '%s: ❌ cluster out of sync\n' "$(date)"
    result=1
  fi
  sleep 30
done

if [ $result -eq 0 ]; then
  printf '✅ Cluster remained in sync during watch period.\n'
else
  printf '⚠️  Issues detected while watching cluster.\n'
fi
exit $result
