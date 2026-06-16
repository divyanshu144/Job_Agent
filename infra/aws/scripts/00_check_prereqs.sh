#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

require_cmd aws
require_cmd jq
require_cmd docker
verify_repo_root

echo "Repository root: $REPO_ROOT"
echo "AWS region: $AWS_REGION"

identity="$(aws sts get-caller-identity)"
account_id="$(printf '%s' "$identity" | jq -r '.Account')"
arn="$(printf '%s' "$identity" | jq -r '.Arn')"

echo "AWS account ID: $account_id"
echo "AWS caller ARN: $arn"

upsert_env AWS_REGION "$AWS_REGION"
upsert_env AWS_ACCOUNT_ID "$account_id"

echo
echo "Prerequisites OK."
echo "Bootstrap env written to: $BOOTSTRAP_ENV"
