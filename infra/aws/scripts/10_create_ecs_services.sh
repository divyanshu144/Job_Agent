#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

require_cmd aws
verify_repo_root
load_bootstrap_env

cluster="${ECS_CLUSTER:-jobfit-cluster}"
subnets="${SUBNET_IDS:-}"
ecs_sg="${ECS_SECURITY_GROUP_ID:-}"
frontend_tg="${FRONTEND_TARGET_GROUP_ARN:-}"
api_tg="${API_TARGET_GROUP_ARN:-}"

if [ -z "$subnets" ] || [ -z "$ecs_sg" ] || [ -z "$frontend_tg" ] || [ -z "$api_tg" ]; then
  echo "SUBNET_IDS, ECS_SECURITY_GROUP_ID, FRONTEND_TARGET_GROUP_ARN, and API_TARGET_GROUP_ARN are required." >&2
  echo "Run 03_create_networking.sh and 08_create_alb.sh first." >&2
  exit 1
fi

network_config="awsvpcConfiguration={subnets=[$subnets],securityGroups=[$ecs_sg],assignPublicIp=ENABLED}"

service_status() {
  local service="$1"
  aws ecs describe-services \
    --region "$AWS_REGION" \
    --cluster "$cluster" \
    --services "$service" \
    --query 'services[0].status' \
    --output text 2>/dev/null || true
}

create_or_update_lb_service() {
  local service="$1" task_def="$2" container="$3" port="$4" tg="$5"
  local status
  status="$(service_status "$service")"
  if [ "$status" = "ACTIVE" ]; then
    echo "Updating ECS service: $service"
    aws ecs update-service \
      --region "$AWS_REGION" \
      --cluster "$cluster" \
      --service "$service" \
      --task-definition "$task_def" \
      --desired-count 1 >/dev/null
  else
    echo "Creating ECS service: $service"
    aws ecs create-service \
      --region "$AWS_REGION" \
      --cluster "$cluster" \
      --service-name "$service" \
      --task-definition "$task_def" \
      --desired-count 1 \
      --launch-type FARGATE \
      --network-configuration "$network_config" \
      --load-balancers "targetGroupArn=$tg,containerName=$container,containerPort=$port" \
      --health-check-grace-period-seconds 120 \
      --tags key=Project,value=JobFit key=Environment,value=staging
  fi
}

create_or_update_worker_service() {
  local service="$1" task_def="$2"
  local status
  status="$(service_status "$service")"
  if [ "$status" = "ACTIVE" ]; then
    echo "Updating ECS service: $service"
    aws ecs update-service \
      --region "$AWS_REGION" \
      --cluster "$cluster" \
      --service "$service" \
      --task-definition "$task_def" \
      --desired-count 1 >/dev/null
  else
    echo "Creating ECS service: $service"
    aws ecs create-service \
      --region "$AWS_REGION" \
      --cluster "$cluster" \
      --service-name "$service" \
      --task-definition "$task_def" \
      --desired-count 1 \
      --launch-type FARGATE \
      --network-configuration "$network_config" \
      --tags key=Project,value=JobFit key=Environment,value=staging
  fi
}

create_or_update_lb_service jobfit-api-service jobfit-api api 8000 "$api_tg"
create_or_update_lb_service jobfit-frontend-service jobfit-frontend frontend 80 "$frontend_tg"
create_or_update_worker_service jobfit-worker-service jobfit-worker
create_or_update_worker_service jobfit-beat-service jobfit-beat

upsert_env API_SERVICE jobfit-api-service
upsert_env FRONTEND_SERVICE jobfit-frontend-service
upsert_env WORKER_SERVICE jobfit-worker-service
upsert_env BEAT_SERVICE jobfit-beat-service

echo
echo "ECS services created or updated."
echo "Staging services use assignPublicIp=ENABLED. Review this before production."
echo "Next: infra/aws/scripts/11_create_github_oidc_role.sh"
