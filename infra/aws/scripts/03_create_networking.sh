#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

require_cmd aws
verify_repo_root
load_bootstrap_env

vpc_id="${JOBFIT_VPC_ID:-${VPC_ID:-}}"
if [ -z "$vpc_id" ]; then
  vpc_id="$(aws ec2 describe-vpcs \
    --region "$AWS_REGION" \
    --filters Name=isDefault,Values=true \
    --query 'Vpcs[0].VpcId' \
    --output text)"
fi

if [ -z "$vpc_id" ] || [ "$vpc_id" = "None" ]; then
  echo "No VPC found. Set JOBFIT_VPC_ID to an existing VPC ID." >&2
  exit 1
fi

subnet_csv="${JOBFIT_SUBNET_IDS:-${SUBNET_IDS:-}}"
if [ -z "$subnet_csv" ]; then
  subnet_csv="$(aws ec2 describe-subnets \
    --region "$AWS_REGION" \
    --filters "Name=vpc-id,Values=$vpc_id" "Name=default-for-az,Values=true" \
    --query 'Subnets[*].SubnetId' \
    --output text | tr '\t' ',')"
fi

subnet_count="$(printf '%s' "$subnet_csv" | tr ',' '\n' | grep -c . || true)"
if [ "$subnet_count" -lt 2 ]; then
  echo "Need at least two subnets for ALB/RDS. Found: $subnet_csv" >&2
  exit 1
fi

get_or_create_sg() {
  local name="$1"
  local desc="$2"
  local sg_id
  sg_id="$(aws ec2 describe-security-groups \
    --region "$AWS_REGION" \
    --filters "Name=vpc-id,Values=$vpc_id" "Name=group-name,Values=$name" \
    --query 'SecurityGroups[0].GroupId' \
    --output text 2>/dev/null || true)"
  if [ -n "$sg_id" ] && [ "$sg_id" != "None" ]; then
    echo "$sg_id"
    return
  fi
  sg_id="$(aws ec2 create-security-group \
    --region "$AWS_REGION" \
    --group-name "$name" \
    --description "$desc" \
    --vpc-id "$vpc_id" \
    --query GroupId \
    --output text)"
  aws ec2 create-tags --region "$AWS_REGION" --resources "$sg_id" --tags Key=Name,Value="$name" Key=Project,Value=JobFit Key=Environment,Value=staging
  echo "$sg_id"
}

authorize_ingress_cidr() {
  local sg_id="$1" port="$2" cidr="$3" desc="$4"
  aws ec2 authorize-security-group-ingress \
    --region "$AWS_REGION" \
    --group-id "$sg_id" \
    --ip-permissions "IpProtocol=tcp,FromPort=$port,ToPort=$port,IpRanges=[{CidrIp=$cidr,Description='$desc'}]" \
    >/dev/null 2>&1 || true
}

authorize_ingress_sg() {
  local sg_id="$1" port="$2" source_sg="$3" desc="$4"
  aws ec2 authorize-security-group-ingress \
    --region "$AWS_REGION" \
    --group-id "$sg_id" \
    --ip-permissions "IpProtocol=tcp,FromPort=$port,ToPort=$port,UserIdGroupPairs=[{GroupId=$source_sg,Description='$desc'}]" \
    >/dev/null 2>&1 || true
}

alb_sg="$(get_or_create_sg jobfit-alb-sg "JobFit staging ALB security group")"
ecs_sg="$(get_or_create_sg jobfit-ecs-sg "JobFit staging ECS task security group")"
rds_sg="$(get_or_create_sg jobfit-rds-sg "JobFit staging RDS security group")"
redis_sg="$(get_or_create_sg jobfit-redis-sg "JobFit staging Redis security group")"

authorize_ingress_cidr "$alb_sg" 80 "0.0.0.0/0" "Public HTTP for staging ALB"
authorize_ingress_sg "$ecs_sg" 80 "$alb_sg" "ALB to frontend container"
authorize_ingress_sg "$ecs_sg" 8000 "$alb_sg" "ALB to API container"
authorize_ingress_sg "$rds_sg" 5432 "$ecs_sg" "ECS tasks to RDS"
authorize_ingress_sg "$redis_sg" 6379 "$ecs_sg" "ECS tasks to Redis"

upsert_env AWS_REGION "$AWS_REGION"
upsert_env VPC_ID "$vpc_id"
upsert_env SUBNET_IDS "$subnet_csv"
upsert_env ALB_SECURITY_GROUP_ID "$alb_sg"
upsert_env ECS_SECURITY_GROUP_ID "$ecs_sg"
upsert_env RDS_SECURITY_GROUP_ID "$rds_sg"
upsert_env REDIS_SECURITY_GROUP_ID "$redis_sg"

echo "VPC: $vpc_id"
echo "Subnets: $subnet_csv"
echo "ALB SG: $alb_sg"
echo "ECS SG: $ecs_sg"
echo "RDS SG: $rds_sg"
echo "Redis SG: $redis_sg"
echo
echo "Networking bootstrap complete."
echo "Next: infra/aws/scripts/04_create_rds.sh"
