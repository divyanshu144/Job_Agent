#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

require_cmd aws
require_cmd openssl
verify_repo_root
load_bootstrap_env

subnets="${SUBNET_IDS:-}"
rds_sg="${RDS_SECURITY_GROUP_ID:-}"
if [ -z "$subnets" ] || [ -z "$rds_sg" ]; then
  echo "SUBNET_IDS and RDS_SECURITY_GROUP_ID are required. Run 03_create_networking.sh first." >&2
  exit 1
fi

db_id="jobfit-postgres"
subnet_group="jobfit-db-subnet-group"
db_name="jobfit"
db_user="jobfit_user"
db_password="${DB_PASSWORD:-$(openssl rand -base64 32 | tr -d '=+/[:space:]' | cut -c1-32)}"
subnet_args=()
IFS=',' read -r -a subnet_array <<< "$subnets"
for subnet in "${subnet_array[@]}"; do
  subnet_args+=("$subnet")
done

if aws rds describe-db-subnet-groups --region "$AWS_REGION" --db-subnet-group-name "$subnet_group" >/dev/null 2>&1; then
  echo "RDS subnet group exists: $subnet_group"
else
  echo "Creating RDS subnet group: $subnet_group"
  aws rds create-db-subnet-group \
    --region "$AWS_REGION" \
    --db-subnet-group-name "$subnet_group" \
    --db-subnet-group-description "JobFit staging DB subnet group" \
    --subnet-ids "${subnet_args[@]}" \
    --tags Key=Project,Value=JobFit Key=Environment,Value=staging >/dev/null
fi

if aws rds describe-db-instances --region "$AWS_REGION" --db-instance-identifier "$db_id" >/dev/null 2>&1; then
  echo "RDS instance exists: $db_id"
else
  echo "Generated DB password for this run: $db_password"
  echo "Store it in a password manager now. It will not be written to git."
  confirm_billable "Create RDS PostgreSQL instance $db_id (db.t4g.micro, 20GB, backup retention 7 days)."
  aws rds create-db-instance \
    --region "$AWS_REGION" \
    --db-instance-identifier "$db_id" \
    --db-name "$db_name" \
    --engine postgres \
    --db-instance-class db.t4g.micro \
    --allocated-storage 20 \
    --storage-type gp3 \
    --master-username "$db_user" \
    --master-user-password "$db_password" \
    --vpc-security-group-ids "$rds_sg" \
    --db-subnet-group-name "$subnet_group" \
    --backup-retention-period 7 \
    --no-publicly-accessible \
    --tags Key=Project,Value=JobFit Key=Environment,Value=staging >/dev/null
fi

echo "Waiting for RDS instance to become available. This can take several minutes."
aws rds wait db-instance-available --region "$AWS_REGION" --db-instance-identifier "$db_id"

endpoint="$(aws rds describe-db-instances \
  --region "$AWS_REGION" \
  --db-instance-identifier "$db_id" \
  --query 'DBInstances[0].Endpoint.Address' \
  --output text)"

upsert_env RDS_INSTANCE_ID "$db_id"
upsert_env RDS_ENDPOINT "$endpoint"
upsert_env POSTGRES_DB "$db_name"
upsert_env POSTGRES_USER "$db_user"

echo
echo "RDS endpoint: $endpoint"
echo "Create this SecureString later with 06_put_ssm_parameters.example.sh:"
echo "postgresql+asyncpg://${db_user}:<DB_PASSWORD>@${endpoint}:5432/${db_name}"
echo "Next: infra/aws/scripts/05_create_redis.sh"
