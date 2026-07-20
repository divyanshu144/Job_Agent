from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.database import SessionLocal, get_db, init_db
from backend.models import DiscoveryRun
from backend.routes.analyse import router as analyse_router
from backend.routes.auth import router as auth_router
from backend.routes.campaign import router as campaign_router
from backend.routes.contacts import router as contacts_router
from backend.routes.discovery import router as discovery_router
from backend.routes.feedback import router as feedback_router
from backend.routes.history import router as history_router
from backend.routes.metrics import router as metrics_router
from backend.routes.profile import router as profile_router
from backend.routes.targets import router as targets_router
from backend.services.instrumentation import configure_logging
from backend.services.rate_limit import limiter


def _check_jwt_secret() -> None:
    """Signing tokens with the repo's published default secret means anyone can
    forge a session for any user id. The log IS the alert (we don't refuse to
    boot — local dev legitimately runs on the default)."""
    from backend.config import Settings

    default_secret = Settings.model_fields["jwt_secret"].default
    if settings.jwt_secret == default_secret:
        if settings.is_production:
            raise RuntimeError(
                "JWT_SECRET must be set to a non-default value when APP_ENV=production"
            )
        logging.getLogger(__name__).critical(
            "jwt_secret is the published default — session tokens are forgeable. "
            "Set JWT_SECRET before exposing this deployment."
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    from backend.services.sentry import init_sentry

    init_sentry("api")
    configure_logging()
    _check_jwt_secret()
    if settings.run_migrations_on_startup:
        await init_db()
    # Reset any runs left in "running" state due to server crash
    async with SessionLocal() as db:
        await db.execute(
            update(DiscoveryRun)
            .where(DiscoveryRun.status == "running")
            .values(status="failed", completed_at=datetime.now(timezone.utc))
        )
        await db.commit()
    yield


app = FastAPI(title="JobFit Agent", lifespan=lifespan)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
# Added before CORS so CORS stays outermost — 429s still get CORS headers.
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix=settings.api_prefix)
app.include_router(profile_router, prefix=settings.api_prefix)
app.include_router(analyse_router, prefix=settings.api_prefix)
app.include_router(history_router, prefix=settings.api_prefix)
app.include_router(discovery_router, prefix=settings.api_prefix)
app.include_router(contacts_router, prefix=settings.api_prefix)
app.include_router(metrics_router, prefix=settings.api_prefix)
app.include_router(feedback_router, prefix=settings.api_prefix)
app.include_router(campaign_router, prefix=settings.api_prefix)
app.include_router(targets_router, prefix=settings.api_prefix)


# Prometheus: per-route latency histograms + status-labelled request counters.
Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)


def _llm_provider_status() -> str:
    """Return non-sensitive LLM provider readiness metadata for health checks."""
    return "anthropic" if settings.anthropic_api_key.strip() else "not_configured"


@app.get("/health")
@limiter.exempt  # type: ignore
async def health(db: AsyncSession = Depends(get_db)) -> JSONResponse:
    """Readiness probe: verifies the database answers, not just that the process is up."""
    return await _health_response(db)


async def _health_response(db: AsyncSession) -> JSONResponse:
    provider = _llm_provider_status()
    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:
        # Class name only — str(exc) can leak connection strings/hosts.
        return JSONResponse(
            status_code=503,
            content={
                "status": "degraded",
                "db": "error",
                "provider": provider,
                "detail": type(exc).__name__,
            },
        )
    return JSONResponse(content={"status": "ok", "db": "ok", "provider": provider})


@app.get(f"{settings.api_prefix}/health", include_in_schema=False)
@limiter.exempt  # type: ignore
async def api_prefixed_health(db: AsyncSession = Depends(get_db)) -> JSONResponse:
    """ALB/public health alias for deployments that route /api/* to the API."""
    return await _health_response(db)
