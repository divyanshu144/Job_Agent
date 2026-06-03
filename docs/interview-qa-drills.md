# JobFit — Mock Q&A Drill Set

Rehearsal questions with model answers. Practice saying the answer out loud in ~30–60s.
Grouped: architecture · async/concurrency · cost · failure handling · data · frontend · system
design/scaling · behavioral.

---

### Architecture

**Q1. Walk me through the architecture.**
A. A FastAPI backend with strict route→service→agent→Anthropic layering, and a React/TS SPA. Two
request shapes: interactive *analysis* streams over SSE (user watches six agents run live); *discovery*
is a fire-and-forget background job — POST returns a `run_id`, the client polls. Six LLM agents share
a `BaseAgent` (uniform cost tracking + model tiering + typed parsing). Persistence is async
SQLAlchemy on SQLite. Every LLM call is logged to an `LLMCall` cost ledger feeding a metrics dashboard.

**Q2. Why six agents instead of one big prompt?**
A. Four reasons: separation of concerns (each agent has one job + its own prompt file + schema),
**partial success** (one agent failing doesn't sink the rest), **per-stage model tiering** (cheap
model for bulk stages), and **observability** (per-agent cost/latency). A mega-prompt is fewer tokens
but un-debuggable, all-or-nothing, and you can't tier it.

**Q3. Why FastAPI / Pydantic / async?**
A. The workload is I/O-bound (LLM + HTTP + DB), so async maximizes concurrency per process. Pydantic
gives validated request/response schemas that double as the agent output contracts, and those same
schemas are mirrored to TS types with a drift check. FastAPI's dependency injection is how we enforce
the DB-session ownership rule.

---

### Async & concurrency

**Q4. What async pitfalls did you hit?**
A. Three. (1) Sharing one `AsyncSession` across `asyncio.gather` coroutines corrupted SQLAlchemy's
unit-of-work — fix: one session per coroutine. (2) Detached `asyncio.create_task`s were garbage-
collected and silently cancelled — fix: hold a strong reference in a module-level set. (3)
`gather(return_exceptions=True)` returns exceptions *as values*; the original code discarded them, so
failures vanished — fix: iterate and log.

**Q5. How do you bound concurrency in discovery?**
A. An `asyncio.Semaphore(5)` around per-job processing, so a run with 200 jobs never opens 200
concurrent LLM calls. Sources fan out with `gather`, but each source's jobs are throttled by the
semaphore.

**Q6. SSE vs WebSocket vs polling — when each?**
A. SSE for analysis: it's one-directional (server→client) streaming of progress, simplest possible
fit, works over plain HTTP. WebSocket would be overkill — we never need client→server mid-stream.
Polling for discovery: the job runs for minutes detached, so holding a connection is wasteful — POST
returns an id, GET polls status + funnel, with a client-side attempts cap so a wedged run doesn't poll
forever.

---

### Cost

**Q7. How do you keep LLM cost under control?**
A. Four levers: **model tiering** (Haiku ~20× cheaper for bulk discovery, Sonnet for the watched
analysis), a **free keyword pre-filter** before any paid call in the discovery funnel, the **Batch
API** (50% off) for non-urgent scoring, and a **per-call cost ledger** (`LLMCall` rows via
`tracked_call`) that powers a dashboard so cost is observable, not a surprise.

**Q8. Tell me about a time a feature didn't pay off.** *(also a behavioral answer)*
A. Prompt caching. The cost dashboard showed ~21,000 cache-creation tokens and **zero reads** — we
were paying the 1.25× write premium for nothing. Caching is a prefix match, but our system prompt
interpolated the profile, JD, and prior outputs into itself, so every request's prefix was unique and
never matched. On the discovery path it was worse — Haiku's minimum cacheable prefix is 4,096 tokens
and ours was ~400, so it never cached at all. I modeled the break-even for padding to hit the minimum
and proved it's negative at *any* call count, because a discounted read of a 4,096-token padded prefix
costs more than the un-padded 380-token prompt at full price. So I removed it — and documented the
exact conditions (a large *fixed* prefix) under which it'd be worth re-adding.

---

### Failure handling

**Q9. An LLM returns malformed JSON mid-pipeline. What happens?**
A. Each agent validates Claude's output against its Pydantic schema and re-raises any failure as a
typed `AgentError`. The orchestrator catches it per-agent, marks the run `partial=True`, and keeps
going — successful agents' outputs are still persisted in a `finally`. The user gets a partial result
with a flag, not a 500.

**Q10. How do you avoid stuck/zombie state in the background pipeline?**
A. Every state has a defined exit on the failure path — e.g. a Phase-1 scoring failure transitions a
job to `filtered` rather than leaving it in `discovered` forever. And on server restart, a lifespan
hook sweeps any run left `running` (from a crash) to `failed`. The lesson: model failure transitions
as explicitly as success transitions.

---

### Data

**Q11. Who owns the DB session?**
A. It depends on the caller. Request-scoped code injects it via FastAPI's `Depends(get_db)`, which
owns commit/rollback/close. Background tasks can't receive DI, so they own their own `async with
SessionLocal()`. Concurrent coroutines each get their own session. Getting "who owns the session"
wrong is how you corrupt data or leak connections in async apps.

**Q12. How do migrations work without Alembic?**
A. `init_db()` runs `create_all` for fresh DBs and, for existing ones, `PRAGMA table_info` + guarded
`ALTER TABLE ADD COLUMN` at startup — additive and idempotent. It's deliberately minimal for a
single-file SQLite app; the moment it's a team Postgres with renames/backfills, I'd move to Alembic.

**Q13. Why SQLite, and when does it break?**
A. Zero-ops, perfect for a single-candidate local app. It breaks on write concurrency — it's a single
writer, and discovery commits a lot concurrently. First scaling move is Postgres + a pool; that also
unblocks adding retention on the unbounded events table.

---

### Frontend

**Q14. How does the frontend consume the pipeline, and how do you model async UI?**
A. One SSE dispatcher parses `event:`/`data:` frames into typed callbacks and aborts on
`pipeline_done`. For discovery it polls every 3s and exits on a terminal status, with an attempts cap
that trips a `timedOut` state. UI flows are explicit state machines — e.g. analysis is
`idle→evaluating→evaluated→generating` — rather than scattered booleans, which prevents impossible
combinations. Mutations are optimistic with revert-on-error.

**Q15. How do you keep frontend and backend types in sync?**
A. TS interfaces mirror the Pydantic schemas 1:1, and a schema-drift check in `make lint` fails the
build if backend fields and frontend fields diverge — so contract drift is a compile-time failure,
not a runtime bug.

---

### System design / scaling

**Q16. Scale discovery to 100k jobs/day — what changes?**
A. Move to Postgres; replace `asyncio.create_task` with a durable job queue (Celery/Arq) so work
survives crashes; make per-job workers idempotent (dedup by hash already exists); batch the 7–9
commits/job into one transaction; lean harder on the Batch API; and partition the funnel so the free
keyword stage runs before anything paid. Add `user_id` to jobs/runs for multi-tenancy.

**Q17. Where are the single points of failure / biggest risks?**
A. (1) SQLite write contention. (2) Background tasks are in-process — a crash loses in-flight
discovery (mitigated by the restart sweep, not solved). (3) External API dependencies (Anthropic, job
boards) — handled with timeouts and fail-open logging, but no circuit breaker yet. (4) The `jd_hash`
cache keys on profile *id* not content, so it can serve stale results after a profile edit.

---

### Behavioral framing tips
- Always answer *decision → why → tradeoff*. Interviewers score the "why."
- Volunteer a weakness before they find it (jd_hash limitation, SQLite, no durable queue) — it reads
  as senior judgment.
- Have the **prompt-caching story** ready for "hardest bug / something that didn't work / a time you
  changed your mind with data."
- Have the **shared-async-session story** ready for "a subtle concurrency bug."
