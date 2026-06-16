#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

require_cmd aws
verify_repo_root

repos=(jobfit-api jobfit-worker jobfit-beat jobfit-frontend)

for repo in "${repos[@]}"; do
  if aws ecr describe-repositories --repository-names "$repo" --region "$AWS_REGION" >/dev/null 2>&1; then
    echo "ECR repository exists: $repo"
  else
    echo "Creating ECR repository: $repo"
    aws ecr create-repository \
      --repository-name "$repo" \
      --region "$AWS_REGION" \
      --image-scanning-configuration scanOnPush=true \
      --encryption-configuration encryptionType=AES256 \
      --tags Key=Project,Value=JobFit Key=Environment,Value=staging >/dev/null
  fi
done

account_id="$(aws_account_id)"
upsert_env AWS_REGION "$AWS_REGION"
upsert_env AWS_ACCOUNT_ID "$account_id"
upsert_env ECR_REGISTRY "${account_id}.dkr.ecr.${AWS_REGION}.amazonaws.com"

echo
echo "ECR bootstrap complete."
echo "Next: infra/aws/scripts/02_create_iam_ecs_roles.sh"
