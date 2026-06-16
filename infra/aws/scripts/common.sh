#!/usr/bin/env bash

# Shared helpers for the JobFit AWS bootstrap scripts.
# This file intentionally performs no AWS mutations when sourced.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AWS_INFRA_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$AWS_INFRA_DIR/../.." && pwd)"
BOOTSTRAP_ENV="$AWS_INFRA_DIR/.aws-bootstrap.env"

AWS_REGION="${AWS_REGION:-eu-west-2}"
export AWS_REGION

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Missing required command: $cmd" >&2
    exit 1
  fi
}

verify_repo_root() {
  if [ ! -f "$REPO_ROOT/Dockerfile" ] || [ ! -f "$REPO_ROOT/frontend/Dockerfile" ] || [ ! -d "$REPO_ROOT/infra/aws" ]; then
    echo "Could not verify repository root at $REPO_ROOT" >&2
    exit 1
  fi
}

load_bootstrap_env() {
  if [ -f "$BOOTSTRAP_ENV" ]; then
    # shellcheck disable=SC1090
    set -a
    source "$BOOTSTRAP_ENV"
    set +a
  fi
}

ensure_bootstrap_env() {
  mkdir -p "$(dirname "$BOOTSTRAP_ENV")"
  touch "$BOOTSTRAP_ENV"
  chmod 600 "$BOOTSTRAP_ENV"
}

upsert_env() {
  local key="$1"
  local value="$2"
  ensure_bootstrap_env
  local tmp
  tmp="$(mktemp)"
  if grep -q "^${key}=" "$BOOTSTRAP_ENV"; then
    awk -v k="$key" -v v="$value" 'BEGIN{FS=OFS="="} $1==k {$0=k"="v} {print}' "$BOOTSTRAP_ENV" > "$tmp"
  else
    cat "$BOOTSTRAP_ENV" > "$tmp"
    printf '%s=%s\n' "$key" "$value" >> "$tmp"
  fi
  mv "$tmp" "$BOOTSTRAP_ENV"
  chmod 600 "$BOOTSTRAP_ENV"
}

aws_account_id() {
  aws sts get-caller-identity --query Account --output text
}

confirm_billable() {
  local prompt="$1"
  echo
  echo "WARNING: $prompt"
  echo "This can create billable AWS resources."
  read -r -p "Type 'create' to continue: " answer
  if [ "$answer" != "create" ]; then
    echo "Aborted."
    exit 0
  fi
}

json_array_from_csv() {
  local csv="$1"
  jq -cn --arg csv "$csv" '$csv | split(",") | map(select(length > 0))'
}

tag_args() {
  printf 'Key=Project,Value=JobFit Key=Environment,Value=staging'
}
