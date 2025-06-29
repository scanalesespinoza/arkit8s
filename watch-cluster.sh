#!/bin/bash
set -euo pipefail

DURATION_MINUTES="${1:-5}"
end=$((SECONDS + DURATION_MINUTES * 60))
result=0

printf '🔎 Watching cluster for %s minute(s)...\n' "$DURATION_MINUTES"

while [ $SECONDS -lt $end ]; do
  if ./validate-cluster.sh >/dev/null 2>&1; then
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
