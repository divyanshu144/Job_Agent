#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

require_cmd aws
verify_repo_root

cluster="jobfit-cluster"

status="$(aws ecs describe-clusters \
  --region "$AWS_REGION" \
  --clusters "$cluster" \
  --query 'clusters[0].status' \
  --output text 2>/dev/null || true)"

if [ "$status" = "ACTIVE" ]; then
  echo "ECS cluster exists: $cluster"
else
  echo "Creating ECS cluster: $cluster"
  aws ecs create-cluster \
    --region "$AWS_REGION" \
    --cluster-name "$cluster" \
    --tags key=Project,value=JobFit key=Environment,value=staging
fi

upsert_env ECS_CLUSTER "$cluster"

echo
echo "ECS cluster bootstrap complete."
echo "Next: infra/aws/scripts/08_create_alb.sh"
