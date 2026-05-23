# api-conventions — API Endpoint Conventions for JobFit Agent

Apply these patterns whenever creating or modifying a backend route.

---

## Route Registration Pattern

Every router is defined in its own file under `backend/routes/` and included in `main.py`.

```python
# backend/routes/example.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database import get_db
from backend.schemas import ExampleRequest, ExampleResponse

router = APIRouter(tags=["example"])

@router.get("/example/{id}", response_model=ExampleResponse)
async def get_example(id: str, db: AsyncSession = Depends(get_db)) -> ExampleResponse:
    ...
```

```python
# backend/main.py — include the router with the settings prefix
from backend.config import settings
from backend.routes.example import router as example_router

app.include_router(example_router, prefix=settings.api_prefix)
```

**Never** hardcode `/api` in route definitions or includes. Always use `settings.api_prefix`.

---

## Request / Response Schema Pattern

All request bodies and responses are typed Pydantic v2 models in `backend/schemas.py`.

```python
# backend/schemas.py
from pydantic import BaseModel, Field

class AnalyseRequest(BaseModel):
    jd: str = Field(..., min_length=50, description="Full job description text")

class AnalyseResponse(BaseModel):
    analysis_id: str
    score: int
    partial: bool = False
```

Rules:
- Every route has an explicit `response_model` on the decorator.
- Request bodies use `Field(..., ...)` with a description for every field.
- Never return raw dicts from route handlers — always a typed Pydantic model.
- Use `model_config = ConfigDict(from_attributes=True)` on schemas that are constructed from ORM models.

---

## Error Handling Pattern

Use `HTTPException` with semantically correct status codes. Never let internal exceptions bubble to the client.

```python
from fastapi import HTTPException

# 404 — resource not found
raise HTTPException(status_code=404, detail=f"Analysis {id} not found")

# 422 — validation failure (FastAPI raises this automatically for Pydantic errors)
# 500 — unexpected internal error
raise HTTPException(status_code=500, detail="Profile build failed — check logs")

# 409 — conflict (e.g., analysis already in progress)
raise HTTPException(status_code=409, detail="Analysis already running for this profile")
```

For the SSE streaming route (`/api/analyse`), errors during the pipeline are NOT HTTPExceptions — they are `pipeline_error` SSE events. `pipeline_done` always fires at the end, with `partial: true` if any agent failed.

---

## Pagination Pattern

Paginated list endpoints accept `limit` and `offset` as query params with defaults.

```python
@router.get("/history", response_model=list[AnalysisSummary])
async def list_history(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> list[AnalysisSummary]:
    ...
```

---

## SSE Route Pattern

The analyse endpoint uses FastAPI's `StreamingResponse` with `media_type="text/event-stream"`.

```python
from fastapi.responses import StreamingResponse

@router.post("/analyse")
async def analyse_job(
    request: AnalyseRequest,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    async def event_generator() -> AsyncGenerator[str, None]:
        async for event in orchestrator.run(request.jd, db):
            yield f"event: {event.name}\ndata: {event.data}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

Headers: set `Cache-Control: no-cache` and `X-Accel-Buffering: no` to prevent proxy buffering.
