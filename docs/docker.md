# Docker

This project supports a full-stack local/demo Docker Compose environment:

- `api`: FastAPI backend and Alembic startup migrations
- `frontend`: React/Vite static build served by nginx
- `db`: PostgreSQL 16
- `redis`: Redis 7
- `worker`: Celery worker for campaign/background tasks
- `beat`: Celery beat scheduler

The non-Docker local workflow (`make run`, `npm run dev`, `pytest`) is unchanged.

The backend Dockerfile has separate targets:

- `api`: FastAPI runtime without TeX.
- `worker`: Celery worker with TeX for campaign PDF resume generation.
- `beat`: Celery beat runtime without TeX.

## Configure

Create a local `.env` from the example:

```bash
cp .env.example .env
```

Set at least:

```bash
ANTHROPIC_API_KEY=sk-ant-...
JWT_SECRET=<a-long-random-local-secret>
```

Docker Compose overrides `DATABASE_URL` and `REDIS_URL` inside containers so they point at the Compose services.

## Build and Run

```bash
docker compose build
docker compose up -d
docker compose ps
```

URLs:

- Frontend: http://localhost:8080
- API: http://localhost:8000
- API health: http://localhost:8000/health
- Prometheus metrics: http://localhost:8000/metrics

The nginx frontend proxies `/api/*` to the `api` service, so the browser client can keep using the relative `/api` base URL from `frontend/src/api/client.ts`.

## Smoke Test

Run the full Docker smoke check:

```bash
scripts/docker_smoke.sh
```

The script builds the stack, starts services, checks API/frontend health, verifies DB/Redis/Celery, verifies prompt files, and confirms `pdflatex` is absent from `api` but present in `worker`.

## Production-Style Compose

Validate the production-style overlay:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml config
```

Run with the overlay:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

The overlay:

- sets `APP_ENV=production` and `COOKIE_SECURE=true`
- removes host port publishing for Postgres, Redis, and API
- keeps frontend as the external entry point
- removes local `./data` and `./assets` bind mounts
- resets backend `env_file` usage so production-style services do not automatically read a developer `.env`

Set production secrets and origins through the deployment environment before starting the production-style stack, especially:

```bash
JWT_SECRET=<long-random-secret>
ANTHROPIC_API_KEY=<anthropic-key>
CORS_ORIGINS=https://your-domain.example
POSTGRES_PASSWORD=<strong-db-password>
```

When `APP_ENV=production`, the API refuses to start if `JWT_SECRET` is still the published default.

## Validate

```bash
curl -i http://localhost:8000/health
curl -i http://localhost:8080/healthz
curl -i http://localhost:8080/
```

Check database migrations/tables:

```bash
docker compose exec db psql -U jobfit -d jobfit -c '\dt'
docker compose exec db psql -U jobfit -d jobfit -c 'select version_num from alembic_version;'
```

Check Celery:

```bash
docker compose exec worker celery -A backend.celery_app:celery_app inspect ping
docker compose exec worker celery -A backend.celery_app:celery_app inspect registered
```

Check that runtime prompts are present:

```bash
docker compose exec api ls -la backend/prompts
docker compose exec api python -c "from pathlib import Path; print(Path('backend/prompts/job_parser.md').exists())"
```

Check the TeX split:

```bash
docker compose exec api sh -lc 'command -v pdflatex || echo "pdflatex absent from api"'
docker compose exec worker sh -lc 'command -v pdflatex'
docker compose exec beat sh -lc 'command -v pdflatex || echo "pdflatex absent from beat"'
```

View logs:

```bash
docker compose logs -f api
docker compose logs -f frontend
docker compose logs -f worker
docker compose logs -f beat
docker compose logs -f db
docker compose logs -f redis
```

Stop services:

```bash
docker compose down
```

Stop services and remove the Postgres volume:

```bash
docker compose down -v
```

## Assets and Data

Compose bind-mounts:

- `./data:/app/data`
- `./assets:/app/assets`

The image includes a non-PII fallback `assets/resume.tex` generated from `assets/resume.example.tex`. Your local `assets/resume.tex`, if present, overrides it through the bind mount.

The local/demo bind mount is intentional for admin/campaign testing with your real LaTeX resume. The production-style overlay removes that mount so local PII is not exposed by default. A real production deployment should provide resume templates through controlled storage or a managed secret/volume instead of mounting a developer workstation directory.

Do not commit real resumes, API keys, OAuth tokens, or `.env`.
