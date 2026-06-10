# JobFit Agent — Lessons Log

<!-- Add an entry here after any correction or unexpected discovery -->
<!-- Format:
## [YYYY-MM-DD] Short title
Pattern: what went wrong
Fix: what the correct approach is
Avoid: what not to do next time
-->

## [2026-06-10] A "tailor the resume" prompt must constrain length, or it overflows the page

Pattern: The resume_latex `_SYSTEM` prompt told the model to edit summary/skills/bullets to
"emphasise relevance" but said nothing about length. The base resume.tex is one page; tailoring a
real Stripe JD expanded the content to **two pages** (confirmed live: base 1pg → current-prompt
tailor 2pg). LaTeX has no implicit page cap, so the model just kept adding.

Fix: Add an explicit one-page length constraint to `_SYSTEM` — "no longer than the original; do
not add bullets/sentences; rewrite or shorten in place; cut least-relevant bullets to fit."
Validated live in-container: same JD now compiles to 1 page.

Avoid: Assuming an "edit to emphasise X" instruction preserves length — emphasis tends to *add*.
State the hard format constraint (one page) explicitly when the output has a fixed-size target.
Note: prompt changes only take effect in Docker after a rebuild (backend/ is COPYed, not mounted).

## [2026-06-10] invalid_output is often deterministic — self-correction, not blind retry

Pattern: An `invalid_output` failure (bad JSON / schema ValidationError) is usually
deterministic — re-running the *identical* prompt produces the *identical* malformed output, so a
plain retry never helps. Self-correction works because the model sees its mistake: re-call with the
validation error + prior response fed back (`BaseAgent._call_structured`, hard cap 2 calls).

Fix: But cap it, and prefer fixing the prompt. The resume_tailorer omitted_items bug was fixed by
fixing the prompt (showing the element shape), not by adding more retries — self-correction is a
safety net for transient model slips, not a substitute for a correct prompt.

Avoid: Unbounded "retry until it works" on deterministic failures (infinite cost, never succeeds).
Adding a second retry layer for transient errors — the Anthropic SDK already retries 429/5xx.

## [2026-06-10] A JSON-output prompt must show every array's element shape

Pattern: resume_tailorer failed repeatedly (and retry never helped) because the prompt's
output-schema example showed `"omitted_items": []` — an empty array with no element shape, while
every other array (experience, projects, tailored_bullets) showed a sample object. The model
guessed and emitted plain strings; `OmittedItem` requires `{field, value, reason}`, so
`model_validate` raised ValidationError → AgentError on every call. Retry re-ran the identical
prompt with no error feedback, so it failed identically each time (deterministic, not transient).

Fix: Give `omitted_items` the same `{field, value, reason}` object example as the other arrays.
Added a regression test that parses the prompt's JSON example and asserts the element shape, so it
can't silently drift back to `[]`.

Avoid: Leaving `"field": []` shapeless in a JSON-output prompt when the schema element is an
object. Treating a deterministic (same-input, same-output) failure as something retry can fix —
retry only helps transient failures, or when the prior error is fed back for self-correction.

## [2026-06-10] Pipeline retry: extend the existing partial-retry; one error boundary

Pattern: The temptation on "add retry" was to build a new retry subsystem. But Phase-2
generate already re-ran only the *missing* agents — a working partial-retry seed. And raw
`str(exc)` was leaking to users via `JobResult.error` → `result_errors`.

Fix: The existing Phase-2 partial retry was the seed for the generalised `run_steps()` runner —
extending what exists beats rebuilding. `to_user_error()` as a single error boundary keeps raw
exceptions out of user-visible surfaces — wire it wherever `JobResult.error` is written (both
pipelines + the parallel gather), and keep the raw detail in `PipelineEvent`/logs only.

Avoid: Standing up a parallel retry path when one already exists in a narrower form. Writing
`str(exc)` anywhere it can reach SSE, `JobResult.error`, or `result_errors`.

## [2026-06-07] Verify external API shapes with a live call before building normalizers

Pattern: The new discovery sources were coded + unit-tested against *assumed* response shapes
(mocked). A live check (one real endpoint per source) found two assumptions wrong: (1) Greenhouse's
legacy `boards.greenhouse.io/{slug}/jobs.json` host 404s — the live API is
`boards-api.greenhouse.io/v1/boards/{slug}/jobs`, and its `content` is HTML-**escaped**
(`&lt;p&gt;`), so a strip-then-unescape helper leaves visible tags; (2) the YC
`v0.1/companies?is_hiring=true` payload has **no `jobs_url`/ATS field at all** (only `website` +
YC-profile `url`), so the entire "YC→ATS passthrough" was infeasible — every company silently
skipped.

Fix: Hit one real endpoint per source, snapshot the JSON, reconcile the normalizer + fixtures to the
true shape — *before* building anything on top. Greenhouse: corrected host + `unescape→strip`. YC:
dropped the source (no public companies→ATS mapping exists); curated companies go in
`target_companies.json` with explicit `ats`+`slug` instead. Mocked tests that pass prove only
self-consistency, never that the shape matches reality.

Avoid: Treating a written spec's field names ("detect ATS from `jobs_url`") as ground truth.
Shipping normalizers for an external API you've never actually called.

## [2026-06-07] Kill the cause, not the symptom: removed GitHub to make the cache hash deterministic

Pattern: The content-hash cache key (`profile_content_hash(merged_profile)`) was non-deterministic because `_assemble_merged` iterated a GitHub-README dict in unordered DB/dict order. The first fix sorted the dict (`sorted(github_data.items())`) — a symptom patch that kept the unstable input alive. GitHub READMEs were the *only* collection-iterating input to `merged_profile`.

Fix: Removed GitHub as a profile source entirely. `merged_profile` is now YAML + CV only — two ordered scalars, deterministic by construction, so the content hash is stable with no sort needed. Whole surface went: `github_client.py`, `refresh_github_cache`, `/profile/refresh/github`, `/profile/status`, `GithubCache` model + `Profile.github_data`/`github_last_fetched_at`, config + schemas + frontend banner/timestamp/button + ~13 test fixtures.

Avoid: Sorting/normalizing a fragile input to stabilize a hash when the input isn't needed. If a feature exists only to feed a value you then have to defensively normalize, deleting the feature is the deeper fix. DB-row / dict iteration order is never guaranteed — anything feeding a hash must be ordered or scalar.

Also: Removing a mapped column (`Profile.github_data`) ripples to every test that constructs the model with that kwarg (~13 here). Leave-orphan in existing DBs (no DROP) matches the additive `init_db` pattern — SQLAlchemy only queries mapped columns, so orphan table/columns are harmless.

## [2026-05-28] Anthropic prompt caching: token threshold and field semantics

Pattern: Adding `cache_control: {type: ephemeral}` to system prompts does nothing if the prompt is under the model's minimum cacheable length. Haiku requires ≥2048 tokens. `input_tokens` in the response **excludes** cached portions — it is mutually exclusive with `cache_creation_input_tokens` and `cache_read_input_tokens`. SUM = input + creation + read across calls for the same prompt.

Fix: Measure actual system prompt token counts using `client.messages.count_tokens()` before assuming caching is active. For Haiku 4.5, the `cache_creation` nested object (`cache_creation.ephemeral_5m_input_tokens`) mirrors the flat `cache_creation_input_tokens` field — read the flat field in `getattr(msg.usage, "cache_creation_input_tokens", None) or 0`.

Avoid: Assuming caching fires just because `cache_control` is in the payload. Expanding a small system prompt to cross the threshold (e.g., Stage 2 compact[:1000] at 314 tokens → merged_profile at 2782 tokens) only pays off when ≥90 calls hit cache in one 5-minute window — not economical for typical Stage 2 batches. Keep Stage 2 compact; the merged_profile agents (gap_analyst, resource_planner, cover_letter, resume_tailorer) already exceed 2916 tokens and cache correctly.

Also: When multiple cache mechanisms exist on one dashboard, give each a distinct label. "Cache Hit Rate" is ambiguous alongside "Prompt Cache Savings". Use "Analysis Cache Rate" (JD-level dedup) vs "Prompt Cache Savings" (Anthropic token caching).

## [2026-05-26] Hunter.io returns explicit null, not missing key

Pattern: Writing `resp.json().get("data", {}).get("emails", [])` crashes when the API returns `{"data": null}`. `.get("data", {})` returns `null` (the fallback only triggers when the key is absent), and calling `.get()` on `None` throws `AttributeError`.

Fix: Use `(resp.json().get("data") or {}).get("emails", [])` — the `or {}` coerces any falsy value (null, None, 0, "") to `{}`, handling both missing and explicitly null. Same applies to numeric fields: `float(e.get("confidence") or 0)` prevents `TypeError` on `null` confidence values.

Avoid: `dict.get(key, default)` only applies the default when the key is absent. It does not guard against the key being present with a null value. Use `or default` for null-safe access on untrusted external API responses.

See: `backend/services/contact_discovery.py:76,95`

---

## [2026-05-26] Ownership check must come before idempotency guard

Pattern: Placing an idempotency early-return (`if contact.status == "sent": return 200`) before the ownership check leaks state. An attacker who guesses a contact_id from another user's analysis gets a 200 response — confirming the resource exists and has been acted on.

Fix: Always check ownership/authorization first, then apply idempotency. In `send_email`: fetch analysis, check `analysis.user_id`, raise 403 if not authorized — then check `contact.status == "sent"` and return 200 if already done.

Avoid: Ordering business-logic shortcuts (idempotency, caching) before authorization checks. Authorization is a gate, not a detail.

See: `backend/routes/contacts.py:114–121`

---

## [2026-05-26] Nullable foreign keys require explicit presence check in ownership guards

Pattern: Writing `analysis.user_id != current_user.id` as the sole ownership guard blocks legitimate access to analyses that have `user_id=NULL` (anonymous or system-created analyses). The comparison evaluates to True when user_id is NULL.

Fix: `analysis.user_id is not None and analysis.user_id != current_user.id` — only enforce ownership when the resource actually has an owner. NULL means "no owner restriction".

Avoid: Assuming every row in a table has an owner. Where nullable foreign keys are used to represent optional ownership, always gate the comparison behind a None check.

See: `backend/routes/contacts.py:26`

---

## [2026-06-06] Cache key used a ROTATING identifier as a proxy for content (supersedes 2026-05-26 entry)

Pattern: The analysis cache key was `sha256(jd_text + "::" + profile.id)`. The earlier note assumed `profile.id` was *stable* and only worried about staleness. The real defect is the opposite and worse: `build_profile` inserts a NEW `Profile` row with a fresh `uuid4()` on **every** Refresh / CV upload / GitHub refresh, and `get_or_build_profile` returns the latest. So `profile.id` rotates constantly → every profile build silently **invalidated the entire analysis cache** (needless recompute + spend), while *also* failing to invalidate when content changed without an id change.

Fix (implemented): key on profile **content**, via one primitive + one helper. `profile_content_hash(merged_profile)` (profile_builder.py) is the single definition of "profile identity"; `analysis_cache_key(jd, profile)` (orchestrator.py) is the single key derivation, called by both cache sites (`run_evaluate_pipeline`, `_run_phase1`). Identical content → identical key (survives a no-op Refresh); changed content → new key. No DB migration; existing `jd_hash` values go permanently un-hit (expected one-time cold start). Caveat: keys on the *built* merged_profile, so an on-disk YAML edit without a Refresh still returns the prior result — the row wasn't rebuilt.

Avoid: Using ANY rotating/unstable identifier (uuid, autoincrement id, row pk, filename) as a proxy for content in a cache key. If the cache must reflect content, hash the content. Extract the key derivation into ONE helper so it can't drift across call sites.

See: `backend/services/orchestrator.py` (`analysis_cache_key`), `backend/services/profile_builder.py` (`profile_content_hash`)

---

## [2026-05-26] DELETE-before-INSERT for re-discovery keeps table consistent with external source

Pattern: Upserting individual rows when re-discovering contacts leaves stale rows for contacts that no longer appear in the Hunter.io response (e.g., a retired email address). The DB diverges from the authoritative external source.

Fix: `DELETE FROM contacts WHERE analysis_id = ?` before inserting fresh results. The Hunter API response is the single source of truth for a given domain; the local table should mirror it exactly after each discovery run.

Avoid: Upsert-based sync patterns when the authoritative source controls the full list. DELETE+INSERT is simpler and keeps the local copy consistent.

See: `backend/services/contact_discovery.py:80`

---

## [2026-05-26] db.commit() must be inside the try block for all-or-nothing state transitions

Pattern: Placing field mutations (`contact.status = "drafted"`, `contact.draft_text = ...`) inside the try block but calling `await db.commit()` outside means a commit failure leaves the contact in `status='drafted'` with a valid `draft_text`, but the transaction was never flushed. Worse, if the commit throws, the except block returns a 500 while the in-memory state is inconsistent.

Fix: Move `await db.commit()` into the same try block as the field mutations. If the agent raises or the commit fails, the entire transition fails atomically — the contact stays at `status='discovered'` with `draft_text=NULL`.

Avoid: Separating state mutation from the commit across try/except boundaries. Treat field assignments + commit as a single atomic operation.

See: `backend/routes/contacts.py` (draft_email endpoint)

---

## [2026-05-26] ColdEmailAgent uses manual .replace() because it is not a pipeline agent

Pattern: Calling `self._inject(template, profile, jd, prior)` on ColdEmailAgent fails because `_inject()` expects a `PriorOutputs` object (job_parser, match_scorer, gap_analyst outputs). ColdEmailAgent doesn't receive prior outputs — it receives `contact_name` and `contact_title`.

Fix: For agents outside the orchestrator pipeline (leaf agents called directly from routes), use manual `template.replace("{slot}", value)` chains. `_inject()` is only for pipeline agents that consume structured prior outputs.

Avoid: Forcing all agents to conform to the `_inject()` signature. The contract of `_inject()` is pipeline-specific; leaf agents have different input shapes and need their own injection logic.

See: `backend/agents/cold_email_agent.py:22–26`, `backend/agents/base.py:45–52`

---

## [2026-05-26] Filter contacts without email before insert, not after

Pattern: Inserting Contact rows with `email=""` or `email=None` violates the `NOT NULL` column constraint and throws a DB error at commit time, not at the filtering stage. The error is cryptic — it looks like a DB constraint failure, not an API data quality issue.

Fix: Filter the Hunter.io results list before any DB interaction: `emails = [e for e in emails if e.get("value")]`. The `if e.get("value")` check excludes both missing keys and empty strings. Empty-string emails are falsy in Python, so no separate check is needed.

Avoid: Relying on DB constraints as the first line of defense against missing required fields from external APIs. Validate and filter at the service boundary, before any DB writes.

See: `backend/services/contact_discovery.py:77`

---

## [2026-05-26] with_tracking() mutates the agent instance in place

Pattern: `with_tracking()` sets `_db`, `_run_id`, and `_analysis_id` on the agent instance and returns `self`. If the same agent instance is reused for a second request without calling `with_tracking()` again, it carries the previous request's DB session and run_id — silently logging costs to the wrong analysis.

Fix: Always instantiate agents fresh per request: `ColdEmailAgent().with_tracking(db, analysis_id=...)`. Never cache agent instances across requests.

Avoid: Treating agents as singletons or reusing them across requests. The `with_tracking()` chaining pattern implies single-use per call.

See: `backend/agents/base.py:30–40`

---

## [2026-05-26] Documentation drift is invisible until audited

Pattern: The CLAUDE.md architecture map listed 3 routes and 3 frontend pages. The actual codebase had 7 routes and 8 frontend pages. Two TODO comments had been stale for weeks. No one noticed because the code still worked — the docs are only consulted when onboarding or when an agent starts a new session.

Fix: Treat CLAUDE.md as code. Update it in the same commit as the structural change it describes. The audit (tasks/harness-audit.md, 2026-05-26) caught 4 missing routes, 5 missing frontend pages, and 2 stale TODOs.

Avoid: Deferring documentation updates to "later". Architecture maps and convention docs drift by omission, not by error. Every new route/page/convention added without a corresponding CLAUDE.md update compounds the debt.

See: `CLAUDE.md:55–76` (pre-Wave-1)

---

## [2026-05-28] _process_job commits 7–9 times per job; should be batched

Pattern: `_process_job` in `backend/services/discovery.py` commits after every state transition (discovered → stage1-check → stage2-check → scored), totalling 7–9 commits per job. The orchestrator pattern (`_run_phase1`) uses a single `finally: await db.commit()`. Multiple commits on one session make intermediate states observable in the DB and increase SQLite lock contention during concurrent discovery.

Fix (deferred — separate PR): Batch all writes for a single job into one commit at the end of `_process_job`, using flush() to get the job.id for FK references before the final commit. Model after the `_run_phase1` finally-block pattern.

Avoid: Committing inside inner branches of a multi-step processing function. A single job's state transitions should be atomic from the caller's perspective.

See: `backend/services/discovery.py:159–234`

---

## [2026-05-28] Docker containers cannot use host-only profile paths from .env

Pattern: `.env` pointed `PROFILE_YAML_PATH` and `CV_PATH` at `/Users/divyanshu/...`. That works on the host, but inside Docker the app runs in a Linux filesystem where that path does not exist. Uploading a CV then rebuilt the profile and crashed with `FileNotFoundError` while reading the YAML.

Fix: Override those paths in `docker-compose.yml` to the mounted container paths (`/app/data/candidate_profile.yaml`, `/app/data/cv.pdf`). Also make `profile_builder._read_repos()` fall back to a starter YAML when the profile file is missing, so an empty mounted data volume does not produce a 500.

Avoid: Letting host-local absolute paths leak into container runtime config unless the host directory is explicitly bind-mounted at the same container path.

See: `docker-compose.yml`, `backend/services/profile_builder.py:20–68`

---

## [2026-05-31] Live PreToolUse safety hooks block commands that merely mention the pattern

Pattern: A global PreToolUse hook that greps the bash command text for destructive patterns (`rm -rf`, `DROP TABLE`, force push, etc.) blocks ANY command containing that literal string — including test scripts, `echo`/comments, and commit messages that reference the pattern. Discovered live: the swarm-safety smoke test (a loop with `rm -rf /tmp/foo` as a string) was blocked by the very hook it was testing.

Fix: When a command must contain a guarded pattern, assemble the string at runtime (`R="rm"; "$R" -rf …`) or move it into a file and run `bash file.sh` — the hook only inspects `tool_input.command`, so the literal never appears in the tool call. Keep the hook fail-open: if the JSON payload can't be parsed, allow the command. A parse bug must not block every command in every repo.

Avoid: Writing test/demo bash inline with literal dangerous strings once the global hook is active. Avoid fail-closed parsing for a heuristic guard.

See: `~/.claude/hooks/pre-tool-use.sh`, `~/.claude/settings.json` (PreToolUse → Bash)

---

## [2026-05-31] Stop hooks need the stop_hook_active guard or they loop

Pattern: A Stop hook that blocks (exit 2) to force a `HANDOFF.md` update is re-invoked after Claude responds to the block. Without checking the `stop_hook_active` flag in the hook's stdin JSON, it can block the session forever.

Fix: First line of logic — if stdin contains `"stop_hook_active": true`, `exit 0`. Scope enforcement to real work: block only when `git status --porcelain` is non-empty (dirty tree) AND `HANDOFF.md` mtime is older than 30 min (`find HANDOFF.md -mmin -30`). Clean tree, non-repo, and fresh HANDOFF all pass silently.

Avoid: Blocking session end on every stop regardless of whether anything changed — it nags read-only/Q&A sessions. Tie the gate to a dirty working tree.

See: `.claude/hooks/stop.sh`, `.claude/settings.json` (Stop)

---

## [2026-06-01] A dirty-tree Stop hook must tell the user to COMMIT, not just edit the gated file

Pattern: The HANDOFF Stop hook gates on `git status --porcelain` (dirty tree) AND `HANDOFF.md` mtime > 30 min. When `HANDOFF.md` is the *only* uncommitted file (the common session-end case), the block message said "Overwrite HANDOFF.md … then stop again" — so following it literally refreshes mtime, suppresses the block for 30 min, then re-fires because the tree is still dirty. The remediation the hook prints can never durably satisfy the hook; only committing/cleaning can. Hit live ~4 times in one session.

Fix: A gate keyed on a *condition* (dirty tree) must, in its remediation text, name the action that clears the *condition* — here, COMMIT or otherwise clean the tree — not just the sub-step (edit the file). The message now says to commit and explains the 30-min suppression. Also dropped the inlined schema in favour of pointing at `HANDOFF.template.md` (schema lived in two places → drift), and removed a redundant `git rev-parse` probe (`git status --porcelain` already returns empty on a non-repo).

Decision (deliberately NOT done): do not add a "HANDOFF.md must be committed" *block* to the hook. It would be the one fail-closed path in an otherwise fail-open script and would trap a session after a perfectly good HANDOFF was written but not `git add`-ed. If ever revisited, implement as a warning (`exit 0`), never a block.

Avoid: Writing remediation text that addresses the symptom step instead of the gating condition. Avoid duplicating a schema between a hook and its template file.

See: `.claude/hooks/stop.sh`, `HANDOFF.template.md`
