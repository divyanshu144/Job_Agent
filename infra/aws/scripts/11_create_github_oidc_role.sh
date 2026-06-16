#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

require_cmd aws
require_cmd jq
verify_repo_root

: "${GITHUB_OWNER:?Set GITHUB_OWNER, e.g. export GITHUB_OWNER=your-github-user}"
: "${GITHUB_REPO:?Set GITHUB_REPO, e.g. export GITHUB_REPO=Job_Ready_Agent}"

account_id="$(aws_account_id)"
role_name="jobfit-github-actions-deploy-role"
provider_url="https://token.actions.githubusercontent.com"
provider_arn="arn:aws:iam::${account_id}:oidc-provider/token.actions.githubusercontent.com"
thumbprint="${GITHUB_OIDC_THUMBPRINT:-6938fd4d98bab03faadb97b34396831e3780aea1}"

if aws iam get-open-id-connect-provider --open-id-connect-provider-arn "$provider_arn" >/dev/null 2>&1; then
  echo "GitHub OIDC provider exists."
else
  echo "Creating GitHub OIDC provider."
  echo "Using thumbprint: $thumbprint"
  aws iam create-open-id-connect-provider \
    --url "$provider_url" \
    --client-id-list sts.amazonaws.com \
    --thumbprint-list "$thumbprint" \
    --tags Key=Project,Value=JobFit Key=Environment,Value=staging >/dev/null
fi

trust_policy="$(mktemp)"
cat > "$trust_policy" <<JSON
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "${provider_arn}"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:${GITHUB_OWNER}/${GITHUB_REPO}:*"
        }
      }
    }
  ]
}
JSON

if aws iam get-role --role-name "$role_name" >/dev/null 2>&1; then
  echo "GitHub Actions role exists: $role_name"
  aws iam update-assume-role-policy \
    --role-name "$role_name" \
    --policy-document "file://$trust_policy"
else
  echo "Creating GitHub Actions role: $role_name"
  aws iam create-role \
    --role-name "$role_name" \
    --assume-role-policy-document "file://$trust_policy" \
    --tags Key=Project,Value=JobFit Key=Environment,Value=staging >/dev/null
fi

policy_file="$(mktemp)"
cat > "$policy_file" <<JSON
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "EcrAuth",
      "Effect": "Allow",
      "Action": "ecr:GetAuthorizationToken",
      "Resource": "*"
    },
    {
      "Sid": "PushJobFitImages",
      "Effect": "Allow",
      "Action": [
        "ecr:BatchCheckLayerAvailability",
        "ecr:CompleteLayerUpload",
        "ecr:DescribeImages",
        "ecr:DescribeRepositories",
        "ecr:InitiateLayerUpload",
        "ecr:PutImage",
        "ecr:UploadLayerPart"
      ],
      "Resource": [
        "arn:aws:ecr:${AWS_REGION}:${account_id}:repository/jobfit-api",
        "arn:aws:ecr:${AWS_REGION}:${account_id}:repository/jobfit-worker",
        "arn:aws:ecr:${AWS_REGION}:${account_id}:repository/jobfit-beat",
        "arn:aws:ecr:${AWS_REGION}:${account_id}:repository/jobfit-frontend"
      ]
    },
    {
      "Sid": "DeployEcsServices",
      "Effect": "Allow",
      "Action": [
        "ecs:DescribeClusters",
        "ecs:DescribeServices",
        "ecs:DescribeTaskDefinition",
        "ecs:DescribeTasks",
        "ecs:RegisterTaskDefinition",
        "ecs:RunTask",
        "ecs:UpdateService",
        "ecs:ListTasks"
      ],
      "Resource": "*"
    },
    {
      "Sid": "PassJobFitEcsRoles",
      "Effect": "Allow",
      "Action": "iam:PassRole",
      "Resource": [
        "arn:aws:iam::${account_id}:role/jobfit-ecs-execution-role",
        "arn:aws:iam::${account_id}:role/jobfit-ecs-task-role"
      ],
      "Condition": {
        "StringEquals": {
          "iam:PassedToService": "ecs-tasks.amazonaws.com"
        }
      }
    }
  ]
}
JSON

aws iam put-role-policy \
  --role-name "$role_name" \
  --policy-name jobfit-github-actions-deploy \
  --policy-document "file://$policy_file"

role_arn="$(aws iam get-role --role-name "$role_name" --query 'Role.Arn' --output text)"
upsert_env GITHUB_ACTIONS_ROLE_ARN "$role_arn"

echo
echo "GitHub Actions OIDC role ready:"
echo "$role_arn"
echo
echo "Add this as GitHub secret: AWS_GITHUB_ACTIONS_ROLE_ARN"
echo "Also set GitHub variables AWS_ECS_SUBNETS and AWS_ECS_SECURITY_GROUPS for aws-migrate.yml."
