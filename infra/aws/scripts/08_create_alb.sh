#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

require_cmd aws
verify_repo_root
load_bootstrap_env

vpc_id="${VPC_ID:-}"
subnets="${SUBNET_IDS:-}"
alb_sg="${ALB_SECURITY_GROUP_ID:-}"

if [ -z "$vpc_id" ] || [ -z "$subnets" ] || [ -z "$alb_sg" ]; then
  echo "VPC_ID, SUBNET_IDS, and ALB_SECURITY_GROUP_ID are required. Run 03_create_networking.sh first." >&2
  exit 1
fi

subnet_args=()
IFS=',' read -r -a subnet_array <<< "$subnets"
for subnet in "${subnet_array[@]}"; do
  subnet_args+=("$subnet")
done

get_tg_arn() {
  local name="$1"
  aws elbv2 describe-target-groups \
    --region "$AWS_REGION" \
    --names "$name" \
    --query 'TargetGroups[0].TargetGroupArn' \
    --output text 2>/dev/null || true
}

create_tg_if_missing() {
  local name="$1" port="$2" health_path="$3"
  local arn
  arn="$(get_tg_arn "$name")"
  if [ -n "$arn" ] && [ "$arn" != "None" ]; then
    echo "$arn"
    return
  fi
  aws elbv2 create-target-group \
    --region "$AWS_REGION" \
    --name "$name" \
    --protocol HTTP \
    --port "$port" \
    --vpc-id "$vpc_id" \
    --target-type ip \
    --health-check-protocol HTTP \
    --health-check-path "$health_path" \
    --matcher HttpCode=200 \
    --tags Key=Project,Value=JobFit Key=Environment,Value=staging \
    --query 'TargetGroups[0].TargetGroupArn' \
    --output text
}

alb_arn="$(aws elbv2 describe-load-balancers \
  --region "$AWS_REGION" \
  --names jobfit-alb \
  --query 'LoadBalancers[0].LoadBalancerArn' \
  --output text 2>/dev/null || true)"

if [ -z "$alb_arn" ] || [ "$alb_arn" = "None" ]; then
  echo "Creating ALB: jobfit-alb"
  alb_arn="$(aws elbv2 create-load-balancer \
    --region "$AWS_REGION" \
    --name jobfit-alb \
    --type application \
    --scheme internet-facing \
    --security-groups "$alb_sg" \
    --subnets "${subnet_args[@]}" \
    --tags Key=Project,Value=JobFit Key=Environment,Value=staging \
    --query 'LoadBalancers[0].LoadBalancerArn' \
    --output text)"
else
  echo "ALB exists: jobfit-alb"
fi

alb_dns="$(aws elbv2 describe-load-balancers \
  --region "$AWS_REGION" \
  --load-balancer-arns "$alb_arn" \
  --query 'LoadBalancers[0].DNSName' \
  --output text)"

frontend_tg="$(create_tg_if_missing jobfit-frontend-tg 80 /healthz)"
api_tg="$(create_tg_if_missing jobfit-api-tg 8000 /health)"

listener_arn="$(aws elbv2 describe-listeners \
  --region "$AWS_REGION" \
  --load-balancer-arn "$alb_arn" \
  --query 'Listeners[?Port==`80`].ListenerArn | [0]' \
  --output text 2>/dev/null || true)"

if [ -z "$listener_arn" ] || [ "$listener_arn" = "None" ]; then
  echo "Creating HTTP listener on port 80"
  listener_arn="$(aws elbv2 create-listener \
    --region "$AWS_REGION" \
    --load-balancer-arn "$alb_arn" \
    --protocol HTTP \
    --port 80 \
    --default-actions "Type=forward,TargetGroupArn=$frontend_tg" \
    --query 'Listeners[0].ListenerArn' \
    --output text)"
else
  echo "HTTP listener exists."
fi

rule_exists="$(aws elbv2 describe-rules \
  --region "$AWS_REGION" \
  --listener-arn "$listener_arn" \
  --query "Rules[?Conditions[?Field=='path-pattern' && contains(Values, '/api/*')]].RuleArn | [0]" \
  --output text 2>/dev/null || true)"

if [ -z "$rule_exists" ] || [ "$rule_exists" = "None" ]; then
  echo "Creating /api/* listener rule"
  aws elbv2 create-rule \
    --region "$AWS_REGION" \
    --listener-arn "$listener_arn" \
    --priority 10 \
    --conditions Field=path-pattern,Values='/api/*' \
    --actions "Type=forward,TargetGroupArn=$api_tg" >/dev/null
else
  echo "/api/* listener rule exists."
fi

upsert_env ALB_ARN "$alb_arn"
upsert_env ALB_DNS_NAME "$alb_dns"
upsert_env ALB_LISTENER_ARN "$listener_arn"
upsert_env FRONTEND_TARGET_GROUP_ARN "$frontend_tg"
upsert_env API_TARGET_GROUP_ARN "$api_tg"

echo
echo "ALB DNS: http://$alb_dns"
echo "WARNING: this creates HTTP only. Add HTTPS/ACM before real production use."
echo "Next: replace placeholders in task definitions, then run 09_register_task_definitions.sh"
