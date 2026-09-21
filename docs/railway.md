# Deploying to Railway

Six services in one Railway project. The browser only talks to the **frontend**;
it serves the SPA and proxies `/api/` to the api over Railway's private network, so
cookie-JWT auth stays same-origin. Only the frontend gets a public domain.

| Service | Source | Start command | Public |
|---|---|---|---|
| `Postgres` | Railway pgvector template | (template) | no |
| `Redis` | Railway Redis | (template) | no |
| `api` | repo root, `Dockerfile` (last stage = `api`) | image default (uvicorn) | no |
| `worker` | repo root, same `Dockerfile` | `celery -A backend.celery_app:celery_app worker --loglevel=info --concurrency=2` | no |
| `beat` | repo root, same `Dockerfile` | `celery -A backend.celery_app:celery_app beat --loglevel=info` | no |
| `frontend` | root directory `frontend/` | image default (nginx) | **yes** |

Railway cannot pick a Docker `--target`, so `Dockerfile` keeps `api` as its final
stage (the default build) and worker/beat override the start command. Compose, ECS and
k8s still choose stages explicitly with `target:`.

Name the api service exactly `api`: the frontend proxies to `api.railway.internal:8000`
(override with `API_UPSTREAM`).

## Variables

Reference variables (`${{Service.VAR}}`) keep credentials out of the config.

**api, worker, beat** (shared):

| Variable | Value |
|---|---|
| `APP_ENV` | `production` |
| `DATABASE_URL` | `postgresql+asyncpg://${{Postgres.PGUSER}}:${{Postgres.PGPASSWORD}}@${{Postgres.RAILWAY_PRIVATE_DOMAIN}}:5432/${{Postgres.PGDATABASE}}` (must be the `+asyncpg` scheme, not Railway's plain `postgresql://`) |
| `REDIS_URL` | `${{Redis.REDIS_URL}}` |
| `JWT_SECRET` | new long random string (never reuse the default) |
| `COOKIE_SECURE` | `true` |
| `CORS_ORIGINS` | `https://<your-domain>` |
| `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `EMBEDDING_PROVIDER` | as in `.env.example` |
| `HUNTER_API_KEY`, `GMAIL_*`, `REED_API_KEY`, `ADZUNA_*`, `SENTRY_DSN` | optional integrations |

`DB_SSL` stays unset: the private network does not need TLS.
Set `RUN_MIGRATIONS_ON_STARTUP=false` on `worker` and `beat` so only the api migrates.

**frontend:**

| Variable | Value |
|---|---|
| `NGINX_CONF` | `nginx.railway.conf.template` (build arg selecting the Railway config) |

`PORT` is injected by Railway. `API_UPSTREAM` and `DNS_RESOLVER` have working defaults.

## Domain (Cloudflare)

Add the custom domain to the `frontend` service, then create the CNAME Railway shows in
Cloudflare. Start with the record **DNS only (grey cloud)** so Railway can issue its
certificate; once it is issued you can turn the proxy on, with SSL mode **Full (strict)**.

## First deploy checklist

1. Postgres + Redis up, then `api`. Watch its logs for the alembic run reaching head.
2. `GET /api/health` through the public domain returns 200.
3. Register through the app (invite/admin flow), upload a CV, run an analysis, download
   the PDF. Never hand-edit the database.
4. Only then enable `worker` and `beat`; confirm the nightly campaign caps are set before
   letting beat dispatch anything that spends on the LLM.

## Cost notes

Railway bills on usage, so idle services are cheap but not free. Keep `--concurrency`
low on the worker (Celery defaults to the host CPU count), and set a usage limit in the
Railway dashboard as a backstop.
