# TODO — Pipeline retry backend (Prompts 1–6) — DONE

- [x] 1. pipeline_errors.py: UserPipelineError + to_user_error mapping
- [x] 2. models: JobResult.error_code/retry_count, Analysis.retry_running_at + migration 0003 (+dedup)
- [x] 3. job_result.py upsert + replace appends + broaden exception handling
- [x] 4. run_steps generalized runner + run_generate wrapper + Phase-1 retry
- [x] 5. concurrency guard (retry_running_at conditional UPDATE)
- [x] 6. retry route + RetryRequest/Step schema + AnalysisDetail.steps
- [x] tests (each section) + make check green (385 passed, 80.33%)
- [x] agent_memory.md: Architecture Decision + Known Gotcha
