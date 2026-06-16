#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

require_cmd aws
require_cmd jq
verify_repo_root

task_defs=(
  "$REPO_ROOT/infra/aws/task-definitions/api.json"
  "$REPO_ROOT/infra/aws/task-definitions/frontend.json"
  "$REPO_ROOT/infra/aws/task-definitions/worker.json"
  "$REPO_ROOT/infra/aws/task-definitions/beat.json"
)

for file in "${task_defs[@]}"; do
  jq empty "$file"
  if grep -E '<AWS_ACCOUNT_ID>|<AWS_REGION>|REPLACE_ME|replace-me|placeholder' "$file" >/dev/null; then
    echo "Refusing to register task definition with placeholders: $file" >&2
    grep -nE '<AWS_ACCOUNT_ID>|<AWS_REGION>|REPLACE_ME|replace-me|placeholder' "$file" >&2 || true
    exit 1
  fi
done

for group in /ecs/jobfit-api /ecs/jobfit-frontend /ecs/jobfit-worker /ecs/jobfit-beat; do
  if aws logs describe-log-groups --region "$AWS_REGION" --log-group-name-prefix "$group" --query 'logGroups[?logGroupName==`'"$group"'`].logGroupName | [0]' --output text | grep -q "$group"; then
    echo "CloudWatch log group exists: $group"
  else
    echo "Creating CloudWatch log group: $group"
    aws logs create-log-group --region "$AWS_REGION" --log-group-name "$group"
    aws logs tag-log-group --region "$AWS_REGION" --log-group-name "$group" --tags Project=JobFit,Environment=staging || true
  fi
done

for file in "${task_defs[@]}"; do
  family="$(jq -r '.family' "$file")"
  echo "Registering task definition: $family"
  arn="$(aws ecs register-task-definition \
    --region "$AWS_REGION" \
    --cli-input-json "file://$file" \
    --query 'taskDefinition.taskDefinitionArn' \
    --output text)"
  key="$(printf '%s' "$family" | tr '[:lower:]-' '[:upper:]_')_TASK_DEFINITION_ARN"
  upsert_env "$key" "$arn"
  echo "$arn"
done

echo
echo "Task definitions registered."
echo "Next: infra/aws/scripts/10_create_ecs_services.sh"
