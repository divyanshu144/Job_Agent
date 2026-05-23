# Cross-Cutting Conventions — JobFit Agent

Apply these invariants to every code change in this project. They are not guidelines — they are constraints.

---

## Config Access

**Rule:** Import `from backend.config import settings`. Never read `os.environ` directly outside of `config.py`.

```python
# correct
from backend.config import settings
url = settings.database_url

# wrong — never do this
import os
url = os.environ["DATABASE_URL"]
```

`settings` is a Pydantic-Settings singleton instantiated once at import time. It validates the environment at startup and raises a clear error if anything is missing. Bypassing it means missing that validation.

---

## DB Sessions

**Rule:** Always inject the async session as a FastAPI dependency. Never construct `AsyncSession` manually.

```python
# correct — in a route
async def get_profile(db: AsyncSession = Depends(get_db)) -> ProfileResponse:
    ...

# wrong — never do this
async def get_profile() -> ProfileResponse:
    async with SessionLocal() as db:  # don't construct manually
        ...
```

The `get_db` dependency in `database.py` handles commit/rollback/close. Manual construction bypasses that and leaks sessions on error.

`init_db()` is called once in `main.py`'s lifespan handler — do not call it anywhere else.

---

## Async Invariants

**Rule:** All I/O is async. No blocking calls in the async path.

```python
# correct — async SQLAlchemy
result = await db.execute(select(Profile))

# correct — async httpx
async with httpx.AsyncClient() as client:
    resp = await client.get(url)

# correct — CPU-bound work (pypdf, heavy computation)
loop = asyncio.get_event_loop()
text = await loop.run_in_executor(None, extract_text_from_pdf, path)

# wrong — blocks the event loop
text = extract_text_from_pdf(path)  # if this is synchronous and slow
```

If a library doesn't have an async interface, wrap it in `run_in_executor`. Never call `time.sleep` — use `await asyncio.sleep`.

---

## API Prefix Convention

**Rule:** Always use `settings.api_prefix` when registering routers. Never hardcode `/api`.

```python
# correct — in main.py
app.include_router(profile_router, prefix=settings.api_prefix)
app.include_router(analyse_router, prefix=settings.api_prefix)

# wrong
app.include_router(profile_router, prefix="/api")
```

This makes the prefix configurable for different deployment environments without touching route files.

---

## Agent Output Parsing

**Rule:** Every agent must parse Claude's response through its Pydantic output schema. Never return raw strings or unvalidated dicts.

```python
# correct
raw = await self.client.messages.create(...)
return JobParserOutput.model_validate_json(raw.content[0].text)

# wrong
return json.loads(raw.content[0].text)  # skips validation
```

If Claude returns malformed JSON, the Pydantic parse will raise — catch it, log it, and re-raise as a typed `AgentError` so the orchestrator can handle partial failure correctly.

---

## Pydantic v2 Syntax

Always use v2 syntax — this project is on Pydantic v2 throughout.

```python
# correct
class MyModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    name: str = Field(..., description="...")

# wrong — v1 syntax
class MyModel(BaseModel):
    class Config:
        orm_mode = True
```
