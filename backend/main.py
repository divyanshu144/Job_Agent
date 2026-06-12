from __future__ import annotations

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


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    configure_logging()
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
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
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


@app.get("/health")
@limiter.exempt  # type: ignore[misc]
async def health(db: AsyncSession = Depends(get_db)) -> JSONResponse:
    """Readiness probe: verifies the database answers, not just that the process is up."""
    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:
        # Class name only — str(exc) can leak connection strings/hosts.
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "db": "error", "detail": type(exc).__name__},
        )
    return JSONResponse(content={"status": "ok", "db": "ok"})
