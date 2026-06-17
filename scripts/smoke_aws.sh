#!/usr/bin/env sh
set -eu

input="${1:-${AWS_APP_HEALTH_URL:-${APP_URL:-}}}"

if [ -z "$input" ]; then
  echo "Usage: scripts/smoke_aws.sh <health-url>" >&2
  echo "Or set AWS_APP_HEALTH_URL to a full health URL, e.g. https://example.com/api/health" >&2
  echo "APP_URL is also accepted and will be checked at APP_URL/api/health." >&2
  exit 2
fi

case "$input" in
  */health|*/health/)
    health_url="${input%/}"
    ;;
  *)
    health_url="${input%/}/api/health"
    ;;
esac

echo "Checking $health_url"

attempts="${SMOKE_ATTEMPTS:-20}"
delay="${SMOKE_DELAY_SECONDS:-10}"
response=""

attempt=1
while [ "$attempt" -le "$attempts" ]; do
  if response="$(curl -fsS "$health_url")"; then
    break
  fi
  if [ "$attempt" -eq "$attempts" ]; then
    echo "AWS smoke check failed after $attempts attempts" >&2
    exit 1
  fi
  echo "Health check attempt $attempt/$attempts failed; retrying in ${delay}s..."
  sleep "$delay"
  attempt=$((attempt + 1))
done

printf '%s\n' "$response"

case "$response" in
  *'"status":"ok"'*|*'"status": "ok"'*)
    echo "AWS smoke check passed"
    ;;
  *)
    echo "AWS smoke check failed: health response did not report status ok" >&2
    exit 1
    ;;
esac
