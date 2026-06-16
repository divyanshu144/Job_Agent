# AWS Bootstrap Scripts

These scripts are reviewable AWS CLI helpers for creating the staging resources used by the existing ECS/GitHub Actions deployment flow. They do not use Terraform, CDK, Pulumi, EKS, or Bedrock.

Run them manually from the repository root or from this directory. They default to `AWS_REGION=eu-west-2`.

## Recommended Order

```bash
infra/aws/scripts/00_check_prereqs.sh
infra/aws/scripts/01_create_ecr.sh
infra/aws/scripts/02_create_iam_ecs_roles.sh
infra/aws/scripts/03_create_networking.sh
infra/aws/scripts/04_create_rds.sh
infra/aws/scripts/05_create_redis.sh
cp infra/aws/scripts/06_put_ssm_parameters.example.sh infra/aws/scripts/06_put_ssm_parameters.sh
$EDITOR infra/aws/scripts/06_put_ssm_parameters.sh
infra/aws/scripts/06_put_ssm_parameters.sh
infra/aws/scripts/07_create_ecs_cluster.sh
infra/aws/scripts/08_create_alb.sh
infra/aws/scripts/09_register_task_definitions.sh
infra/aws/scripts/10_create_ecs_services.sh
GITHUB_OWNER=<owner> GITHUB_REPO=<repo> infra/aws/scripts/11_create_github_oidc_role.sh
```

Before running `09_register_task_definitions.sh`, replace placeholders in `infra/aws/task-definitions/*.json`, especially:

- `<AWS_ACCOUNT_ID>`
- `https://replace-me.example.com`
- ECS role ARNs if your role names differ
- SSM parameter ARNs if your naming differs

## Billable Resources

These scripts can create billable AWS resources:

- `04_create_rds.sh`: RDS PostgreSQL instance.
- `05_create_redis.sh`: ElastiCache Redis node.
- `08_create_alb.sh`: Application Load Balancer.
- `10_create_ecs_services.sh`: ECS Fargate running tasks.

The RDS and Redis scripts require typing `create` before they create the database/cache. Other scripts are still resource-creating and should be reviewed before running.

## Bootstrap Env File

Several scripts write non-secret IDs and endpoints to:

```text
infra/aws/.aws-bootstrap.env
```

This file is ignored by git. It may contain AWS resource IDs and endpoints, but it should not contain API keys or passwords. The RDS script prints a generated password if `DB_PASSWORD` is not provided, but it does not write the password to the env file.

## Secrets

Never edit real secrets into `06_put_ssm_parameters.example.sh`.

Copy it first:

```bash
cp infra/aws/scripts/06_put_ssm_parameters.example.sh infra/aws/scripts/06_put_ssm_parameters.sh
```

Then edit the ignored copy and run it. It writes these SSM SecureString values:

- `/jobfit/staging/database-url`
- `/jobfit/staging/redis-url`
- `/jobfit/staging/celery-broker-url`
- `/jobfit/staging/celery-result-backend`
- `/jobfit/staging/jwt-secret`
- `/jobfit/staging/anthropic-api-key`

Optional integration secrets can be added later if needed.

## GitHub Setup

After `11_create_github_oidc_role.sh`, add the printed ARN as:

- GitHub secret: `AWS_GITHUB_ACTIONS_ROLE_ARN`

For migration workflow support, add repository variables:

- `AWS_ECS_SUBNETS`: comma-separated subnet IDs, for example `subnet-a,subnet-b`
- `AWS_ECS_SECURITY_GROUPS`: comma-separated ECS task security group IDs

Optional smoke-test variable:

- `AWS_APP_HEALTH_URL`: for example `http://<alb-dns-name>/api/health`

## Deploy and Migrate

Deploy from GitHub Actions:

```bash
gh workflow run deploy-aws.yml
```

Run migrations manually:

```bash
gh workflow run aws-migrate.yml
```

Run a local smoke test against the ALB:

```bash
scripts/smoke_aws.sh http://<alb-dns-name>
```

## Safety Notes

- Scripts are written to be idempotent where practical.
- Scripts do not delete resources.
- Scripts do not store real secrets in the repository.
- This is a staging/demo bootstrap path, not full production infrastructure.
- Add HTTPS/ACM, stricter IAM review, CloudWatch alarms, and S3-backed uploads before real production use.
