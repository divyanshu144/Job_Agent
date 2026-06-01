from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import update

from backend.config import settings
from backend.database import SessionLocal, init_db
from backend.models import DiscoveryRun
from backend.routes.analyse import router as analyse_router
from backend.routes.auth import router as auth_router
from backend.routes.contacts import router as contacts_router
from backend.routes.discovery import router as discovery_router
from backend.routes.history import router as history_router
from backend.routes.metrics import router as metrics_router
from backend.routes.profile import router as profile_router
from backend.services.instrumentation import configure_logging


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


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
