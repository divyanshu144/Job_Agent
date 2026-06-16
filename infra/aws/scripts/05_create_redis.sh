#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

require_cmd aws
verify_repo_root
load_bootstrap_env

subnets="${SUBNET_IDS:-}"
redis_sg="${REDIS_SECURITY_GROUP_ID:-}"
if [ -z "$subnets" ] || [ -z "$redis_sg" ]; then
  echo "SUBNET_IDS and REDIS_SECURITY_GROUP_ID are required. Run 03_create_networking.sh first." >&2
  exit 1
fi

cluster_id="jobfit-redis"
subnet_group="jobfit-redis-subnet-group"
subnet_args=()
IFS=',' read -r -a subnet_array <<< "$subnets"
for subnet in "${subnet_array[@]}"; do
  subnet_args+=("$subnet")
done

if aws elasticache describe-cache-subnet-groups --region "$AWS_REGION" --cache-subnet-group-name "$subnet_group" >/dev/null 2>&1; then
  echo "ElastiCache subnet group exists: $subnet_group"
else
  echo "Creating ElastiCache subnet group: $subnet_group"
  aws elasticache create-cache-subnet-group \
    --region "$AWS_REGION" \
    --cache-subnet-group-name "$subnet_group" \
    --cache-subnet-group-description "JobFit staging Redis subnet group" \
    --subnet-ids "${subnet_args[@]}" >/dev/null
fi

if aws elasticache describe-cache-clusters --region "$AWS_REGION" --cache-cluster-id "$cluster_id" >/dev/null 2>&1; then
  echo "Redis cache cluster exists: $cluster_id"
else
  confirm_billable "Create ElastiCache Redis cluster $cluster_id (cache.t4g.micro, one node)."
  aws elasticache create-cache-cluster \
    --region "$AWS_REGION" \
    --cache-cluster-id "$cluster_id" \
    --engine redis \
    --cache-node-type cache.t4g.micro \
    --num-cache-nodes 1 \
    --cache-subnet-group-name "$subnet_group" \
    --security-group-ids "$redis_sg" \
    --tags Key=Project,Value=JobFit Key=Environment,Value=staging >/dev/null
fi

echo "Waiting for Redis cluster to become available. This can take several minutes."
aws elasticache wait cache-cluster-available --region "$AWS_REGION" --cache-cluster-id "$cluster_id"

endpoint="$(aws elasticache describe-cache-clusters \
  --region "$AWS_REGION" \
  --cache-cluster-id "$cluster_id" \
  --show-cache-node-info \
  --query 'CacheClusters[0].CacheNodes[0].Endpoint.Address' \
  --output text)"

upsert_env REDIS_CLUSTER_ID "$cluster_id"
upsert_env REDIS_ENDPOINT "$endpoint"

echo
echo "Redis endpoint: $endpoint"
echo "Redis URL for SSM: redis://${endpoint}:6379/0"
echo "Next: copy 06_put_ssm_parameters.example.sh to 06_put_ssm_parameters.sh and insert real secrets locally."
