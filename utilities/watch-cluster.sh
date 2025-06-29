#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DURATION_MINUTES="${1:-5}"
DETAIL_LEVEL="${2:-default}"
end=$((SECONDS + DURATION_MINUTES * 60))
result=0

printf '🔎 Watching cluster for %s minute(s) (detail: %s)...\n' "$DURATION_MINUTES" "$DETAIL_LEVEL"

while [ $SECONDS -lt $end ]; do
  status=0
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
