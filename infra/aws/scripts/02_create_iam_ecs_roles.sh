#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

require_cmd aws
require_cmd jq
verify_repo_root

account_id="$(aws_account_id)"
execution_role="jobfit-ecs-execution-role"
task_role="jobfit-ecs-task-role"

trust_policy="$(mktemp)"
cat > "$trust_policy" <<'JSON'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "Service": "ecs-tasks.amazonaws.com" },
      "Action": "sts:AssumeRole"
    }
  ]
}
JSON

create_role_if_missing() {
  local role_name="$1"
  if aws iam get-role --role-name "$role_name" >/dev/null 2>&1; then
    echo "IAM role exists: $role_name"
  else
    echo "Creating IAM role: $role_name"
    aws iam create-role \
      --role-name "$role_name" \
      --assume-role-policy-document "file://$trust_policy" \
      --tags Key=Project,Value=JobFit Key=Environment,Value=staging >/dev/null
  fi
}

create_role_if_missing "$execution_role"
create_role_if_missing "$task_role"

aws iam attach-role-policy \
  --role-name "$execution_role" \
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy

ssm_policy="$(mktemp)"
cat > "$ssm_policy" <<JSON
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadJobFitStagingParameters",
      "Effect": "Allow",
      "Action": [
        "ssm:GetParameter",
        "ssm:GetParameters",
        "ssm:GetParametersByPath"
      ],
      "Resource": "arn:aws:ssm:${AWS_REGION}:${account_id}:parameter/jobfit/staging/*"
    },
    {
      "Sid": "DecryptSsmSecureStringsForJobFitStaging",
      "Effect": "Allow",
      "Action": "kms:Decrypt",
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "kms:ViaService": "ssm.${AWS_REGION}.amazonaws.com"
        }
      }
    }
  ]
}
JSON

# ECS resolves task definition secrets with the execution role. The task role
# gets the same narrow read policy for future app-level SSM reads if needed.
for role in "$execution_role" "$task_role"; do
  aws iam put-role-policy \
    --role-name "$role" \
    --policy-name jobfit-staging-ssm-read \
    --policy-document "file://$ssm_policy"
done

execution_role_arn="$(aws iam get-role --role-name "$execution_role" --query 'Role.Arn' --output text)"
task_role_arn="$(aws iam get-role --role-name "$task_role" --query 'Role.Arn' --output text)"

upsert_env ECS_EXECUTION_ROLE_ARN "$execution_role_arn"
upsert_env ECS_TASK_ROLE_ARN "$task_role_arn"

echo
echo "IAM role bootstrap complete."
echo "Execution role: $execution_role_arn"
echo "Task role: $task_role_arn"
echo "Next: infra/aws/scripts/03_create_networking.sh"
