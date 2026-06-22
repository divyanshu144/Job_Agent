# TODO

> Snapshot reset 2026-06-21. The FDE-readiness goal (5 tasks) and the multi-tenant
> campaign feature are complete and shipped (history through `87117f2`); the prior
> detailed checklist is preserved in git history. Deployment/infra work since then
> is also shipped (see HANDOFF.md for the commit-by-commit breakdown).

## Done (shipped on main)

- [x] FDE readiness: health/metrics, agent retry+breaker, campaign UI, consistency evals, rate limiting
- [x] Multi-tenant campaign system (backend units 1–6 + frontend) + two review rounds + cleanup pass
- [x] Docker (multi-stage) + docker-compose + prod override + local Kubernetes manifests
- [x] CI: `make check` + Docker image build/smoke workflows
- [x] AWS ECS Fargate deployment (`deploy-aws.yml`, `aws-migrate.yml`, `infra/aws/` task defs); RDS + ElastiCache
- [x] OpenAI semantic embeddings + pgvector with keyword fallback (`services/memory.py`)
- [x] Resume PDF tooling: dedicated `backend-tex` Docker stage (api+worker only)
- [x] Docs sync (CLAUDE.md / README.md / HANDOFF.md / todo.md) to current architecture
- [x] **Resume → YAML auto-populate** feature (extractor agent, PUT /profile/yaml, UI) — `v1.0.0`
- [x] Dockerfile texlive layer-order fix (texlive cached across backend code changes) — `dad30a3`
- [x] Dropped redundant `chown -R /app` in the tex stage — `dad30a3`
- [x] CORS cutover to `https://app.jobfitapp.uk` (committed task-defs + deployed) — `fb63edc`
- [x] Deploy hardening: tag-based trigger + concurrency guard; ECS circuit breaker + rollback;
      beat singleton (min 0/max 100, AZ rebalancing off); documented in `infra/aws/README.md`
- [x] **Cut `v1.0.0` release tag + deploy** — live, prod smoke-tested at `app.jobfitapp.uk`

## Open / candidate (not committed to)

- [ ] Wire discovery `search_profiles` to per-user `yaml_data` (today reads on-disk
      `data/candidate_profile.yaml`, `discovery.py:57`)
- [ ] Remove the dormant non-`links` `ProfileReviewData` fields (kept `links`)
- [ ] `GET/PATCH /api/campaign/settings` route pair (enabled toggle + caps display)
- [ ] Per-run cost on `CampaignRunResponse`
- [ ] Redis `storage_uri` for the rate limiter when going multi-worker
