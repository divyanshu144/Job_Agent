#!/usr/bin/env bash
set -Eeuo pipefail

NS="${NS:-jobfit}"

log() {
  printf '\n==> %s\n' "$*"
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    printf 'Missing required command: %s\n' "$1" >&2
    exit 1
  fi
}

wait_for_http() {
  local url="$1"
  for _ in {1..30}; do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  printf 'Timed out waiting for %s\n' "$url" >&2
  return 1
}

start_port_forward() {
  local service="$1"
  local mapping="$2"
  kubectl -n "$NS" port-forward "svc/${service}" "$mapping" >/tmp/jobfit-k8s-${service}.log 2>&1 &
  echo "$!"
}

cleanup() {
  if [ -n "${API_PF_PID:-}" ]; then kill "$API_PF_PID" >/dev/null 2>&1 || true; fi
  if [ -n "${FRONTEND_PF_PID:-}" ]; then kill "$FRONTEND_PF_PID" >/dev/null 2>&1 || true; fi
}
trap cleanup EXIT

require_cmd kubectl
require_cmd curl

log "Checking namespace"
kubectl get namespace "$NS" >/dev/null

log "Waiting for pods"
kubectl -n "$NS" wait --for=condition=Ready pod -l app=postgres --timeout=300s
kubectl -n "$NS" wait --for=condition=Ready pod -l app=redis --timeout=300s
kubectl -n "$NS" wait --for=condition=Ready pod -l app=api --timeout=300s
kubectl -n "$NS" wait --for=condition=Ready pod -l app=frontend --timeout=300s

log "Checking API health through port-forward"
API_PF_PID="$(start_port_forward api 8000:8000)"
wait_for_http http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/health >/dev/null

log "Checking frontend health through port-forward"
FRONTEND_PF_PID="$(start_port_forward frontend 8080:80)"
wait_for_http http://127.0.0.1:8080/healthz
curl -fsS http://127.0.0.1:8080/healthz >/dev/null
curl -fsSI http://127.0.0.1:8080/ >/dev/null

log "Checking Postgres"
kubectl -n "$NS" exec statefulset/postgres -- pg_isready -U jobfit -d jobfit
kubectl -n "$NS" exec statefulset/postgres -- psql -U jobfit -d jobfit -c '\dt' | grep -q 'users'

log "Checking Redis"
kubectl -n "$NS" exec deploy/redis -- redis-cli ping | grep -q 'PONG'

log "Checking Celery worker"
kubectl -n "$NS" exec deploy/worker -- sh -lc 'task_id=$(celery -A backend.celery_app:celery_app call health.ping); timeout 20s celery -A backend.celery_app:celery_app result "$task_id"' | grep -q 'pong'

log "Checking prompt files"
kubectl -n "$NS" exec deploy/api -- python -c "from pathlib import Path; prompts=list(Path('backend/prompts').glob('*.md')); assert prompts; assert Path('backend/prompts/job_parser.md').exists(); print(len(prompts))"

log "Checking TeX split"
kubectl -n "$NS" exec deploy/api -- sh -lc '! command -v pdflatex >/dev/null'
kubectl -n "$NS" exec deploy/worker -- sh -lc 'command -v pdflatex >/dev/null'
kubectl -n "$NS" exec deploy/beat -- sh -lc '! command -v pdflatex >/dev/null'

log "Kubernetes smoke passed"
