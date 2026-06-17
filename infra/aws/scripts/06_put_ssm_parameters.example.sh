#!/usr/bin/env bash
set -euo pipefail

# EXAMPLE ONLY.
# Copy this file to infra/aws/scripts/06_put_ssm_parameters.sh, keep that local
# file ignored by git, and replace placeholder values there. Do not commit real
# API keys, database passwords, Redis URLs, or JWT secrets.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

if [ "$(basename "$0")" = "06_put_ssm_parameters.example.sh" ]; then
  echo "This is an example script and will not write secrets."
  echo "Copy it to infra/aws/scripts/06_put_ssm_parameters.sh, edit real values locally, then run the copy."
  exit 0
fi

require_cmd aws
verify_repo_root
load_bootstrap_env

# Replace all CHANGE_ME values in your local ignored copy.
DATABASE_URL="${DATABASE_URL:-postgresql+asyncpg://jobfit_user:CHANGE_ME_DB_PASSWORD@${RDS_ENDPOINT:-CHANGE_ME_RDS_ENDPOINT}:5432/jobfit}"
REDIS_URL="${REDIS_URL:-redis://${REDIS_ENDPOINT:-CHANGE_ME_REDIS_ENDPOINT}:6379/0}"
CELERY_BROKER_URL="${CELERY_BROKER_URL:-$REDIS_URL}"
CELERY_RESULT_BACKEND="${CELERY_RESULT_BACKEND:-$REDIS_URL}"
JWT_SECRET="${JWT_SECRET:-CHANGE_ME_LONG_RANDOM_SECRET}"
ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-CHANGE_ME_ANTHROPIC_API_KEY}"
OPENAI_API_KEY="${OPENAI_API_KEY:-CHANGE_ME_OPENAI_API_KEY}"

case "$DATABASE_URL$REDIS_URL$JWT_SECRET$ANTHROPIC_API_KEY$OPENAI_API_KEY" in
  *CHANGE_ME*)
    echo "Refusing to write placeholder secrets. Edit your local copy first." >&2
    exit 1
    ;;
esac

put_secret() {
  local name="$1"
  local value="$2"
  aws ssm put-parameter \
    --region "$AWS_REGION" \
    --name "$name" \
    --type SecureString \
    --value "$value" \
    --overwrite >/dev/null
  echo "Wrote SecureString: $name"
}

put_secret /jobfit/staging/database-url "$DATABASE_URL"
put_secret /jobfit/staging/redis-url "$REDIS_URL"
put_secret /jobfit/staging/celery-broker-url "$CELERY_BROKER_URL"
put_secret /jobfit/staging/celery-result-backend "$CELERY_RESULT_BACKEND"
put_secret /jobfit/staging/jwt-secret "$JWT_SECRET"
put_secret /jobfit/staging/anthropic-api-key "$ANTHROPIC_API_KEY"
put_secret /jobfit/staging/openai-api-key "$OPENAI_API_KEY"

echo
echo "SSM parameter bootstrap complete."
echo "Next: infra/aws/scripts/07_create_ecs_cluster.sh"
