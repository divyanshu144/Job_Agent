#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

log() {
  printf '\n==> %s\n' "$*"
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    printf 'Missing required command: %s\n' "$1" >&2
    exit 1
  fi
}

wait_for_healthy() {
  local service="$1"
  local container_id
  container_id="$(docker compose ps -q "$service")"
  if [ -z "$container_id" ]; then
    printf 'No container found for service: %s\n' "$service" >&2
    exit 1
  fi
  for _ in {1..60}; do
    status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id")"
    if [ "$status" = "healthy" ] || [ "$status" = "running" ]; then
      return 0
    fi
    sleep 2
  done
  printf 'Service %s did not become healthy\n' "$service" >&2
  docker compose ps "$service" >&2
  exit 1
}

require_cmd docker
require_cmd curl

if [ ! -f .env ]; then
  log "Creating local .env from .env.example"
  cp .env.example .env
fi

log "Building Docker Compose stack"
docker compose build

log "Starting Docker Compose stack"
docker compose up -d --remove-orphans

log "Waiting for healthy services"
wait_for_healthy db
wait_for_healthy redis
wait_for_healthy api
wait_for_healthy frontend
wait_for_healthy worker

log "Waiting for API health"
for _ in {1..30}; do
  if curl -fsS http://127.0.0.1:8000/health >/dev/null; then
    break
  fi
  sleep 2
done
curl -fsS http://127.0.0.1:8000/health >/dev/null

log "Checking frontend health"
curl -fsS http://127.0.0.1:8080/healthz >/dev/null
curl -fsSI http://127.0.0.1:8080/ >/dev/null

log "Checking database tables"
docker compose exec -T db psql -U jobfit -d jobfit -c '\dt' | grep -q 'users'

log "Checking Redis"
docker compose exec -T redis redis-cli ping | grep -q 'PONG'

log "Checking Celery worker"
for _ in {1..12}; do
  if docker compose exec -T worker sh -lc 'task_id=$(celery -A backend.celery_app:celery_app call health.ping); timeout 20s celery -A backend.celery_app:celery_app result "$task_id"' | grep -q 'pong'; then
    celery_ready=1
    break
  fi
  sleep 5
done
if [ "${celery_ready:-0}" != "1" ]; then
  printf 'Celery worker did not respond to inspect ping\n' >&2
  exit 1
fi

log "Checking backend prompts"
docker compose exec -T api python -c "from pathlib import Path; prompts=list(Path('backend/prompts').glob('*.md')); assert prompts; assert Path('backend/prompts/job_parser.md').exists(); print(len(prompts))"

log "Checking TeX availability"
docker compose exec -T api sh -lc 'command -v pdflatex >/dev/null'
docker compose exec -T worker sh -lc 'command -v pdflatex >/dev/null'
docker compose exec -T beat sh -lc '! command -v pdflatex >/dev/null'

log "Docker smoke passed"
